"""Download pinned H3 artifacts with resumable files and SHA256 verification."""
import concurrent.futures
import hashlib
import json
import pathlib
import subprocess
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO = "Comfy-Org/MiniMax-H3"
FILES = [
    "diffusion_models/minimax_h3_fl2va_pruned_fp8_scaled.safetensors",
    "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
    "vae/minimax_h3_video_vae_fp16.safetensors",
    "vae/minimax_h3_audio_vae_fp32.safetensors",
    "loras/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
]

def get_json(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)

def download(item, revision, proxy=None, repo=REPO):
    dest = ROOT / "ComfyUI/models" / item["path"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".part")
    url = f"https://huggingface.co/{repo}/resolve/{revision}/{item.get('source_path', item['path'])}?download=true"
    if not dest.exists():
        logpath = ROOT / "logs" / (dest.stem + ".download.log")
        print(f"DOWNLOAD {item['path']} ({item['size'] / 1e9:.2f} GB)", flush=True)
        with logpath.open("a") as log:
            aria = ROOT / "tools/aria2-1.37.0-win-64bit-build1/aria2c.exe"
            if aria.exists():
                command = [str(aria), "--no-conf=true", "--continue=true", "--max-connection-per-server=8",
                           "--split=8", "--min-split-size=64M", "--file-allocation=none", "--max-tries=12",
                           "--retry-wait=5", "--connect-timeout=30", "--timeout=120", "--auto-file-renaming=false",
                           "--summary-interval=30", "--console-log-level=warn", "--enable-color=false",
                           "--dir=" + str(partial.parent), "--out=" + partial.name, url]
            else:
                if partial.with_suffix(partial.suffix + ".aria2").exists():
                    raise RuntimeError("aria2 is required to resume this segmented download")
                command = ["curl.exe", "-L", "--fail", "--retry", "12", "--retry-delay", "5",
                           "--connect-timeout", "30", "--speed-limit", "1024", "--speed-time", "120",
                           "-C", "-", "-o", str(partial), url]
            if proxy:
                command[1:1] = ["--all-proxy=" + proxy] if aria.exists() else ["--proxy", proxy]
            subprocess.run(command, stdout=log, stderr=log, check=True)
        if partial.stat().st_size != item["size"]:
            raise RuntimeError(f"Wrong size: {partial}")
        candidate = partial
    else:
        candidate = dest
    print(f"VERIFY {dest.name}", flush=True)
    with candidate.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != item["sha256"]:
        raise RuntimeError(f"SHA256 mismatch, keep file for inspection: {candidate}")
    if candidate == partial:
        partial.replace(dest)
    print(f"OK {dest.name} sha256={digest}", flush=True)
    return {**item, "verified_sha256": digest, "verified_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}

def main():
    manifest_path = ROOT / "docs/models-manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        revision = get_json(f"https://huggingface.co/api/models/{REPO}")["sha"]
        tree = get_json(f"https://huggingface.co/api/models/{REPO}/tree/{revision}?recursive=true")
        files = [{"path": x["path"], "size": x["size"], "sha256": x["lfs"]["oid"]}
                 for x in tree if x["path"] in FILES]
        if len(files) != len(FILES):
            raise RuntimeError("Model catalog incomplete")
        manifest = {"repo": REPO, "revision": revision, "files": files}
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda x: download(x, manifest["revision"]), manifest["files"]))
    (ROOT / "docs/model-verification.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("ALL MODELS VERIFIED", flush=True)

if __name__ == "__main__":
    main()
