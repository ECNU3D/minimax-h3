> 本文从原根 README 迁入，保留历史部署命令与实测日期。日常使用以 [导演台说明](../h3_director/README.md) 和 [当前生产协议](h3-agent-production.md) 为准；文中的命令在仓库根目录执行。

> **2026-10-17 环境清理：** 根目录旧 CUDA12.8 `.venv` 已按用户要求停用并核验目录已不存在。当前入口统一使用 `.venv-cu130`，`start.cmd` 使用生产启动参数，`repair-environment.ps1` 按 `requirements-cu130-sage-lock.txt` 恢复 CUDA13 环境。音频 CUDA12.8 环境保留。两份 H3 FP8、Qwen INT8 实验编码器和 BiRefNet 已另获批准删除，详情记录在本机的停用模型清单。下文涉及 `.venv` 或这些模型的命令仅为历史实测记录，不是当前可直接运行的默认入口；当前视频生产使用 `h3_batch.py` 的 Ref2VA INT8 路线。

> **2026-09-16 Agent 生产更新：** [固定脚本/重试预算/goal 停止协议](h3-agent-production.md) · [剪辑与字幕](video-editing-workflow.md) · [文档索引](README.md)。

# MiniMax H3 本地部署与使用手册

**最新：文生参考图 → 三图全能参考视频已跑通。** Klein 4B 生成白底人物、完整场景、白底道具，H3 输出原生 1344×768、10.125 秒视频；视频阶段约 3 分 53 秒，效果等待用户查看。[播放本版](../ComfyUI/output/video/white_reference_demo_h3_768p_00001_.mp4) · [当前调用手册与工作流](three-white-reference-workflow.md) · [模型选型研究](image-model-selection.md)。

**10 秒原生 1080p 双图全能参考已通过（2026-09-13）：** 当前 5080 16GB + 48GB 内存，使用 INT8 ConvRot + SageAttention + KJ H3 分块，生成 1920×1080、10.125 秒视频，用时约 10 分 6 秒。[播放视频](../ComfyUI/output/video/h3_r2v_1080p_sage_int8_00001_.mp4) · [成功工作流、启动方法与实测记录](test-1080p-48gb.md)。今后运行这套配置使用 `start-1080p-sage.cmd`。

**全能参考 Ref2VA 已验证：** Mario.jpg + Carsle.jpg 两张独立参考图，生成 864×480、10.125 秒视频，专用 Turbo 4 步用时约 129 秒。[视频、工作流与使用说明](reference-to-video.md)。Ref2VA 主模型和专用 LoRA 已补齐并通过官方 SHA256 校验。

**参考图生成视频已验证：** 使用 `Mario.jpg` 生成 864×480、约 5.17 秒视频，用时约 104 秒。[视频与使用说明](image-to-video.md) · [可复用图生视频工作流](../workflows/H3-5080-I2V-480p-5s.json)。

以下历史命令中的部署目录应替换为实际的仓库根目录。

环境核查日期：2026-09-13（早期视频成绩保留原测试日期）。本文针对这台 Windows 电脑，不是多卡服务器教程。

**48GB / CUDA 13 / SageAttention 更新：** 已新增独立测试环境，Sage 算子通过 5080 验证；1080p 完整视频结果见 [实测记录](test-1080p-48gb.md)，网上证据和安装版本见 [SageAttention 与低显存路线](sageattention-5080-research.md)。

**已完成本机部署和三档视频实测。** 640×384 用时约 61 秒，864×480 用时约 93 秒；2026-09-11 补测的 1280×720 用时约 245 秒。三段均为 124 帧、24fps、约 5.17 秒，含 32kHz 双声道音频。完整证据见 [实测记录](test-results.md) 和 [720p 实测及用法](test-720p.md)。

直接查看：[720p 高清测试视频](../ComfyUI/output/video/h3_hd_00001_.mp4)。高清任务在 1280×736 上生成，编码前上下各裁掉 8 像素，输出标准 1280×720。

**10 秒 720p 补测也已通过：** 243 帧、24fps、实际 10.125 秒，Turbo 8 步用时约 11 分 20 秒，无 OOM。[播放 10 秒视频](../ComfyUI/output/video/h3_hd_10s_00001_.mp4)；复现命令及证据见 [720p 文档](test-720p.md)。

直接查看：[快速测试视频](../ComfyUI/output/video/h3_smoke_00001_.mp4) · [清晰预览视频](../ComfyUI/output/video/h3_balanced_00001_.mp4)。

## 1. 硬件与方案

| 项目 | 本机信息 | 对部署的影响 |
|---|---|---|
| GPU | NVIDIA RTX 5080，16GB，Blackwell / sm_120 | 能执行 CUDA；完整大模型无法全部常驻显存 |
| CPU | Ryzen 7 9800X3D，8 核 16 线程 | 负责加载、卸载及系统任务 |
| 内存 | 已升级为 48GB（3×16GB DDR5）；早期测试为 32GB | 仍需留意显存、中间张量及系统内存峰值 |
| 系统盘 | GIGABYTE AG4732TB SSD，C 盘初始约 1.64TiB 空闲 | 模型放本机 SSD，使用 mmap 和动态卸载 |
| NVIDIA 驱动 | 已升级为 591.86；早期测试为 576.88 | 现可使用独立 cu130 环境，原 cu128 环境保留 |
| 操作系统 | Windows 11 家庭中文版，64 位 | 使用原生 Windows Python 环境 |
| 分页文件 | 系统自动管理，首次观察分配约 5GB | 保持自动管理，保证 C 盘余量 |

**当前选择：ComfyUI 原生节点 + FL2VA 裁剪 FP8 模型 + NVFP4 文本编码器 + GPU/内存/SSD 动态卸载。**

FL2VA 一套权重覆盖文生视频和首尾帧图生视频。后续已另行安装约 21GB 的 Ref2VA 主模型和约 2GB 的专用 4 步 LoRA，并实测双图全能参考；两类模型和 LoRA 不能混用。

| 路线 | 本机取舍 |
|---|---|
| ComfyUI | 选用。已有 H3 原生工作流、量化格式、卸载和可视化界面，后续更易操作 |
| Diffusers | 适合 Python 集成，但需要自己管理流程和卸载，不是这次桌面使用的优先方案 |
| SGLang / vLLM | 适合服务化与多卡环境，对这台 16GB Windows 单卡电脑增加部署复杂度 |
| 云端 API | 不属于本地权重推理，本次测试不用它 |

“最优”在这里指**兼顾可行性与可维护性的方案**，不是所有参数组合的性能冠军。早期因旧驱动采用 FP8 兼容路线。驱动已升级，CUDA 13 / Ref2VA INT8 ConvRot + SageAttention + KJ 分块已通过 10 秒 1080p 双图测试，具体参数见新增实测记录。[量化格式说明](https://huggingface.co/Comfy-Org/MiniMax-H3) · [CUDA 驱动兼容表](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html)

本地开放的是 H3-Base。官方完整系统还含 H3-Context-IR 和 H3-Regenerate-2K 云端模块，不能将本次本地预览描述成完整官方 2K 系统。[MiniMax 官方模型卡](https://huggingface.co/MiniMaxAI/MiniMax-H3)

## 2. 目录与权重

```text
minimax h3/
├── .venv/                  独立 Python 包环境
├── ComfyUI/                官方源码，模型、界面和输出
│   ├── models/
│   ├── output/video/        生成的 MP4
│   └── user/default/workflows/H3-5080.json
├── docs/                   硬件、版本、权重校验和实测记录
├── logs/                   服务日志、下载日志、任务结果
├── scripts/                下载、生成、检查脚本
├── workflows/              原始模板、适配模板和 API 请求
├── tools/                  独立 Python、uv 与 aria2 分段下载工具
├── prompt.txt              可编辑的示例提示词
├── start.cmd / start.ps1    启动本地服务
├── stop.ps1                停止本项目启动的服务
└── generate-test.cmd       提交固定参数测试
```

| 相对于 `ComfyUI/models/` 的文件 | 大小（十进制 GB） |
|---|---:|
| `diffusion_models/minimax_h3_fl2va_pruned_fp8_scaled.safetensors` | 20.958 |
| `text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | 15.687 |
| `vae/minimax_h3_video_vae_fp16.safetensors` | 5.208 |
| `vae/minimax_h3_audio_vae_fp32.safetensors` | 0.605 |
| `loras/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors` | 1.956 |
| **合计** | **44.415GB，约 41.37GiB** |

运行环境、下载缓存、输出和 Windows 分页文件另占空间。至少为整个项目及临时空间预留 80–100GB；这不是推理时的显存要求。

下载来源是官方 Comfy-Org 仓库，固定 revision 和每个文件的 SHA256 存在 `docs/models-manifest.json`。只有通过校验才会将 `.part` 改成正式 `.safetensors` 文件名。`docs/model-verification.json` 保存本机核验结果。

## 3. 最简单的使用方式

1. 双击 `start.cmd`，稍等服务启动。
2. 浏览器打开 <http://127.0.0.1:8188>。
3. 从左侧工作流列表打开 `H3-5080`（快速）或 `H3-5080-balanced`（清晰预览），也可以把 `workflows/` 下对应 JSON 拖入画布。
4. 修改主节点的 `prompt`，先保留预览分辨率、5 秒、Turbo 8 步。
5. 点击运行，等待完成。首次模型读取通常比重复生成慢。
6. 在界面预览或打开 `ComfyUI/output/video/` 下的新 MP4。

也可以在 PowerShell 中操作：

```powershell
Set-Location 'C:\Users\shang\zheyu\minimax h3'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
& .\.venv\Scripts\python.exe .\scripts\generate.py
```

编辑 `prompt.txt` 后生成自己的视频：

```powershell
& .\.venv\Scripts\python.exe .\scripts\generate.py --prompt-file .\prompt.txt --name my_video --width 640 --height 384 --seconds 5 --seed 42
```

生成脚本只访问本机 ComfyUI；任务 ID、提交参数、输出位置和执行时间保存在 `logs/`。如果终端中断，后台队列可能仍在运行，不要立刻重复提交。

关闭服务：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\stop.ps1
```

关闭浏览器标签页并不会退出 Python 服务。停止服务会中断正在运行的任务。

## 4. 参数怎么选

| 用途 | 分辨率 | 时长 | 模式 | 状态 |
|---|---|---|---|---|
| 快速试提示词 | 640×384 | 输入 5 秒 | Turbo LoRA，8 步 | 已通过，服务端 61.20 秒 |
| 日常清晰预览 | 864×480 | 5 秒 | Turbo，8 步 | 已通过，服务端 93.45 秒 |
| 720p 成片 | 1280×736 → 裁为 1280×720 | 5 秒 | Turbo，8 步 | 已通过，服务端 244.73 秒；命令见 [720p 用法](test-720p.md) |
| 更重视运动和音质 | 先保持 640×384 | 5 秒 | Base，20 步 | 需另行测试 |
| 原生横屏尺寸候选 | 1344×768 | 从 5 秒开始 | Base，20–25 步 | 高负载，未因规格支持就视为本机通过 |

命令行切换 Base：

```powershell
& .\.venv\Scripts\python.exe .\scripts\generate.py --prompt-file .\prompt.txt --base --steps 20 --name base_preview
```

宽高用 32 的倍数。输出帧数会向上对齐到 `17k+5`：5 秒输入按 24fps 计算为 120 帧，再对齐为 124 帧，实际视频约 5.167 秒。这里是模型时序结构，不是编码器出错。相关逻辑可在本地 `ComfyUI/comfy_extras/nodes_minimax_h3.py` 的 `align_frame_count` 看到。

Turbo 必须同时加载对应 LoRA。仅将 Base 的步数改成 8 不能等同于加速模型。保持 batch=1；先只改一个参数。分辨率、时长和参考输入都会增加负载；减少步数主要减少时间，不保证降低峰值显存。

生成时不要同时运行另一套大型 AI 模型或大型游戏。启动脚本传入 `--reserve-vram 2`，但动态显存管理并不等同于固定留下 2GB 物理空闲显存：实测整卡占用曾达到约 15GB。32GB 系统内存也是约束，两个配置的最低可用内存分别约 2.74/2.17GiB。不要把本次成功理解为还有大量并发空间。

清晰预览命令：

```powershell
& .\.venv\Scripts\python.exe .\scripts\generate.py --prompt-file .\prompt.txt --width 864 --height 480 --seconds 5 --name clear_preview
```

## 5. 提示词怎么写

建议先用单镜头、单主体、明确运动，再逐步增加复杂度。可写中文；本次固定英文提示词是为了方便重跑比较，不代表模型只支持英文。

```text
integrated_multimodal_description: 一个连续固定镜头。清晨的花园池塘，一只橙色纸船从左向右缓缓漂动，船边扩散出细小涟漪。水面倒映绿色树叶，光线柔和，写实摄影。不要切镜，不要字幕。
overall_soundscape: 轻柔的水声，远处偶尔传来鸟鸣。
non_diegetic_music: 无背景音乐。
```

这三个标签可以明确区分画面、环境声和配乐。避免在 5 秒里塞进十个镜头，或同时要求“固定机位”和“大幅绕拍”。要有人声时明确说话者、台词和出场时间。图生视频可以在原生 H3 节点连接首帧或尾帧；本次交付主要验证文生视频。

## 6. 常见坑与排错

先做这三步：看服务日志最后一条异常；运行诊断；用固定预览参数重试一次。

```powershell
Get-Content .\logs\comfy.stderr.log -Tail 100
& .\.venv\Scripts\python.exe .\scripts\doctor.py
```

诊断只读取本机信息，结果写入 `logs/doctor.json`。不会上传日志。

| 现象 | 检查和处理 |
|---|---|
| 网页打不开 | 查看服务日志；确认后台 Python 未退出、8188 端口没有被其他程序占用。启动脚本输出 PID 不等同于已经启动成功 |
| `Torch not compiled with CUDA enabled` | 很可能装了 CPU 版 torch。使用本项目 `.venv` 并按版本锁恢复 CUDA 12.8 轮子 |
| `driver too old` / CUDA 初始化失败 | 核对 `nvidia-smi` 与 `docs/gpu-validation.json`。576.88 不适合 CUDA 13，不要直接运行当前官方 cu130 安装命令 |
| `no kernel image` / `sm_120` 不支持 | 5080 要使用包含 Blackwell 架构支持的 PyTorch；本机 CUDA 运算验证文件记录了架构列表 |
| 日志提示优化 CUDA operations 需要 cu130 | 当前 cu128 路线禁用 Comfy Kitchen 的 CUDA 加速后端。这是兼容路线的性能限制；是否成功须看最终任务状态 |
| `CUDA out of memory` | 先停止其他 GPU 任务，保持 batch=1，回到预览分辨率和 5 秒；必要时重启服务释放残留显存。不要盲目改为 `--highvram` |
| 内存不足 / 页面文件太小 / WinError 1455 | 查看任务管理器的“已提交”内存。保持系统自动管理分页文件和 C 盘余量，关闭不必要的大内存程序；不要关闭分页文件 |
| 模型文件不在下拉列表 | 确认放在正确子目录，文件名不含 `.part`；下载成功后刷新模型列表或重启 ComfyUI |
| 缺少 MiniMax H3 节点 | 启动了别处的旧版 ComfyUI，或依赖导入失败。核对服务路径、版本与日志 |
| 加载时 tensor / shape / header 错误 | 先校验 SHA256，再核对所用模型家族和工作流。不要改扩展名假装下载完成 |
| 下载断网、超时 | 重新运行 `scripts/download_models.py`。保留 `.part` 与 `.aria2`；分段文件只有大小正确仍不能证明下载完整 |
| 下载 401/403 | 查看下载日志，确认官方仓库可访问、固定 revision 仍存在、下载链接未失效。脚本重新执行会重新取得下载重定向 |
| GPU 利用率上下波动，长时间加载 | 16GB 显存需要卸载和磁盘读取。结合日志、磁盘读取和显存看进度；不要仅凭低 GPU 利用率判断卡死 |
| 视频黑屏、静止、严重失真 | 检查模型完整性、任务错误、是否遗漏 Turbo LoRA；回到固定种子和示例提示词比较。MP4 存在不代表生成质量合格 |
| 没声音 | 先检查播放器是否静音；确认工作流连接音频 VAE 和 CreateVideo 的 audio 输入。运行视频检查脚本确认音轨存在 |
| 安装了某插件后坏了 | 当前启动脚本禁用所有 custom nodes。先保留该基线排查，不要一次安装大量节点包 |
| PowerShell 禁止执行脚本 | 使用提供的 `.cmd`，它仅对本次 PowerShell 进程设置执行策略，不修改全局策略 |
| 路径里有空格导致命令失败 | 本项目路径包含空格，PowerShell 中路径需要引号和调用运算符 `&` |
| 画布上有节点方框却看不到文字 | 先把右下角缩放调到 80% 或 100%；本次观察到约 54% 时节点文字被简化隐藏。画面被截断时拖动画布或收起侧边栏，不要误判为模型加载失败 |

完整模型校验（会读取全部约 44GB 文件，需要一些时间）：

```powershell
& .\.venv\Scripts\python.exe .\scripts\doctor.py --hash
```

检查某个生成文件是否可解码、帧数是否正确、音轨是否存在：

```powershell
& .\.venv\Scripts\python.exe .\scripts\inspect_video.py '.\ComfyUI\output\video\你的文件.mp4'
```

该命令会输出 `.inspection.json` 和分时刻缩略图 `.contact.jpg`。统计数据不能替代人工观看和试听。

## 7. 日常维护与恢复

**先冻结能工作的版本，再升级。** 不要每次启动都自动 git pull / pip upgrade。

保留：`docs/models-manifest.json`、`docs/model-verification.json`、`docs/requirements-lock.txt`、`docs/comfy-commit.txt`、工作流、提示词、实测记录，以及重要输出视频。模型可以按固定 revision 重下载，个人生成结果不能靠重下载恢复。

升级前停止服务，将 Python 环境版本导出，记录 ComfyUI 提交，备份 `user/`、自定义工作流与脚本。尽量在另一份代码和虚拟环境中验证新版本，沿用同一份模型目录，避免升级破坏唯一能工作的环境。

```powershell
& .\.venv-cu130\Scripts\python.exe -m pip freeze
git -C .\ComfyUI rev-parse HEAD
git -C .\ComfyUI status --short
```

不要对有个人改动的代码目录盲目执行 `git reset --hard`。恢复 Python 包前，先确认没有正在运行的服务，再按 CUDA13 锁定依赖重建环境；版本锁里的 `+cu130` 必须能从 PyTorch CUDA 13 源获取。

```powershell
& .\tools\uv.exe pip install --python .\.venv-cu130\Scripts\python.exe -r .\docs\requirements-cu130-sage-lock.txt --extra-index-url https://download.pytorch.org/whl/cu130 --index-strategy unsafe-best-match
```

这里的版本锁安装命令用于已有 `.venv-cu130` 的依赖恢复。项目自带 Python 3.12.14，位于 `tools/python/`，不依赖 Codex 的缓存解释器。若 `.venv-cu130` 损坏或移动了整个项目，先停止使用它的本项目 Python 进程，再运行 `repair-environment.ps1`，它会使用项目解释器重建虚拟环境并恢复 CUDA13 锁定依赖。该修复脚本的恢复路径不等同于已实测的全新系统安装。`requirements-lock.txt` 及旧 doctor 报告保留为历史 CUDA12.8 证据，不再由当前修复入口安装。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\repair-environment.ps1
```

磁盘维护：定期清理不需要的输出和日志；确认模型已校验后再清理下载缓存。不要在下载运行时删除 `.part`/`.aria2`。不要删除模型目录后以为界面会自动补齐。Windows、驱动或 PyTorch 升级后，先跑固定测试，再做正式生成。

服务只监听 `127.0.0.1:8188`，默认关闭云端 API 节点与自定义节点；1080p 专用启动方式通过 `-KJNodes` 白名单启用 KJNodes。下载模型和安装依赖需要联网，生成工作流使用本地权重。不要为了方便随意改成公网监听。

## 8. 后续提速顺序

以下为最初部署时的升级顺序。当前驱动与内存已升级，CUDA 13、SageAttention、Ref2VA INT8 ConvRot 均已安装，后续操作先参考新实测文档，不需重复升级驱动。

1. 保持当前基线和输出，先记录完整单次耗时。
2. 在准备好升级驱动的维护窗口安装 NVIDIA 官方适配 RTX 5080 的新驱动，重启后确认正常。CUDA 13 系列要求 R580 或更新驱动家族，具体版本还要符合所选软件包要求。
3. 在另一个虚拟环境试 CUDA 13 的 PyTorch，使用 `pruned_int8_convrot` 主模型；不要把 FP8 文件重命名成 INT8。
4. 确认量化和卸载有效，再考虑匹配 Windows/Python/PyTorch/CUDA 的 SageAttention。每次只改一个变量，用相同种子比较速度与画面。
5. 如果实际瓶颈是系统内存压力，再评估内存扩容；如果瓶颈是显存与 PCIe 卸载，增加内存不能把 16GB 显卡变成大显存卡。

2026-09-13 已完成驱动升级、独立 CUDA 13 环境安装、SageAttention 算子测试及 10 秒原生 1080p 双图生成；完整证据见新增 [1080p 记录](test-1080p-48gb.md) 为准。不承诺固定加速比例或逐像素质量等价。

## 9. 参考资料

- [MiniMax 官方模型与基础能力](https://huggingface.co/MiniMaxAI/MiniMax-H3)
- [Comfy-Org 模型文件与量化选择](https://huggingface.co/Comfy-Org/MiniMax-H3)
- [ComfyUI H3 教程](https://docs.comfy.org/tutorials/video/minimax/minimax-h3)
- [ComfyUI 原生工作流说明](https://docs.comfy.org/tutorials/video/minimax/minimax-h3-native)
- [ComfyUI 官方源码](https://github.com/Comfy-Org/ComfyUI)
- [NVIDIA CUDA 驱动兼容](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html)
- [aria2 官方续传说明](https://aria2.github.io/manual/en/html/aria2c.html)

开放权重不等于无条件商用。用于商业项目或对外提供服务前，应核对下载仓库当前许可证及官方商业授权要求；本手册面向本机个人部署验证。
