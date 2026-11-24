"""Download only the three pinned official Qwen Image 2.1 test weights."""
import hashlib
import json
import pathlib
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUN = ROOT / 'runs/qwen21-20260921'
MODEL_ROOT = ROOT / 'tools/qwen21/models'
REVISION = 'ace0edeb3791a594ddfa36ed5f41a178a394e921'
FILES = [
    ('diffusion_models/qwen_image_2.1_int8_convrot.safetensors', 7256783064,
     'cb74113cb03faecd79611b01fd7fd642f0aa60d6f0b95086abee214d75eaa57d'),
    ('text_encoders/qwen3vl_8b_w4a8.safetensors', 6312105364,
     '7754425e55e7bea2bfde4dde59a4cc236cb44e5ee9c215ea66ef8d47012824eb'),
    ('vae/qwen_image_2.1_vae_bf16.safetensors', 675509688,
     'bb21f7473051e1ac368515dd3f2e15cd44d7a11748ee8823e1ddca3e4876b7c9'),
]


def download(spec):
    name, size, expected = spec
    dest = MODEL_ROOT / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix('.safetensors.part')
    url = f'https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/{REVISION}/{name}?download=true'
    if not dest.exists():
        session = requests.Session()
        session.trust_env = False
        for attempt in range(3):
            try:
                response = session.get(url, allow_redirects=False, timeout=20)
                response.raise_for_status()
                download_url = response.headers.get('Location', url)
                break
            except requests.RequestException:
                if attempt == 2:
                    raise
                time.sleep(2)
        command = [str(ROOT / 'tools/aria2-1.37.0-win-64bit-build1/aria2c.exe'),
                   '--no-conf=true', '--all-proxy=', '--continue=true', '--max-connection-per-server=8',
                   '--split=8', '--min-split-size=64M', '--file-allocation=none',
                   '--max-tries=5', '--retry-wait=3', '--connect-timeout=20', '--timeout=60',
                   '--auto-file-renaming=false', '--summary-interval=20', '--enable-color=false',
                   '--dir=' + str(dest.parent), '--out=' + partial.name, download_url]
        print('Downloading', name, flush=True)
        with (RUN / (dest.stem + '.download.log')).open('a') as log:
            for attempt in range(3):
                result = subprocess.run(command, stdout=log, stderr=log)
                if result.returncode == 0:
                    break
                if attempt == 2:
                    raise RuntimeError(f'Download failed; inspect {dest.stem}.download.log')
                time.sleep(2)
    candidate = dest if dest.exists() else partial
    if candidate.stat().st_size != size:
        raise ValueError(f'Incorrect size: {candidate}')
    with candidate.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual != expected:
        raise ValueError(f'SHA256 mismatch: {candidate}')
    if candidate == partial:
        partial.replace(dest)
    print('Verified', name, flush=True)
    return dict(path=str(dest), source_url=url, size=size, sha256=actual,
                revision=REVISION, verified_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'))


if __name__ == '__main__':
    RUN.mkdir(parents=True, exist_ok=True)
    manifest = dict(repo='Comfy-Org/Qwen-Image-2.1', provider='HuggingFace', revision=REVISION,
                    files=[dict(path=n, size=s, sha256=h) for n, s, h in FILES])
    (RUN / 'model-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(download, FILES))
    (RUN / 'model-verification.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
