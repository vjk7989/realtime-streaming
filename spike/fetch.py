"""Download and verify one model from spike/models.yaml (see docs/adr/0003)."""
import argparse
import hashlib
import json
import os
import shutil
import sys

import yaml
from huggingface_hub import HfApi, hf_hub_download
from huggingface_hub.utils import EntryNotFoundError, RepositoryNotFoundError

DEFAULT_MODELS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models.yaml")
CHUNK = 1024 * 1024


def load_models(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["models"]


def find_model(models, model_id):
    return next((m for m in models if m["id"] == model_id), None)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def check_disk(dest, needed_bytes):
    return shutil.disk_usage(dest).free >= needed_bytes * 1.2


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("id")
    p.add_argument("--dest", required=True)
    p.add_argument("--models", default=DEFAULT_MODELS)
    args = p.parse_args(argv)

    model = find_model(load_models(args.models), args.id)
    if model is None:
        print(f"unknown id: {args.id}", file=sys.stderr)
        return 4

    files = [model["file"]] + ([model["mmproj"]] if model.get("mmproj") else [])
    try:
        infos = HfApi().get_paths_info(model["repo"], files, expand=True)
    except (RepositoryNotFoundError, EntryNotFoundError) as e:
        print(f"not found on HF: {e}", file=sys.stderr)
        return 4
    lfs = {i.path: i.lfs for i in infos if getattr(i, "lfs", None)}
    missing = [f for f in files if f not in lfs]
    if missing:
        print(f"not found on HF: {model['repo']}/{missing}", file=sys.stderr)
        return 4

    os.makedirs(args.dest, exist_ok=True)
    needed = sum(lfs[f].size for f in files)
    if not check_disk(args.dest, needed):
        print(f"not enough disk in {args.dest}: need {needed} x 1.2", file=sys.stderr)
        return 3

    paths = []
    for f in files:
        try:
            path = hf_hub_download(model["repo"], f, local_dir=args.dest)
        except (RepositoryNotFoundError, EntryNotFoundError) as e:
            print(f"not found on HF: {e}", file=sys.stderr)
            return 4
        if sha256_file(path) != lfs[f].sha256:
            os.remove(path)
            print(f"sha256 mismatch: {f}", file=sys.stderr)
            return 2
        paths.append(path)

    print(json.dumps({
        "id": model["id"],
        "model_path": paths[0],
        "mmproj_path": paths[1] if len(paths) > 1 else None,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
