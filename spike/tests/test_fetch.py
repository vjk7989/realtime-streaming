"""models.yaml contract checks and fetch.py tests (no network)."""
import re

from conftest import ALLOWED_MODES

ID_RE = re.compile(r"^[a-z0-9-]+$")
NEEDS_MMPROJ = {"vision", "asr", "tts", "d1"}


def test_llama_tag_pinned(models_doc):
    assert models_doc.get("llama_tag") == "b11960"


def test_models_nonempty_list(models):
    assert isinstance(models, list) and models


def test_ids_unique_and_well_formed(models):
    ids = [m["id"] for m in models]
    assert len(ids) == len(set(ids)), "duplicate ids"
    bad = [i for i in ids if not ID_RE.match(i)]
    assert not bad, f"ids must match [a-z0-9-]+ (ADR 0003): {bad}"


def test_required_fields(models):
    for m in models:
        for key in ("repo", "file", "modes"):
            assert m.get(key), f"{m.get('id')}: missing {key}"
        assert m["file"].endswith(".gguf")


def test_modes_subset_of_allowed(models):
    for m in models:
        assert isinstance(m["modes"], list) and m["modes"], m["id"]
        assert set(m["modes"]) <= ALLOWED_MODES, m["id"]
        assert len(m["modes"]) == len(set(m["modes"])), f"{m['id']}: duplicate modes"


def test_multimodal_models_have_mmproj(models):
    for m in models:
        if set(m["modes"]) & NEEDS_MMPROJ:
            assert m.get("mmproj"), f"{m['id']} uses {m['modes']} but has no mmproj"


def test_text_only_model_has_no_mmproj(models):
    text_only = [m for m in models if m["modes"] == ["text"]]
    assert text_only, "expected a text-only model (text-1-7b)"
    assert all(not m.get("mmproj") for m in text_only)


def test_server_args_is_list_of_strings(models):
    for m in models:
        if "server_args" in m:
            assert all(isinstance(a, str) for a in m["server_args"]), m["id"]


# ---------------------------------------------------------------- fetch.py
import hashlib
import json
from collections import namedtuple
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from huggingface_hub.errors import EntryNotFoundError, RepositoryNotFoundError

import fetch
from conftest import MODELS_YAML, first_model

DiskUsage = namedtuple("DiskUsage", "total used free")
PAYLOAD = b"fake gguf bytes"
GOOD_SHA = hashlib.sha256(PAYLOAD).hexdigest()
PLENTY = DiskUsage(10**13, 0, 10**13)


class FakeHF:
    """Stands in for HfApi + hf_hub_download. Configure, then install()."""

    def __init__(self, monkeypatch, sha=GOOD_SHA, size=len(PAYLOAD)):
        self.sha, self.size = sha, size
        self.info_error = None      # exception for get_paths_info to raise
        self.omit = set()           # paths get_paths_info leaves out
        self.downloads = []
        hf = self

        class Api:
            def get_paths_info(self, repo_id, paths, **kw):
                if hf.info_error:
                    raise hf.info_error
                if isinstance(paths, str):
                    paths = [paths]
                return [SimpleNamespace(path=p, size=hf.size,
                                        lfs=SimpleNamespace(size=hf.size, sha256=hf.sha))
                        for p in paths if p not in hf.omit]

        def download(repo_id, filename, local_dir=None, **kw):
            hf.downloads.append(filename)
            out = fetch.os.path.join(local_dir, filename)
            with open(out, "wb") as f:
                f.write(PAYLOAD)
            return out

        monkeypatch.setattr(fetch, "HfApi", Api)
        monkeypatch.setattr(fetch, "hf_hub_download", download)


@pytest.fixture
def hf(monkeypatch):
    monkeypatch.setattr(fetch.shutil, "disk_usage", lambda p: PLENTY)
    return FakeHF(monkeypatch)


def run(model_id, dest):
    return fetch.main([model_id, "--dest", str(dest)])


def with_mmproj(models):
    return first_model(models, lambda m: m.get("mmproj"))


def without_mmproj(models):
    return first_model(models, lambda m: not m.get("mmproj"))


# -- helpers

def test_sha256_file_known_values(tmp_path):
    empty, abc = tmp_path / "empty", tmp_path / "abc"
    empty.write_bytes(b"")
    abc.write_bytes(b"abc")
    assert fetch.sha256_file(empty) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert fetch.sha256_file(abc) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_sha256_file_multi_chunk(tmp_path):
    data = bytes(range(256)) * 9000  # > 2 MiB, crosses chunk boundaries
    p = tmp_path / "big"
    p.write_bytes(data)
    assert fetch.sha256_file(p) == hashlib.sha256(data).hexdigest()


def test_load_and_find_model(models):
    loaded = fetch.load_models(MODELS_YAML)
    first = models[0]["id"]
    assert fetch.find_model(loaded, first)["id"] == first
    assert fetch.find_model(loaded, "no-such-model") is None


@pytest.mark.parametrize("free,ok", [(1199, False), (1200, True), (10**9, True)])
def test_check_disk_threshold(monkeypatch, tmp_path, free, ok):
    monkeypatch.setattr(fetch.shutil, "disk_usage", lambda p: DiskUsage(10**9, 0, free))
    assert bool(fetch.check_disk(str(tmp_path), 1000)) is ok


# -- CLI exit codes

def test_unknown_id_exit_4(hf, tmp_path):
    assert run("no-such-model", tmp_path) == 4
    assert hf.downloads == []


def hf_error(cls, msg):
    try:
        return cls(msg, response=MagicMock(status_code=404, headers={}))
    except TypeError:  # older huggingface_hub signatures
        return cls(msg)


@pytest.mark.parametrize("cls", [RepositoryNotFoundError, EntryNotFoundError])
def test_hf_not_found_exit_4(hf, models, tmp_path, cls):
    hf.info_error = hf_error(cls, "404 Not Found")
    assert run(models[0]["id"], tmp_path) == 4
    assert hf.downloads == []


def test_file_missing_from_paths_info_exit_4(hf, models, tmp_path):
    m = with_mmproj(models)
    hf.omit = {m["mmproj"]}
    assert run(m["id"], tmp_path) == 4
    assert hf.downloads == []


def test_insufficient_disk_exit_3_without_download(hf, monkeypatch, models, tmp_path):
    hf.size = 10**9
    monkeypatch.setattr(fetch.shutil, "disk_usage",
                        lambda p: DiskUsage(10**12, 0, int(hf.size * 1.2) - 1))
    assert run(without_mmproj(models)["id"], tmp_path) == 3
    assert hf.downloads == []


def test_sha_mismatch_exit_2_and_file_deleted(hf, models, tmp_path):
    hf.sha = "0" * 64
    m = models[0]
    assert run(m["id"], tmp_path) == 2
    assert not list(tmp_path.rglob(m["file"])), "mismatched file must be deleted"


def test_success_with_mmproj_prints_json(hf, models, tmp_path, capsys):
    m = with_mmproj(models)
    dest = tmp_path / "new" / "dir"  # --dest is auto-created
    assert run(m["id"], dest) == 0
    line = capsys.readouterr().out.strip().splitlines()[-1]
    out = json.loads(line)
    assert set(out) == {"id", "model_path", "mmproj_path"}
    assert out["id"] == m["id"]
    assert fetch.os.path.basename(out["model_path"]) == m["file"]
    assert fetch.os.path.basename(out["mmproj_path"]) == m["mmproj"]
    assert fetch.os.path.isfile(out["model_path"]) and fetch.os.path.isfile(out["mmproj_path"])


def test_success_without_mmproj_gives_null(hf, models, tmp_path, capsys):
    m = without_mmproj(models)
    assert run(m["id"], tmp_path) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["mmproj_path"] is None
    assert hf.downloads == [m["file"]]
