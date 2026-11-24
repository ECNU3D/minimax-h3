"""Download pinned Krea 2 assets and verify every file against publisher SHA256."""
import argparse
import concurrent.futures
import hashlib
import json
import pathlib
import requests
from download_models import ROOT, download


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--proxy', default=None)
    args = parser.parse_args()
    bundle = ROOT / 'workflows/krea2-raw-slider'
    manifest = json.loads((bundle / 'models-manifest.json').read_text(encoding='utf-8'))
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(download, item, item['revision'], args.proxy, item['repo'])
                for item in manifest if item['provider'] == 'huggingface']
        for job in concurrent.futures.as_completed(jobs):
            results.append(job.result())
            (bundle / 'model-verification.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    for item in manifest:
        if item['provider'] != 'civitai':
            continue
        dest = ROOT / 'ComfyUI/models' / item['path']
        candidate = dest if dest.exists() else dest.with_suffix('.safetensors.part')
        if not dest.exists() and item.get('verified_mirror'):
            mirror = item['verified_mirror']
            if mirror['sha256'] != item['sha256'] or mirror['size'] != item['size']:
                raise RuntimeError('Mirror does not match publisher manifest')
            download(mirror, mirror['revision'], args.proxy, mirror['repo'])
            candidate = dest
        if not dest.exists():
            proxies = {'http': args.proxy, 'https': args.proxy} if args.proxy else None
            with requests.get(item['url'], proxies=proxies, stream=True, timeout=(30, 90)) as response:
                response.raise_for_status()
                with candidate.open('wb') as stream:
                    for chunk in response.iter_content(1024 * 1024):
                        stream.write(chunk)
        with candidate.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if candidate.stat().st_size != item['size'] or digest != item['sha256']:
            raise RuntimeError(f'Slider verification failed: {candidate}')
        if candidate != dest:
            candidate.replace(dest)
        results.append({**item, 'verified_sha256': digest})
        print(f'OK {dest.name} sha256={digest}', flush=True)
    (bundle / 'model-verification.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print('ALL KREA2 MODELS VERIFIED', flush=True)


if __name__ == '__main__':
    main()
