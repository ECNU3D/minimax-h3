# H3 专用原生 768p 工作流

2026-09-20，按《H3本地配置改进方案.md》新增 `ref2v-768p-8step` 档位。

2026-09-20，用户试听分镜测试的「768p 基线」后确认作为导演台默认。该基线与现有 `ref2v-768p-8step` 数值相同：Euler / simple / 8 步、Turbo LoRA 强度 1、video/audio shift 12/3、denoise 1、BasicGuider、FP32 音频 VAE。导演台单镜与自动制作继续使用此档位，界面标明「768p 默认基线」。每镜保留自身时长、种子和提示词，不将测试用的 12 秒和种子全局覆盖；已排队任务的快照与既有视频保留。`test_video_profile.py` 对比实验室基线与生产图，防止两套参数偏离。

- 原生画布支持横屏 1344×768 和竖屏 768×1344。两种画布共用 Ref2VA INT8 ConvRot、原 Qwen3-VL NVFP4 编码器及 FP16 视频 VAE。
- 官方 LightX2V Ref2V Turbo 8-step v1.0 **768p** LoRA，strength 1.0；模型版本及 SHA256 在 `h3-768p-models-manifest.json`。
- Euler，simple，8 steps，BasicGuider，denoise 1；显式 video/audio shift 12/3。
- SageAttention、head chunks 4、FFN chunks 8、seq threshold 4096。
- 参考条件与解码共用视频 VAE，guider/scheduler 共用最终模型分支。
- 同次解码保存 0、24、48、72、96、末帧的编码前 PNG，同时输出 H.264 MP4 与原生音频。
- 24fps；帧数向上对齐为 `17*k+5`，5秒=124帧，8秒=192帧，10秒=243帧。

在镜头 spec 增加 `"profile": "ref2v-768p-8step"` 即可选择。竖屏设 `"width": 768, "height": 1344`。省略档位时沿用旧 4 步配方及旧输入指纹。

导演工作台中，在「分镜制作」选择「768p 高质量（默认）」，打开镜头详情，在「生成画幅」选竖屏。批量制作可统一选择横屏或竖屏，也可沿用各分镜的设置。

模型下载：`.\.venv-cu130\Scripts\python.exe scripts/download_h3_768p.py --python-download`；支持可选 `--proxy`。Python 下载方式用于本机 aria2/curl 的 Windows TLS 握手失败，仍从同一固定官方 revision 下载并验证文件大小和 SHA256。

唯一生产入口仍为：

```powershell
.\.venv-cu130\Scripts\python.exe scripts/h3_batch.py --spec runs/parents-768p-20260920/spec.json --run-dir runs/parents-768p-20260920 --allow-reference-override
.\.venv-cu130\Scripts\python.exe scripts/h3_batch.py --spec runs/parents-768p-20260920/spec.json --run-dir runs/parents-768p-20260920 --campaign parents-768p-20260920 --allow-reference-override --execute
```

本轮依据用户新明确指令重新生成 s039 / s048，授权及旧版本映射在该 run 的 `authorization.json`。保留导演台现有两镜的提示词、种子、参考顺序、时长，s039原有2图 / s048原有3图。新批次仍是每镜最多2次，累计3次执行失败停止。后续修订继续使用同一 campaign 和稳定镜号。

导出到 `workflows/H3-Ref2V-768p-8step-s039.json`、`workflows/H3-Ref2V-768p-8step-s048.json` 的编辑器工作流供查看；agent 实际提交始终通过上述固定入口。

执行状态、真实产物与SHA256见每镜 `result.json` / `job.json`，视觉检查另记，不将执行成功当作用户验收。
