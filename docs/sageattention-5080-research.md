# RTX 5080 / H3 / 1080p：SageAttention 与低显存路线

核查日期：2026-09-13。本机 RTX 5080 16GB、48GB 系统内存、驱动 591.86。

**本机现已跑通完整 10.125 秒原生 1080p 双图 Ref2VA，约 10 分 6 秒。** 成功配置是下方 INT8 + H3 专用 Sage + KJ 分块的组合，详见 [成片和实测记录](test-1080p-48gb.md)。早期 FP8 尝试未完成，以下保留研究与调整依据。

## 网上证据能说明什么

| 来源 | 实际报告 | 适用范围 |
|---|---|---|
| [HR Endless Sampler 作者](https://github.com/hradec/ComfyUI-HR-Endless-Sampler#tips-to-render-1080p-with-16gb-of-vram) | 16GB GPU、Ref2VA、5 张参考图、1080p、625 帧；chunk_frames=56、video_continuation=22，KJ Low VRAM Attention=4 | 是原生分辨率的分段生成；没有证明 5080 能一次联合采样完整 10 秒。作者未在这段说明中注明 GPU 型号。 |
| [RTX5080 专门项目](https://github.com/Harry5450/MiniMax-H3-ComfyUI-RTX5080) | Windows / 5080 / 16GB；864×480 基准，再用 Lanczos 放大为 1080p | 放大输出，不能当原生 1080p 推理证据。 |
| [KJNodes 作者源码](https://github.com/kijai/ComfyUI-KJNodes/blob/main/nodes/minimax_nodes.py) | H3 专用注意力分组，及按 token 分块的前馈计算 | 降低中间张量峰值；不做时间分段。节点仍标记 experimental，应验证当前模型、后端和输出。 |
| [Comfy-Org 模型卡](https://huggingface.co/Comfy-Org/MiniMax-H3) | CUDA 13 优先使用 INT8 ConvRot；FP8 为兼容路线 | 本机驱动升级后可以测试官方推荐格式，需真正下载对应权重，不能重命名 FP8 文件。 |

结论：网上存在 **16GB 显存生成原生 1080p 全能参考视频** 的可复现配置方向，因此不能凭此前 OOM 就断言硬件完全不支持。完整 10 秒联合采样、时间分段、低清放大是不同测试条件，必须分别记录。

## SageAttention 安装与算子验证

独立环境 `.venv-cu130`：Python 3.12.14、PyTorch 2.11.0+cu130、SageAttention 2.2.0+cu130torch2.10.0andhigher.post6、triton-windows 3.6.0.post26。

- [Windows SageAttention 维护者说明](https://github.com/woct0rdho/SageAttention)：预编译包支持 RTX 50 系列；ABI3 支持 Python ≥3.10，stable libtorch ABI 包支持 PyTorch ≥2.10。CUDA 主版本必须匹配。
- [Triton Windows 官方分支](https://github.com/triton-lang/triton-windows)：PyTorch 2.11 对应 Triton 3.6。
- [本次 Sage 发布页](https://github.com/woct0rdho/SageAttention/releases/tag/v2.2.0-windows.post6)。cu130/torch2.10+ 包 SHA256：`1635283f5c01ec3cda58a784d0d7eabbcaffaf9511d1b263db4750e1ed7958bb`，安装时校验。

本机执行了 56 头、2048 token、每头 128 维的 FP16/BF16 运算；输出有限值，与 PyTorch SDPA 的余弦相似度均约 0.99927。[实际结果](sage-validation.json)。这个测试证明算子可执行，不代表整段视频质量与基线完全相同，也不是模型加速比。

维护者现也推荐 Comfy Kitchen 自带注意力；本轮为回应 SageAttention 的对比请求，明确安装并使用独立 SageAttention，服务器日志须出现 `Using sage attention`。

## 本地启动和分块选项

切换前先停止旧服务。在项目目录运行：

```powershell
.\stop.ps1
.\start.ps1 -Cuda13 -SageAttention -KJNodes -VramHeadroom 4
```

只白名单启用 `ComfyUI-KJNodes`，其余自定义节点仍禁用。KJNodes 固定版本：`57105374f47d0fbb49c9c3926fb981702e0a4b5c`。

生成脚本增加 `--head-chunks 4 --ffn-chunks 8`，对应注意力分成 4 组、前馈分成 8 块。分块仍保留完整时间序列，可能有额外开销；Sage 本身采用近似量化计算，不承诺逐像素等价。

**完整视频测试结果以 [1080p 实测记录](test-1080p-48gb.md) 为准。** 未完成的任务不能记为成功；主动中止也不能记成 CUDA OOM。

## INT8 + H3 专用 Sage 的完整序列实验

已下载并校验 `minimax_h3_ref2va_pruned_int8_convrot.safetensors`（20,970,379,616 字节），固定同一官方仓库 revision，校验结果见 [int8-reference-verification.json](int8-reference-verification.json)。原 FP8 权重保留。

在注意力分组节点之前增加 `MiniMaxH3MemoryEfficientSageAttentionPatch`，并把动态 headroom 改为 8。该实现来自同一 KJNodes 仓库的 [ltxv_nodes.py](https://github.com/kijai/ComfyUI-KJNodes/blob/57105374f47d0fbb49c9c3926fb981702e0a4b5c/nodes/ltxv_nodes.py)，直接使用 Sage 内核并提早释放中间张量。

```powershell
.\stop.ps1
.\start.ps1 -Cuda13 -SageAttention -KJNodes -VramHeadroom 8
.\.venv-cu130\Scripts\python.exe scripts/generate.py --references Mario.jpg Carsle.jpg --prompt-file prompts/mario-castle-r2v.txt --width 1920 --height 1088 --crop-1080p --seconds 10 --head-chunks 4 --ffn-chunks 8 --memory-efficient-sage --int8 --name h3_r2v_1080p_sage_int8
```

可视化工作流：[H3-5080-R2V-1080p-10s-Sage-KJ-INT8.json](../workflows/H3-5080-R2V-1080p-10s-Sage-KJ-INT8.json)。也已保存到 ComfyUI 的用户工作流目录。节点类型和连线经过当前服务校验；实际执行使用同参数的 API 工作流。

## 维护与排错

- 完整包快照：[requirements-cu130-sage-lock.txt](requirements-cu130-sage-lock.txt)。不要在原 `.venv` 混装 CUDA 13 的 Sage wheel；新环境的 torch / Sage CUDA 主版本需一致。
- 缺少 KJ 节点：先停止服务，再按带 `-KJNodes` 的命令启动。仅把工作流导入原默认服务不会自动启用插件。
- `Using sage attention` 证明全局后端选择；日志还应出现 `Applying MiniMax H3 Memory Efficient Sage Attention Patch` 及 composing 提示，证明 H3 补丁与注意力分组同时启用。
- `sageattention is not new enough`：确认用的是 `.venv-cu130`、上述 wheel 和匹配的 Triton，先重跑 `scripts/test_sage.py`。不要只根据 `pip` 命令无报错判断安装位置。
- 黑屏、噪点或明显异常：保存任务日志和视频；使用相同 seed 关闭专用 Sage 补丁、切回原工作流比较，不要把文件能解码等同于画面正常。
- 生成慢：观察采样步数，并结合 GPU 功耗与栈快照；Windows 的共享 GPU 内存统计也可能含映射/固定内存，单凭共享内存数值不能断定完全卡死。本轮保留了中止原因，未把中止冒充 OOM。
- 更新前保存包快照和 KJ commit；只在独立环境更新，并先做小测试。回到原方案可运行 `stop.ps1` 后不带参数运行 `start.ps1`，再使用先前已通过的 480p / 720p 工作流。
- INT8 权重损坏或下载中断：`scripts/download_int8_reference.py` 可断点续传并检查官方 SHA256；当前下载脚本使用本机代理 `127.0.0.1:7897`，代理端口变更时相应调整。
- `scripts/doctor.py` 已纳入 Sage / Triton 与 INT8 权重检查；常规检查不读取全部权重，`--hash` 才执行完整哈希验证。
