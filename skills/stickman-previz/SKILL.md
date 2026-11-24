---
name: stickman-previz
description: 把 Seedance/视频生成分镜提示词或自然语言分镜描述翻译成导演分镜台（director_board）的 ScenePlay JSON，用火柴人白模预演运镜与人物走位动作，导出分镜参考视频。触发场景：把分镜提示词导入导演分镜台、生成火柴人预演场景、ScenePlay JSON 生成、分镜白模预演、运镜走位预览等。
---

# 火柴人分镜翻译（ScenePlay JSON v1）

## 概述

导演分镜台（`director_board`，自由三维模式）用火柴人白模在三维舞台上预演镜头：
景别、运镜、人物走位与动作都可以播放、录制成 WebM 参考视频、导出分镜表 PNG。
本 skill 把一段视频生成提示词（如 Seedance 分镜脚本）或自然语言分镜描述，
翻译成该平台可直接加载的 **ScenePlay JSON**。

产出的 JSON 有两种用法：

1. 应用内：自由三维模式 → 「🤖 AI 分镜」→ JSON 抽屉 → 粘贴 → 校验并应用；
2. 或保存为 `.json` 文件交给用户自行粘贴。

## 翻译原则

只保留（白模预演唯一关心的东西）：

- **景别**（每个镜头的取景大小）
- **运镜**（推拉摇移升降环绕变焦、幅度、时长、缓动）
- **人物空间调度**：数量、相对位置、朝向、走位（从哪走到哪）
- **人物动作与姿势**（出拳、倒地、坐、指点……）
- **对构图有意义的道具**，用基本几何体近似（桌→box、柱→cylinder、石→sphere/box）

坚决丢弃（白模上没有意义）：

- 视觉风格、色调、光线、材质、画质词
- 天气氛围、环境细节描写
- 人物长相、服装、发型、表情
- 台词内容、旁白、字幕、`@图片n` 参考图引用
- 负向提示词（"不要有：xxx"）

信息不足时做合理的导演假设（对话间距 1.5–3 米、面对面、动作在原点附近），不要提问。

## ScenePlay JSON v1 规范

顶层：`{"version": 1, "title"?, "characters": [...], "props"?: [...], "shots": [...]}`

坐标系：米为单位，Y 向上，地面 y=0，所有角度用**度**。
facing 朝向：0 = 面向 +Z，90 = 面向 +X，180 = 面向 -Z。场景控制在 ±10 米内。

### characters（≥1）

```jsonc
{"key": "唯一英文slug", "name": "显示名(可中文)", "position": [x, z],
 "facing": 度, "pose"?: "standing", "color"?: "#hex", "scale"?: 1}
```

- `position` 是地面平面 `[x, z]` 两个数。
- `pose`（静止姿势）：`standing | sitting | walking | crouching | pointing | arms-raised | lying`。

### props（可选）

```jsonc
{"key": "slug", "kind": "box|cylinder|sphere|cone|torus|plane", "name"?,
 "position": [x, y, z], "size"?: [宽, 高, 深], "rotationY"?: 度, "color"?}
```

- `position.y` 是几何中心高度（0.8 高的箱子放地上 → y=0.4）。

### shots（≥1，按时间顺序）

```jsonc
{"name"?, "size": 景别, "framing": {…} 或 "camera": {…},
 "move"?, "moveAmount"?, "duration"?: 秒, "easing"?: "linear"|"ease-in-out",
 "note"?, "performances"?: [...]}
```

- `size` 景别：`extreme-wide`(大远景) `wide`(远景/全景) `full`(全身) `medium`(中景)
  `medium-close`(中近景) `close-up`(特写) `extreme-close-up`(大特写)。
- **优先用 framing**（平台自动求解机位）：
  `{"subject": "key" 或 ["key1","key2"], "angle"?: 度, "height"?: "low"|"eye"|"high"|"top", "distance"?: 米}`
  - 单人 subject 时 `angle` 相对人物朝向：0 = 正对脸，45 = 前侧 3/4，90 = 正侧，180 = 背后。
  - 多人 / 道具 subject 时 `angle` 是世界方位（0 = 从 +Z 方向拍）。
- 精确机位才用 `camera: {"position": [x,y,z], "target": [x,y,z]}`。
- `move` 运镜：`static | pan(横摇) | tilt(俯仰) | dolly(推拉) | truck(横移) | crane(升降) | orbit(环绕) | zoom(变焦)`。
- `moveAmount` 带符号：pan/tilt/orbit/zoom 用**度**（dolly 正=推近、crane 正=升、orbit 整圈=360、zoom 正=变紧），dolly/truck/crane 用**米**。
- **一个 shot 只有一种运镜**——原分镜里"0-3秒…3-8秒…"多段运镜要拆成多个 shot。
- 推镜（dolly 正值）幅度 ≤ 相机到主体距离的一半；近景推 0.3–0.5 米即可
  （贴脸推镜会被平台自动截断）。

### performances（镜头内的人物表演）

```jsonc
{"character": "key",
 "from"?: {"position": [x,z], "facing": 度},   // 省略=初始摆位
 "to"?:   {"position": [x,z], "facing": 度},   // 省略=原地
 "arrive"?: 秒,                                 // 第几秒走到 to 并停住
 "face"?: "key",                                // 始终面向的人物
 "actions"?: [{"action": 名, "start": 秒, "end"?: 秒, "target"?: "key"}]}
```

- from→to 是该镜头的走位；**移动中自动播放走路/跑步动画**并自动面向行进方向，
  普通走动既不用写 actions 也不用算 facing。
- 动作表：
  - 循环：`idle`(呼吸) `walk` `run` `wave`(挥手) `guard`(格斗架势)
  - 一次性：`punch`(0.55s) `kick`(0.75s) `dodge`(0.5s) `stagger`(踉跄 0.8s) `fall`(倒地并保持) `getup`(起身 1.1s)
  - 定格：`stand` `sit` `crouch` `lie` `point` `arms-raised`
- `start` 从镜头开始计秒；动作可叠加在走位上（边走边在 3.2s 出拳）。

**打斗编排规则（避免"虚空打斗"）**：

- 每个 `punch`/`kick` **必须写 `target`**（挨打者的 key）——平台会自动把攻方在
  击中瞬间吸附到攻击距离（拳 0.75 米 / 踢 1.05 米）并面向对方，无需手算坐标。
- 击中瞬间 ≈ 攻击 `start` + 0.3 秒（拳）/ 0.4 秒（踢）。守方写 `"face": 攻方key`，
  反应动作从击中瞬间开始：`dodge`，或被击中 `stagger` → `fall`。
- 典型一拍：双方 `guard` → 攻方 `{"action":"punch","start":1.0,"target":"def"}`
  → 守方 `{"action":"stagger","start":1.3}`、`{"action":"fall","start":2.0}`。
- 多回合打斗拆成多个镜头，每镜头 1–2 拍。
- 给一次性动作留够收尾时间：`fall` 需 0.9 秒、`getup` 需 1.1 秒。

**节奏与连贯（所有场景通用）**：

- 位移距离 = 速度 × 时长：走路约 1.2 米/秒，奔跑约 3–5 米/秒（低于 2.2 米/秒
  自动按走路播放）。追逐场景按此拉开足够距离。
- 镜头之间保持位置连贯：下一镜的 `from` 接上一镜结束的位置，不要跳回初始摆位。

## 输出要求

只输出一个合法 JSON 对象（应用内粘贴时不要代码围栏）。人名、note 可用中文。

## 示例

输入（节选）：

> 3-8秒：跟随镜头，中景，甲从门口走向桌前的乙，乙起身迎接。
> 8-10秒：切特写，缓慢推近甲的侧脸。
> 画面风格：写实主义，暖色调。不要有：模糊、文字。

输出：

```json
{"version":1,"title":"会面","characters":[{"key":"jia","name":"甲","position":[0,4],"facing":180},{"key":"yi","name":"乙","position":[0,-1],"facing":0,"pose":"sitting"}],"props":[{"key":"table","kind":"box","name":"桌子","position":[0.9,0.4,-1],"size":[1.2,0.8,0.7]}],"shots":[{"name":"走向桌前","size":"medium","framing":{"subject":["jia","yi"],"angle":90,"height":"eye"},"move":"truck","moveAmount":2,"duration":5,"easing":"ease-in-out","note":"甲走向乙，乙起身迎接","performances":[{"character":"jia","from":{"position":[0,4],"facing":180},"to":{"position":[0,0],"facing":180}},{"character":"yi","actions":[{"action":"sit","start":0,"end":2.5},{"action":"stand","start":2.5}]}]},{"name":"侧脸特写","size":"close-up","framing":{"subject":"jia","angle":80,"height":"eye"},"move":"dolly","moveAmount":0.6,"duration":2,"easing":"ease-in-out","note":"推近甲的侧脸"}]}
```

风格 / 负向提示词全部丢弃——它们与白模预演无关。

> 应用内嵌的同一规范在 `director_board/src/lib/stickmanSkillPrompt.ts`；
> 两处必须同步修改。
