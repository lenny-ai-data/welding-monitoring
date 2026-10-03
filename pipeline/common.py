"""Chemins et constantes partagés par les scripts du pipeline.

Les scripts se lancent depuis pipeline/ (le Makefile s'en charge) et importent ce module. C'est ici que se
définissent l'arborescence des données, le découpage des vidéos annotées et les classes de segmentation.
"""

from pathlib import Path

# Arborescence -------------------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data"
INTERIM = RAW / "interim"
PROCESSED = RAW / "processed"
MODELS = ROOT / "models"
APP_DATA = ROOT / "app_data"

VIDEOS_DIR = INTERIM / "high_speed_camera_videos"
LABELS_DIR = INTERIM / "Labels"
METADATA_XLSX = RAW / "Laser_Welding_Dataset_Metadata.xlsx"

# Vidéos annotées ----------------------------------------------------------------------------------
# Découpage par vidéo, jamais par frame. La vidéo de validation (choix du checkpoint) est prise dans
# TRAIN_RUNS par 05_train_seg.py ; les vidéos d'évaluation ne servent jamais à l'entraînement.
TRAIN_RUNS = ["DoE3_9", "DoE3_16", "DoE3_22", "DoE3_24", "DoE3_25", "DoE3_26"]
EVAL_RUNS = ["DoE3_19", "DoE3_23"]
LABELED_RUNS = TRAIN_RUNS + EVAL_RUNS

# Segmentation et vidéos ---------------------------------------------------------------------------
# Classes de segmentation (0 = fond). Priorité de fusion : spatter > plasma > weld.
CLASSES = {1: "weld", 2: "plasma", 3: "spatter"}
CLASS_IDS = {v: k for k, v in CLASSES.items()}

SIZE = 512  # résolution de travail (frames, masques, vidéos web)
PLAYBACK_FPS = 30  # cadence des vidéos web : une frame caméra par frame vidéo

# Chemins des fichiers source ----------------------------------------------------------------------


def run_dir_name(run_id: str) -> str:
    """Nom du dossier d'un run dans le dataset (convention de nommage Photron)."""
    return f"{run_id}_C001H001S0001"


def video_path(run_id: str) -> Path:
    serie = run_id.split("_")[0].upper()
    name = run_dir_name(run_id)
    return VIDEOS_DIR / serie / name / f"{name}.avi"


def cihx_path(run_id: str) -> Path:
    return video_path(run_id).with_suffix(".cihx")
