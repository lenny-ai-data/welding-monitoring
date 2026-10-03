"""Accès en lecture seule aux artefacts précalculés (app_data/).

Toute donnée désignée par l'utilisateur (run, frame) passe par une liste blanche : aucun chemin
n'est jamais construit à partir d'une saisie brute.
"""

import json
import os
import re
from functools import cache
from pathlib import Path

# Emplacement des données et liste blanche ---------------------------------------------------------
DATA_DIR = Path(os.environ.get("WELDMON_DATA", Path(__file__).resolve().parents[3] / "app_data"))
MEDIA_DIR = DATA_DIR / "media"

RUN_ID_RE = re.compile(r"^DoE[123]_([1-9]|1\d|2[0-7])$")
N_SEG_FRAMES = 164  # frames annotées par vidéo (même valeur que pipeline/04_labels.py et assets/seg.js)

# Lecture des artefacts (mise en cache : les fichiers ne changent pas pendant la vie du processus) -


def _read(name: str):
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


@cache
def meta() -> dict:
    return _read("meta.json")


@cache
def runs() -> list[dict]:
    """Runs triés par série puis ordre d'exécution."""
    return _read("runs.json")


@cache
def runs_by_id() -> dict[str, dict]:
    return {r["run_id"]: r for r in runs()}


@cache
def doe() -> dict:
    return _read("doe.json")


@cache
def seg() -> dict:
    return _read("seg_metrics.json")


# Runs ---------------------------------------------------------------------------------------------


def valid_run(run_id: object) -> str | None:
    """Renvoie le run_id s'il est bien formé ET connu, sinon None."""
    if isinstance(run_id, str) and RUN_ID_RE.match(run_id) and run_id in runs_by_id():
        return run_id
    return None


@cache
def timeseries(run_id: str) -> dict:
    run_id = valid_run(run_id)
    if run_id is None:
        raise KeyError("run inconnu")
    return _read(f"ts/{run_id}.json")


def labeled_runs() -> list[str]:
    return list(seg()["runs"])


def run_label(run: dict) -> str:
    return (
        f"{run['serie']} · essai {run['point']:>2}, {run['power_w']:.0f} W · "
        f"{run['feedrate_mm_s']:.0f} mm/s · déf. {run['defocus_mm']:+.1f} mm · PFO {run['pfo_y_mm']:.0f} mm"
    )


def next_run(run_id: str) -> str:
    """Run suivant dans l'ordre d'exécution (mode ligne de production), en bouclant."""
    ids = [r["run_id"] for r in runs()]
    return ids[(ids.index(run_id) + 1) % len(ids)]
