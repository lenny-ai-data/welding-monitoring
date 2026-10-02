"""Chemins et constantes partagés par les scripts du pipeline."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data"
INTERIM = RAW / "interim"
PROCESSED = RAW / "processed"
MODELS = ROOT / "models"
APP_DATA = ROOT / "app_data"

VIDEOS_DIR = INTERIM / "high_speed_camera_videos"
LABELS_DIR = INTERIM / "Labels"
METADATA_XLSX = RAW / "Laser_Welding_Dataset_Metadata.xlsx"

TRAIN_RUNS = ["DoE3_9", "DoE3_16", "DoE3_22", "DoE3_24", "DoE3_25", "DoE3_26"]
EVAL_RUNS = ["DoE3_19", "DoE3_23"]
LABELED_RUNS = TRAIN_RUNS + EVAL_RUNS

# Classes de segmentation (0 = fond). Priorité de fusion : spatter > plasma > weld.
CLASSES = {1: "weld", 2: "plasma", 3: "spatter"}
CLASS_IDS = {v: k for k, v in CLASSES.items()}

SIZE = 512  # résolution de travail (frames, masques, vidéos web)
PLAYBACK_FPS = 30


def run_dir_name(run_id: str) -> str:
    return f"{run_id}_C001H001S0001"


def video_path(run_id: str) -> Path:
    serie = run_id.split("_")[0].upper()
    name = run_dir_name(run_id)
    return VIDEOS_DIR / serie / name / f"{name}.avi"


def cihx_path(run_id: str) -> Path:
    return video_path(run_id).with_suffix(".cihx")
