> **成片补充（2026-09-16）：** 镜头预算/恢复见 [h3-agent-production.md](h3-agent-production.md)，剪辑/字幕验收见 [video-editing-workflow.md](video-editing-workflow.md)。先复用已有视频与声线，按真实语音时长排 cue；必要音轨缺失必须失败。音频数值通过不代表听感或字幕同步通过。

# 本机音频工作流：音效、配乐、人物声音与现有视频混音

用户已批准按 `audio-film-model-proposal.md` 的主方案实测，不重新生成视频。本文记录本地调用与维护；最终听感由用户试听确认，`success` 只表示执行和文件检查通过。

## 环境与文件布局

- Windows，RTX 5080 16GB，系统内存 48GB。
- 原 H3 环境 `.venv-cu130` 保留原状。
- `audio/env-sfx`：MOSS-SoundEffect v2，Python 3.12，torch 2.9.0 CUDA12.8，transformers 4.57.1。
- `audio/env-tts`：Qwen3-TTS VoiceDesign / Base，Python 3.12，torch 2.9.0 CUDA12.8，transformers 4.57.3。
- `audio/env-music`：ACE-Step 1.5 SFT，Python 3.12，官方 Windows torch 2.7.1 CUDA12.8，transformers 4.57.3。
- 上述配置已在本机实测通过；精确版本以 `docs/audio-environments/` 导出的清单及每个阶段 `stage.json` 为准。
- 权重放在 `audio/models/`，来源和文件 SHA256 在各目录的 `snapshot-verified.json`，固定版本目录在 `docs/audio-models/`。

代码固定版本：

| 上游 | Git commit |
|---|---|
| OpenMOSS/MOSS-TTS | `934d6826b084c46a0d033402174d5f8ac4ed2519` |
| ace-step/ACE-Step-1.5 | `ca1e85fe9430179831e6bc6be790c332190a3866` |
| QwenLM/Qwen3-TTS | `022e286b98fbec7e1e916cb940cdf532cd9f488e` |

模型续传命令（已存在的文件也会重新校验，不会重复下载）：

```powershell
.venv-cu130/Scripts/python.exe scripts/audio_download.py OpenMOSS-Team/MOSS-SoundEffect-v2.0 --dest audio/models/moss-sfx
.venv-cu130/Scripts/python.exe scripts/audio_download.py Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign --dest audio/models/qwen-design
.venv-cu130/Scripts/python.exe scripts/audio_download.py Qwen/Qwen3-TTS-12Hz-1.7B-Base --dest audio/models/qwen-base
.venv-cu130/Scripts/python.exe scripts/audio_download.py ACE-Step/Ace-Step1.5 --dest audio/models/ace --include Qwen3-Embedding-0.6B --include acestep-5Hz-lm-1.7B --include vae
.venv-cu130/Scripts/python.exe scripts/audio_download.py ACE-Step/acestep-v15-sft --dest audio/models/ace/acestep-v15-sft
```

下载器复用 `docs/audio-models/` 内的固定版本目录，默认代理7897，可用 `--proxy` 改地址。不要删除目录清单后再下载并声称仍是原版本。

依赖修复应先创建新的 `audio/env-*-repair` 环境，用对应的 `docs/audio-environments/*-freeze.txt` 恢复；torch 的 `+cu128` 包需要 `https://download.pytorch.org/whl/cu128` 索引。清单中本地 editable 路径指向本项目上游源码，搬动工程时需要同步更改该路径。

首次安装时先单独装对应 torch/torchaudio（SFX、音乐还装torchvision），再安装其他依赖。SFX采用其 `moss_soundeffect_v2/pyproject.toml`，TTS采用Qwen项目依赖，音乐采用 `configs/audio-music-requirements.txt`；后者只包含此推理路径所需依赖。`configs/audio-torch-excludes.txt` 可在安装这些包时通过 uv 的 `--excludes` 防止替换已经安装的CUDA版torch。初次安装清单和最终freeze的角色不同，维护时以实测freeze为准。

## 运行入口

在项目根目录运行，使用新目录保存一个新版本：

```powershell
.venv-cu130/Scripts/python.exe scripts/audio_film_pipeline.py --config configs/audio-film-test.json --run-dir runs/audio_film_test
```

只运行一类可加 `--only design`、`--only clone`、`--only sfx`、`--only music` 或 `--only mix`。声音复用依赖已经生成的设计声音；混音依赖所有对应音轨。相同目录、相同输入重跑会校验音频 SHA256 并跳过已完成项目。修改提示词、种子或模型后使用新目录，避免把新旧素材混为一版。

阶段按顺序独占 GPU，每阶段用独立进程，退出后释放模型。入口会检查 ComfyUI 队列，有其他任务时退出，不抢占其工作。运行前也应关闭自己不需要的其他显存占用程序。

## 配置与输出

`configs/audio-film-test.json` 保存全部文本、种子、时长、步数、模型目录以及原视频哈希。可从该文件复制新版本。每段音频附带同名 JSON，包含输入、模型版本、输出哈希、真实时长、采样率、声道数、生成用时、显存分配峰值及波形检查。

| 目录 | 内容 |
|---|---|
| `design/` | 三种虚构设计声音，朗读同一段中文 |
| `clone/` | 使用年轻成年女声母版生成的三句不同台词 |
| `sfx/` | 风、鸟、水各两版，以及一个提灯与木桌接触音效 |
| `music/` | 两段30秒器乐配乐及 ACE 原始输出和参数 |
| `mix/` | 风、鸟、音乐、旁白、接触声分轨，master.wav，试听 MP4，原 H3 音轨 |

保留原始 float WAV，不用峰值归一化覆盖模型输出；混音分轨和 master 用48kHz、24-bit PCM，视频中的音频为AAC。MOSS 原生单声道；放入立体声混音时复制到左右声道，不冒充原生立体声环境录音。Qwen 的采样率以返回值记录，混音阶段重采样。

`stage.json` 保存模型加载时间和阶段总时间、每两秒一次的进程RAM/整卡显存采样。整卡显存含桌面和其他进程，不等于模型自身占用；torch allocated/reserved 峰值仅描述该进程的 PyTorch 分配。采样可能漏过极短峰值。

## 设计声音与复用

VoiceDesign 输入 `text + language + instruct`，用文字描述年龄感、性别、音区、沙哑程度、语速和讲述方式。年龄是听感目标，不是精确数值约束。样本未通过听审前，不能声称准确实现了指定年龄、性别或表演。

Base 阶段用设计样本 WAV 和其准确文字创建 `voice_clone_prompt`，三句台词共享同一个提示。更换声音母版时同时更换文本，不能拿不同内容的文字去配已有音频。母版和哈希是角色声音资产；仅重新使用描述提示词并不能保证生成相同声线。

Base 的声音复用接口不等于 CustomVoice 的逐句 `instruct` 控制，本轮不承诺每句可精确改情绪。这里是画外音，不是人物对白口型测试。

## 运行参数和兼容处理

MOSS：100步、CFG4、sigma shift5，默认实际生成30秒再裁出请求长度。10秒请求不能按三分之一时间估算。关闭 torch.compile，使用上游分阶段CPU卸载，使文本编码器、DiT和VAE轮流占显存。VAE保留上游浮点路径，不盲目全模型半精度转换。

Qwen：BF16、PyTorch SDPA、逐条生成，不强制安装 FlashAttention。

ACE：SFT 2B、1.7B音乐LM、50步、CFG7、单条30秒、纯器乐，LM后端 `pt`，开启CPU卸载、不量化、不编译。独立安装推理依赖，训练、nano-vLLM、MLX和torchao不是本轮必需组件。

ACE 上游的“共享权重存在”预检查还要求默认 Turbo，即使选择了 SFT。封装在当前进程内将共享检查限定为 VAE、文本编码器和所选 LM；SFT 仍由原有检查独立验证。没有下载额外 Turbo，也不伪造其目录或权重。上游如同步模型目录内的 Python 文件，需要记录实际运行代码和哈希，不能把下载时的代码清单冒充同步后的清单。

## 混音与原视频保护

固定原视频为 `white_reference_demo_h3_768p_00001_.mp4`，1344×768、243帧、24fps、10.125秒。输入 SHA256：`2004fc371f8bd6080cc018a23966500169a899e00902141dc73d616d24adcd89`。

只提取视频流并直接复制，不重新渲染画面。混音完成后比较前后压缩视频流的 SHA256，必须相同。原 H3 音轨另外导出供比较，不叠加到新混音里。

首版用风、鸟、安静神秘配乐、年轻女声旁白和一次提灯接触声。水声只供独立试听。接触点根据画面取约7.9秒，再对齐生成音效的能量峰，属于可审阅的初版定位，不是已解决所有动作同步的模型。混音有旁白期间的轻度配乐压低、首尾淡入淡出和峰值余量；最终响度报告单独保存，不把指定目标当成已测结果。

## 常见错误和恢复

- **Hugging Face 超时 / SSL握手失败**：检查本地代理 `http://127.0.0.1:7897`；重新执行相同下载命令，保留 `.part` 与 `.aria2` 继续下载。不要通过关闭证书验证解决。下载器会校验文件长度、LFS SHA256或Git blob hash，全部通过才写完成清单。
- **uv 等待 torch 缓存锁超时**：另一个环境正在下载相同的大 wheel。等首个安装完成后重试，不删除正在使用的锁或缓存。不同环境不应同时更新同一个安装目录。
- **显存不足**：先确认没有别的 GPU 任务；一次一个模型阶段、batch1、CPU卸载、关闭编译。不要降低原H3参数或改原环境来解决音频问题。保留失败日志，重启该音频进程后续跑。
- **缺少依赖 / 版本不匹配**：先确认调用的是对应 `audio/env-*` 的 Python。不要在 `.venv-cu130` 里全量安装音频项目的依赖。
- **声音太长**：缩短台词后在新目录生成，不直接截掉台词尾部。首版旁白过长时选择已生成的短句；若仍过长则明确报错。
- **旁白念错字 / 声线漂移 / BGM出现人声**：这些需要听审，成功退出不是通过。换提示词或种子生成新版本，保留旧版以便比较。
- **素材或配置变更**：使用新 `--run-dir`。被修改或损坏的输出不通过复用哈希检查；已更改输入则拒绝覆盖旧版。

## 后续 agent 的维护约定

1. 先读本文件、配置与目标 run 的 `manifest.json`，区分“准备好”“执行成功”“用户听审通过”。
2. 不重新生成视频；如下一任务需要生成画面，使用项目原有三张参考图工作流，另获该任务授权。
3. 不自动升级三个上游仓库、transformers、torch、CUDA依赖。升级放到新环境、新模型版本目录，先做一条回归试听，再考虑替换。
4. 保留配置、模型清单、环境清单、日志、原始音频、分轨和最终输出。缓存可重建，母版和工程记录需要备份。
5. 最终电影流程可让 agent 编排镜头、台词、音效事件、配乐和混音，但本次短片测试不证明长片音乐发展、跨镜头连续性或对白口型已经解决。

## 本机实测结果（2026-09-13）

主方案已全部跑通：15段独立生成音频、5条混音分轨、一段10.125秒试听视频。所有音频均通过时长、文件哈希、非静音、有限数值检查；15段原始生成音频均没有超过满幅的样本。最终视频解码确认1344×768、24fps、243帧，压缩视频流哈希与原视频一致。完整记录见 `runs/audio_film_test/validation.json`，试听见该目录 `LISTEN.md`。

| 模块 | 生成结果 | 单条生成耗时，不含加载 | torch allocated 峰值 |
|---|---|---|---|
| MOSS音效 | 6条10秒环境声 + 1条5秒接触声 | 17.8–23.4秒 | 8.28GiB |
| Qwen声音设计 | 3条，8.00/8.64/11.20秒 | 12.7–19.5秒 | 4.22GiB |
| Qwen声音复用 | 3条，4.64/6.08/6.48秒 | 7.4–11.1秒 | 4.39GiB |
| ACE配乐 | 2条30秒、48kHz立体声 | 21.4秒 / 17.2秒 | 5.01GiB |

| 阶段 | 本次加载时间 | 加载+生成总时间 | 整卡显存采样峰值 | 进程RAM采样峰值 |
|---|---|---|---|---|
| 声音设计 | 54.8秒 | 100.9秒 | 6.46GiB | 2.56GiB |
| 声音复用 | 6.8秒 | 35.7秒 | 6.94GiB | 3.54GiB |
| 音效 | 12.3秒 | 144.9秒 | 11.29GiB | 13.92GiB |
| 配乐 | 21.5秒 | 60.3秒 | 6.91GiB | 17.32GiB |

加载耗时受首次模块导入、系统文件缓存和磁盘影响；这不是严格控制冷/热缓存的跨模型性能排名。整卡占用包括Windows桌面等，表中torch峰值仅是该音频进程的分配，二者不要混用。

初版混音使用6.08秒的 `narration_1`，从0.4秒开始，全文为“风穿过叶间，我提起旧灯，仿佛唤醒了温室的记忆。”使用安静神秘配乐的前10.125秒，音乐完整30秒版本另外保留。接触声从原始样本约3.28秒处取片段，能量峰对齐约7.90秒。

Master实测响度为 **-19.41 LUFS**，真峰值 **-6.72 dBTP**；最终AAC解码样本峰值约0.460，未削波。`loudness-analysis.txt` 中 `input_*` 是已交付master的测量值，`output_*` 是分析滤镜的虚拟输出，未写入成片，不应当成实际master指标。

试听MP3做了有峰值上限的音量调整，便于比较，特别是原始接触声音量偏小；所有原始WAV和成片混音均另行保留。静音/削波检查不能证明音效语义准确、音乐绝无人声或角色声线完全一致，仍需用户听审。当前所有素材标为 `pending_user_review`。

## 本次实际遇到的兼容细节

- Hugging Face 多次SSL握手失败，断点续传和重试后全部完成，没有关闭TLS校验。Python普通依赖改为直连PyPI后完成安装。
- 两个环境同时取同一个torch wheel触发uv缓存锁超时；等首次下载完成后，第二个环境用本机缓存离线装好，无需重复下载。
- Qwen 导入时提示系统缺少SoX、未安装flash-attn，但本次12Hz VoiceDesign/Base采用SDPA路径，6条语音均成功。没有为无关25Hz处理路径额外安装SoX。
- ACE提示没有LyCORIS、Lightning、bitsandbytes；这些属于未使用的训练/适配器路径，本轮原生SFT推理不受影响。
- ACE首次启动自动将3个模型目录内Python文件同步为固定Git commit的版本。`snapshot-verified.json` 保留下载时的来源清单；**当前运行代码的实际哈希在 `docs/audio-environments/inventory.json` 的 `runtime_ace_model_code`**，不能把这3个文件的下载哈希当成当前运行哈希。权重文件没有修改。
- 因此，在已运行的ACE SFT目录重做下载校验，3个Python文件可能报“Git blob hash mismatch”，这是已记录的代码同步，不代表权重损坏。若要恢复纯下载快照，应先备份这3个Python文件，再单独重新下载它们；再次初始化时上游会按当前固定Git版本同步。其他文件的哈希不匹配仍应按异常处理。
- 实际续跑验证已完成：相同配置重跑跳过15条已验证生成音频，重建混音、试听目录并再次通过完整检查。未重新调用H3。
