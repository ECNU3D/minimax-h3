"""Download the reviewed Klein models from pinned official repository metadata."""
import argparse
import concurrent.futures
import json
from download_models import ROOT, download

parser = argparse.ArgumentParser()
parser.add_argument('--proxy', default=None, help='Optional HTTP proxy, e.g. http://127.0.0.1:7897')
args = parser.parse_args()
catalog = json.loads((ROOT / 'docs/image-model-catalog.json').read_text(encoding='utf-8'))
specs = [
    ('black-forest-labs/FLUX.2-klein-4b-fp8', 'flux-2-klein-4b-fp8.safetensors', 'diffusion_models'),
    ('black-forest-labs/FLUX.2-klein-base-4b-fp8', 'flux-2-klein-base-4b-fp8.safetensors', 'diffusion_models'),
    ('Comfy-Org/vae-text-encorder-for-flux-klein-4b', 'split_files/text_encoders/qwen_3_4b.safetensors', 'text_encoders'),
    ('Comfy-Org/flux2-dev', 'split_files/vae/flux2-vae.safetensors', 'vae'),
]
manifest = []
for repo, source, folder in specs:
    entry = catalog[repo]
    file = next(x for x in entry['files'] if x['path'] == source)
    manifest.append(dict(repo=repo, revision=entry['revision'], source_path=source,
                         path=folder+'/'+source.rsplit('/',1)[-1], size=file['size'], sha256=file['lfs']['oid']))
(ROOT / 'docs/image-models-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    results = list(pool.map(lambda x: download(x, x['revision'], args.proxy, x['repo']), manifest))
(ROOT / 'docs/image-model-verification.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
