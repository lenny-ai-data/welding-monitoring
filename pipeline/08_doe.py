"""Modèles de surface de réponse (Box-Behnken, 4 facteurs) sur les KPI vision.

Modèle quadratique complet en facteurs codés (-1, 0, +1) + effet de série (DoE1/2/3) :
y = b0 + Σ bi·xi + Σ bii·xi² + Σ bij·xi·xj + série. Ajusté par moindres carrés sur les 81 runs.
Les coefficients sont exportés : l'app recalcule les contours sans numpy.
"""

import itertools
import json

import numpy as np
import pandas as pd
from common import PROCESSED
from scipy import stats

FACTORS = {  # nom : (colonne, centre, demi-étendue, libellé, unité)
    "P": ("power_w", 3500, 500, "Puissance", "W"),
    "v": ("feedrate_mm_s", 200, 50, "Vitesse d'avance", "mm/s"),
    "f": ("defocus_mm", 0.0, 0.2, "Défocalisation", "mm"),
    "y": ("pfo_y_mm", 45, 20, "Translation PFO Y", "mm"),
}
KPIS = {
    "plasma_mean_mm2": ("Aire moyenne du plasma", "mm²"),
    "plasma_cv": ("Instabilité du plasma (CV)", ""),
    "plasma_height_mm": ("Hauteur du panache", "mm"),
    "spatter_mean": ("Projections visibles / frame", ""),
    "weld_width_mm": ("Largeur du cordon", "mm"),
    "speed_error_pct": ("Écart vitesse mesurée / consigne", "%"),
}


def terms(names: list[str]) -> list[tuple[str, ...]]:
    lin = [(a,) for a in names]
    quad = [(a, a) for a in names]
    inter = list(itertools.combinations(names, 2))
    return lin + quad + inter


def design_matrix(coded: pd.DataFrame, series: pd.Series, model_terms) -> tuple[np.ndarray, list[str]]:
    cols = [np.ones(len(coded))]
    labels = ["intercept"]
    for t in model_terms:
        cols.append(np.prod([coded[a].to_numpy() for a in t], axis=0))
        labels.append("·".join(t) if len(set(t)) > 1 else (f"{t[0]}²" if len(t) == 2 else t[0]))
    for s in sorted(series.unique())[1:]:  # DoE1 = référence
        cols.append((series == s).astype(float).to_numpy())
        labels.append(f"série {s}")
    return np.column_stack(cols), labels


def fit(X: np.ndarray, y: np.ndarray) -> dict:
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    n, p = X.shape
    dof = n - p
    sigma2 = resid @ resid / dof
    cov = sigma2 * np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(cov))
    t = beta / se
    ss_tot = ((y - y.mean()) ** 2).sum()
    r2 = 1 - (resid @ resid) / ss_tot
    return {
        "beta": beta,
        "se": se,
        "t": t,
        "p": 2 * stats.t.sf(np.abs(t), dof),
        "r2": r2,
        "r2_adj": 1 - (1 - r2) * (n - 1) / dof,
        "rmse": float(np.sqrt(sigma2)),
        "dof": dof,
    }


def main() -> None:
    runs = pd.read_parquet(PROCESSED / "runs.parquet").merge(
        pd.read_parquet(PROCESSED / "run_kpis.parquet"), on="run_id"
    )
    coded = pd.DataFrame({k: (runs[c] - c0) / h for k, (c, c0, h, *_) in FACTORS.items()})
    model_terms = terms(list(FACTORS))
    out = {
        "factors": {
            k: {"column": c, "center": c0, "half_range": h, "label": lab, "unit": u}
            for k, (c, c0, h, lab, u) in FACTORS.items()
        },
        "terms": [list(t) for t in model_terms],
        "kpis": {},
    }

    for kpi, (label, unit) in KPIS.items():
        ok = runs[kpi].notna()
        X, names = design_matrix(coded[ok], runs.loc[ok, "serie"], model_terms)
        res = fit(X, runs.loc[ok, kpi].to_numpy(float))
        n_terms = 1 + len(model_terms)
        series_offsets = res["beta"][n_terms:]
        out["kpis"][kpi] = {
            "label": label,
            "unit": unit,
            "n": int(ok.sum()),
            "r2": round(float(res["r2"]), 4),
            "r2_adj": round(float(res["r2_adj"]), 4),
            "rmse": round(res["rmse"], 5),
            "dof": int(res["dof"]),
            "t_crit": round(float(stats.t.ppf(0.975, res["dof"])), 4),
            # Valeurs ajustées (série comprise) : base de la carte de contrôle des résidus.
            "fitted": {rid: round(float(v), 5) for rid, v in zip(runs.loc[ok, "run_id"], X @ res["beta"], strict=True)},
            # Intercept moyenné sur les séries, pour des surfaces « série moyenne ».
            "intercept": float(res["beta"][0] + series_offsets.sum() / 3),
            "coefs": [float(b) for b in res["beta"][1:n_terms]],
            "effects": [
                {"term": nm, "coef": round(float(b), 5), "t": round(float(t), 3), "p": round(float(p), 5)}
                for nm, b, t, p in zip(names[1:], res["beta"][1:], res["t"][1:], res["p"][1:], strict=True)
            ],
        }
        print(
            f"{kpi:20s} R² {res['r2']:.3f}  R²aj {res['r2_adj']:.3f}  "
            f"termes significatifs (p<0,05) : "
            f"{[nm for nm, p in zip(names[1:], res['p'][1:], strict=True) if p < 0.05]}"
        )

    (PROCESSED / "doe.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
