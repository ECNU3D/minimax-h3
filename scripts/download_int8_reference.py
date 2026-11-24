"""Download the official CUDA 13 Ref2VA INT8 model at the saved revision."""
import json
from download_models import ROOT, REPO, download

repo = json.loads((ROOT / 'docs/hf-r2v-repo.json').read_text(encoding='utf-8'))
tree = json.loads((ROOT / 'docs/hf-r2v-tree.json').read_text(encoding='utf-8'))
name = 'diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors'
item = next(x for x in tree if x['path'] == name)
item = dict(path=name, size=item['size'], sha256=item['lfs']['oid'])
manifest = dict(repo=REPO, revision=repo['sha'], files=[item])
(ROOT / 'docs/int8-reference-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
result = download(item, repo['sha'], 'http://127.0.0.1:7897')
(ROOT / 'docs/int8-reference-verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
