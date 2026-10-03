"""Métriques de segmentation : IoU par classe et détection des projections par instance."""

import cv2
import numpy as np

IGNORE = 255  # pixels non annotés, exclus du calcul

# Segmentation au pixel : matrice de confusion et IoU ----------------------------------------------


def confusion(gt: np.ndarray, pred: np.ndarray, n_classes: int) -> np.ndarray:
    """Matrice de confusion (lignes : annotation, colonnes : prédiction), pixels ignorés exclus."""
    valid = gt != IGNORE
    idx = gt[valid].astype(np.int64) * n_classes + pred[valid].astype(np.int64)
    return np.bincount(idx, minlength=n_classes**2).reshape(n_classes, n_classes)


def iou_from_confusion(cm: np.ndarray) -> np.ndarray:
    """IoU par classe ; NaN pour une classe absente de l'annotation comme de la prédiction."""
    inter = np.diag(cm).astype(float)
    union = cm.sum(0) + cm.sum(1) - inter
    with np.errstate(invalid="ignore", divide="ignore"):
        return inter / union


# Détection des projections, objet par objet -------------------------------------------------------


def components(mask: np.ndarray, min_px: int = 4) -> list[np.ndarray]:
    """Composantes connexes d'un masque binaire, d'au moins min_px pixels."""
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    return [lab == i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= min_px]


def instance_matches(gt_mask: np.ndarray, pred_mask: np.ndarray, min_px: int = 4) -> dict:
    """Comptages d'appariement : une projection prédite est correcte si elle recouvre une
    projection annotée (tolérance de 2 px pour les très petits objets), et réciproquement."""
    kernel = np.ones((5, 5), np.uint8)
    gts = components(gt_mask, min_px)
    preds = components(pred_mask, min_px)
    gt_dil = cv2.dilate(gt_mask.astype(np.uint8), kernel) > 0
    pred_dil = cv2.dilate(pred_mask.astype(np.uint8), kernel) > 0
    tp_pred = sum(1 for p in preds if (p & gt_dil).any())
    tp_gt = sum(1 for g in gts if (g & pred_dil).any())
    return {"n_pred": len(preds), "tp_pred": tp_pred, "n_gt": len(gts), "tp_gt": tp_gt}


def f1(counts: dict) -> dict:
    """Précision, rappel et F1 à partir des comptages de instance_matches (cumulés sur plusieurs frames)."""
    precision = counts["tp_pred"] / counts["n_pred"] if counts["n_pred"] else 0.0
    recall = counts["tp_gt"] / counts["n_gt"] if counts["n_gt"] else 0.0
    score = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": score}
