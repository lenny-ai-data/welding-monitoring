"""Étape 02 : construit la table des 81 runs, plan Box-Behnken (xlsx) et métadonnées caméra (.cihx).

L'ordre d'exécution du xlsx liste les points d'essai dans l'ordre où ils ont été soudés ;
il est recoupé avec l'horodatage des enregistrements Photron (corrélation affichée en console).

Entrées : data/Laser_Welding_Dataset_Metadata.xlsx, data/interim/.../<run>.cihx
Sorties : data/processed/runs.parquet (colonnes décrites dans docs/donnees.md)
Usage   : make data (étapes 01 à 03)
"""

import re
from datetime import datetime

import pandas as pd
from common import METADATA_XLSX, PROCESSED, cihx_path

# Plan d'expériences (xlsx) ------------------------------------------------------------------------
# Colonnes de la feuille Excel et nom retenu dans la table des runs.
FACTOR_COLUMNS = {
    "Sampling point": "point",
    "Power [W]": "power_w",
    "Feedrate [mm/s]": "feedrate_mm_s",
    "Defocus [mm]": "defocus_mm",
    "PFO Y translation [mm]": "pfo_y_mm",
    "Inclination angle [deg]": "inclination_deg",
}


def read_design(sheet: str) -> pd.DataFrame:
    """Les 27 points d'une série (feuille DOE1, DOE2 ou DOE3) et leur rang de soudage."""
    raw = pd.read_excel(METADATA_XLSX, sheet_name=sheet, header=None)
    header = raw.iloc[0].tolist()
    design = raw.iloc[1:28].copy()
    design.columns = header
    design = design.rename(columns=FACTOR_COLUMNS).astype(float)
    design["point"] = design["point"].astype(int)

    # Bloc "Execution order" : séquence des points d'essai dans l'ordre de soudage.
    start = raw.index[raw[0].astype(str).str.strip() == "Execution order"][0] + 1
    order = raw.iloc[start:, 0].dropna().astype(int).tolist()
    assert sorted(order) == list(range(1, 28)), f"ordre d'exécution incomplet ({sheet})"
    design["exec_rank"] = design["point"].map({p: i + 1 for i, p in enumerate(order)})
    return design


# Métadonnées caméra (.cihx) -----------------------------------------------------------------------


def read_cihx(path) -> dict:
    """Nombre de frames, cadence, exposition et horodatage, lus dans l'en-tête XML du fichier .cihx."""
    blob = path.read_bytes()
    xml = blob[blob.find(b"<?xml") :].decode("utf-8", "replace")

    def tag(name: str) -> str:
        return re.search(rf"<{name}>(.*?)</{name}>", xml).group(1)

    recorded = datetime.strptime(f"{tag('date')} {tag('time')}", "%Y/%m/%d %H:%M:%S")
    return {
        "n_frames": int(tag("totalFrame")),
        "fps": int(tag("recordRate")),
        "shutter_ns": int(tag("shutterSpeedNsec")),
        "recorded_at": recorded,
        "camera": tag("deviceName"),
    }


# Table des runs -----------------------------------------------------------------------------------


def build_runs() -> pd.DataFrame:
    rows = []
    for serie in ("DOE1", "DOE2", "DOE3"):
        design = read_design(serie)
        for rec in design.to_dict("records"):
            run_id = f"DoE{serie[-1]}_{rec['point']}"
            rows.append({"run_id": run_id, "serie": f"DoE{serie[-1]}", **rec, **read_cihx(cihx_path(run_id))})
    runs = pd.DataFrame(rows)
    runs["duration_ms"] = runs["n_frames"] / runs["fps"] * 1000
    runs["line_energy_j_mm"] = runs["power_w"] / runs["feedrate_mm_s"]
    runs["is_center"] = (
        (runs.power_w == 3500) & (runs.feedrate_mm_s == 200) & (runs.defocus_mm == 0) & (runs.pfo_y_mm == 45)
    )
    return runs


def check_order(runs: pd.DataFrame) -> None:
    """Vérifie que l'ordre d'exécution déclaré suit globalement l'horodatage caméra."""
    for serie, grp in runs.groupby("serie"):
        rho = grp["exec_rank"].corr(grp["recorded_at"].rank(), method="spearman")
        print(f"{serie}: corrélation ordre déclaré / horodatage = {rho:.2f}")


# Point d'entrée -----------------------------------------------------------------------------------


def main() -> None:
    runs = build_runs()
    check_order(runs)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    runs.to_parquet(PROCESSED / "runs.parquet", index=False)
    print(runs.groupby(["serie", "fps"]).size().to_string())
    print(f"{len(runs)} runs -> {PROCESSED / 'runs.parquet'}")


if __name__ == "__main__":
    main()
