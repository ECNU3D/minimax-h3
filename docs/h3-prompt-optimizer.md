# H3 官方 Skill 提示词优化

入口：导演台分镜详情，以及独立「分镜测试」的提示词编辑区，点击「DeepSeek 优化提示词」。

上游为 MiniMax-AI 官方仓库的 [h3-prompt-writing](https://github.com/MiniMax-AI/MiniMax-H3/tree/main/skills/h3-prompt-writing)。官方 skill 和 `references/ref-en.txt`、`references/base-en.txt` 原文保存在 `h3_director/agent/skills/h3-prompt-writing/`；`source.json` 记录下载来源、时间和逐文件 SHA256。文件按内容哈希固定，不自动跟随上游更新。每次优化都复制本次指南，避免等待过程中内容变化。

该 skill 是提示词规范，不需要调用 MiniMax 云端生成 API。优化固定使用现有 `.env` 的 DeepSeek 配置，复用受限的 Agent runtime，不受项目选择 Codex 或 DeepSeek 审片的设置影响。不会运行工具或生成图片、视频，不变更生成预算。

官方正文规范使用英文。本地默认保留用户的中文编辑偏好，可选 English，英文 section 名保持不变，台词保留原文。当前本地工作流为 Ref2VA，输出固定为六段。无参考的实验仍沿用本地 Ref2VA 图，不引入首帧或尾帧模式。只提供文字和参考素材的文字描述，不声称看过图像或听过音频。

操作：

1. 先保存当前内容并请求优化。DeepSeek 返回后，原文与候选并排显示，可查看逐行增删、修改说明和需人工核对的事项。
2. 点击「采用优化版」才替换提示词。测试区一起替换画面、环境音、配乐及对应语言版本；种子、时长、参考顺序、现有素材与 campaign 保持不变。
3. 已采用记录可点击「回退到优化前」。若之后修改过提示词、时长或参考素材，会拒绝直接覆盖，可先从对比中复制历史内容。

记录保存在 `h3_director/data/prompt-optimizations/<id>/`：原始输入、skill 副本、模型原始响应、候选、差异及日志。素材内还保存采用与回退历史。后台结果不会自动覆盖编辑内容，失败或重启中断也不会改写原文。排队和运行中的优化在服务重启后标为失败，需手动重新发起；不自动重复调用模型。

结构、参考标签和已有 `<d>` 台词有程序检查，但剧情、动作和语言意图的语义保真仍需用户比较，不保证生成效果一定提高。时间与资源配置不会被优化器修改。

验证包含：真实 DeepSeek 单人中文对白候选及采用/回退、独立浏览器对比/采用/回退、HTTP 接口与冲突回归。未提交视频。真实调用记录：`runs/h3-prompt-optimizer-smoke-1789997046/`。
