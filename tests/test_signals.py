import numpy as np
import pytest
from metrics import confusion, f1, instance_matches, iou_from_confusion


def test_detect_on_off_ignores_single_frame_flicker(signals):
    plasma = np.zeros(600)
    plasma[100:400] = 500
    plasma[250] = 0  # scintillement d'une frame pendant le soudage
    plasma[50] = 500  # fausse détection isolée avant l'allumage
    on, off = signals.detect_on_off(plasma, fps=6000)
    assert abs(on - 100) <= 2 and abs(off - 399) <= 2


def test_detect_on_off_without_plasma(signals):
    assert signals.detect_on_off(np.zeros(300), fps=6000) is None


def test_front_slope_recovers_speed(signals):
    frames = np.arange(100, 400)
    front = 20 + 1.8 * frames + np.random.default_rng(0).normal(0, 0.5, frames.size)
    slope, r2 = signals.front_slope(frames, front)
    assert slope == pytest.approx(1.8, rel=1e-2)
    assert r2 > 0.99


def test_group_events_merges_consecutive_frames(signals):
    mask = np.array([0, 1, 1, 0, 0, 1, 0, 1, 1, 1], bool)
    assert signals.group_events(mask) == [(1, 2), (5, 5), (7, 9)]
    assert signals.group_events(mask, min_len=2) == [(1, 2), (7, 9)]


def test_steady_slice_trims_transients(signals):
    sl = signals.steady_slice(100, 300)
    assert (sl.start, sl.stop) == (130, 290)


def test_iou_ignores_unlabeled_pixels():
    gt = np.array([[0, 1], [2, 255]], np.uint8)
    pred = np.array([[0, 1], [2, 3]], np.uint8)
    iou = iou_from_confusion(confusion(gt, pred, 4))
    assert iou[1] == 1 and iou[2] == 1


def test_spatter_instance_matching():
    gt = np.zeros((40, 40), bool)
    pred = np.zeros((40, 40), bool)
    gt[5:8, 5:8] = True  # détectée (décalée d'1 px)
    pred[6:9, 6:9] = True
    gt[30:33, 30:33] = True  # manquée
    pred[20:23, 5:8] = True  # fausse alarme
    counts = instance_matches(gt, pred)
    assert counts == {"n_pred": 2, "tp_pred": 1, "n_gt": 2, "tp_gt": 1}
    assert f1(counts)["f1"] == pytest.approx(0.5)


def test_off_bounded_by_weld_front_arrival(signals):
    plasma = np.zeros(600)
    plasma[100:500] = 2000  # lueur résiduelle jusqu'à 500 alors que le cordon s'arrête vers 400
    front = np.full(600, np.nan)
    front[100:400] = np.linspace(40, 460, 300)
    front[400:] = 460
    on, off = signals.detect_on_off(plasma, fps=6000, front=front)
    assert abs(on - 100) <= 2
    assert 395 <= off <= 410


def test_group_events_debounce(signals):
    mask = np.array([1, 0, 1, 1, 0, 0, 0, 1], bool)
    assert signals.group_events(mask, max_gap=1) == [(0, 3), (7, 7)]
    assert signals.group_events(mask, max_gap=3) == [(0, 7)]
