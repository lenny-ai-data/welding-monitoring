"""Entraîne le U-Net (cordon / plasma / projections) puis l'évalue sur les 2 vidéos tenues à l'écart.

Découpage par vidéo (jamais par frame, pour éviter les fuites entre frames voisines) :
- train : 5 vidéos DoE3 annotées ; validation (choix du checkpoint) : DoE3_16 ;
- évaluation finale : DoE3_19 et DoE3_23, jamais vues pendant l'entraînement.
"""

import json
import sys
import time

import baseline_cv
import cv2
import numpy as np
import pandas as pd
import segmentation_models_pytorch as smp
import torch
from common import CLASSES, EVAL_RUNS, MODELS, PROCESSED, TRAIN_RUNS
from metrics import IGNORE, confusion, f1, instance_matches, iou_from_confusion
from segmodel import ENCODER, N_CLASSES, build_model, load_model, suppress_static, to_tensor
from torch.utils.data import DataLoader, Dataset
from torchvision import tv_tensors
from torchvision.transforms import v2

VAL_RUNS = ["DoE3_16"]
FIT_RUNS = [r for r in TRAIN_RUNS if r not in VAL_RUNS]
EPOCHS, BATCH, LR = 80, 8, 3e-4
SEED = 42
DEVICE = "cuda"


def load_run(run_id: str) -> tuple[np.ndarray, np.ndarray]:
    root = PROCESSED / "labels" / run_id
    frames = sorted((root / "frames").glob("*.png"))
    imgs = np.stack([cv2.imread(str(p), cv2.IMREAD_GRAYSCALE) for p in frames])
    masks = np.stack([cv2.imread(str(root / "masks" / p.name), cv2.IMREAD_GRAYSCALE) for p in frames])
    return imgs, masks


class RandomGamma(torch.nn.Module):
    """Correction gamma aléatoire (images uniquement, le masque n'est pas modifié)."""

    def __init__(self, low: float, high: float):
        super().__init__()
        self.low, self.high = low, high

    def forward(self, img, mask):
        gamma = float(np.exp(np.random.uniform(np.log(self.low), np.log(self.high))))
        out = (img.float() / 255.0).pow(gamma).mul(255.0).round().to(torch.uint8)
        return tv_tensors.wrap(out, like=img), mask


class WeldFrames(Dataset):
    def __init__(self, runs: list[str], train: bool):
        data = [load_run(r) for r in runs]
        self.imgs = np.concatenate([d[0] for d in data])
        self.masks = np.concatenate([d[1] for d in data])
        # Pas de flip horizontal : le sens de soudage (gauche -> droite) est une information.
        # Augmentations fortes en cadrage et en exposition : les séries DoE1 / DoE2 (non annotées)
        # ont un éclairage et un cadrage différents de DoE3 (seule série annotée).
        self.aug = (
            v2.Compose(
                [
                    v2.RandomAffine(degrees=4, translate=(0.08, 0.2), scale=(0.85, 1.15)),
                    v2.RandomApply([v2.ColorJitter(brightness=0.6, contrast=0.6)], p=0.9),
                    v2.RandomApply([RandomGamma(0.5, 2.0)], p=0.6),
                    v2.RandomApply([v2.GaussianBlur(5, sigma=(0.1, 1.5))], p=0.3),
                ]
            )
            if train
            else None
        )

    def __len__(self) -> int:
        return len(self.imgs)

    def __getitem__(self, i: int):
        img = tv_tensors.Image(torch.from_numpy(self.imgs[i])[None])
        mask = tv_tensors.Mask(torch.from_numpy(self.masks[i]))
        if self.aug:
            img, mask = self.aug(img, mask)
        x = img.float().div(255.0).sub(0.45).div(0.25)
        return x, mask.long()


@torch.no_grad()
def predict(model, imgs: np.ndarray, batch: int = 16) -> np.ndarray:
    out = []
    for i in range(0, len(imgs), batch):
        x = to_tensor(imgs[i : i + batch]).to(DEVICE)
        with torch.autocast("cuda", dtype=torch.float16):
            out.append(model(x).argmax(1).cpu().numpy().astype(np.uint8))
    return np.concatenate(out)


def evaluate(gt: np.ndarray, pred: np.ndarray) -> dict:
    cm = confusion(gt, pred, N_CLASSES)
    iou = iou_from_confusion(cm)
    counts = {"n_pred": 0, "tp_pred": 0, "n_gt": 0, "tp_gt": 0}
    for g, p in zip(gt, pred, strict=True):
        for k, v in instance_matches(g == 3, p == 3).items():
            counts[k] += v
    area_gt = (gt == 2).sum((1, 2))
    area_pred = (pred == 2).sum((1, 2))
    return {
        "iou": {CLASSES[c]: round(float(iou[c]), 4) for c in CLASSES},
        "miou": round(float(np.nanmean(iou[1:])), 4),
        "spatter_detection": {k: round(v, 4) for k, v in f1(counts).items()} | counts,
        "plasma_area_corr": round(float(np.corrcoef(area_gt, area_pred)[0, 1]), 4),
    }


def baseline(runs: list[str], threshold: int) -> np.ndarray:
    preds = []
    for r in runs:
        imgs, _ = load_run(r)
        preds.append(np.stack([baseline_cv.segment(im, imgs[0], threshold) for im in imgs]))
    return np.concatenate(preds)


def tune_baseline() -> int:
    """Seuil de la baseline choisi sur les vidéos d'entraînement (IoU plasma)."""
    gts = np.concatenate([load_run(r)[1] for r in TRAIN_RUNS])
    scores = {t: evaluate(gts, baseline(TRAIN_RUNS, t))["iou"]["plasma"] for t in range(20, 141, 20)}
    best = max(scores, key=scores.get)
    print(f"baseline : seuil retenu {best} (IoU plasma train {scores[best]:.3f})")
    return best


def train() -> torch.nn.Module:
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    train_ds, val_ds = WeldFrames(FIT_RUNS, train=True), WeldFrames(VAL_RUNS, train=False)
    loader = DataLoader(
        train_ds, batch_size=BATCH, shuffle=True, num_workers=6, drop_last=True, persistent_workers=True
    )
    model = build_model().to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=LR, total_steps=EPOCHS * len(loader))
    dice = smp.losses.DiceLoss("multiclass", ignore_index=IGNORE)
    ce = torch.nn.CrossEntropyLoss(ignore_index=IGNORE)
    scaler = torch.amp.GradScaler()
    best, best_state, history = -1.0, None, []

    for epoch in range(1, EPOCHS + 1):
        model.train()
        t0, total = time.time(), 0.0
        for x, y in loader:
            x, y = x.to(DEVICE, non_blocking=True), y.to(DEVICE, non_blocking=True)
            opt.zero_grad(set_to_none=True)
            with torch.autocast("cuda", dtype=torch.float16):
                logits = model(x)
                loss = ce(logits, y) + dice(logits, y)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            sched.step()
            total += loss.item()
        model.eval()
        val = evaluate(val_ds.masks, predict(model, val_ds.imgs))
        history.append({"epoch": epoch, "loss": total / len(loader), "val_miou": val["miou"]})
        if val["miou"] > best:
            best, best_state = val["miou"], {k: v.detach().clone() for k, v in model.state_dict().items()}
        print(
            f"epoch {epoch:3d}  loss {total / len(loader):.4f}  val mIoU {val['miou']:.4f}  "
            f"{val['iou']}  {time.time() - t0:.0f}s",
            flush=True,
        )

    model.load_state_dict(best_state)
    pd.DataFrame(history).to_csv(MODELS / "history.csv", index=False)
    return model


def main() -> None:
    MODELS.mkdir(exist_ok=True)
    if "--eval-only" in sys.argv:
        model = load_model(MODELS / "unet.pt", DEVICE)
    else:
        model = train()
        torch.save(model.state_dict(), MODELS / "unet.pt")

    def predict_run(run_id: str) -> np.ndarray:
        # Même post-traitement qu'en production (rejet des détections immobiles).
        return suppress_static(predict(model, load_run(run_id)[0]))

    gt_eval = np.concatenate([load_run(r)[1] for r in EVAL_RUNS])
    pred_eval = np.concatenate([predict_run(r) for r in EVAL_RUNS])
    threshold = tune_baseline()
    report = {
        "model": {
            "arch": "U-Net",
            "encoder": ENCODER,
            "input": "512x512 gris",
            "epochs": EPOCHS,
            "train_runs": FIT_RUNS,
            "val_runs": VAL_RUNS,
            "eval_runs": EVAL_RUNS,
            "params_m": round(sum(p.numel() for p in model.parameters()) / 1e6, 1),
        },
        "eval": evaluate(gt_eval, pred_eval),
        "eval_raw": evaluate(gt_eval, np.concatenate([predict(model, load_run(r)[0]) for r in EVAL_RUNS])),
        "eval_per_run": {r: evaluate(load_run(r)[1], predict_run(r)) for r in EVAL_RUNS},
        "baseline": {"threshold": threshold, **evaluate(gt_eval, baseline(EVAL_RUNS, threshold))},
    }
    (MODELS / "metrics.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
