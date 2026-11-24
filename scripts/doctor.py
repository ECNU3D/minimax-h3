"""Read-only environment and model diagnostics. Does not send data online."""
import argparse
import hashlib
import importlib.metadata
import json
import pathlib
import platform
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hash", action="store_true", help="Read all model files and verify SHA256 (several minutes)")
    args = parser.parse_args()
    report = {"python": sys.version, "executable": sys.executable, "base_prefix": sys.base_prefix,
              "os": platform.platform(), "packages": {}, "models": []}
    for package in ("torch", "torchvision", "torchaudio", "comfy-kitchen", "comfy-aimdo", "transformers", "av", "comfyui-frontend-package", "sageattention", "triton-windows"):
        try:
            report["packages"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            report["packages"][package] = "MISSING"
    try:
        import torch
        report["cuda"] = {"runtime": torch.version.cuda, "available": torch.cuda.is_available()}
        if torch.cuda.is_available():
            report["cuda"].update(gpu=torch.cuda.get_device_name(), capability=torch.cuda.get_device_capability(),
                                  total_vram=torch.cuda.get_device_properties(0).total_memory)
            x = torch.ones((256, 256), dtype=torch.bfloat16, device="cuda")
            report["cuda"]["matmul_ok"] = bool(torch.isfinite(x @ x).all())
    except Exception as exc:
        report["cuda_error"] = repr(exc)
    report["nvidia_smi"] = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total,memory.used,temperature.gpu", "--format=csv"], capture_output=True, text=True).stdout.strip()
    manifest = json.loads((ROOT / "docs/models-manifest.json").read_text(encoding="utf-8"))
    reference_manifest = ROOT / "docs/reference-models-manifest.json"
    if reference_manifest.exists():
        manifest["files"].extend(json.loads(reference_manifest.read_text(encoding="utf-8"))["files"])
    int8_manifest = ROOT / "docs/int8-reference-manifest.json"
    if int8_manifest.exists():
        manifest["files"].extend(json.loads(int8_manifest.read_text(encoding="utf-8"))["files"])
    image_manifest = ROOT / "docs/image-models-manifest.json"
    if image_manifest.exists():
        manifest["files"].extend(json.loads(image_manifest.read_text(encoding="utf-8")))
    for item in manifest["files"]:
        path = ROOT / "ComfyUI/models" / item["path"]
        status = {"path": item["path"], "exists": path.exists()}
        if path.exists():
            status["size_ok"] = path.stat().st_size == item["size"]
            if args.hash:
                with path.open("rb") as stream:
                    status["sha256_ok"] = hashlib.file_digest(stream, "sha256").hexdigest() == item["sha256"]
        report["models"].append(status)
    try:
        with urllib.request.urlopen("http://127.0.0.1:8188/system_stats", timeout=5) as response:
            report["server"] = json.load(response)
    except Exception as exc:
        report["server"] = {"unavailable": str(exc)}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    (ROOT / "logs/doctor.json").write_text(text, encoding="utf-8")

if __name__ == "__main__":
    main()
