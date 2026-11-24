# 白底人物 + 场景 + 白底道具 → H3

> 2026-09-16 生产补充：本文仍是三张参考资产的权威默认；**agent 批量视频提交、预算和停止协议以 [h3-agent-production.md](h3-agent-production.md) 为入口**。下列完整 pipeline 命令保留为 9/13 单镜实测复现；agent 生产只用它的 `--until references` 阶段生成缺失资产，视频统一交 `h3_batch.py`。9/16 的长批次稳定性问题尚未被根治，不能把下表单镜成绩当稳定性保证。

2026-09-13，当前默认和后续 agent 的优先入口。按用户要求保持简单：三张独立参考直接进入 H3，不抠图、不合成首帧、不加入第四张构图图。画面由用户查看后决定是否调整，不自动反复重跑。

## 配置与引用

FLUX.2 Klein 4B Distilled FP8 生成三张图，4 步 / CFG 1。H3 使用 Ref2VA INT8 ConvRot + 专用 Turbo 4 步 LoRA + SageAttention + KJ 分块。模型串行运行，图像阶段结束后释放缓存。

| 引用 | 文件 | 尺寸 | 内容 |
|---|---|---|---|
| `<Picture 1>` | character_front.png | 768×1152 | 白底单人全身，定义身份与服装 |
| `<Picture 2>` | scene.png | 1344×768 | 温室、桌子、植物和建筑 |
| `<Picture 3>` | prop.png | 1024×1024 | 白底单盏黄铜提灯 |

视频提示词明确引用三个标签，说明白底只用于展示人物/道具，整段视频发生在第二张图的温室里。动作是拿起提灯、稍停、放回。原文：[greenhouse-h3-three-white.txt](../prompts/greenhouse-h3-three-white.txt)。

配置：[three-white-references.json](../configs/three-white-references.json)。默认 `greenhouse-reference-video.json` 当前内容相同。人物/场景/道具种子分别 20260913/20260916/20260917，视频种子 20260922。

H3 为 **1344×768 原生分辨率、243 帧、24fps、10.125 秒**，没有放大或裁切。三个独立 LoadImage 输入进入 MiniMaxH3ReferenceToVideo，不使用 first_frame。

## 启动和调用

硬件：RTX 5080 16GB / 48GB RAM；Windows 11，驱动 591.86。先检查 `http://127.0.0.1:8188/queue`，避免打断别的任务。

```powershell
Set-Location 'C:\Users\shang\zheyu\minimax h3'
$env:PYTHONUTF8 = '1'
.\start.ps1 -Cuda13 -SageAttention -KJNodes -VramHeadroom 8
.\.venv-cu130\Scripts\python.exe scripts/reference_video_pipeline.py --config configs/three-white-references.json --run-dir runs/my_shot_001
```

已有服务时 start 不会切换参数。如需切换，等队列空闲，再 stop.ps1 和 start。也可用 start-1080p-sage.cmd 启动同一配置。只监听本机地址。

增加 `--until references` 可仅生成图片；之后同目录去掉此参数继续视频。成功阶段会校验请求指纹及输出 SHA256 后复用。默认目录为 `runs/white_reference_demo`；新镜头请使用新目录。

修改 `stages` 的 prompt_file、seed、尺寸即可换人物/场景/道具；提示词文件相对于项目根目录。图像宽高为 16 的倍数，视频宽高为 32 的倍数。修改 video.references 时同步修改 `<Picture n>` 标签。当前 H3 steps=4、head_chunks=4、ffn_chunks=8；分块不是将视频切成多段。

## 输出契约

- `manifest.json`：执行状态、配置、模型固定版本/哈希、软件版本、产物和任务 ID。
- `config.snapshot.json`：本轮配置快照。
- `assets/`：三张原图及 reference-board.jpg。
- `jobs/<stage>/job.json`：完整 history、耗时、输出路径和 SHA256。
- `jobs/<stage>/workflow_api.json`：该阶段实际运行的 API 图。
- `jobs/<stage>/resources.jsonl`：约每 3 秒一次整卡资源采样，不是精确瞬时峰值。
- `workflow_combined_api.json` / `workflow_combined_editor.json`：完整依赖图和 GUI 导入文件。

视频路径在 `manifest.video.path`，原文件位于 ComfyUI/output/video。自动逐帧解码并生成同名 inspection.json 和每秒一帧的 contact.jpg；这检查编码和数值，不等于用户认可画面。

GUI 合并图还会复制到 `ComfyUI/user/default/workflows/Reference-to-H3-<name>.json`。分阶段 CLI 是实际验证路径，合并 GUI 图只导出和检查结构，不能称为已单次完整执行验证。单独三参考视频 GUI 文件为 `workflows/H3-Three-White-References-768p-10s.json`，对应的 API 图就是本轮执行请求。

## 恢复与维护

- 客户端退出但服务器仍在运行：原配置、原目录重跑，使用已保存 prompt ID 继续等待，不重复提交。客户端超时不会取消服务器任务。
- 输入改变：优先使用新目录；也可 `--force-stage prop --force-stage video` 重算受影响阶段。旧记录归档到该阶段 `attempts/<prompt-id>/`。旧任务仍在队列里时拒绝强制重提。
- 服务重启丢失 history：会报 job disappeared，先检查磁盘输出，再决定新目录或 force。
- OOM：核对 cu130 环境、Sage/KJ、其他显存进程，保持已验证尺寸与分块。系统内存有余量不代表显存足够。
- 道具变形、背景混入、身份漂移：保留原图和视频，核实标签和顺序，根据用户具体反馈修改下一版。白底不能保证永远不会被带入视频。
- `/free` 可正常返回空 body，客户端已兼容。
- 透明 PNG 的 alpha 与 RGB 会被 LoadImage 拆开；当前 H3 没有 MASK 输入。因此本轮不采用抠图路线。BiRefNet 权重曾下载完成，但未用于此流程，已于 2026-10-17 按用户批准清理；自带抠图模板需恢复该权重后才能使用。

图像模型固定版本与 SHA256：image-models-manifest.json；验证记录：image-model-verification.json。重新下载可运行 `scripts/download_image_models.py --proxy http://127.0.0.1:7897`（使用项目 cu130 Python）；没有此代理时省略参数。下载断点续传且检查哈希。

环境检查用 `scripts/doctor.py`，可选 `--hash` 全量读盘验证。锁定包清单为 requirements-cu130-sage-lock.txt。新增图像能力没有升级 ComfyUI 核心，也没有修改 ComfyUI/KJNodes 源码。Klein 使用独立 Qwen3-4B 和 Flux2 VAE，不能混用 H3 编码器或 VAE。更新前保留版本和成功 run，更新后先测小图。

## 已有扩展能力和历史实验

人物三视图已生成，见 `runs/greenhouse_demo/assets/character-turnaround.png`；侧/背各从同一正面母版编辑。单图入口是 generate_image.py，侧/背提示词分别 reference-side.txt 和 reference-back.txt。三视图不默认拼成一张送给 H3。

Klein Base 多参考合成首帧已单独测试，但不加入当前默认视频链。用户明确无需再测首帧视频。greenhouse_final 的单张合成图视频已取消；greenhouse_demo 和 greenhouse_clean 是带光带/白雾的历史实验，不能当作当前版本。

模型研究和 Base/Distilled 实际比较见 [image-model-selection.md](image-model-selection.md)。Qwen Edit 等备选未做本机画质对比，不能宣称 Klein 在所有任务上最佳。

## 本版测量

本版已完成；画面效果等待用户查看。视频：[white_reference_demo_h3_768p_00001_.mp4](../ComfyUI/output/video/white_reference_demo_h3_768p_00001_.mp4)。参考图：[三图概览](../runs/white_reference_demo/assets/reference-board.jpg)。

| 阶段 | 服务端耗时 |
|---|---:|
| 白底人物 | 5.642 秒 |
| 完整场景 | 2.699 秒 |
| 白底道具 | 2.656 秒 |
| H3 10 秒原生 768p | 233.221 秒 |
| 四阶段合计 | 244.218 秒 |

合计不含下载、人工检查和客户端轮询开销，也不是冷启动速度保证。视频阶段整卡显存采样最大 10068 MiB，系统可用内存最低约 8.55 GiB。MP4 为 H.264 + AAC，243 帧全部解码通过；音频 32kHz 双声道，采样数值有限。未以数值检查声称听感质量合格。

验证了三个独立参考及提示词标签、全部阶段断点复用、环境诊断与模型文件大小；pip check 通过。原始记录在 runs/white_reference_demo/manifest.json，测量汇总在 [reference-pipeline-results.json](reference-pipeline-results.json)，用户评价状态在该 run 的 review.json。
