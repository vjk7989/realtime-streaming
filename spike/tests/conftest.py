"""Shared fixtures for the Phase 0 spike tests. No network, no llama.cpp."""
import sys
from pathlib import Path

import pytest
import yaml

SPIKE_DIR = Path(__file__).resolve().parents[1]
if str(SPIKE_DIR) not in sys.path:
    sys.path.insert(0, str(SPIKE_DIR))

MODELS_YAML = SPIKE_DIR / "models.yaml"
ALLOWED_MODES = {"text", "vision", "asr", "tts", "d1"}
ROW_FIELDS = {
    "model", "mode", "status", "runs", "tok_s", "ttft_ms", "ttfa_ms",
    "peak_rss_mb", "wall_s", "detail", "llama_tag",
}
STATUSES = {"ok", "unsupported", "oom", "timeout", "missing_file", "error"}


@pytest.fixture(scope="session")
def models_doc():
    """The raw parsed spike/models.yaml."""
    with open(MODELS_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def models(models_doc):
    return models_doc["models"]


def first_model(models, pred):
    """First model satisfying pred, or skip the test if the yaml has none."""
    for m in models:
        if pred(m):
            return m
    pytest.skip("no model in models.yaml matches this test's needs")
