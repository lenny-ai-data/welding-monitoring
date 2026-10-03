"""Mesure des temps d'inférence, poste par poste, sur une vidéo (aucun fichier du projet n'est modifié).

Sert à dimensionner un déploiement : débit du modèle selon la taille de lot et la précision, latence
d'une image, coût des étapes autour du modèle, mémoire GPU, et débit sur CPU pour comparaison.
Résultats commentés dans docs/production.md.

Entrées : AVI du run choisi, models/unet.pt
Sorties : tableau en console
Usage   : make bench            (run DoE3_19 par défaut)
          python bench_infer.py DoE3_23
"""

import importlib
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import torch
from common import MODELS
from segmodel import load_model, suppress_static, to_tensor

infer = importlib.import_module("06_infer")

RUN = sys.argv[1] if len(sys.argv) > 1 else "DoE3_19"
BATCHES = [1, 8, 32]
CPU_FRAMES = 32  # le CPU est lent : un échantillon suffit pour estimer son débit

# Chronométrage ------------------------------------------------------------------------------------


def timed(fn, *args, repeat: int = 1, cuda: bool = True):
    """Résultat du dernier appel et durée moyenne d'un appel (s), GPU synchronisé avant et après."""
    if cuda:
        torch.cuda.synchronize()
    t0 = time.perf_counter()
    for _ in range(repeat):
        out = fn(*args)
    if cuda:
        torch.cuda.synchronize()
    return out, (time.perf_counter() - t0) / repeat


@torch.no_grad()
def forward_rate(model, frames: np.ndarray, batch: int, half: bool, device: str = "cuda") -> float:
    """Débit (images/s) du modèle seul : passe avant, sans argmax ni retour des résultats vers le CPU."""
    x = to_tensor(frames[:batch]).to(device)
    with torch.autocast("cuda", dtype=torch.float16, enabled=half and device == "cuda"):
        for _ in range(5):  # chauffe
            model(x)
        repeat = max(3, 256 // batch)
        _, dt = timed(model, x, repeat=repeat, cuda=device == "cuda")
    return batch / dt


# Point d'entrée -----------------------------------------------------------------------------------


def main() -> None:
    model = load_model(MODELS / "unet.pt", "cuda")
    frames, t_decode = timed(infer.decode, RUN, cuda=False)
    n = len(frames)
    infer.segment(model, frames[:64])  # chauffe

    raw, t_seg = timed(infer.segment, model, frames, repeat=3)
    labels, t_post = timed(suppress_static, raw, cuda=False)
    _, t_feat = timed(lambda: [infer.frame_features(i, lab) for i, lab in zip(frames, labels, strict=True)], cuda=False)
    with tempfile.TemporaryDirectory() as tmp:
        infer.APP_DATA = Path(tmp)
        (Path(tmp) / "media" / "videos").mkdir(parents=True)
        _, t_video = timed(infer.write_overlay_video, RUN, frames, labels, cuda=False)

    torch.cuda.reset_peak_memory_stats()
    rates = {(b, h): forward_rate(model, frames, b, h) for b in BATCHES for h in (True, False)}
    peak_mb = torch.cuda.max_memory_allocated() / 2**20
    cpu_rate = forward_rate(load_model(MODELS / "unet.pt", "cpu"), frames[:CPU_FRAMES], 8, False, "cpu")

    print(f"{RUN} : {n} frames, {torch.cuda.get_device_name()}, PyTorch {torch.__version__}\n")
    print("Chaîne de 06_infer, vidéo entière")
    for label, dt in [
        ("décodage AVI + redimensionnement", t_decode),
        ("U-Net (lots de 32, fp16, argmax)", t_seg),
        ("post-traitement (suppress_static)", t_post),
        ("mesures par frame", t_feat),
        ("encodage de la vidéo IA (démo)", t_video),
    ]:
        print(f"  {label:36s} {dt:6.2f} s  {n / dt:7.0f} im/s")
    print("\nModèle seul (passe avant)")
    for (b, h), r in rates.items():
        print(f"  lot {b:2d}, {'fp16' if h else 'fp32'}  {r:7.0f} im/s  ({1000 * b / r:6.2f} ms par lot)")
    print(f"  CPU, lot 8, fp32   {cpu_rate:7.1f} im/s  ({torch.get_num_threads()} threads)")
    print(f"\nMémoire GPU de pointe : {peak_mb:.0f} Mo")


if __name__ == "__main__":
    main()
