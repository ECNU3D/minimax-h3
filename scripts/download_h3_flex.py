"""Download only the pinned official Comfy Ref2VA Flex adapter; verify before install."""
import argparse
import hashlib
import json
import time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proxy')
    parser.add_argument('--aria2', action='store_true', help='Use the project resumable multi-connection downloader')
    args = parser.parse_args()
    manifest = json.loads((ROOT/'docs/h3-flex-models-manifest.json').read_text(encoding='utf-8'))
    results = []
    for item in manifest['files']:
        if args.aria2:
            from download_models import download
            results.append(download(item, manifest['revision'], args.proxy, manifest['repo']))
            continue
        dest = ROOT/'ComfyUI/models'/item['path']
        dest.parent.mkdir(parents=True, exist_ok=True)
        partial = dest.with_suffix(dest.suffix+'.requests.part')
        url = f"https://huggingface.co/{manifest['repo']}/resolve/{manifest['revision']}/{item['source_path']}?download=true"
        candidate = dest
        if not dest.exists():
            candidate = partial
            offset = partial.stat().st_size if partial.exists() else 0
            session = requests.Session(); session.trust_env = False
            with session.get(url, stream=True, timeout=(30,120),
                             proxies={'https':args.proxy} if args.proxy else {},
                             headers={'Range':f'bytes={offset}-'} if offset else {}) as response:
                response.raise_for_status()
                if offset and response.status_code != 206: offset = 0
                downloaded = offset; notice = time.monotonic()
                with partial.open('ab' if offset else 'wb') as out:
                    for chunk in response.iter_content(8*1024*1024):
                        out.write(chunk); downloaded += len(chunk)
                        if time.monotonic()-notice >= 15:
                            print(f'DOWNLOAD {downloaded/item["size"]:.1%} ({downloaded/1e9:.2f} GB)',flush=True)
                            notice = time.monotonic()
        with candidate.open('rb') as stream:
            actual = hashlib.file_digest(stream,'sha256').hexdigest()
        if candidate.stat().st_size != item['size'] or actual != item['sha256']:
            raise RuntimeError(f'Size/SHA256 mismatch; file preserved: {candidate}')
        if candidate != dest: candidate.replace(dest)
        results.append({**item,'verified_sha256':actual,'repo':manifest['repo'],
                        'revision':manifest['revision'],'verified_at':time.strftime('%Y-%m-%dT%H:%M:%S%z')})
        print('VERIFIED '+dest.name+' '+actual,flush=True)
    (ROOT/'docs/h3-flex-model-verification.json').write_text(json.dumps(results,indent=2),encoding='utf-8')


if __name__ == '__main__': main()
