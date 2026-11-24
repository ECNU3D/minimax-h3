"""Adapt the official ComfyUI template to this machine's installed weights."""
import json
import pathlib
import copy
import uuid

from generate import DEFAULT_PROMPT

ROOT = pathlib.Path(__file__).resolve().parents[1]
source = (ROOT / "workflows/official_t2v.json").read_text(encoding="utf-8")
source = source.replace("minimax_h3_fl2va_pruned_int8_convrot.safetensors", "minimax_h3_fl2va_pruned_fp8_scaled.safetensors")
workflow = json.loads(source)
workflow["nodes"] = [n for n in workflow["nodes"] if n["id"] not in (115, 117, 118)]
removed_links = {link[0] for link in workflow["links"] if link[1] == 115}
workflow["links"] = [link for link in workflow["links"] if link[0] not in removed_links]
for node in workflow["nodes"]:
    for value in node.get("inputs", []):
        if value.get("link") in removed_links:
            value["link"] = None
    if node["id"] == 140:
        node["widgets_values"][:5] = [DEFAULT_PROMPT, 640, 384, 5, 20260910]
        node["widgets_values"][9] = True
        node["title"] = "MiniMax H3 | RTX 5080 local preview"
        node["pos"] = [40, 0]
    elif node["id"] == 92:
        node["widgets_values"] = ["video/H3_5080", "mp4", "h264"]
        node["pos"] = [730, 0]
        node["size"] = [500, 350]
    elif node["id"] == 116:
        node["widgets_values"] = ["# MiniMax H3 本地生成\n\nRTX 5080 16GB / 32GB 内存实测通过。\n\n左侧修改提示词、宽高、时长和种子。保留 Turbo 8 步，点击运行。输出包含原生双声道音轨。\n\n640×384：服务端约 61 秒；864×480：约 93 秒。均为输入 5 秒、实际 124 帧。\n\n文件保存在 ComfyUI/output/video。排错和维护请阅读项目 README.md。"]
        node["pos"] = [730, 440]
        node["size"] = [500, 280]
workflow.setdefault("extra", {})["ds"] = {"scale": 0.8, "offset": [100, 150]}
user_dir = ROOT / "ComfyUI/user/default/workflows"
user_dir.mkdir(parents=True, exist_ok=True)
for name, width, height in [("H3-5080", 640, 384), ("H3-5080-balanced", 864, 480)]:
    output = copy.deepcopy(workflow)
    output["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "local:minimax-h3:" + name))
    for node in output["nodes"]:
        if node["id"] == 140:
            node["widgets_values"][1:3] = [width, height]
        elif node["id"] == 92:
            node["widgets_values"][0] = "video/" + name
    path = ROOT / "workflows" / (name + ".json")
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    (user_dir / path.name).write_bytes(path.read_bytes())
    print(path)
