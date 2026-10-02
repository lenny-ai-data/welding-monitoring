"""Baseline « vision classique » : soustraction de fond + seuillage.

Sert de référence honnête face au modèle : le panache de plasma est le pixel le plus lumineux
de la scène, on le segmente sans apprentissage ; les petites taches lumineuses hors panache
sont comptées comme projections. Le cordon n'est pas accessible par cette méthode.
"""

import cv2
import numpy as np

PLASMA, SPATTER = 2, 3
KERNEL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))


def segment(img: np.ndarray, background: np.ndarray, threshold: int, spatter_max_px: int = 400) -> np.ndarray:
    diff = img.astype(np.int16) - background.astype(np.int16)
    hot = (diff > threshold).astype(np.uint8)
    hot = cv2.morphologyEx(hot, cv2.MORPH_OPEN, KERNEL)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(hot, connectivity=8)
    out = np.zeros_like(img, dtype=np.uint8)
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        out[lab == i] = SPATTER if area <= spatter_max_px else PLASMA
    return out
