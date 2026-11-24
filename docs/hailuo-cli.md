# 海螺国内站 H3 命令行

入口：`C:/Users/shang/bin/hailuo.cmd`，源码：`tools/hailuo-cli/`。

这是本项目封装的消费者网页自动化 CLI，使用海螺国内站当前账号的订阅贝壳，不是 MiniMax 开放平台 API 或海螺官方发布的 CLI。它复用用户已登录的独立 Chrome 目录，不需要操作或重载 LuoFlow 插件。默认后台执行。

## 生成与下载

配置格式见 [skill 配置参考](../skills/hailuo-cli/references/config.md)。在项目目录运行，当前 shell 尚未识别 `hailuo` 时使用完整路径：

```powershell
& 'C:/Users/shang/bin/hailuo.cmd' help
& 'C:/Users/shang/bin/hailuo.cmd' prepare --config configs/my-shot.json
& 'C:/Users/shang/bin/hailuo.cmd' generate --config configs/my-shot.json --wait 900
& 'C:/Users/shang/bin/hailuo.cmd' batch --config configs/my-batch.json --wait 900
```

`prepare` 不付费。生成命令自动选择 MiniMax H3 全能参考、按顺序上传参考图、通过原生 @ 菜单插入图片节点，核对完整提示词、参数、单条输出数量及网页报价；付费后等待原任务并保存正式 MP4。

批量文件引用 1–6 个独立镜头配置，需要每条积分上限及总上限。全部预检查通过后，约间隔三秒发送请求，已接受任务在服务端按会员配额同时运行或排队。六条批量不表示六条同时计算。

目前配置接受三图或其他 1–12 张有序图片、16:9、768p/2K、4–15 秒。分辨率默认 768p，最高 2K，设置 `settings.resolution="2K"` 即可选择；批量镜头可分别设置。2026-10-05 实际上传三图并验证了 2K/4s 页面参数及 48 贝壳报价，没有提交付费生成，检查记录位于 `runs/hailuo-cli-preflight-2k-20261005/`。真实付费测试覆盖 768p/4s/三图全能参考。网页不暴露 seed 或精确模型权重版本。

## 续查、重新下载与已知拒绝

```powershell
hailuo status --id original-shot-id --wait 900
hailuo batch --config configs/my-batch.json --resume --wait 900
hailuo download --id original-shot-id
hailuo batch --config configs/my-batch.json --resume --download --wait 0
```

`status`、`download` 和 `--resume` 都不提交付费任务。默认生成等待 600 秒，可设置 0–3600 秒；超时保存 pending 状态，再用原 ID 续查。`status --offline` 只读总账。

下载菜单包含独立的“去除AI生成水印”和“去除品牌水印”开关。CLI 默认 `--watermark none`，去除两类可见水印；`--watermark ai` 保留 AI 标识并去除品牌，`--watermark all` 保留两类，也可写在配置的 `settings.downloadWatermark`。此前七个测试的快捷下载仅去除品牌，仍含 AI 标识，旧文件保留。首次开启去 AI 标识需用户确认单独的《去水印规则》：

```powershell
hailuo watermark-consent --id original-shot-id
hailuo download --id original-shot-id --watermark none
```

确认命令打开可见 Chrome 规则窗口，等待用户本人点击“同意”，随后自动下载该任务；CLI 不代点。确认保存于独立登录目录，后续可后台下载。规则说明仅去除可见标识，仍可能保留元数据中的隐式标识。默认去除水印模式遇到协议或开关不可用会报错，不会悄悄下载预览充数。其他模式若正式下载失败而预览可取，记录 `downloadWarning` / `downloadMethod=preview-media-url`，不能称作正式下载成功。

CLI 悬停原任务“全部下载”打开菜单，设置开关后点击菜单中的“下载”，捕获其产生的文件链接，核对 videoID 并保存原始 MP4 字节。旧视频按哈希保存在 `video-before-watermark-*.mp4`，原预览保存在 `preview-video.mp4`。本机 Chrome 原生 Blob 下载曾崩溃，CLI 暂时捕获按钮产生的文件链接读取内容，随后恢复页面方法；没有拼造下载地址或后期修改视频。

首次六请求同一瞬间发送时，平台明确拒绝五个请求：`code=2400003 / 当前资源较忙，请重试`，无 task ID。CLI 支持在已有用户授权内显式重试这种确切拒绝：

```powershell
hailuo batch --config configs/my-batch.json --retry-busy --wait 900
```

此分支仅允许资源忙拒绝且无任何任务回执的原镜头，每条最多三次请求，保留历史；已接受、未知或完成的其他任务只查询，不付费。不自动重试，也不能与 `--resume` 合并。其他失败保存错误。

## 状态与登录

用户首次运行 `hailuo login`，在独立 Chrome 窗口完成登录。已登录可直接使用。首次功能协议由用户阅读并确认，CLI 不代为接受。`--headed` 可显示窗口。

登录目录：`%LOCALAPPDATA%/HailuoH3Cli/browser-profile`，不进入项目或 skill。总账：`%LOCALAPPDATA%/HailuoH3Cli/jobs/<shotId>.json`。CLI 不复制普通 Chrome Cookie，不导出令牌。

付费点击前先持久写入 attempted；失联保留 uncertain。相同 ID 或相同输入不能通过改名、改积分上限再次提交。命令间排他锁防止争用登录目录，批量在同一浏览器上下文中运行。中断后检查原进程与原任务，不删总账或锁来直接重投。

旧插件镜头 `luoflow-h3-omni-20261005-three-references` 仍为用户报告的 submitted/uncertain，CLI 保留锁。此次七个新授权测试使用不同动作及稳定的新逻辑 ID，没有解除旧任务保护。

## 实测结果（2026-10-05）

- 单条 1/1，六镜头批量 6/6，全部取得真实服务端 batchID、视频 ID 和正式下载文件。
- 768p/4s/三图全能参考每条 28 贝壳；余额 4500 → 4304，合计 196。五次资源忙拒绝没有额外扣费；查询和重复下载后余额仍为 4304。
- 七条均为 1344×768、24fps、107 帧、4.458333 秒，H.264 + AAC；逐文件 SHA256 唯一，完整解码通过。
- 2026-10-06 用户本人确认去水印规则，七条原任务均重新下载，两个去水印开关开启；逐条四帧检查没有品牌或“AI生成”可见水印。旧快捷下载按哈希保存并复核；重新下载没有扣费，余额仍为 4304。首次确认后的六条后台下载成功，无需逐条点击。
- 原生 @ 引用、费用检查和成片角色/场景/道具已检查。视觉观察与执行完成分开记录，用户尚未作最终视觉验收。
- 当前标准会员页面列出同时运行 2、排队 8；实际观察到两条运行、其他等待。测试先有一条接受，之后间隔提交的五条同时处于未完成状态，不能据此声称六条同时计算或六条同时未完成。
- 12 项离线测试通过，覆盖预算、总账、回执隔离、原生引用、明确拒绝重试范围、正式下载 Blob 字节保真、水印选项及未确认协议时拦截。

详见 [实测报告](../runs/hailuo-cli-e2e-20261005/report.md) 与该目录的 `manifest.json`、各镜头 `job.json`、`media.json`、`preflight.json/png`、`submission-response*.json` 和 `native-download.json`。

## Agent skill 与重建

[hailuo-cli skill](../skills/hailuo-cli/SKILL.md) 为 canonical 版本，已按项目约定同步到 `.agents/skills/hailuo-cli`、`.claude/skills/hailuo-cli`、`.trae/skills/hailuo-cli`。项目内 agent 可使用 `$hailuo-cli`，`AGENTS.md` 已添加提供方路由。

```powershell
cd tools/hailuo-cli
npm ci --ignore-scripts --no-fund --no-audit
npm run build
npm test
```

固定 Playwright 1.63.0 / TypeScript 5.9.3，使用已安装的 Chrome。构建共享 LuoFlow `src/page.ts` 的 H3 参数与预检查函数；CLI 本身独立运行。正常生成无需重新构建。
