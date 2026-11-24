---
name: h3-local-storyboard
description: 将定稿剧本或 Seedance 分镜适配为本仓库 ComfyUI H3 的本地提示词和有序参考清单，供导演台或 h3_batch.py 使用。用于本地 H3 分镜适配，不执行生成、不承诺云平台音视频编辑能力。
---

# 本地 H3 分镜适配

输入是用户已定稿的剧本、分镜和现有资产。保留原稿、对白、信息增量、镜头编号与人物关系；生成独立的 H3 版本，不覆盖 Seedance 原稿。前期创作可继续在 Trae 完成。

先读 `docs/h3-agent-production.md`。正式视频只能由 `scripts/h3_batch.py` 生成。本技能仅规划，不修改 campaign、预算、STOP 或服务配置。

## 能力与流程规则分开

- 当前本机 `MiniMaxH3ReferenceToVideo` 节点支持 **0–9 张图**，本地批处理 Ref2VA 入口要求 **1–9 张**；三张是先前温室案例的默认流程，不是模型上限。多人物镜头可以列两个人物、一个场景、一个道具，不应为凑三张删掉角色。不要为没有人物或道具的镜头硬塞无关资产。
- 独立资产库可含人物正/侧/背三视图；每镜只选择需要的视角。不要把三视图作为三个人写进画面。
- 保留当前默认三图流程。用户明确采用导演台的逐镜可变参考时，任务配置记录 `reference_policy=variable_1_to_9`，执行由导演台通过 `--allow-reference-override` 显式传达选择；不可为了掩盖错误自动删图、改标签或放宽预算。
- 本项目 `generate.graph()` 目前只接静态图；底层节点虽有视频、音频输入，脚本未接线也未完成相应验收。不要输出依赖 `@视频` 或音色克隆的可执行任务。
- Ref2VA 的构图参考不是 FL2VA 首帧硬约束。原 Seedance 首尾帧镜头单独标注待适配；不要默默冒充同一能力。
- 默认 1344×768、24fps、单次请求不超过15秒；10秒请求会对齐到243帧/10.125秒。多图额外消耗显存与时间，9图是接口上限，不是本机满载稳定性承诺。

## 输出契约

对每镜输出：稳定 shot ID、原镜编号、时长、场景、必须送达的信息、H3 提示词、**本镜有序资产 ID 列表**、声音处理方案、验收项目、待人工解决事项。资产文件未生成时给稳定资产 ID，不伪造文件路径。生成后由导演台解析成真实路径和 SHA256。

正文 `<Picture 1>`…`<Picture N>` 必须与本镜上传顺序逐一对应；全局的 C01/S01/P01 是资产 ID，不是模型的 Picture 编号。定义参考职能：身份、服装、环境、道具或构图。每镜自包含，不依赖“上一镜”记忆。

按官方 Ref2VA 指南整理：`subject_definitions`（人物/物体/环境从哪张图来）、`summary`、`retention_analysis`、`detailed_description`、`overall_soundscape`、`non_diegetic_music`。这是官方推荐的提示结构，不是 ComfyUI JSON 节点的额外输入字段。人物可写成 `<Subject 1> is the woman in <Picture 1>...`，Picture 指向文件，Subject 指向语义主体。

优先英文视觉描述，保留原语言台词和画面文字。单个连续镜头描述清晰的起始构图、动作过程、结束状态。若确需多镜段，写 `[Shot 1]`、`[Shot 2] At MM:SS.mmm`；不默认把长对白压进短镜，也不随意删台词换时长。

声音方案需明确：原生台词用稳定说话人 ID 与官方 `<d>[Chinese] 原台词</d>` 格式；后期配音则在交接清单中完整保留台词，视觉正文不诱发重复配音。字幕/手机UI/纸面关键信息保留为后期必达项；不能把“中文生成能力”当字字准确保证。

## 与自动审片衔接

每镜给可观察的验收条件，例如“恰好两人；陈默左、沈宁右；沈宁把文件夹放在右侧桌面；玻璃门位于右后方”。条件不能只是“电影感好”。审查输入包括实际参考图与视频时间码抽帧；看不到/听不到的事项标记未验证。Agent 可以建议完整修订提示词，但实际重做仍计入原 campaign 与原 shot 的两次总提交预算。

## 依据

- [官方 H3 模型规格](https://huggingface.co/MiniMaxAI/MiniMax-H3)：Ref2VA 最多9图；完整 Context-IR 编排服务未随模型开源。本技能提供可检查的适配流程，不宣称复刻官方服务或保证质量等同云端。
- [官方 Ref2VA 提示指南](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md)
- 本机源码：`ComfyUI/comfy_extras/nodes_minimax_h3.py` 的 `MiniMaxH3ReferenceToVideo`；脚本规则：`scripts/h3_batch.py`。
