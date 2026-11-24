# Krea 2 人物参考换装与局部体型微调

已在 RTX 5080 16GB / 32GB RAM 上完成实际图片测试，日期 2026-09-21。推荐分两步：先换装，再局部微调。两张工作流都在 ComfyUI → 工作流 → `Krea2-Study` 中。

## 1. 参考图换装

打开 `krea2_reference_outfit_slider.json`。

1. 在「① 上传人物参考图」上传一张清晰、脸部完整、穿着衣服的人像。
2. 在「② 换装指令」描述衣服的颜色、材质、款式，以及需要保持的部分。
3. 先保持丰满度为 `0`，点击运行。默认 768×1024、10 步、CFG 1、ref_boost 4、grounding_px 768。
4. 下载或保存满意的结果，作为第二步输入。

示例指令：

```text
Change her navy T-shirt to a fully opaque burgundy long-sleeve crew-neck knit sweater. Keep the same person, facial features, hairstyle, pose, beige trousers, background and lighting. Natural clothing catalog photograph.
```

本机实测短袖变为酒红色长袖毛衣，人物相似度较高，脸部纹理与背景有小幅变化，并非精确锁脸。换装需重建衣料，局部颜色、褶皱、姿势均可能漂移。

参考模式已接入原来的丰满度 slider，但本次 `ref_boost=4` 和 `1` 下，`slider=0/+2` 的区别都很弱。因此不建议把这个模式当作可靠的体型调节器，也不建议靠一味加大强度解决。

## 2. 换装后局部微调

打开 `krea2_local_clothed_adjust.json`。此工作流使用现有 RAW FP8 + Turbo + slider，不需要额外模型。

1. 上传第一步的换装结果。
2. **先设置遮罩**：示例是 768×1024，白色区域大小 460×440，位置 x=150、y=325，边缘柔化 40。它仅适合随附示例的站位。换图后需让黑色底图尺寸与输入一致，并调整白色区域大小、位置。白色只覆盖需要编辑的衣服躯干，不要覆盖脸。
3. 遮罩预览中，白色允许修改，黑色保留原图。也可使用上传图节点的遮罩编辑器手动涂抹，把该节点的 `MASK` 输出分别接到 `SetLatentNoiseMask.mask` 和最终 `ImageCompositeMasked.mask`，替代示例矩形遮罩。
4. 在「② 丰满度」调整 `strength_model`：正值增加、负值减小，`0` 关闭 LoRA。建议先固定 seed 对照 `-1 / 0 / +1`。
5. 提示词应描述要保留的衣服。默认 12 步、CFG 1、denoise 0.6；seed 固定为 20260921。

本次对照实际测试了 `-2 / 0 / +2`。毛衣覆盖下的形体变化较小，衣物纹理和褶皱也会变化；不是按杯型或厘米进行精确调节。`slider=0` 仍会发生普通局部重绘，不代表输出和输入完全相同。

最终合成保留遮罩以外的原始像素。已逐像素核验本次三个结果的脸部和矩形区域外像素均与第一步换装结果完全一致。这只保证相对于该输入、且位于遮罩外的内容；第一步换装仍可能改变脸部，遮罩内背景、手臂、衣服纹理仍可能改变。

## 本机配置与测量

| 项目 | 配置 / 结果 |
|---|---|
| 基础模型 | 现有 Krea 2 RAW FP8 + 官方 Turbo rank64 adapter |
| 人物编辑 | Krea2 Identity Edit v1.2 r64，457,111,048 字节 |
| 节点扩展 | comfyui-krea2edit 1.2.5，无新增 Python 依赖 |
| 参考换装 | 768×1024、单张、10 步、CFG 1，约 17–23 秒 |
| 局部微调 | 768×1024、单张、12 步、CFG 1、denoise 0.6，约 9–11 秒 |
| 全程采样显存峰值 | 最高约 14,976 MiB（每 5 秒采样，可能漏掉瞬时峰值） |

时间为 ComfyUI 执行时间，不含下载；首次加载和其他显存占用会影响速度。当前结果只验证了一位合成人物、一种换装和当前遮罩，不能推广为对任意人物/衣物的质量保证。

使用项目根目录 `start-krea2-study.cmd` 启动，它现在会启用人物编辑扩展。若已有服务器运行，启动器不会自动改变其参数；需在队列空闲时停止现有服务器，再启动。当前服务器已经启用扩展。旧浏览器页面可能保留过期节点目录，重新打开 ComfyUI 页面可解决；无需重装模型。

## 来源、固定版本与复现

- [模型作者页面](https://huggingface.co/conradlocke/krea2-identity-edit)：这是社区人物编辑微调，并非 Krea 官方的人物一致性功能。
- [节点作者仓库](https://github.com/lbouaraba/comfyui-krea2edit)：以其现成工作流为结构参考，已适配本机模型、单张输入和中文说明。
- 模型 revision：`89e9e7a09ee2e5c9331e952063d79b1b8a703280`。
- 模型 SHA256：`f794b47142555c929cf536a2f1e4f335174b9aedbb08572b07d45814d4242423`，已验证。
- 节点固定 commit：`86f886dac23013d88996e3a2e99093ba44d322fb`。
- 原有基础模型、Turbo 和 slider 的版本与哈希保存在相邻 `../krea2-raw-slider/models-manifest.json`。

参考模式使用图像语义编码和 VAE 参考 token；不是普通低 denoise 图生图。局部微调使用普通 masked img2img，并将遮罩外原始像素合成回去。没有修改 ComfyUI 或 KJNodes 源码。

构建工作流：`.venv-cu130/Scripts/python.exe scripts/build_krea2_reference_workflow.py`。

单次验证：`.venv-cu130/Scripts/python.exe scripts/verify_krea2_reference.py --workflow outfit --strength 0`，或 `--workflow local --strength 1`。每次保存独立 run，保留参考图顺序、哈希、完整指令、种子、尺寸、模型清单和输出哈希。队列非空时不提交。测试结果见 `validation.md`。
