# 本地参考图 → H3 视频：Agent 调用手册

> **2026-09-16：批量生产入口已经收敛到 [固定脚本与停止协议](h3-agent-production.md)。** 本文用于参考资产及底层历史流程；不要从历史四参考实验推导当前默认，也不要用完整 pipeline 绕开视频预算。

> **最新默认入口：[白底三参考工作流](three-white-reference-workflow.md)。** 用户已指定白底人物 + 完整场景 + 白底道具，三图直接进入 H3；不抠图、不合成首帧。下文保留前期扩展方案的说明，涉及四参考/首帧合成的部分不适用于当前默认配置。当前目录为 runs/white_reference_demo。

更新时间：2026-09-13。工作目录：`C:\Users\shang\zheyu\minimax h3`。硬件为 RTX 5080 16GB、48GB RAM、驱动 591.86。这里记录本项目自己实现的工作流；不依赖付费 API，不下载运行第三方整套工作流。

> 实测结果见本文末尾。模型选择依据见 [image-model-selection.md](image-model-selection.md)，文件存在不等同于已验证成片。

## 1. 当前默认与历史方案

当前默认只有白底人物、完整场景、白底道具三张独立参考。缺失资产用本脚本 `--until references` 生成；视频由 `h3_batch.py` 复用锁定参考。每集不重新生成同一人物/场景。详见 [三参考流程](three-white-reference-workflow.md)。

### 以下为历史扩展实验，不是当前默认

FLUX.2 Klein 4B Distilled 负责母版/三视图/场景/道具，Klein 4B Base 负责三图构图合成和单图局部修正，H3 Ref2VA INT8 ConvRot 负责视频。模型串行运行，图像与视频阶段切换时请求释放 ComfyUI 模型缓存。原生节点足以完成图像部分；H3 使用此前已验证的 SageAttention 和 KJ 省显存补丁。混合选择来自本机比较：快速版首帧初稿曾产生两盏灯，Base 成功控制为一盏；详见选型文档。

1. 文生图生成一张人物正面母版。
2. 侧面、背面分别从同一母版编辑，组成前/侧/背三视图。
3. 文生图分别生成空场景和独立道具。
4. 用人物母版、场景、道具三张图合成首帧候选，再单图编辑得到构图参考。本次编辑误删了提灯，保留为人物/场景布局参考；不认定其完成了精确道具编辑。
5. 历史 H3 **全能参考**实验使用人物母版、场景、道具、最终构图四张图，生成 1344×768、243 帧 / 24fps = 10.125 秒视频；当前不采用此四图方案。

这里 768p 是 H3 原生 `1344×768`，没有低清放大或裁切。为了避免把角色三视图理解为三个人，不默认将三视图拼图直接输入 H3。侧/背图供设计核查，必要时才作为额外身份参考。首帧候选作为第四张构图参考并单独交付，但 Ref2VA 不把它钉为第一帧；如需首帧模式，使用另一套 FL2VA 权重和现有 `scripts/generate.py --image` 路径，不能把 Ref2VA 命名改成 FL2VA。

## 2. 启动

检查当前队列，避免打断其他生成任务。服务应运行在下列配置：

```powershell
Set-Location 'C:\Users\shang\zheyu\minimax h3'
$env:PYTHONUTF8 = '1'
# 如果已有服务但需要切换配置，先等待当前任务结束，再执行 stop.ps1。
.\start.ps1 -Cuda13 -SageAttention -KJNodes -VramHeadroom 8
```

也可双击 `start-1080p-sage.cmd`，名称来自前一次 1080p 实测，同样适用于本流程。服务已运行时 `start.ps1` 不会自动切换参数；需先执行 `stop.ps1` 再启动。只监听 `127.0.0.1:8188`。

## 3. 一条命令执行全部阶段

```powershell
.\.venv-cu130\Scripts\python.exe scripts/reference_video_pipeline.py --config configs/greenhouse-reference-video.json --run-dir runs/my_shot_001
```

如先只检查参考图：

```powershell
.\.venv-cu130\Scripts\python.exe scripts/reference_video_pipeline.py --config configs/greenhouse-reference-video.json --run-dir runs/my_shot_001 --until references
# 查看 runs/my_shot_001/assets/reference-board.jpg，检查人物、视角、道具与构图。
# 然后以同一 run-dir 执行第一条命令，已成功阶段会校验哈希并复用。
```

生成需要数分钟，保持服务和客户端运行。客户端每分钟输出进度，不因退出或超时自动停止服务器任务。

## 4. 机器可读输入

配置文件为 UTF-8 JSON，见 [示例配置](../configs/greenhouse-reference-video.json)。

| 字段 | 约定 |
|---|---|
| `image_variant` | `distilled`：4 步、CFG 1；`base`：默认 20 步、CFG 5。前五个阶段用快速版，构图与修正用 Base。 |
| `stages` | 按依赖顺序排列；每项有唯一 `name`、`prompt_file`、`width`、`height`、`seed`、`references`。 |
| `prompt_file` | 相对于项目根目录；支持 UTF-8 中文，示例用英文明确描述外观和动作。 |
| `references` | 图像阶段为此前阶段名称的有序列表；编辑提示词中的 Image 1/2/3 必须按该顺序解释。 |
| `variant` / `steps` | 可在单个图像阶段覆盖默认模型版本和步数。 |
| 图像宽高 | 16 的倍数。人物默认 768×1152；场景和首帧 1344×768；道具 1024×1024。 |
| `video.references` | 当前默认 `<Picture 1>` 人物、`<Picture 2>` 场景、`<Picture 3>` 道具；第四张构图仅属历史实验。 |
| `video.width/height` | 32 的倍数；本次 1344×768。 |
| `video.seconds` | 会按 H3 的 17k+5 帧数网格向上对齐；10 秒实际 243 帧 / 10.125 秒。 |
| `video.steps` | Ref2V Turbo 专用 LoRA 为 4 步，不要误用 FL2V 的 8 步 LoRA。 |
| `head_chunks/ffn_chunks` | 当前 4/8；仅改变计算分组，不是把时间序列切段。 |

更改角色时，先改人物母版描述，再同步侧/背编辑描述和 H3 的外观描述，避免提示词与参考图冲突。外观锚点用可观察特征：发型、服装颜色与结构、鞋子、独特道具形状；避免只给角色起名字来期待跨图记忆。

## 5. 输出契约

`--run-dir` 下：

```text
manifest.json                    当前状态、配置、模型固定版本/校验值、软件版本、每阶段产物、SHA256、原始提示词、任务 ID、耗时
config.snapshot.json             本轮配置快照
assets/character_front.png       正面身份母版
assets/character_side.png        母版参考编辑的侧视图
assets/character_back.png        母版参考编辑的背视图
assets/character-turnaround.png  前/侧/背全尺寸拼板（仅排版，没有另行生成身份）
assets/scene.png                 空场景
assets/prop.png                  独立道具
assets/firstframe_composite.png  有人物和一盏亮灯的首帧候选
assets/firstframe.png            实际送入 H3 的构图参考（本例桌上无灯）
assets/reference-board.jpg       六图概览
jobs/<stage>/job.json            ComfyUI history、API 请求哈希、输出文件与哈希
jobs/<stage>/workflow_api.json   该阶段可重放 API 请求
jobs/<stage>/resources.jsonl     约每 3 秒整卡资源采样（非精确瞬时峰值）
workflow_combined_api.json       合并后的完整依赖图
workflow_combined_editor.json    可视化平铺图
```

MP4 的实际绝对路径在 `manifest.json` 的 `video.path`。原始文件位于 `ComfyUI/output/video/`。视频完成后自动逐帧解码、检查音频数值，并生成同名 `.inspection.json` 与每秒一帧的 `.contact.jpg`；结果也写入 manifest 的 `video_inspection`。这不替代人工视觉检查或听音。可视化工作流也写入 `ComfyUI/user/default/workflows/Reference-to-H3-<run-dir-name>.json`。

状态为 `running` / `references_ready` / `success` / `error`。`success` 且 `video.path` 存在代表执行完成；画面是否接受另记 `review.json`，不能将执行成功等同于视觉合格。CLI 正常退出 0；异常非零，并将错误写入 manifest。单个任务保留 ComfyUI `prompt_id`，后续 agent 可通过 `/history/<prompt_id>` 查询。

**分阶段 CLI 是本轮验证的执行路径。** 合并图用于查看连接关系和可视化使用；全部图像同时参与单个大图时，缓存峰值可能更高，不能把导出的合并图当成已经另跑一次的证据。

## 6. 单独生图 / 编辑

```powershell
# 文生图
.\.venv-cu130\Scripts\python.exe scripts/generate_image.py --prompt-file prompts/reference-character.txt --width 768 --height 1152 --variant distilled --seed 20260913 --run-dir runs/my_character
# 用同一母版生成侧面（替换成真实输出路径）
.\.venv-cu130\Scripts\python.exe scripts/generate_image.py --prompt-file prompts/reference-side.txt --references runs/my_shot_001/assets/character_front.png --width 768 --height 1152 --variant distilled --seed 20260914 --run-dir runs/my_side
```

函数级入口：`generate_image.graph(...)` 构建 API 图；`workflow_client.run_job(graph, folder, url, force, timeout)` 提交并记录。H3 构图复用现有 `generate.graph(...)`。不用额外图像服务或 Diffusers 环境。

## 7. 断点与错误处理

- **客户端中断、服务仍在运行：** 原命令和原 `run-dir` 重跑，复用保存的 prompt ID 继续轮询；不会重复提交相同任务。
- **成功阶段重跑：** 校验请求指纹及文件 SHA256 后复用。修改了提示词、seed、模型、尺寸或输入内容时，用新的 `run-dir`；也可明确 `--force` 重算全部阶段。
- **只修正一个阶段：** 修改对应提示词或阶段配置后，用 `--force-stage firstframe` 只重算首帧；如该产物被后续阶段引用，也要明确重算受影响阶段。优先使用新目录保留完整比较记录。新版客户端会将强制重算前的 job/API/资源记录移到 `jobs/<stage>/attempts/<old-prompt-id>/`；若旧任务仍在队列里则拒绝重复提交。该参数可重复，例如 `--force-stage character_side --force-stage character_back`。
- **服务重启导致 history 丢失：** 客户端会明确报告 job disappeared。检查是否已有输出，确认无需保留在途任务后用新 run-dir 或 `--force` 重提，不能假装旧任务仍可恢复。
- **OOM：** 先看失败节点是文本编码、图像采样还是 H3。检查是否启动了正确环境/参数、是否还有其他显存任务；图像减少像素或参考数量，H3 保持已验证 768p 参数。不要仅凭剩余系统内存判断显存足够。
- **侧面没转过去、背面露出正脸：** 属于语义失败，即使服务 success 也不能当三视图合格。强化严格 90/180 度描述，尝试 Base 或换 seed，仍从原始母版编辑；记录修订，不覆盖“成功”判断。
- **人物脸或衣服漂移：** 原始母版作为主参考；不要由侧面继续生成背面。固定种子并不能替代图像条件。三视图只是视觉锚点，不保证三维几何闭合。
- **首帧人物/道具数量不对：** 明确 Image 1/2/3 各自角色和空间尺寸，避免三张参考里的背景被混入；必要时减少复杂动作。首帧质量与 Ref2VA 视频质量分别检查。当前例子有两个不同用途的构图产物：`firstframe_composite` 保留一盏亮灯，适合作为亮灯场景的首帧候选；`firstframe` 无提灯，只接受为 Ref2VA 的布局参考，提灯由第三张独立参考图提供。若要求首帧已精确包含全部道具，当前无灯版本不满足，需进一步编辑核查。
- **复杂合成忽略“不发光”或多出道具：** 本轮 Base 也出现过，不能把换 Base 当作保证。将多图构图与单图局部修正分开，检查真实图像后再生成视频；提示词中的否定词不代表约束已执行。
- **视频出现前景光带：** 保留失败样本；优先检查参考是否有发光或矛盾信号，加入干净构图参考并减少复杂光效。本轮修订同时改变了多个条件，不能据此确定唯一原因，也不能无证据归咎于 SageAttention 或量化。
- **下载失败：** `scripts/download_image_models.py --proxy http://127.0.0.1:7897` 断点续传并校验固定 revision 的 SHA256；代理端口变化时修改参数。
- **API 成功但响应体为空：** ComfyUI `/free` 正常返回空响应，客户端须接受空 body，不能强制解析 JSON。本轮发现并修复了这个客户端错误，参考资产生成记录得以复用，没有重复丢失工作。
- **停止：** API `/interrupt` 会影响当前任务，只在确认队列里是自己的任务时使用。不要因为 CLI 超时就直接杀整个服务器或其他 Python。

## 8. 依赖维护

首次配置图像权重运行 `scripts/download_image_models.py --proxy http://127.0.0.1:7897`（使用 `.venv-cu130` 的 Python）；下载清单共约 16.54 GB 十进制，包含两个扩散模型、一个文本编码器和一个 VAE。若没有此代理，省略参数并使用可访问的网络。`scripts/doctor.py` 可检查环境和文件大小，`--hash` 可全量校验，但需读取较多磁盘数据。

新增图像模型未要求升级 ComfyUI 核心或 Python 包。共用 `.venv-cu130`，软件基线见 [requirements-cu130-sage-lock.txt](requirements-cu130-sage-lock.txt)。KJNodes commit 见 [Sage 文档](sageattention-5080-research.md)。

图像权重清单：[image-models-manifest.json](image-models-manifest.json)，每项含官方 repo、固定 revision、源路径、安装路径、字节数、SHA256。下载完成的校验记录为 `image-model-verification.json`。不重命名不同格式的权重，不将 H3 的 Qwen3-VL-32B 编码器用于 Klein；Klein 使用独立 `qwen_3_4b.safetensors`，CLIP 类型 `flux2`，独立 Flux2 VAE。

更新前记录版本并保留一个已通过的 run；更新后先做小图编辑，再测视频。清理文件前先确认 manifest 是否仍引用它。PNG 内含生成元数据，分享时按需要决定是否保留提示词；所有计算在本机，安装/模型下载才联网。

## 9. 本次实测

结果整理中；原始任务记录保存在 `runs/greenhouse_demo`（第一版，有前景光带）及 `runs/greenhouse_clean`（修订版）。
