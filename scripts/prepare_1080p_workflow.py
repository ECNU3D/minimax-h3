"""Save the 10-second 1080p R2V test as a reusable editor workflow."""
import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
workflow = json.loads((ROOT / "workflows/H3-5080-R2V-2Images-480p-10s.json").read_text(encoding="utf-8"))
name = "H3-5080-R2V-1080p-10s-48GB"
workflow["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "local:minimax-h3:" + name))
removed_links = {link[0] for link in workflow["links"] if link[1] == 115}
workflow["links"] = [link for link in workflow["links"] if link[0] not in removed_links]
workflow["nodes"] = [node for node in workflow["nodes"] if node["id"] != 115]
new_node_id = max(node["id"] for node in workflow["nodes"]) + 1
new_link_id = max(link[0] for link in workflow["links"]) + 1
image_link = next(link for link in workflow["links"] if link[1] == 122 and link[3] == 130)
old_image_link_id = image_link[0]
image_link[1] = new_node_id
workflow["links"].append([new_link_id, 122, 0, new_node_id, 0, "IMAGE"])
for node in workflow["nodes"]:
    node.pop("widgets_values_named", None)
    for value in node.get("inputs", []):
        if value.get("link") in removed_links:
            value["link"] = None
    if node["id"] == 136:
        node["widgets_values"][1:3] = [1920, 1088]
        node["title"] = "R2V | Generate 1920x1088, crop to 1080p"
    elif node["id"] == 122:
        node["outputs"][0]["links"] = [new_link_id]
    elif node["id"] == 92:
        node["widgets_values"] = ["video/H3_R2V_1080p_10s", "mp4", "h264"]
    elif node["id"] == 116:
        node["widgets_values"] = ["# 1080p / 10 秒 / 双图参考\n\n硬件：RTX 5080 16GB，系统内存 48GB。\n\nPicture 1 = Mario；Picture 2 = 城堡。修改图片和提示词后运行。\n\nH3 生成尺寸 1920×1088；编码前上下各裁 4 像素，输出 1920×1080。没有低清放大。\n\n10 秒对应 243 帧 / 24fps = 10.125 秒。Ref2VA FP8 + Ref2V Turbo 4 步。\n\n这是高负载配置，运行状态、耗时与限制见 docs/test-1080p-48gb.md。"]
workflow["nodes"].append({
    "id": new_node_id, "type": "ImageCrop", "pos": [2150, 1370], "size": [280, 190],
    "flags": {}, "order": 30, "mode": 0,
    "inputs": [{"name": "image", "type": "IMAGE", "link": new_link_id}],
    "outputs": [{"name": "IMAGE", "type": "IMAGE", "links": [old_image_link_id]}],
    "properties": {"Node name for S&R": "ImageCrop"},
    "widgets_values": [1920, 1080, 0, 4], "title": "Exact 1080p | Crop 4px top/bottom",
})
workflow["last_node_id"] = new_node_id
workflow["last_link_id"] = new_link_id
for directory in (ROOT / "workflows", ROOT / "ComfyUI/user/default/workflows"):
    path = directory / f"{name}.json"
    path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)
