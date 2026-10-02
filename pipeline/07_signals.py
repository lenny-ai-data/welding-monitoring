"""Transforme les mesures vision par frame en signaux de monitoring, événements et KPI par run.

Ce qui est mesuré vs reconstruit :
- mesuré (vision IA) : plasma, projections, cordon, position du front -> vitesse d'avance ;
- reconstruit : consignes power / feedrate (constantes du plan d'expériences) appliquées entre
  l'allumage et l'extinction du laser, eux-mêmes détectés à l'image.

Étalonnage px -> mm : un facteur d'échelle par série (le cadrage de la caméra change entre DoE1,
DoE2 et DoE3), estimé comme la médiane, sur les runs de la série, du rapport vitesse de consigne /
vitesse du front en px/s. Les écarts run par run à la consigne sont ensuite de vraies mesures.

Le front du cordon est robustifié : une position n'est retenue que si elle reste proche du
panache de plasma (qui suit le laser), puis filtrée par médiane glissante ; la vitesse de régime
est la pente de Theil-Sen (insensible aux valeurs aberrantes résiduelles).
"""

import json

import numpy as np
import pandas as pd
from common import PROCESSED
from scipy.signal import savgol_filter
from scipy.stats import theilslopes

PLASMA_SMOOTH_MS = 2.0  # moyenne glissante causale affichée sur le plasma
PLASMA_MIN_PX = 150  # aire minimale (px à 512, ~0,2 mm²) pour considérer le plasma présent
ON_WINDOW_MS = 1.5  # fenêtre de lissage de la détection allumage / extinction
SPEED_WINDOW_MS = 20.0  # fenêtre de la pente glissante (régression locale d'ordre 1)
STAB_WINDOW_MS = 5.0  # fenêtre du coefficient de variation glissant du plasma
SPEED_TOL = 0.20  # écart de vitesse toléré avant alarme (bruit de mesure médian ~5 %)
ALARM_MERGE_MS = 1.0  # deux alarmes de même type à moins de 1 ms d'écart sont fusionnées
SPEED_ALARM_MS = 5.0  # durée minimale d'un écart de vitesse pour lever une alarme
SPIKE_SIGMA = 3.0
FRONT_GATE_PX = 60  # écart maximal front du cordon / centre du panache (px à 512, ~2 mm)
FRONT_MEDIAN_MS = 1.5  # fenêtre de la médiane glissante sur le front
FRONT_END_TOL_PX = 4  # le front est « arrivé » à moins de 4 px de sa position finale


def frames_for(ms: float, fps: int, odd: bool = False) -> int:
    n = max(3, int(round(ms * fps / 1000)))
    return n + 1 if odd and n % 2 == 0 else n


def detect_on_off(plasma_px: np.ndarray, fps: int, front: np.ndarray | None = None) -> tuple[int, int] | None:
    """Fenêtre laser ON : premier et dernier instant où le plasma est présent sur la majorité
    d'une fenêtre glissante (robuste aux scintillements d'une frame).

    Si la position du front du cordon est fournie, l'extinction est bornée par l'instant où le front
    atteint sa position finale : une lueur résiduelle (cratère, reflet) après la fin du cordon ne
    prolonge pas la phase ON."""
    present = (plasma_px >= PLASMA_MIN_PX).astype(float)
    win = frames_for(ON_WINDOW_MS, fps)
    frac = pd.Series(present).rolling(win, center=True, min_periods=1).mean().to_numpy()
    idx = np.nonzero(frac > 0.5)[0]
    if len(idx) == 0:
        return None
    on, off = int(idx[0]), int(idx[-1])
    if front is not None and np.isfinite(front[on:]).sum() > 10:
        # Position finale : quasi-maximum du front (la fin de vidéo peut être masquée par une fausse
        # détection de plasma qui invalide le front).
        final = np.nanpercentile(front[on:], 99)
        if np.isfinite(final):
            reached = np.nonzero(front[on:] >= final - FRONT_END_TOL_PX)[0]
            if len(reached):
                off = min(off, on + int(reached[0]) + frames_for(ON_WINDOW_MS, fps))
    return on, off


def front_slope(frames: np.ndarray, front_px: np.ndarray) -> tuple[float, float]:
    """Pente robuste (Theil-Sen, px/frame) du front en régime établi, et R² de la droite obtenue."""
    ok = ~np.isnan(front_px)
    if ok.sum() < 10:
        return np.nan, np.nan
    x, y = frames[ok], front_px[ok]
    if len(x) > 400:  # Theil-Sen est quadratique : sous-échantillonnage régulier
        keep = np.linspace(0, len(x) - 1, 400).astype(int)
        x, y = x[keep], y[keep]
    slope, intercept, *_ = theilslopes(y, x)
    resid = y - (slope * x + intercept)
    r2 = 1 - resid.var() / y.var() if y.var() > 0 else np.nan
    return float(slope), float(r2)


def clean_front(f: pd.DataFrame, fps: int) -> np.ndarray:
    """Position du front du cordon (px) débarrassée des détections incohérentes avec le laser."""
    x1 = np.array(f.weld_x1, dtype=float)  # copie modifiable
    cx = f.plasma_cx.to_numpy(float)
    has_plasma = f.plasma_px.to_numpy() >= PLASMA_MIN_PX
    x1[has_plasma & (np.abs(x1 - cx) > FRONT_GATE_PX)] = np.nan
    win = frames_for(FRONT_MEDIAN_MS, fps)
    return pd.Series(x1).rolling(win, center=True, min_periods=1).median().to_numpy()


def steady_slice(on: int, off: int) -> slice:
    """Régime établi : on écarte 15 % au démarrage et 5 % avant l'extinction."""
    span = off - on
    return slice(on + int(0.15 * span), off - int(0.05 * span))


def calibrate(runs: pd.DataFrame, feats: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    rows = []
    for run in runs.itertuples():
        f = feats[feats.run_id == run.run_id].sort_values("frame")
        front = clean_front(f, run.fps)
        window = detect_on_off(f.plasma_px.to_numpy(), run.fps, front)
        if window is None:
            continue
        sl = steady_slice(*window)
        slope, r2 = front_slope(f.frame.to_numpy()[sl], front[sl])
        rows.append(
            {
                "run_id": run.run_id,
                "serie": run.serie,
                "px_per_s": slope * run.fps,
                "r2": r2,
                "mm_per_px_run": run.feedrate_mm_s / (slope * run.fps),
            }
        )
    cal = pd.DataFrame(rows)
    scales = {}
    for serie, grp in cal.groupby("serie"):
        good = grp[grp.r2 > 0.95]
        cv = float(good.mm_per_px_run.std() / good.mm_per_px_run.mean())
        scales[serie] = {
            "mm_per_px_512": float(good.mm_per_px_run.median()),
            "runs_used": len(good),
            "runs": len(grp),
            "cv": cv,
        }
        print(
            f"étalonnage {serie} : {scales[serie]['mm_per_px_512']:.5f} mm/px (512 px) "
            f"sur {len(good)}/{len(grp)} runs, CV {cv:.1%}"
        )
    return scales, cal


def group_events(mask: np.ndarray, min_len: int = 1, max_gap: int = 0) -> list[tuple[int, int]]:
    """Regroupe les frames consécutives d'un masque booléen en (début, fin).

    max_gap : deux épisodes séparés d'au plus max_gap frames n'en font qu'un (anti-rebond, comme une
    alarme de supervision qui ne se redéclenche pas en rafale)."""
    events, start = [], None
    for i, m in enumerate(np.append(mask, False)):
        if m and start is None:
            start = i
        elif not m and start is not None:
            if events and start - events[-1][1] - 1 <= max_gap:
                events[-1] = (events[-1][0], i - 1)
            else:
                events.append((start, i - 1))
            start = None
    return [(s, e) for s, e in events if e - s + 1 >= min_len]


def run_signals(run, f: pd.DataFrame, scale: float, spatter_burst: int) -> tuple[dict, dict]:
    fps, n = run.fps, len(f)
    frame = f.frame.to_numpy()
    t_ms = frame / fps * 1000
    plasma_px = f.plasma_px.to_numpy().astype(float)
    front = clean_front(f, fps)
    window = detect_on_off(plasma_px, fps, front)
    on, off = window if window else (n, n)
    is_on = (frame >= on) & (frame <= off)

    # Front du cordon robustifié, interpolé sur la phase ON, lissé puis dérivé.
    speed = np.full(n, np.nan)
    sg = frames_for(SPEED_WINDOW_MS, fps, odd=True)
    valid = is_on & ~np.isnan(front)
    if valid.sum() > sg:
        idx = np.arange(np.nonzero(valid)[0][0], np.nonzero(valid)[0][-1] + 1)
        filled = pd.Series(front[idx]).interpolate(limit_direction="both").to_numpy()
        d = savgol_filter(filled, sg, 1, deriv=1)  # pente glissante, px / frame
        speed[idx] = d * fps * scale
        speed[idx[: sg // 2]] = np.nan  # bords du filtre peu fiables
        speed[idx[-(sg // 2) :]] = np.nan

    plasma_mm2 = plasma_px * scale**2
    # Moyenne glissante causale (seules les frames passées) : ce qu'afficherait un moniteur en ligne.
    plasma_smooth = (
        pd.Series(np.where(is_on, plasma_mm2, np.nan))
        .rolling(frames_for(PLASMA_SMOOTH_MS, fps), min_periods=1)
        .mean()
        .to_numpy()
    )
    stab_win = frames_for(STAB_WINDOW_MS, fps)
    roll = pd.Series(np.where(is_on, plasma_mm2, np.nan)).rolling(stab_win, center=True, min_periods=3)
    plasma_cv = (roll.std() / roll.mean()).to_numpy()

    x0 = (
        pd.Series(f.weld_x0.to_numpy(float))
        .rolling(frames_for(FRONT_MEDIAN_MS, fps), center=True, min_periods=1)
        .median()
        .to_numpy()
    )
    weld_len = (front - x0) * scale
    spatter_n = f.spatter_n.to_numpy()

    # Événements -------------------------------------------------------------------------------
    events = []
    if window:
        events += [{"type": "on", "start": on, "end": on}, {"type": "off", "start": off, "end": off}]
        sl = steady_slice(on, off)
        ref = plasma_mm2[sl]
        med = np.median(ref)
        sigma = 1.4826 * np.median(np.abs(ref - med))  # écart-type robuste (MAD)
        plasma_threshold = med + SPIKE_SIGMA * sigma
        merge = frames_for(ALARM_MERGE_MS, fps)
        spikes = is_on & (plasma_mm2 > plasma_threshold)
        events += [{"type": "plasma_spike", "start": s, "end": e} for s, e in group_events(spikes, max_gap=merge)]
        bursts = is_on & (spatter_n >= spatter_burst)
        events += [{"type": "spatter_burst", "start": s, "end": e} for s, e in group_events(bursts, max_gap=merge)]
        steady = np.zeros(n, bool)
        steady[sl] = True
        dev = steady & (np.abs(speed - run.feedrate_mm_s) > SPEED_TOL * run.feedrate_mm_s)
        events += [
            {"type": "speed_deviation", "start": s, "end": e}
            for s, e in group_events(dev, frames_for(SPEED_ALARM_MS, fps))
        ]
    else:
        plasma_threshold = None
    events.sort(key=lambda e: e["start"])
    for e in events:
        e["t_ms"] = round(e["start"] / fps * 1000, 2)

    # KPI ----------------------------------------------------------------------------------------
    kpi = {
        "laser_on_ms": round(on / fps * 1000, 2) if window else None,
        "laser_off_ms": round(off / fps * 1000, 2) if window else None,
    }
    if window:
        sl = steady_slice(on, off)
        slope, r2 = front_slope(frame[sl], front[sl])
        after = f.weld_width_px.to_numpy()[off + 1 :]
        speed_meas = slope * fps * scale
        kpi |= {
            "weld_duration_ms": round((off - on) / fps * 1000, 2),
            "speed_measured_mm_s": round(speed_meas, 1),
            "speed_error_pct": round(100 * (speed_meas / run.feedrate_mm_s - 1), 2),
            "front_fit_r2": round(r2, 4),
            "seam_length_mm": round(
                float(np.nanmedian(weld_len[off + 1 :])) if off + 1 < n else float(np.nanmax(weld_len)), 2
            ),
            "plasma_mean_mm2": round(float(plasma_mm2[sl].mean()), 3),
            "plasma_cv": round(float(plasma_mm2[sl].std() / plasma_mm2[sl].mean()), 4),
            "plasma_height_mm": round(float(np.nanmean(f.plasma_h.to_numpy()[sl]) * scale), 3),
            "spatter_mean": round(float(spatter_n[sl].mean()), 3),
            "spatter_px_mean": round(float(f.spatter_px.to_numpy()[sl].mean() * scale**2), 4),
            "weld_width_mm": round(float(np.nanmedian(after) * scale), 3) if len(after) else None,
            "n_plasma_spike": sum(e["type"] == "plasma_spike" for e in events),
            "n_spatter_burst": sum(e["type"] == "spatter_burst" for e in events),
            "n_speed_deviation": sum(e["type"] == "speed_deviation" for e in events),
        }

    def col(a, nd):
        return [None if not np.isfinite(v) else round(float(v), nd) for v in a]

    ts = {
        "t_ms": col(t_ms, 3),
        "on": [int(v) for v in is_on],
        "power_cmd_w": [run.power_w if v else 0 for v in is_on],
        "feed_cmd_mm_s": [run.feedrate_mm_s if v else 0 for v in is_on],
        "speed_mm_s": col(speed, 1),
        "plasma_mm2": col(plasma_mm2, 3),
        "plasma_smooth_mm2": col(plasma_smooth, 3),
        "plasma_threshold_mm2": None if plasma_threshold is None else round(float(plasma_threshold), 3),
        "plasma_cv": col(plasma_cv, 3),
        "plasma_height_mm": col(f.plasma_h.to_numpy() * scale, 2),
        "spatter_n": [int(v) for v in spatter_n],
        "weld_length_mm": col(weld_len, 2),
        "events": events,
    }
    return ts, kpi


def main() -> None:
    runs = pd.read_parquet(PROCESSED / "runs.parquet")
    feats = pd.read_parquet(PROCESSED / "frame_features.parquet")
    scales, cal = calibrate(runs, feats)

    # Seuil de rafale de projections : quantile 99 % du nombre de projections visibles
    # pendant les phases laser ON, sur l'ensemble du dataset.
    on_counts = []
    for run in runs.itertuples():
        f = feats[feats.run_id == run.run_id].sort_values("frame")
        w = detect_on_off(f.plasma_px.to_numpy(), run.fps, clean_front(f, run.fps))
        if w:
            on_counts.append(f.spatter_n.to_numpy()[w[0] : w[1] + 1])
    spatter_burst = max(3, int(np.quantile(np.concatenate(on_counts), 0.99)))
    print(f"seuil rafale de projections : {spatter_burst} projections visibles simultanément")

    out_ts = PROCESSED / "ts"
    out_ts.mkdir(exist_ok=True)
    kpis = []
    for run in runs.itertuples():
        f = feats[feats.run_id == run.run_id].sort_values("frame").reset_index(drop=True)
        ts, kpi = run_signals(run, f, scales[run.serie]["mm_per_px_512"], spatter_burst)
        (out_ts / f"{run.run_id}.json").write_text(json.dumps(ts, separators=(",", ":")))
        kpis.append({"run_id": run.run_id, **kpi})

    kpis = pd.DataFrame(kpis).merge(cal[["run_id", "mm_per_px_run"]], on="run_id", how="left")
    kpis.to_parquet(PROCESSED / "run_kpis.parquet", index=False)
    (PROCESSED / "calibration.json").write_text(
        json.dumps(
            {
                "series": {
                    s: v | {"mm_per_px_1024": v["mm_per_px_512"] / 2, "field_of_view_mm": v["mm_per_px_512"] * 512}
                    for s, v in scales.items()
                },
                "spatter_burst_threshold": spatter_burst,
                "alarm_rules": {
                    "plasma_spike_sigma": SPIKE_SIGMA,
                    "spatter_burst_count": spatter_burst,
                    "speed_tolerance_pct": round(100 * SPEED_TOL),
                    "speed_min_duration_ms": SPEED_ALARM_MS,
                },
            },
            indent=2,
        )
    )
    print(kpis.describe().T[["mean", "std", "min", "max"]].round(3).to_string())


if __name__ == "__main__":
    main()
