"""Validate installed SageAttention on this GPU before video inference."""
import json
import pathlib
import time
import importlib.metadata
import torch
from sageattention import sageattn

torch.manual_seed(20260913)
results = []
for dtype in (torch.float16, torch.bfloat16):
    q, k, v = [torch.randn(1, 56, 2048, 128, device='cuda', dtype=dtype) for _ in range(3)]
    start = time.perf_counter()
    actual = sageattn(q, k, v, tensor_layout='HND', is_causal=False, smooth_k=False)
    torch.cuda.synchronize()
    elapsed = time.perf_counter() - start
    expected = torch.nn.functional.scaled_dot_product_attention(q, k, v)
    similarity = torch.nn.functional.cosine_similarity(actual.float().flatten(), expected.float().flatten(), dim=0).item()
    finite = bool(actual.isfinite().all())
    results.append(dict(dtype=str(dtype), shape=list(actual.shape), finite=finite, cosine_similarity=similarity, first_call_seconds=elapsed))
    assert finite and similarity > 0.99, results[-1]
result = dict(torch=torch.__version__, cuda=torch.version.cuda, gpu=torch.cuda.get_device_name(),
              sageattention=importlib.metadata.version('sageattention'), triton=importlib.metadata.version('triton-windows'), tests=results)
path = pathlib.Path(__file__).resolve().parents[1] / 'docs/sage-validation.json'
path.write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
