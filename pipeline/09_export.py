"""Exporte les artefacts légers consommés par l'app (app_data/), sans dépendance numpy/pandas côté app.

app_data/
  meta.json          étalonnage, modèle, attribution du dataset
  runs.json          81 runs : facteurs, métadonnées caméra, KPI
  doe.json           modèles de surface de réponse
  seg_metrics.json   métriques du modèle + comparaison GT / IA frame par frame
  ts/<run>.json      signaux temporels
  media/seg/<run>/{frames/*.webp, gt/*.png, pred/*.png}
"""

import json
import shutil
from datetime import UTC, datetime

import cv2
import numpy as np
import pandas as pd
from common import APP_DATA, CLASSES, EVAL_RUNS, LABELED_RUNS, MODELS, PLAYBACK_FPS, PROCESSED
from metrics import confusion, iou_from_confusion

DATASET = {
    "title": "High-Speed Laser Beam Welding Video Dataset with Weld, Plasma, and Spatter Annotations",
    "authors": "A. Darwish, M. Persson, A. Andersson Lassila, D. Lönn, S. Ericson, K. Salomonsson",
    "institution": "University of Skövde",
    "year": 2026,
    "doi": "10.5281/zenodo.22282527",
    "url": "https://doi.org/10.5281/zenodo.22282527",
    "license": "CC BY-NC 4.0",
    "license_url": "https://creativecommons.org/licenses/by-nc/4.0/",
    "changes": "Vidéos transcodées en H.264 512 px ; masques fusionnés en cartes sémantiques ; "
    "prédictions d'un modèle de segmentation et indicateurs dérivés ajoutés.",
}

# Verdict qualité d'une soudure, à partir de ses alarmes (pics de plasma + rafales de projections).
# Un écart de vitesse soutenu (alarme vitesse) rend la soudure NOK quel que soit le reste.
VERDICT_OK_MAX = 10  # jusqu'à 10 alarmes : OK
VERDICT_WARN_MAX = 15  # de 11 à 15 : OK avec warning ; au-delà : NOK
SPEED_WARN_PCT = 10  # zone de vigilance sur la vitesse (l'alarme reste à ±20 % pendant 5 ms)
STABILITY_QUANTILE = 0.90  # limite d'instabilité : 90e centile du CV plasma (laser ON, 81 runs)


def clean(v):
    if isinstance(v, float | np.floating):
        return None if not np.isfinite(v) else round(float(v), 5)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    return v


def verdict(rec: dict) -> str:
    if rec["n_speed_deviation"] or rec["n_alarms"] > VERDICT_WARN_MAX:
        return "nok"
    return "ok" if rec["n_alarms"] <= VERDICT_OK_MAX else "warn"


def stability_limit() -> float:
    cv = []
    for f in (PROCESSED / "ts").glob("*.json"):
        ts = json.loads(f.read_text())
        cv += [c for c, on in zip(ts["plasma_cv"], ts["on"], strict=True) if on and c is not None]
    return round(float(np.quantile(cv, STABILITY_QUANTILE)), 3)


def export_runs() -> list[dict]:
    runs = pd.read_parquet(PROCESSED / "runs.parquet").merge(
        pd.read_parquet(PROCESSED / "run_kpis.parquet"), on="run_id"
    )
    runs = runs.sort_values(["serie", "exec_rank"])
    records = []
    for rec in runs.to_dict("records"):
        rec = {k: clean(v) for k, v in rec.items()}
        rec["split"] = "eval" if rec["run_id"] in EVAL_RUNS else "train" if rec["run_id"] in LABELED_RUNS else None
        rec["slowmo"] = rec["fps"] // PLAYBACK_FPS
        # Le modèle n'a vu que des images DoE3 : DoE1 / DoE2 (éclairage, cadrage) sont hors domaine.
        rec["in_domain"] = rec["serie"] == "DoE3"
        rec["n_alarms"] = rec["n_plasma_spike"] + rec["n_spatter_burst"]
        rec["verdict"] = verdict(rec)
        rec.pop("camera", None)
        records.append(rec)
    return records


def export_seg() -> dict:
    labeled = pd.read_parquet(PROCESSED / "labeled_frames.parquet")
    fps = pd.read_parquet(PROCESSED / "runs.parquet").set_index("run_id")["fps"]
    report = json.loads((MODELS / "metrics.json").read_text())
    report["runs"] = {}
    for run_id in LABELED_RUNS:
        out = APP_DATA / "media" / "seg" / run_id
        for sub in ("frames", "gt", "pred"):
            (out / sub).mkdir(parents=True, exist_ok=True)
        frames = []
        for row in labeled[labeled.run_id == run_id].itertuples():
            name = f"{row.gt_index:03d}"
            img = cv2.imread(str(PROCESSED / "labels" / run_id / "frames" / f"{name}.png"), 0)
            gt = cv2.imread(str(PROCESSED / "labels" / run_id / "masks" / f"{name}.png"), 0)
            pred = cv2.imread(str(PROCESSED / "preds" / run_id / f"{name}.png"), 0)
            cv2.imwrite(str(out / "frames" / f"{name}.webp"), img, [cv2.IMWRITE_WEBP_QUALITY, 72])
            cv2.imwrite(str(out / "gt" / f"{name}.png"), gt, [cv2.IMWRITE_PNG_COMPRESSION, 9])
            cv2.imwrite(str(out / "pred" / f"{name}.png"), pred, [cv2.IMWRITE_PNG_COMPRESSION, 9])
            iou = iou_from_confusion(confusion(gt, pred, 4))
            frames.append(
                {
                    "k": row.gt_index,
                    "frame": row.video_frame,
                    "t_ms": round(row.video_frame / fps[run_id] * 1000, 2),
                    "gt": {c: int((gt == i).sum()) for i, c in CLASSES.items()},
                    "pred": {c: int((pred == i).sum()) for i, c in CLASSES.items()},
                    "iou": {c: clean(iou[i]) for i, c in CLASSES.items()},
                }
            )
        report["runs"][run_id] = {"split": "eval" if run_id in EVAL_RUNS else "train", "frames": frames}
    return report


def main() -> None:
    (APP_DATA / "ts").mkdir(parents=True, exist_ok=True)
    for f in (PROCESSED / "ts").glob("*.json"):
        shutil.copy(f, APP_DATA / "ts" / f.name)
    runs = export_runs()
    (APP_DATA / "runs.json").write_text(json.dumps(runs, ensure_ascii=False, separators=(",", ":")))
    shutil.copy(PROCESSED / "doe.json", APP_DATA / "doe.json")
    seg = export_seg()
    (APP_DATA / "seg_metrics.json").write_text(json.dumps(seg, ensure_ascii=False, separators=(",", ":")))
    meta = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "calibration": json.loads((PROCESSED / "calibration.json").read_text()),
        "model": seg["model"],
        "dataset": DATASET,
        "playback_fps": PLAYBACK_FPS,
        "camera": "Photron FASTCAM Nova S9, 1024×1024, mono 8 bits",
        "quality": {
            "verdict_ok_max_alarms": VERDICT_OK_MAX,
            "verdict_warn_max_alarms": VERDICT_WARN_MAX,
            "speed_warn_pct": SPEED_WARN_PCT,
            "stability_limit_cv": stability_limit(),
            "stability_quantile": STABILITY_QUANTILE,
        },
    }
    (APP_DATA / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    size = sum(p.stat().st_size for p in APP_DATA.rglob("*") if p.is_file()) / 1e6
    print(f"{len(runs)} runs exportés ; app_data = {size:.1f} Mo")


if __name__ == "__main__":
    main()
