"""Normalise les 8 vidéos annotées en cartes de labels sémantiques 512 px.

- schéma CSV commun (les exports SAM2 ont 18, 33 ou 46 colonnes) ;
- mapping frame annotée -> frame vidéo reconstruit (round(linspace)) et vérifié ;
- fusion des instances par priorité spatter > plasma > weld, `dynamic_other` ignoré (255).
"""

import cv2
import numpy as np
import pandas as pd
from common import (
    CLASS_IDS,
    EVAL_RUNS,
    LABELED_RUNS,
    LABELS_DIR,
    PROCESSED,
    SIZE,
    run_dir_name,
    video_path,
)

IGNORE = 255
N_LABELED = 164
COMMON = [
    "frame_file",
    "frame_index",
    "mask_path",
    "label",
    "track_id",
    "area",
    "bbox_x",
    "bbox_y",
    "bbox_w",
    "bbox_h",
    "cx_geo",
    "cy_geo",
]
PAINT_ORDER = ["dynamic_other", "weld", "plasma", "spatter"]  # le dernier peint gagne
OUT = PROCESSED / "labels"


def run_root(run_id: str):
    split = "eval_ground_truth" if run_id in EVAL_RUNS else "training_labeled"
    return LABELS_DIR / split / run_dir_name(run_id)


def video_frames(run_id: str, indices) -> dict[int, np.ndarray]:
    wanted, frames = set(indices), {}
    cap = cv2.VideoCapture(str(video_path(run_id)))
    i = 0
    while len(frames) < len(wanted):
        ok, img = cap.read()
        if not ok:
            break
        if i in wanted:
            frames[i] = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        i += 1
    cap.release()
    return frames


def frame_mapping(run_id: str, n_video_frames: int) -> np.ndarray:
    """Index vidéo de chaque frame annotée, vérifié contre les fichiers de mapping fournis."""
    mapping = np.round(np.linspace(0, n_video_frames - 1, N_LABELED)).astype(int)
    root = run_root(run_id)
    for ref_file, col in [
        (root / "frames" / "frame_mapping.csv", "original_video_frame_index"),
        (root / f"{run_id}_gui_frame_mapping.csv", "original_frame_index"),
    ]:
        if ref_file.exists():
            ref = pd.read_csv(ref_file)[col].to_numpy()
            assert np.array_equal(ref, mapping[: len(ref)]), f"mapping incohérent pour {run_id}"
            print(f"  {run_id}: mapping identique à {ref_file.name} ({len(ref)} frames)")
    return mapping


def check_pixels(run_id: str, mapping: np.ndarray) -> float:
    """Écart moyen entre frames annotées et frames décodées de l'AVI (échantillon)."""
    sample = mapping[::20]
    decoded = video_frames(run_id, sample)
    diffs = []
    for k, idx in zip(range(0, N_LABELED, 20), sample, strict=True):
        ref = cv2.imread(str(run_root(run_id) / "frames" / f"frame_{k:05d}.png"), cv2.IMREAD_GRAYSCALE)
        diffs.append(np.abs(ref.astype(int) - decoded[idx].astype(int)).mean())
    return float(np.mean(diffs))


def load_instances(run_id: str) -> pd.DataFrame:
    df = pd.read_csv(run_root(run_id) / "labels_final.csv")
    df = df[~df["ignore"].astype(bool)][COMMON].copy()
    df["mask_file"] = df["mask_path"].str.split("/").str[-1]
    df["run_id"] = run_id
    return df.drop(columns="mask_path")


def label_map(run_id: str, instances: pd.DataFrame) -> np.ndarray:
    lab = np.zeros((SIZE, SIZE), np.uint8)
    for cls in PAINT_ORDER:
        for mask_file in instances.loc[instances.label == cls, "mask_file"]:
            m = cv2.imread(str(run_root(run_id) / "final_masks" / mask_file), cv2.IMREAD_GRAYSCALE)
            m = cv2.resize((m > 0).astype(np.float32), (SIZE, SIZE), interpolation=cv2.INTER_AREA) >= 0.5
            lab[m] = CLASS_IDS.get(cls, IGNORE)
    return lab


def main() -> None:
    runs = pd.read_parquet(PROCESSED / "runs.parquet").set_index("run_id")
    index_rows, all_instances = [], []
    for run_id in LABELED_RUNS:
        mapping = frame_mapping(run_id, int(runs.at[run_id, "n_frames"]))
        mad = check_pixels(run_id, mapping)
        print(f"  {run_id}: écart pixel moyen frames annotées / AVI = {mad:.2f}")
        assert mad < 2.0, f"frames annotées non alignées pour {run_id}"

        instances = load_instances(run_id)
        instances["video_frame"] = mapping[instances.frame_index]
        all_instances.append(instances)

        (OUT / run_id / "frames").mkdir(parents=True, exist_ok=True)
        (OUT / run_id / "masks").mkdir(parents=True, exist_ok=True)
        for k in range(N_LABELED):
            img = cv2.imread(str(run_root(run_id) / "frames" / f"frame_{k:05d}.png"), cv2.IMREAD_GRAYSCALE)
            img = cv2.resize(img, (SIZE, SIZE), interpolation=cv2.INTER_AREA)
            lab = label_map(run_id, instances[instances.frame_index == k])
            cv2.imwrite(str(OUT / run_id / "frames" / f"{k:03d}.png"), img)
            cv2.imwrite(str(OUT / run_id / "masks" / f"{k:03d}.png"), lab)
            row = {
                "run_id": run_id,
                "gt_index": k,
                "video_frame": int(mapping[k]),
                "split": "eval" if run_id in EVAL_RUNS else "train",
            }
            row.update({f"px_{name}": int((lab == cid).sum()) for name, cid in CLASS_IDS.items()})
            index_rows.append(row)
        print(f"ok {run_id}: {len(instances)} instances")

    pd.DataFrame(index_rows).to_parquet(PROCESSED / "labeled_frames.parquet", index=False)
    pd.concat(all_instances).to_parquet(PROCESSED / "label_instances.parquet", index=False)


if __name__ == "__main__":
    main()
