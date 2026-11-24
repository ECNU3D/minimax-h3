# Krea 2 RAW + Breast Size Slider 本地学习配置

适用本机：NVIDIA RTX 5080 16GB、当前可见系统内存约 31.1GiB（32GB 级别）、Windows 11。使用本项目现有 CUDA 13 环境和 ComfyUI 0.35.0。

## 打开与使用

1. 双击项目根目录 `start-krea2-study.cmd`，打开 `http://127.0.0.1:8188`。
2. 左侧“工作流” → `Krea2-Study` → 选择以下一个工作流。也可以把本目录的工作流 JSON 拖入 ComfyUI；不要拖入 `.api.json`。
3. 在 `06 | Prompt` 修改提示词，在 `05 | Breast slider / 0 = off` 修改 `strength_model`。
4. 保持固定 seed，先比较 `-1 / 0 / +1`；0 关闭 slider，负值减小、正值增大。默认样例是成年人日常服装目录摄影。
5. 点击“运行”。图片保存到 `ComfyUI/output/krea2-study/`，PNG 内保留生成参数和工作流。

| 文件 | 用途 | 默认设置 |
|---|---|---|
| `krea2_raw_slider_fast.json` | 快速预览，日常调提示词与 slider | RAW FP8 + 官方 rank-64 Turbo LoRA 强度 1.0；8 步、CFG 1、Euler/simple |
| `krea2_raw_slider_quality.json` | 纯 RAW 对照学习 | RAW FP8，不加 Turbo LoRA；52 步、ComfyUI CFG 4.5、Euler/simple |

两版均为 1024×1024、batch 1、seed 20260921。不要把纯 RAW 的步数/CFG 直接套在快速版上。`quality` 是纯 RAW 对照配置的文件名，不代表已证明其画质优于快速版。

## 选型理由

- RAW BF16 主模型约 26.3GB，超出本机显存；选 Comfy-Org 原生支持的 RAW FP8 scaled（约 13.14GB），保留硬件 FP8 路径和原生 LoRA 支持。
- 文本编码器选配套 `qwen3vl_4b_fp8_scaled.safetensors`（约 5.24GB）。原有 Klein 的 `qwen_3_4b` 不是这里需要的 Qwen3-VL，不能互换。
- VAE 使用官方配套 Qwen Image VAE。推理过程中由 ComfyUI 动态管理显存、顺序加载组件。所有模型不能同时完整常驻 16GB 显存。
- 额外提供官方 Turbo adapter（约 469MB），复用同一 RAW 主模型做 8 步预览，避免另下载一份大型 Turbo 主模型。
- slider 使用作者 Loraholic 的 **Krea-2_v2**，模型 ID 2540187、版本 ID 3131773。未混用同一页面上的 ZImageTurbo 版本；无需触发词。
- 全部节点是 ComfyUI 原生节点。未安装额外自定义节点、未修改 ComfyUI/KJNodes 源码、未升级现有 Torch 环境。

这是一项基于本机资源与可验证来源的配置选择，未对所有量化格式进行速度/画质排名。较高分辨率、批量与多个 LoRA 会增加显存压力；遇到不足时先保持 batch 1，再把分辨率降到 768×1024。

## 参数与局限

作者描述建议着装情况下 slider 范围约 -5 到 +8，但强度不是厘米或罩杯，不保证只改变局部。学习时从 -1 到 +1 开始，固定提示词、分辨率和 seed；同时观察脸部、姿势、衣料和整体比例是否漂移。

官方 Krea 原始代码的 guidance 公式是 `cond + guidance * (cond - uncond)`，ComfyUI 标准 CFG 是 `uncond + cfg * (cond - uncond)`。因此官方 RAW 示例的 3.5 对应这里的 ComfyUI 4.5。该工作流使用 ComfyUI 原生 Krea 的固定 sampling shift 1.15，而官方 RAW 代码采用随分辨率变化的调度；本配置不是原始代码逐像素复现。

原始官方模板另存于 `sources/official_image_krea2_turbo_t2i.json`，来源和本地模板校验值见 `sources/template-provenance.json`。当前工作流从该模板的加载—编码—采样—解码结构改编为平铺节点，替换 RAW 和 slider、取消提示词自动扩写，便于查看每个变量。

## 来源与校验

- [Comfy-Org Krea-2 模型仓库](https://huggingface.co/Comfy-Org/Krea-2)
- [官方 ComfyUI 模板说明](https://docs.comfy.org/tutorials/image/krea/krea-2)
- [Krea RAW 模型卡](https://huggingface.co/krea/Krea-2-Raw)
- [Krea 官方采样实现](https://github.com/krea-ai/krea-2/blob/main/sampling.py)
- [Loraholic slider 作者页面](https://civitai.com/models/2540187?modelVersionId=3131773)

`models-manifest.json` 固定模型 revision、Civitai version/file ID、文件大小与发布方 SHA256。实际下载后校验结果在 `model-verification.json`。Krea 模型适用发布方 Krea 2 Community License，slider 许可信息保留于 `sources/slider-model.json`。

作者站点的下载接口本次返回 401，因此 slider 从公开的 [Sentinel7/krea2 备份](https://huggingface.co/Sentinel7/krea2/tree/6fd28a000e144e827b20ea59b1a4f54bfc3d5ba3/2540187/3131773)取得。实际下载字节的 SHA256 为 `24c2acd5d3bf88920a084984099928c85ed17c985d914b8ceb19a1731aafd07f`，与作者 Civitai API 完全一致。该备份不是作者本人仓库；`slider-mirror-verification.json` 保存传输来源与复核记录，原始 manifest 中的作者哈希仍是校验依据。

恢复下载（项目根目录执行，代理端口按本机实际设置）：

```powershell
.venv-cu130/Scripts/python.exe scripts/download_krea2_models.py --proxy http://127.0.0.1:7897
```

运行单次图片验收：

```powershell
.venv-cu130/Scripts/python.exe scripts/verify_krea2_workflow.py --preset fast
.venv-cu130/Scripts/python.exe scripts/verify_krea2_workflow.py --preset quality
```

验收脚本在队列非空时不提交；单次记录 prompt、seed、尺寸、GPU 占用采样、服务器 history、输出 SHA256。记录位于 `runs/krea2-study-*`。执行成功与人工视觉接受分开记录。

当前部署与实际验收结果见 `validation.md`。

## 泳装对照测试

另提供 `krea2_raw_slider_swimwear_test.json`：30 岁成年模特、两件式泳装、768×1024、固定 seed，快速版参数。已实际比较 slider `-4 / 0 / +4`，可见丰满程度变化，也观察到脸部和腰线轻微漂移。三张原图、逐次耗时和结论见 [泳装对照测试](swimwear-comparison.md)。此工作流默认 +4，在第 05 节点直接修改强度即可继续比较。
