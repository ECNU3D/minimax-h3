"""Save the H3 low-memory experiment as an editor workflow."""
import argparse
import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--int8', action='store_true')
parser.add_argument('--memory-efficient-sage', action='store_true')
args = parser.parse_args()
w = json.loads((ROOT / 'workflows/H3-5080-R2V-1080p-10s-48GB.json').read_text(encoding='utf-8'))
name = 'H3-5080-R2V-1080p-10s-Sage-KJ' + ('-INT8' if args.int8 else '')
w['id'] = str(uuid.uuid5(uuid.NAMESPACE_URL, 'local:minimax-h3:' + name))
max_node = max(n['id'] for n in w['nodes'])
max_link = max(l[0] for l in w['links'])
head, ffn = max_node + 1, max_node + 2
first, second = max_link + 1, max_link + 2
edge = next(l for l in w['links'] if l[3] == 126 and l[-1] == 'MODEL')
old_id, source_id, source_slot = edge[:3]
edge[1:3] = [ffn, 0]
w['links'].extend([[first, source_id, source_slot, head, 0, 'MODEL'], [second, head, 0, ffn, 0, 'MODEL']])
for n in w['nodes']:
    if n['id'] == source_id:
        n['outputs'][source_slot]['links'] = [first if x == old_id else x for x in n['outputs'][source_slot]['links']]
    if n['type'] == 'UNETLoader' and args.int8:
        n['widgets_values'][0] = n['widgets_values'][0].replace('fp8_scaled', 'int8_convrot')
    if n['type'] == 'SaveVideo':
        n['widgets_values'][0] = 'video/' + name
    if n['type'] == 'MarkdownNote':
        n['widgets_values'] = ['# SageAttention / KJ H3 1080p 实验\n\nMario + Castle，全能参考，243 帧 / 24fps = 10.125 秒。\n\n启动：start.ps1 -Cuda13 -SageAttention -KJNodes -VramHeadroom 4\n\n注意力 4 组，前馈 8 块，完整时间序列。\n\n生成 1920×1088 后仅裁掉上下 4 像素。\n\n运行结果、维护与限制见 docs/test-1080p-48gb.md。']
for nid, kind, in_link, out_link, widgets, pos in [
    (head, 'MiniMaxLowVRAMAttention', first, second, [4], [1650, 1670]),
    (ffn, 'MiniMaxChunkFeedForward', second, old_id, [8, 4096], [2000, 1670]),
]:
    w['nodes'].append(dict(id=nid, type=kind, pos=pos, size=[310, 140], flags={}, order=31 + nid - head, mode=0,
                           inputs=[dict(name='model', type='MODEL', link=in_link)],
                           outputs=[dict(name='model', type='MODEL', links=[out_link])],
                           properties={'Node name for S&R': kind}, widgets_values=widgets))
w['last_node_id'], w['last_link_id'] = ffn, second
if args.memory_efficient_sage:
    sage_id, sage_link = ffn + 1, second + 1
    first_edge = next(l for l in w['links'] if l[0] == first)
    first_edge[1:3] = [sage_id, 0]
    w['links'].append([sage_link, source_id, source_slot, sage_id, 0, 'MODEL'])
    for n in w['nodes']:
        if n['id'] == source_id:
            n['outputs'][source_slot]['links'] = [sage_link if x == first else x for x in n['outputs'][source_slot]['links']]
        if n['type'] == 'MarkdownNote':
            n['widgets_values'][0] = n['widgets_values'][0].replace('-VramHeadroom 4', '-VramHeadroom 8') + '\n\n启用 H3 专用 Mem Eff Sage Attention Patch。'
    w['nodes'].append(dict(id=sage_id, type='MiniMaxH3MemoryEfficientSageAttentionPatch', pos=[1280, 1670], size=[330, 80],
        flags={}, order=30, mode=0, inputs=[dict(name='model', type='MODEL', link=sage_link)],
        outputs=[dict(name='model', type='MODEL', links=[first])],
        properties={'Node name for S&R': 'MiniMaxH3MemoryEfficientSageAttentionPatch'}, widgets_values=[]))
    w['last_node_id'], w['last_link_id'] = sage_id, sage_link
for folder in [ROOT / 'workflows', ROOT / 'ComfyUI/user/default/workflows']:
    path = folder / (name + '.json')
    path.write_text(json.dumps(w, ensure_ascii=False, indent=2), encoding='utf-8')
    print(path)
