"""Étape 06 : inférence du U-Net sur toutes les frames des 81 vidéos.

Chaque vidéo est segmentée frame par frame, puis post-traitée en entier (segmodel.suppress_static). Les
mesures sont prises en pixels à 512 px ; la conversion en mm se fait à l'étape 07.

Entrées : AVI des 81 runs, models/unet.pt, data/processed/runs.parquet, labeled_frames.parquet
Sorties :
- data/processed/frame_features.parquet : mesures vision par frame (plasma, projections, cordon) ;
- data/processed/preds/<run>/NNN.png : prédictions aux frames annotées (comparaison GT / IA) ;
- app_data/media/videos/<run>_ia.mp4 : vidéo avec masques IA incrustés.
Usage   : make infer (GPU CUDA et ffmpeg, environ 10 min sur RTX 3090)
"""

import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
import pandas as pd
import torch
from common import APP_DATA, LABELED_RUNS, MODELS, PLAYBACK_FPS, PROCESSED, SIZE, video_path
from segmodel import load_model, suppress_static, to_tensor

# Paramètres ---------------------------------------------------------------------------------------
DEVICE = "cuda"
BATCH = 32
MIN_SPATTER_PX = 4  # une projection compte à partir de 4 px (en dessous : bruit)
# Couleurs d'incrustation (BGR), identiques aux séries de l'app (thème sombre) :
# cordon #9550d8, plasma #dd6a1e, projections #d2448c.
OVERLAY = {1: (216, 80, 149), 2: (30, 106, 221), 3: (140, 68, 210)}
ALPHA = 0.45  # opacité du remplissage des masques

# Décodage et segmentation -------------------------------------------------------------------------


def decode(run_id: str) -> np.ndarray:
    """Toutes les frames d'un AVI, en niveaux de gris 512 px : (N, 512, 512) uint8."""
    cap = cv2.VideoCapture(str(video_path(run_id)))
    frames = []
    while True:
        ok, img = cap.read()
        if not ok:
            break
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        frames.append(cv2.resize(gray, (SIZE, SIZE), interpolation=cv2.INTER_AREA))
    cap.release()
    return np.stack(frames)


@torch.no_grad()
def segment(model, frames: np.ndarray) -> np.ndarray:
    """Cartes de labels brutes (avant post-traitement), par lots de BATCH frames."""
    out = np.empty(frames.shape, np.uint8)
    for i in range(0, len(frames), BATCH):
        x = to_tensor(frames[i : i + BATCH]).to(DEVICE)
        with torch.autocast("cuda", dtype=torch.float16):
            out[i : i + BATCH] = model(x).argmax(1).cpu().numpy()
    return out


# Mesures par frame --------------------------------------------------------------------------------


def frame_features(img: np.ndarray, lab: np.ndarray) -> dict:
    """Mesures en pixels (échelle 512 px) ; la conversion en mm se fait à l'étape signaux."""
    f = {"mean_gray": float(img.mean())}

    plasma = lab == 2
    f["plasma_px"] = int(plasma.sum())
    if f["plasma_px"]:
        ys, xs = np.nonzero(plasma)
        f |= {
            "plasma_cx": float(xs.mean()),
            "plasma_cy": float(ys.mean()),
            "plasma_top": int(ys.min()),
            "plasma_h": int(ys.max() - ys.min() + 1),
            "plasma_w": int(xs.max() - xs.min() + 1),
            "plasma_gray": float(img[plasma].mean()),
        }

    n, _, stats, _ = cv2.connectedComponentsWithStats((lab == 3).astype(np.uint8), connectivity=8)
    areas = stats[1:, cv2.CC_STAT_AREA]
    areas = areas[areas >= MIN_SPATTER_PX]
    f["spatter_n"] = int(len(areas))
    f["spatter_px"] = int(areas.sum())

    weld = lab == 1
    f["weld_px"] = int(weld.sum())
    cols = np.nonzero(weld.sum(0) >= 3)[0]  # colonnes réellement couvertes par le cordon
    if len(cols):
        f |= {
            "weld_x0": int(cols.min()),
            "weld_x1": int(cols.max()),
            "weld_width_px": float(weld[:, cols].sum() / len(cols)),
        }
    return f


# Sorties visuelles --------------------------------------------------------------------------------


def write_overlay_video(run_id: str, frames: np.ndarray, labels: np.ndarray) -> None:
    """Vidéo web avec masques incrustés, encodée à la volée (frames envoyées à ffmpeg par un tube)."""
    dst = APP_DATA / "media" / "videos" / f"{run_id}_ia.mp4"
    proc = subprocess.Popen(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s",
            f"{SIZE}x{SIZE}",
            "-r",
            str(PLAYBACK_FPS),
            "-i",
            "-",
            "-c:v",
            "libx264",
            "-preset",
            "slower",
            "-crf",
            "33",
            "-g",
            str(PLAYBACK_FPS),
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(dst),
        ],
        stdin=subprocess.PIPE,
    )
    for img, lab in zip(frames, labels, strict=True):
        bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        tint = bgr.copy()
        for cid, color in OVERLAY.items():
            tint[lab == cid] = color
        out = cv2.addWeighted(tint, ALPHA, bgr, 1 - ALPHA, 0)
        for cid, color in OVERLAY.items():  # contours pleins pour que les petites projections ressortent
            contours, _ = cv2.findContours((lab == cid).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(out, contours, -1, color, 1, lineType=cv2.LINE_AA)
        proc.stdin.write(out.tobytes())
    proc.stdin.close()
    if proc.wait():
        raise RuntimeError(f"ffmpeg a échoué pour {run_id}")


def save_labeled_preds(run_id: str, labels: np.ndarray, labeled: pd.DataFrame) -> None:
    """Prédictions aux frames annotées, pour la comparaison annotation / IA de l'app."""
    out = PROCESSED / "preds" / run_id
    out.mkdir(parents=True, exist_ok=True)
    for row in labeled[labeled.run_id == run_id].itertuples():
        cv2.imwrite(str(out / f"{row.gt_index:03d}.png"), labels[row.video_frame])


# Point d'entrée -----------------------------------------------------------------------------------


def main() -> None:
    model = load_model(MODELS / "unet.pt", DEVICE)
    runs = pd.read_parquet(PROCESSED / "runs.parquet")
    labeled = pd.read_parquet(PROCESSED / "labeled_frames.parquet")
    rows, run_ids = [], list(runs.run_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        # Décodage CPU en avance de 2 vidéos sur le GPU (mémoire bornée).
        pending = [pool.submit(decode, r) for r in run_ids[:2]]
        for k, run_id in enumerate(run_ids):
            frames = pending.pop(0).result()
            if k + 2 < len(run_ids):
                pending.append(pool.submit(decode, run_ids[k + 2]))
            t0 = time.time()
            labels = suppress_static(segment(model, frames))
            feats = [frame_features(img, lab) for img, lab in zip(frames, labels, strict=True)]
            rows.extend({"run_id": run_id, "frame": i, **f} for i, f in enumerate(feats))
            write_overlay_video(run_id, frames, labels)
            if run_id in LABELED_RUNS:
                save_labeled_preds(run_id, labels, labeled)
            print(f"ok {run_id}: {len(frames)} frames, {time.time() - t0:.1f}s", flush=True)
    pd.DataFrame(rows).to_parquet(PROCESSED / "frame_features.parquet", index=False)
    print(f"{len(rows)} frames -> frame_features.parquet")


if __name__ == "__main__":
    main()
