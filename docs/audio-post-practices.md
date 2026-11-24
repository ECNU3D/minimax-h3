# 声音后期参考与实践

核对日期：2026-10-05。本轮对象为《预制爱》H3 成片 v2；原声和旧成片保留。

## 可复用的可靠参考

1. [Blackmagic 官方 DaVinci Resolve / Fairlight 培训](https://www.blackmagicdesign.com/products/davinciresolve/training)：含音频后期、声音设计、混音、配音与 ADR 的课程和练习资料。用于组织对白、环境、音效和音乐分轨、建立完整混音与验收流程。
2. [Adobe 官方音乐 ducking 文档](https://helpx.adobe.com/premiere/desktop/add-audio-effects/adjust-volume-and-levels/automatically-duck-audio.html)：对白驱动的音乐避让、关键帧和衔接速度可调整。用于让音乐在对白下自然降低，而非切断重启。
3. [Mixkit 音乐库及官方 FAQ](https://mixkit.co/free-stock-music/)与[许可页](https://mixkit.co/license/)：提供真实可试听、可下载曲目。FAQ 列明网络视频、社媒、播客等用途；不适用于 CD、DVD、游戏、电视与广播。这里记录本片网络／本地试片用途，不能把该许可描述成所有渠道通用。
4. [MiniMax 同步语音官方文档](https://platform.minimax.cn/docs/api-reference/speech-t2a-http)：本次经用户指定，用 API 为缺失呼唤补录，保留请求、字幕时间与响应追踪记录。

检索到社区 [design-sound-mix-plan skill](https://github.com/jeffreytse/grimoire-core/blob/main/skills/film/editing/skills/design-sound-mix-plan/SKILL.md)，其中分轨、对白优先、上下文试听可作流程参考；没有证据把它称为“经典行业标准”，未安装或执行其中代码，也不采纳未核实的声学数字。官方教程作为主要依据。

## 本片的具体应用

- 旧版问题：三段独立 ACE-Step 配乐被多次截取、叠加程序生成的钢琴／口哨、额外重击，再按场景多次归零。技术上能输出，音乐却缺少连续发展的基础。
- v2：使用 Eugenio Mininni 的《Silent Descent》（Mixkit 614；目录标注钢琴、弦乐、内省／忧郁）一个连续源段。音乐时间线 11.5–132.875 秒，源时间 0–121.375 秒；雨中 97.75–104.75 秒静音，但源时钟继续，之后从同一位置自然接续。开头和结尾保留原声。
- 默认音乐在对白下降 8 dB，用渐变包络恢复；这一数值仅为本次起点，不代表已通过听音验收。
- 删掉旧版所有外加的合成配乐、合成口哨与额外冲击声；环境和动作声来自现有 H3 音轨。原素材中的口哨保留，但不能宣称满足“同一主题固定跑调／准音”的旧要求。
- 母亲 V05、V06、V09 保留 H3 原声；父亲 V01 也恢复原声，避免与恢复的底轨双重发声。原声过剪点时保留声音尾部。少年和来访者沿用既有 Qwen3-TTS 旁白。
- 仅 V02、V10 缺失呼唤用 MiniMax speech-2.8-hd。正文“澈澈，洗手吃饭。”只生成一份母带，首尾复用，尾句降低 1.5 dB；使用系统音色，不宣称克隆了 H3 母亲。
- 字幕从干净画面母版重烧，保持原剪辑 3555 帧；原声活动区间和 API 时间分别注明来源。信号活动检测不等于 ASR 或人工听审。

## 验收边界

逐项记录视频完整解码、声音有限值与峰值、响度、实际中文字形边界和抽帧。听感、台词可懂性、原声与补录的音色差异仍需实听；不得仅凭上述数值宣布接受。交付包含成片、三条分轨、MiniMax 母带、音乐试听和复现脚本。
