"""Configuration pytest : accès aux scripts du pipeline, dont les noms commencent par un numéro."""

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))


def pipeline_module(name: str):
    """Les scripts du pipeline sont préfixés par un numéro : import par nom de fichier."""
    return importlib.import_module(name)


@pytest.fixture(scope="session")
def signals():
    return pipeline_module("07_signals")
