import os
import sys
from pathlib import Path

import pytest

TRAINING = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRAINING))
sys.path.insert(0, str(TRAINING.parent / "apps" / "api"))  # `app` before ruff-sorted imports


@pytest.fixture(autouse=True)
def _runs_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never write test metadata into training/runs/."""
    monkeypatch.setenv("SQM_RUNS_DIR", str(tmp_path / "runs"))
    import common

    monkeypatch.setattr(common, "RUNS", tmp_path / "runs")
    os.environ.setdefault("ENV", "test")
