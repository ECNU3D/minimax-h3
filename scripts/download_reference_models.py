"""Download and hash-check the separate Ref2VA weights using saved official metadata."""
import argparse
import concurrent.futures
import json
from download_models import ROOT, REPO, download

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--proxy")
args = parser.parse_args()
repo = json.loads((ROOT / "docs/hf-r2v-repo.json").read_text(encoding="utf-8"))
tree = json.loads((ROOT / "docs/hf-r2v-tree.json").read_text(encoding="utf-8"))
paths = {
    "diffusion_models/minimax_h3_ref2va_pruned_fp8_scaled.safetensors",
    "loras/minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors",
}
files = [{"path": item["path"], "size": item["size"], "sha256": item["lfs"]["oid"]}
         for item in tree if item["path"] in paths]
if len(files) != 2:
    raise RuntimeError("Official model metadata is incomplete")
manifest = {"repo": REPO, "revision": repo["sha"], "files": files}
(ROOT / "docs/reference-models-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    results = list(pool.map(lambda item: download(item, manifest["revision"], args.proxy), files))
(ROOT / "docs/reference-model-verification.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
print("REFERENCE MODELS VERIFIED", flush=True)
