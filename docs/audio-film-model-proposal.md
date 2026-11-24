# 本地电影音频模型选型与测试提案

调研日期：2026-09-13。提案已获用户确认，正在按主方案实测，复用现有视频。本文保留选型时的依据；最新部署状态和实测结果见 [本地音频工作流](audio-local-workflow.md)。

硬件沿用本机已核实配置：RTX 5080 16GB、48GB RAM、Windows 11、驱动 591.86。现有视频环境为 torch 2.11.0+cu130、transformers 5.17.0。配音需求按“不同年龄感、性别、声线可控”理解。

## 1. 推荐决定

第一阶段采用三个功能模块：**MOSS-SoundEffect v2.0（音效）+ ACE-Step 1.5 2B-SFT（BGM/音乐）+ Qwen3-TTS 1.7B VoiceDesign / Base（角色声音设计与复用）**。视频沿用已有 Klein → H3 三参考流程。音频模型串行运行，不与 H3 同时占用 GPU。

这是基于能力、已公开权重、许可、硬件和自动化接口的优先测试方案，尚不是本机听感实测后的冠军。不能用各作者不同数据集上的分数拼出统一排名，也不将厂商 GPU 测速当作本机速度。

| 模块 | 默认模型 | 选它的理由 | 本机判断 |
|---|---|---|---|
| 风、鸟、水、脚步、碰撞等独立音效 | OpenMOSS-Team/MOSS-SoundEffect-v2.0 | 中英文描述；48kHz；最长 30 秒；模型卡标明 Apache-2.0；有 Python 推理入口 | 1.3B DiT 之外还有文本编码器/VAE；16GB 以 BF16、batch=1 作为待测配置，暂无本机峰值证据 |
| 无人声配乐及歌曲 | ACE-Step/acestep-v15-sft + 1.7B 音乐 LM | 可指定乐器、情绪、BPM、调性、时长和 instrumental；提供 Python/REST API 与 Windows 路径；MIT | 官方 12–16GB 档包含 2B 模型与 1.7B LM；使用卸载，优先标准 PyTorch 后端 |
| 原创角色声音与连续台词 | Qwen3-TTS-12Hz-1.7B-VoiceDesign + Qwen3-TTS-12Hz-1.7B-Base | 用文字设计声音，再从生成的样音建立可复用声音参考；两者 Apache-2.0 | 两个模型分时加载；1.7B 配置值得在16GB上测试，但不预报精确峰值或耗时 |

能力与许可来源：[MOSS 音效模型卡](https://huggingface.co/OpenMOSS-Team/MOSS-SoundEffect-v2.0)、[ACE SFT 权重](https://huggingface.co/ACE-Step/acestep-v15-sft)、[ACE 显存分档](https://github.com/ace-step/ACE-Step-1.5/blob/main/docs/en/GPU_COMPATIBILITY.md)、[Qwen VoiceDesign 权重](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign)、[Qwen Base 权重](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base)。

## 2. 音效：为什么不直接沿用旧榜单

MOSS v2 在 2026-05 已公开，是独立 DiT/Flow Matching 音效模型，不要误下载同名家族里旧的 8B 自回归音效模型。风、鸟、水适合分别生成，才能独立调音量、远近和位置。它是文本到音效，不自动知道“杯子在第 4.2 秒碰到桌子”；动作声需要按事件时间放置，或以后用视频条件模型生成。

| 候选 | 核实情况 | 本次取舍 |
|---|---|---|
| Stable Audio 3 Small SFX | 新版专用音效，约0.6B，支持生成和修补/续接；示例为8步；Stability 专用许可及 Gemma 条款，权重入口需接受条件 | **音效首要备选**；值得同提示词盲听比较，但不优先于明确 Apache 模型作为开源默认 |
| Stable Audio Open 1.0 | 44.1kHz立体声、最长47秒、英文提示词；Stability Community License | 保留兼容备选，新部署不只因教程多就优先旧版 |
| TangoFlux | 文本到音频，但当前官方 README 明示研究/非商业及数据相关限制 | 不作为通用发行工作流默认 |
| MMAudio large_44k_v2 | 文本或视频生成同步音频；官方约6GB、训练默认8秒；权重 CC-BY-NC 4.0，代码 MIT | 非商业同步实验有价值；不能把代码MIT当权重可无限制商用 |
| HunyuanVideo-Foley | 48kHz视频+文字拟音；官方 XL 卸载约8GB，XXL卸载约12GB；主要支持Linux；专用许可有地域限制 | **后续动作同步升级候选**，不在首轮安装；先保留 H3 原生音轨做对照 |
| Omni2Sound（CVPR 2026） | 已有代码/权重，统一文本/视频音效；代码和权重CC-BY-NC；参考环境较旧 | 研究备选，当前不增加一套视频音效运行环境 |

来源：[Stable Audio 3 Small SFX](https://huggingface.co/stabilityai/stable-audio-3-small-sfx)、[Stable Audio Open](https://huggingface.co/stabilityai/stable-audio-open-1.0)、[TangoFlux 官方许可说明](https://github.com/declare-lab/TangoFlux#license)、[MMAudio](https://github.com/hkchengrex/MMAudio)、[HunyuanVideo-Foley](https://github.com/Tencent-Hunyuan/HunyuanVideo-Foley)、[Hunyuan 许可](https://github.com/Tencent-Hunyuan/HunyuanVideo-Foley/blob/main/LICENSE)、[Omni2Sound](https://github.com/omni2sound/Omni2Sound)。这里记录项目条款差异，不作“所有生成内容必然无权利争议”的保证。

## 3. BGM 与音乐

默认用 ACE 1.5 的 **2B-SFT**，优先可调采样/引导与16GB余量；并非只追求最低步数。工程上先选32–64步范围中的官方推荐配置做30秒样本，以实测确定保留值。生成纯配乐明确设置 instrumental，避免模型自行唱歌。整场戏先生成一条较长音乐，再按镜头剪辑，避免每10秒重新作曲造成风格和乐句断裂。

ACE 已有 **4B XL**，不是不知道新版。官方将16GB列为需要offload的配置，20GB以上更宽裕；可作为后续画质优先的对比项。首轮不同时安装全部 ACE 变体。官方的 Turbo 亚秒/数秒宣传不能套到 SFT、长时长或本机。

HeartMuLa 3B 也公开了歌曲生成与单卡 lazy_load 路径，是偏歌曲/歌词任务的备选；当前以电影无人声BGM为主，ACE 的器乐参数、编辑与自动化接口更符合首轮需求。这是任务匹配判断，不是已盲听证明 HeartMuLa 更差。

来源：[ACE 官方推理参数](https://github.com/ace-step/ACE-Step-1.5/blob/main/docs/en/INFERENCE.md)、[ACE 官方选型](https://github.com/ace-step/ACE-Step-1.5)、[HeartMuLa 官方仓库](https://github.com/HeartMuLa/heartlib)。

## 4. 配音与声音锚定

角色外观母版之外，单独建立声音母版。建议先设计三个虚构声音：年轻成年女性、低沉中年男性、沙哑老年女性。年龄是听感描述，不是“输入45岁就精确得到45岁”的数值约束；性别、气声、沙哑、共鸣、口音、语速可以组合描述，结果仍需试听。

固定角色流程：VoiceDesign生成参考样音 → 保存样音、逐字文本和设计描述 → Base提取可复用voice clone prompt → 后续各句使用同一声音参考。官方已有这条工作流。不要每句话都重新执行VoiceDesign，否则声线可能漂移。[Qwen 官方 Design then Clone](https://github.com/QwenLM/Qwen3-TTS#voice-design-then-clone)

必须区分三个版本：VoiceDesign 是原创声音设计；Base 是参考声音复用；CustomVoice 是预设说话人和指令控制。**不能把 CustomVoice 的逐句 instruct 能力，直接当成 Base 对任意克隆声音都提供的同等接口。** 首轮重点验证声音差异、中文准确度、跨句一致性和停顿；强烈表演情绪另做对比，不承诺任意克隆声音都能精确哭笑怒吼。

| 候选 | 适用方向与本次取舍 |
|---|---|
| MOSS-VoiceGenerator 1.7B | 中英文自由声音设计与情绪风格，Apache家族；是 Qwen 声音设计的第一对照候选，不因同用MOSS音效就假定两者可共用环境 |
| CosyVoice 3 | 中文/方言、读音修正、参考声音、情绪/语速指令；若配音重点转为中文戏剧表演，优先加测它 |
| IndexTTS 2.5 | 已于2026-08公开，支持情绪与读音控制、duration_factor；当前采用bilibili模型使用许可，不能照搬旧教程写Apache。语速因子也不等于绝对时码口型对齐 |
| Fish Audio S2 Pro | 强项是细粒度表达及多说话人对话；当前代码/权重为Fish Audio Research License，非本次宽松许可默认 |

来源：[MOSS VoiceGenerator](https://huggingface.co/OpenMOSS-Team/MOSS-VoiceGenerator)、[CosyVoice 官方仓库](https://github.com/QwenAudio/CosyVoice)、[IndexTTS 当前版本与许可](https://github.com/index-tts/index-tts)、[Fish Speech 当前许可与能力](https://github.com/fishaudio/fish-speech)。

## 5. Agent 自动化工作流设计

采用一个编排入口，分别调用图像、视频、配音、音效和配乐模块。保持每个镜头的JSON清单与独立音轨，不建一个所有模型同时常驻的大服务。

1. Agent生成剧本、角色表、分镜表和声音事件表。每个声音有角色/类别、提示词、起止时间、音量、声像和产物路径。
2. 生成角色外观及声音参考，场景与道具图仍遵循已确认的白底三参考方案。
3. 有对白的镜头先生成台词并测量实际长度，再确定镜头时长；避免视频结束后强塞一长句配音。旁白可以放在不要求口型的画面上。
4. H3按镜头生成视频。保留原音轨，后期可选择保留、降低或替换；避免原音和新拟音同一事件叠加。
5. MOSS按声音事件生成素材，连续环境音覆盖场景，短促事件按时间轴放置。生成时长不保证事件发生在指定毫秒，必要时检测起音后裁切/平移。
6. ACE按整场戏生成BGM；跨镜头沿用同一条音乐，需要时续接/重新配器，避免频繁风格跳变。
7. 对白、环境、动作、音乐分别存WAV，统一到项目48kHz后混音，做淡入淡出、对白期间配乐自动压低和防削波，最后编码交付视频。
8. 自动检查缺帧、时长、静音/削波、配音文本差异、重复片段和跨镜头资源引用；失败只重算对应阶段，保留seed、模型版本、输入和输出hash。语义/听感指标用于提示，不能把一个分数当作“电影级通过”。

“生成可听的配音”和“人物嘴型准确匹配这段配音”是两个任务。H3的参考音频也不能未经测试就当成精确口型驱动。后续可单独评估 [MuseTalk](https://github.com/TMElyralab/MuseTalk) 等口型处理，但要测试正脸、侧脸、遮挡和表情；当前不安装、不以旁白测试冒充对白口型已解决。

自动化能生成完整候选成片，但稳定的电影级结果仍取决于跨镜头人物一致性、动作和口型、表演、音乐发展与混音。可做有限次数的自动修订和完整记录，不能预先保证任意剧本一次成片。

## 6. 安装方式与兼容性（仅提案）

- MOSS-SoundEffect v2 官方单独锁定 Python3.12、torch2.9、transformers4.57、numpy1.26，与现有H3环境不一致。单独虚拟环境，先用官方CUDA12.8支持路径；不降级H3环境。
- MOSS默认有torch.compile/Triton，Windows首测关闭编译，确认数值结果后再决定加速；官方也说明可用TORCHDYNAMO_DISABLE处理编译问题。[官方环境说明](https://raw.githubusercontent.com/OpenMOSS/MOSS-TTS/main/moss_soundeffect_v2/README.md)
- ACE官方有Windows脚本和REST接口。本机ComfyUI源码也已具备ACE1.5原生节点，但这只证明接口存在，不代表完整音乐能力均已测试。首轮优先官方Python/API接口，必要时再保存Comfy图。
- Qwen用独立环境、逐个加载模型，先验证可用的PyTorch注意力实现；不把现有H3的SageAttention当成TTS的通用插件。FlashAttention不是首测的强制前置。
- 三个模块轮流占GPU，完成即卸载/退出。运行时记录真实峰值、耗时、冷启动和热启动区别。尚未给出任何本机音频生成速度结论。
- 确认后才固定当时仓库revision、文件清单与SHA256，并下载所需权重；不自动拉取全部备选模型。

## 7. 请求确认的首轮测试范围

首轮只安装主方案，复用已有10.125秒温室视频，不重新生成视频画面。

| 测试 | 交付 |
|---|---|
| 音效 | 风、鸟、水各10秒，每种2个seed；另做一个短促金属/木桌接触声 |
| BGM | 安静神秘、紧张悬疑各30秒无人声配乐，检查有无意外唱词和明显断裂 |
| 声音设计 | 3种不同年龄感/性别/声线，读同一段中文，便于比较 |
| 声线复用 | 选一条设计声音，连续生成3句不同台词，检查跨句一致性和中文读音 |
| 最小混音 | 用温室视频加入合适环境声、动作声、一句画外音和BGM；保留所有独立音轨。水声作为独立试听，不因测试有水声就硬塞进无水画面 |
| 自动化交付 | 一个调用入口、配置示例、素材清单、运行日志、资源测量、恢复方法、混音结果与完整文档 |

测试结果交给用户听后再确定默认声线和音乐风格。首次确认不包含安装Stable Audio 3、Hunyuan Foley、MOSS VoiceGenerator、CosyVoice、IndexTTS、Fish或口型模型；若主方案某项不达标，再提交对应替换建议。
