"""Étape 01 : décompresse les archives Zenodo dans data/interim/.

Aucune transformation : data/interim/ est le contenu exact des archives et peut être supprimé puis recréé.
Idempotent : un fichier déjà extrait avec la bonne taille est sauté.

Entrées : data/Labels.zip, data/high_speed_camera_videos.zip
Sorties : data/interim/Labels/, data/interim/high_speed_camera_videos/
Usage   : make data (étapes 01 à 03)
"""

import zipfile

from common import INTERIM, RAW

ARCHIVES = ["Labels.zip", "high_speed_camera_videos.zip"]


def main() -> None:
    INTERIM.mkdir(parents=True, exist_ok=True)
    for name in ARCHIVES:
        with zipfile.ZipFile(RAW / name) as zf:
            for info in zf.infolist():
                target = INTERIM / info.filename
                if info.is_dir() or (target.exists() and target.stat().st_size == info.file_size):
                    continue
                zf.extract(info, INTERIM)
        print(f"ok {name}")


if __name__ == "__main__":
    main()
