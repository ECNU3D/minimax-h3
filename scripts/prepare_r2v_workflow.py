"""Adapt the native R2V template for two references on this RTX 5080."""
import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / ".venv-cu130/Lib/site-packages/comfyui_workflow_templates_json/templates/video_minimax_h3_r2v.json"
workflow = json.loads(source.read_text(encoding="utf-8"))
api = json.loads((ROOT / "workflows/h3_mario_castle_r2v_api.json").read_text(encoding="utf-8"))
name = "H3-5080-R2V-2Images-480p-10s"
workflow["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "local:minimax-h3:" + name))
workflow["nodes"] = [node for node in workflow["nodes"] if node["id"] not in (117, 140)]
positions = {
    137: [0, 0], 139: [0, 410], 138: [370, 0], 136: [820, 0],
    115: [370, 510], 132: [370, 730], 131: [370, 850], 146: [820, 460],
    92: [1300, 0], 116: [1300, 470],
    127: [0, 1050], 145: [0, 1200], 128: [0, 1350], 119: [0, 1520], 120: [0, 1650],
    141: [720, 1050], 143: [720, 1210], 144: [720, 1350], 142: [1040, 1210],
    129: [1380, 1000], 126: [1380, 1140], 123: [1380, 1250], 124: [1380, 1370],
    125: [1810, 1140], 122: [1810, 1380], 121: [1810, 1510], 130: [1810, 1640],
}
for node in workflow["nodes"]:
    node.pop("widgets_values_named", None)
    node["pos"] = positions[node["id"]]
    if node["id"] == 127:
        node["widgets_values"] = [api["1"]["inputs"]["unet_name"], "default"]
    elif node["id"] == 137:
        node["widgets_values"] = [api["20"]["inputs"]["image"], "image"]
        node["title"] = "Picture 1 | Mario character"
    elif node["id"] == 139:
        node["widgets_values"] = [api["21"]["inputs"]["image"], "image"]
        node["title"] = "Picture 2 | Castle object"
    elif node["id"] == 138:
        node["widgets_values"] = [api["5"]["inputs"]["prompt"]]
        node["size"] = [400, 450]
        node["title"] = "Prompt | <Picture 1> + <Picture 2>"
    elif node["id"] == 132:
        node["widgets_values"] = [10]
    elif node["id"] == 129:
        node["widgets_values"] = [20260910, "fixed"]
    elif node["id"] == 146:
        node["widgets_values"] = [True]
        node["title"] = "Turbo enabled | Ref2V 4-step LoRA"
    elif node["id"] == 92:
        node["widgets_values"] = ["video/H3_Mario_Castle_R2V", "mp4", "h264"]
        node["size"] = [600, 400]
    elif node["id"] == 116:
        node["size"] = [600, 400]
        node["widgets_values"] = ["# H3 全能参考：两图生成视频\n\n左侧 Picture 1 为角色，Picture 2 为城堡。两者作为独立参考输入，均不固定首尾帧。\n\n替换图片后，在提示词中用 <Picture 1>、<Picture 2> 指定每张图的用途。\n\n480p：16:9 / 0.4MP / 32 对齐 → 864×480。时长 10 秒 → 243 帧 / 24fps = 10.125 秒。\n\n已选择 Ref2VA FP8 专用模型、Ref2V Turbo 4 步 LoRA，ref_image_size=match。不要替换成 FL2VA 或 FL2V LoRA。\n\n底部是模型与采样节点。配置与排错见 docs/reference-to-video.md。"]
workflow["groups"] = []
workflow.setdefault("extra", {})["ds"] = {"scale": 0.7, "offset": [70, 100]}
for directory in (ROOT / "workflows", ROOT / "ComfyUI/user/default/workflows"):
    path = directory / f"{name}.json"
    path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)
