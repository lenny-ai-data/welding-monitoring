"""Étape 03 : transcode les AVI Photron (msmpeg4v3, 1024²) en MP4 H.264 512 px pour le web.

Chaque frame source devient une frame vidéo à 30 fps (aucune duplication ni perte) :
l'index de frame se retrouve donc exactement via `currentTime * 30` dans le navigateur.
Le nombre de frames de chaque MP4 est vérifié contre le .cihx ; le script échoue en cas d'écart.

Une vidéo ou un poster déjà présent est sauté : pour retranscoder (nouveau réglage ffmpeg), supprimer
d'abord les fichiers concernés.

Entrées : data/interim/.../<run>.avi, data/processed/runs.parquet
Sorties : app_data/media/videos/<run>.mp4, app_data/media/posters/<run>.jpg (image d'attente du lecteur)
Usage   : make data (étapes 01 à 03) ; nécessite ffmpeg et ffprobe
"""

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
from common import APP_DATA, PLAYBACK_FPS, PROCESSED, SIZE, video_path

# Paramètres ---------------------------------------------------------------------------------------
OUT_VIDEOS = APP_DATA / "media" / "videos"
OUT_POSTERS = APP_DATA / "media" / "posters"
# Réglages x264 (dans transcode) : CRF 32 et preset slower, pour des vidéos légères (moins de 2 Mo) au prix
# d'un encodage plus lent ; une image clé par seconde de lecture (-g 30) pour se déplacer vite dans la vidéo.

# Transcodage --------------------------------------------------------------------------------------


def count_frames(path) -> int:
    """Nombre réel de frames d'une vidéo (comptage des paquets par ffprobe)."""
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_packets",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=nb_read_packets",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    return int(json.loads(out.stdout)["streams"][0]["nb_read_packets"])


def transcode(run: dict) -> dict:
    """Transcode un run et extrait son poster ; renvoie de quoi contrôler le résultat."""
    src = video_path(run["run_id"])
    dst = OUT_VIDEOS / f"{run['run_id']}.mp4"
    poster = OUT_POSTERS / f"{run['run_id']}.jpg"
    if not dst.exists():
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-r",
                str(PLAYBACK_FPS),
                "-i",
                str(src),
                "-vf",
                f"scale={SIZE}:{SIZE}:flags=area,format=yuv420p",
                "-c:v",
                "libx264",
                "-preset",
                "slower",
                "-crf",
                "32",
                "-g",
                str(PLAYBACK_FPS),
                "-an",
                "-movflags",
                "+faststart",
                str(dst),
            ],
            check=True,
        )
    if not poster.exists():
        # Image d'attente : milieu de la phase de soudage (~35 % de la vidéo).
        t = 0.35 * run["n_frames"] / PLAYBACK_FPS
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-ss",
                f"{t:.3f}",
                "-i",
                str(dst),
                "-frames:v",
                "1",
                "-q:v",
                "4",
                str(poster),
            ],
            check=True,
        )
    return {
        "run_id": run["run_id"],
        "frames_mp4": count_frames(dst),
        "n_frames": run["n_frames"],
        "mb": dst.stat().st_size / 1e6,
    }


# Point d'entrée -----------------------------------------------------------------------------------


def main() -> None:
    OUT_VIDEOS.mkdir(parents=True, exist_ok=True)
    OUT_POSTERS.mkdir(parents=True, exist_ok=True)
    runs = pd.read_parquet(PROCESSED / "runs.parquet")
    with ThreadPoolExecutor(max_workers=6) as pool:
        report = pd.DataFrame(pool.map(transcode, runs.to_dict("records")))
    bad = report[report.frames_mp4 != report.n_frames]
    print(f"{len(report)} vidéos, {report.mb.sum():.1f} Mo (max {report.mb.max():.2f} Mo)")
    if len(bad):
        print("Écarts de nombre de frames :\n", bad.to_string())
        raise SystemExit(1)
    print("nombre de frames identique au .cihx pour toutes les vidéos")


if __name__ == "__main__":
    main()
