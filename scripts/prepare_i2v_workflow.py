"""Save a reusable editor workflow matching the tested Mario first-frame job."""
import json
import pathlib
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[1]
workflow = json.loads((ROOT / "workflows/H3-5080-balanced.json").read_text(encoding="utf-8"))
api = json.loads((ROOT / "workflows/h3_mario_i2v_api.json").read_text(encoding="utf-8"))
name = "H3-5080-I2V-480p-5s"
workflow["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "local:minimax-h3:" + name))
workflow["last_node_id"] = 142
workflow["last_link_id"] = 250
for node in workflow["nodes"]:
    node.pop("widgets_values_named", None)
    if node["id"] == 140:
        node["title"] = "H3 Image to Video | 480p / 5s / Turbo 8"
        node["widgets_values"][:5] = [api["5"]["inputs"]["prompt"], 864, 480, 5, 20260910]
        node["inputs"][0]["link"] = 250
        node["pos"] = [440, 0]
        node["order"] = 2
    elif node["id"] == 92:
        node["widgets_values"] = ["video/H3_Mario_I2V", "mp4", "h264"]
        node["pos"] = [1000, 0]
        node["order"] = 3
    elif node["id"] == 116:
        node["pos"] = [1000, 440]
        node["size"] = [500, 340]
        node["widgets_values"] = ["# 参考图生成视频\n\n1. 在 Load Reference Image 节点上传或选择图片。\n2. 修改 H3 中的动作提示词，再点击运行。\n3. 保持 864×480、5 秒、Turbo 开启、8 步，可复用本次配置。\n\n图片等比例缩放并用白色补边，连接到 first_frame，避免把竖图拉宽。\n\n如改分辨率，需同时修改补边节点和 H3 的宽高（32 对齐）。\n\n实际输出 124 帧 / 24fps ≈ 5.17 秒。视频保存在 ComfyUI/output/video。\n\n这是首帧图生视频，参考图会作为第一帧；不是任意多图参考。"]

def node(node_id, kind, pos, size, inputs, outputs, widgets, title, order):
    return {"id": node_id, "type": kind, "pos": pos, "size": size, "flags": {}, "order": order,
            "mode": 0, "inputs": inputs, "outputs": outputs, "properties": {"Node name for S&R": kind},
            "widgets_values": widgets, "title": title}

workflow["nodes"].extend([
    node(141, "LoadImage", [0, 0], [340, 400], [],
         [{"name": "IMAGE", "type": "IMAGE", "links": [249]}, {"name": "MASK", "type": "MASK", "links": None}],
         [api["17"]["inputs"]["image"], "image"], "Load Reference Image", 0),
    node(142, "ResizeAndPadImage", [0, 460], [340, 220],
         [{"name": "image", "type": "IMAGE", "link": 249}],
         [{"name": "IMAGE", "type": "IMAGE", "links": [250]}],
         [864, 480, "white", "lanczos"], "Fit Reference | Preserve Aspect Ratio", 1),
])
workflow["links"].extend([[249, 141, 0, 142, 0, "IMAGE"], [250, 142, 0, 140, 0, "IMAGE"]])
workflow.setdefault("extra", {})["ds"] = {"scale": 0.7, "offset": [70, 60]}
for folder in [ROOT / "workflows", ROOT / "ComfyUI/user/default/workflows"]:
    path = folder / f"{name}.json"
    path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)
