"""Download the pinned official 768p Ref2V LoRA, verifying size and SHA256."""
import argparse
import json
import requests
from download_models import ROOT, download

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proxy')
    parser.add_argument('--python-download', action='store_true', help='Use requests when Windows aria2 TLS is unavailable')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'docs/h3-768p-models-manifest.json').read_text(encoding='utf-8'))
    if args.python_download:
        for item in manifest['files']:
            dest = ROOT / 'ComfyUI/models' / item['path']
            if dest.exists():
                continue
            partial = dest.with_suffix('.requests.part')
            offset = partial.stat().st_size if partial.exists() else 0
            url = f"https://huggingface.co/{manifest['repo']}/resolve/{manifest['revision']}/{item['source_path']}?download=true"
            session = requests.Session()
            session.trust_env = False
            with session.get(url, stream=True, timeout=(30, 120),
                             proxies={'https': args.proxy} if args.proxy else {},
                             headers={'Range': f'bytes={offset}-'} if offset else {}) as response:
                response.raise_for_status()
                if offset and response.status_code != 206:
                    offset = 0
                with partial.open('ab' if offset else 'wb') as stream:
                    for chunk in response.iter_content(8 * 1024 * 1024):
                        stream.write(chunk)
            import hashlib
            with partial.open('rb') as stream:
                actual = hashlib.file_digest(stream, 'sha256').hexdigest()
            if partial.stat().st_size != item['size'] or actual != item['sha256']:
                raise RuntimeError('Official download size/SHA256 mismatch; partial preserved')
            partial.replace(dest)
    results = [download(item, manifest['revision'], args.proxy, manifest['repo']) for item in manifest['files']]
    (ROOT / 'docs/h3-768p-model-verification.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
