# 48GB 内存：10 秒 1080p 测试

**2026-09-13 已成功：RTX 5080 16GB + 48GB RAM，Mario + Castle 双图全能参考，原生 1920×1080、243 帧、24fps、10.125 秒。服务执行 606.431 秒（约 10 分 6 秒），四步采样约 494 秒。**

[播放成片](../ComfyUI/output/video/h3_r2v_1080p_sage_int8_00001_.mp4) · [逐秒预览](../ComfyUI/output/video/h3_r2v_1080p_sage_int8_00001_.contact.jpg) · [完整解码检查](../ComfyUI/output/video/h3_r2v_1080p_sage_int8_00001_.inspection.json)

成功组合：**CUDA 13 + 官方 Ref2VA INT8 ConvRot + SageAttention 2.2 + H3 Mem Eff Sage 补丁 + 注意力 4 组 + 前馈 8 块 + 动态卸载 / headroom 8。** 完整 243 帧联合采样，没有时间分段，也没有从低清放大。多项配置共同变化，不能把全部改善归因于 Sage 单独加速。

## 以后怎么使用成功配置

1. 如已有旧服务运行，先执行 `stop.ps1`；再双击项目根目录的 [start-1080p-sage.cmd](../start-1080p-sage.cmd)。
2. 打开 `http://127.0.0.1:8188`，载入 [H3-5080-R2V-1080p-10s-Sage-KJ-INT8.json](../workflows/H3-5080-R2V-1080p-10s-Sage-KJ-INT8.json)。同名文件已保存到 ComfyUI 用户工作流目录。
3. 在两个图片节点选择参考图，并在提示词中按 `<Picture 1>`、`<Picture 2>` 顺序描述；执行工作流，视频保存在 `ComfyUI/output/video/`。

完整复现命令、版本和故障处理见 [SageAttention 专项说明](sageattention-5080-research.md)。本次实际执行的是同参数 [API 工作流](../workflows/h3_r2v_1080p_sage_int8_api.json)；可视化工作流已校验节点和连线，未另行重复运行整段视频。

## 成片与资源检查

- 所有 243 帧完整解码，H.264，1920×1080，文件 2,720,573 字节；AAC 32kHz 双声道，音频有限值且非静音。音频做了信号检查，未作听感评价。
- 逐秒画面可见 Mario 从左侧走来、转身挥手、进入城堡门，结尾城堡留在画面中；参考角色与建筑均可识别，未见整屏黑屏或噪点崩坏。仍存在生成模型常见的风格重绘，未逐帧评估全部细小动作。
- 约每 5 秒资源采样：整卡显存最高 **15,618MiB ≈15.25GiB**，系统可用内存最低 **7.13GiB**，GPU 温度最高 **76°C**。这不是精确的瞬时分配峰值，也不代表能同时运行其他大模型。
- 无 OOM，服务器记录 `execution_success`。[任务记录](../logs/h3_r2v_1080p_sage_int8_63a05281-f7d9-4afa-af75-25e0ea710142.json) · [服务日志](1080p-sage-int8-success-server.log) · [环境诊断](doctor-cu130-sage.json)。客户端轮询计时为 611.41 秒，包含等待下一次查询的延迟；服务端真实执行时间为 606.431 秒。
- 生成后已释放缓存模型，服务保持可用。以后增加参考图数量、时长或分辨率仍需重新评估显存；本次证明的是这套具体配置。

## 下方保留早期失败及中止记录

测试日期：2026-09-12。沿用 Mario.jpg + Carsle.jpg 双图 Ref2VA，Turbo 4 步、seed=20260910、res_multistep / simple，目标 243 帧 / 24fps = 10.125 秒。H3 在 1920×1088 上采样，编码前上下各裁 4 像素，得到 1920×1080。没有低清放大。

## 升级后硬件

3×16GB DDR5，系统可用总量约 47.1GiB，检查时可用约 37.6GiB；RTX 5080 16GB，驱动 591.86。[硬件快照](hardware-48gb-1080p.json)。系统内存和显存用途不同，增加系统内存不等于增加显卡上的高速显存。

## 初步尝试

1. **旧 cu128 环境 + 动态显存 + reserve-vram 2。** 未等到第一步结束就观察到约 13GiB 共享 GPU 内存使用，助手主动中止以调整配置。这不是成功运行，也不是模型主动报错。证据：[GPU 内存计数](1080p-default-gpu-memory.json)、[日志](1080p-default-vram-server.log)、[提交记录](../logs/h3_r2v_1080p_10s_48gb_85b63d7e-f9e5-448f-974a-08e94e0ba155.json)。
2. **旧 cu128 环境 + 禁用动态显存 + reserve-vram 4。** 47.05 秒后发生 CUDA OOM，失败在采样的 RMS/RoPE 回退运算，已分配约 13.10GiB 时请求额外约 1.98GiB。没有生成视频。系统可用内存采样最低为 0.579GiB；传统卸载也增加了系统内存压力。证据：[日志](1080p-conservative-cu128-server.log)、[失败记录](../logs/h3_r2v_1080p_10s_conservative_b91e0cbc-ed35-4a5d-b632-adf4b026191b.json)。

## CUDA 13 独立测试环境

后续 cu130 动态卸载进行了默认设置、额外 8GB headroom 两轮尝试：分别在第一步完成前约 2 分钟、10 分钟主动中止，以调整共享显存换页问题。这两轮没有明确 OOM，也没有成片，不能据此证明最终一定无法完成。对应日志为 `1080p-cu130-default-server.log` 与 `1080p-headroom8-server.log`。

为利用新驱动支持的优化算子，新增 `.venv-cu130`，保留原 `.venv`。CUDA 13.x 的驱动最低要求为 R580；591.86 满足版本门槛。[NVIDIA 兼容说明](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html)。

原环境包版本保存在 [requirements-before-1080p.txt](requirements-before-1080p.txt)。新环境使用同一项目 Python 3.12，PyTorch 2.11.0/cu130、torchvision 0.26.0、torchaudio 2.11.0，其余包按该快照安装。复用 FP8 模型，不重复下载大权重。

启动参数已扩展：`start.ps1 -Cuda13` 选择新环境；不加参数仍选择原 cu128 环境。`-ConservativeVRAM` 只用于已记录的传统卸载实验，不能将其视为已通过的 1080p 方案。切换前先运行 `stop.ps1`，避免复用仍在运行的旧服务。停止脚本只允许结束本项目两套环境启动的 ComfyUI。

早期 [1080p 可视化工作流](../workflows/H3-5080-R2V-1080p-10s-48GB.json) 仅用于记录 FP8 尝试，未验证成功。后续使用应选择本文开头的 Sage-KJ-INT8 工作流。

## 2026-09-13：SageAttention 实验

SageAttention 和匹配的 Triton 已安装到 `.venv-cu130`，FP16/BF16 实际算子验证通过。版本、下载来源、网上 16GB 1080p 证据见 [专项说明](sageattention-5080-research.md)。

1. **SageAttention + FP8 + 传统卸载 + reserve-vram 4 + LowMemory。** 任务 `5b3dbc65-c7fd-4a01-ac52-4d3c8d1c2ba2`。系统可用内存接近零，首步未完成时主动停止；没有成片，也没有将主动停止记为 CUDA OOM。[服务日志](1080p-sage-only-server.log)。单独换 Sage 不能保证其他运算的内存峰值下降。
2. **SageAttention + FP8 + 动态卸载 + headroom 4 + KJ 注意力 4 组 / 前馈 8 块。** 任务 `a1575975-0dbc-48e3-818b-955b416eaabb`。系统可用内存改善到约 21–25GiB，GPU 仍有约 5GiB 共享内存，进度慢。栈快照确认计算已进入第 12 个 DiT 层，并非完全卡死。第一步结束前主动停止，改测 INT8 与专用 Sage 补丁；没有声称该配置最终一定不能完成。[诊断快照](1080p-sage-kj-stack.txt) · [服务日志](1080p-sage-kj-fp8-server.log)。

这两轮仍使用相同 Mario / Castle 参考图、相同 seed、243 帧以及 1920×1088 原生采样尺寸。
