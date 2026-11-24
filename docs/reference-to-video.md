# H3 全能参考：Mario 与城堡

本次使用独立 Ref2VA 模型和 `MiniMaxH3ReferenceToVideo` 原生节点。

参考图映射：

- `<Picture 1>`：`Mario.jpg`，角色身份、衣着、卡通造型。
- `<Picture 2>`：`Carsle.jpg`，城堡的棕色砖墙、垛口、上下层结构和中央门洞。

两张图片都传入 reference images，且视频 VAE 已连接，将参考图编码为参与扩散的参考潜变量。没有连接 first_frame / last_frame，也没有把图片拼接后充当首帧。

## 工作流与复用

[可视化工作流](../workflows/H3-5080-R2V-2Images-480p-10s.json) 已保存到项目 workflows 和 ComfyUI 用户工作流目录，并在 ComfyUI 界面打开、核对参考图连线及参数后重新保存。[播放生成视频](../ComfyUI/output/video/h3_mario_castle_r2v_00001_.mp4)。

打开 ComfyUI 左侧“工作流”，选择 **H3-5080-R2V-2Images-480p-10s**。左侧分别上传角色图和城堡图，在提示词中按连接顺序使用 `<Picture 1>`、`<Picture 2>`。注意端口名字从 ref_image_0 开始，但提示词编号从 Picture 1 开始。

本次场景：Mario 从左侧走到城堡门前，转身挥手，再走进门洞。分辨率沿用 864×480，10 秒输入按模型规则对齐为 243 帧 / 24fps，即 10.125 秒。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
& .\.venv\Scripts\python.exe .\scripts\generate.py --references .\Mario.jpg .\Carsle.jpg --prompt-file .\prompts\mario-castle-r2v.txt --width 864 --height 480 --seconds 10 --name h3_mario_castle_r2v
```

`--references` 选择 Ref2VA 权重和专用 Ref2V Turbo 4 步 LoRA；`--image` 才是旧的首帧模式，不能混用。需要 Base 模式时加 `--base`，默认 20 步；本机 Base 多图参考尚未实测。

## 模型与设置

- 主模型：`minimax_h3_ref2va_pruned_fp8_scaled.safetensors`，20,958,205,608 字节。
- LoRA：`minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors`，1,956,193,000 字节。
- 继续复用 Qwen3-VL NVFP4 文本编码器和 H3 视频 / 音频 VAE。
- `ref_image_size=match`，避免不必要的参考 token 负载；此处两张输入图本身较小。
- Turbo 4 步、strength=1、res_multistep / simple，seed=20260910。

Ref2VA 不能用 FL2VA 权重或 FL2V 8 步 LoRA 替代。官方节点支持图像、视频及音频参考，本次只验证双图输入。参考输入影响身份与物体特征，不承诺像素级还原或准确完成所有动作。

官方仓库 revision 固定为 `a98869194787969724c7425d95d0ed73ce9202af`。[新增模型清单](reference-models-manifest.json) 保留官方文件大小与 SHA256。下载脚本支持断点续传，校验通过后才将 `.part` 改成正式模型文件。运行 `scripts/doctor.py` 会同时检查原有与新增权重。

网络故障时可运行 `scripts/download_reference_models.py --proxy http://127.0.0.1:7897` 使用本机已运行的代理；端口仅适用于当前环境，换电脑应调整。无代理时省略 `--proxy`。此选项不改变系统代理配置。

来源：[ComfyUI 原生 R2V 教程](https://docs.comfy.org/tutorials/video/minimax/minimax-h3-native)、[Comfy-Org 权重仓库](https://huggingface.co/Comfy-Org/MiniMax-H3)。

## 实测结果

| 项目 | 结果 |
|---|---|
| 模式 | Ref2VA，2 张独立参考图片，无首尾帧 |
| 输出 | 864×480，243 帧，24fps，10.125 秒 |
| 采样 | Ref2V Turbo 4 步，ref_image_size=match |
| 服务端生成耗时 | 128.59 秒，约 2 分 9 秒；不含首次权重下载 |
| 客户端完成检测 | 131.67 秒 |
| 文件大小 | 852,784 字节 |
| 音轨 | AAC，32kHz，双声道，324,608 个解码样本 |
| 整卡显存最高采样值 | 15,492 MiB |
| 系统可用内存最低采样值 | 3.443 GiB |
| GPU 最高采样温度 | 68°C |
| 任务结果 | success，无 OOM，243 帧及音轨完整解码通过 |

逐秒画面检查：开头是城堡，Mario 从左侧走来，约 4–5 秒在门前挥手，随后转身进入门洞，结尾保留城堡。城堡的砖纹、垛口、上下层和黑色门洞有明显参考对应；Mario 的红帽、蓝背带裤、白手套等身份特征保留。但输出角色更接近立体玩偶，并非原图平面卡通线条的完全复刻。

音轨数值有限且非静音，RMS 0.118806，解码峰值 1.053361 略高于 1，未进行人耳音质或语义评分。正式发布前可检查音频峰值及是否需要限幅。参考图、随机种子相同也不保证跨环境逐字节一致。

资源数据来自约 5 秒一次、共 27 次整机/整卡采样，不是精确的模型显存分配峰值。本次是一次成功验证，不能由此推断更高分辨率、更多参考图或 Base 20 步也同样稳定。可视化工作流经前端加载保存；本次生成来自对应的 API 工作流。

证据：[实际 API 工作流](../workflows/h3_mario_castle_r2v_api.json)、[任务参数与结果](../logs/h3_mario_castle_r2v_d5ba34f0-914e-4d67-a791-1c902cc0b896.json)、[资源采样](../logs/h3_mario_castle_r2v_d5ba34f0-914e-4d67-a791-1c902cc0b896.resources.jsonl)、[逐秒画面](../ComfyUI/output/video/h3_mario_castle_r2v_00001_.contact.jpg)、[解码检查](../ComfyUI/output/video/h3_mario_castle_r2v_00001_.inspection.json)、[新权重 SHA256 校验](reference-model-verification.json)、[服务日志](r2v-server.log)。
