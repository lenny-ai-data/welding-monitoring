"""Modèle de segmentation partagé entre entraînement et inférence."""

import numpy as np
import segmentation_models_pytorch as smp
import torch

ENCODER = "resnet34"
N_CLASSES = 4  # fond, cordon, plasma, projections
MEAN, STD = 0.45, 0.25  # statistiques approx. des frames (niveaux de gris normalisés 0-1)


def build_model(pretrained: bool = True) -> torch.nn.Module:
    return smp.Unet(
        encoder_name=ENCODER,
        encoder_weights="imagenet" if pretrained else None,
        in_channels=1,
        classes=N_CLASSES,
    )


def to_tensor(gray: np.ndarray) -> torch.Tensor:
    """uint8 (H, W) ou (N, H, W) -> float tensor (N, 1, H, W) normalisé."""
    x = torch.from_numpy(gray).float().div_(255.0)
    if x.ndim == 2:
        x = x[None]
    return x[:, None].sub_(MEAN).div_(STD)


def load_model(path, device: str = "cuda") -> torch.nn.Module:
    model = build_model(pretrained=False)
    model.load_state_dict(torch.load(path, map_location=device, weights_only=True))
    return model.to(device).eval()
