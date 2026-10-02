"""Décompresse les archives Zenodo dans data/interim (idempotent)."""

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
