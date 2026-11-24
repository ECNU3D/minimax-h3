# Qwen-Image-2.1 本机部署与实测

2026-09-21，RTX 5080 16GB / Ryzen 7 9800X3D / 32GB RAM / Windows。

已完成四张图片的真实推理和人工目视检查。全部使用 1024×1024、25 步、CFG 1、Euler / simple；没有使用云端图像生成 API。

| 样例 | 服务端时间 | 整卡显存采样最大值 | 观察 |
|---|---:|---:|---|
| 写实人物 | 10.971 秒 | 12.86 GiB | 短发、黄色外套、红围巾及白背景符合提示词。 |
| 中文海报 | 9.584 秒 | 12.85 GiB | 标题、标语、日期与地点三行文字目视核对正确。 |
| 透明提灯 | 8.299 秒 | 13.46 GiB | RGBA 原图，alpha 范围 0–255；约 79.2% 像素的 alpha ≤ 8。透明区和提手镂空可用，玻璃与细边仍应按用途检查。 |
| 人物编辑 | 13.127 秒 | 14.86 GiB | 白背景替换为温室，外套改为蓝色，脸、发型、围巾和构图基本保留；衣服局部褶皱和扣件有变化。 |

计时来自 ComfyUI execution_start / execution_success，包括节点执行、必要的加载、解码与保存，不含安装下载。首张包括首次模型加载，后续存在缓存条件差异。显存每约 3 秒采样一次，包含桌面占用，不是瞬时峰值。测试期间最低可用系统内存约 16.5 GiB。每项只测一次，不能推广为所有提示词、2K 或多参考图的性能保证。

三张普通图片也输出 RGBA，其 alpha 接近不透明但并非每个像素都等于 255（人物 245–255、海报 247–255、编辑 253–255）。需要严格不透明图时，应另存白底合成副本；原始结果已保留。

## 打开与使用

服务地址：<http://127.0.0.1:8190>。

从项目根目录启动：

```powershell
.\start-qwen21.ps1
```

在 ComfyUI 的工作流列表中打开 `01_portrait`、`02_chinese_poster`、`03_transparent_lantern` 或 `04_portrait_edit`，修改提示词和 seed 后运行。也可导入 [工作流目录](../runs/qwen21-20260921/prepared-workflows/) 的 JSON。编辑样例使用的原始人物图已复制到独立 ComfyUI 的 input 目录。

CLI 恢复已保存的四项测试（成功项校验哈希后复用，不重复出图）：

```powershell
tools/qwen21/env/Scripts/python.exe scripts/qwen21_examples.py
```

[样例配置](../configs/qwen21-examples.json) 保存全部提示词、尺寸、种子和参考顺序。修改已有样例时，应使用新的样例 name 保存新一轮结果；脚本拒绝覆盖不同配置的旧任务。不确定提交或超时不会自动重提。

## 部署位置与版本

- 独立源码：`tools/qwen21/ComfyUI`，ComfyUI 0.37.0，commit `b0f4b7b294ce482a2e071d9d762c133d38c7aa07`。
- 环境：`tools/qwen21/env`。通过 `h3_base_readonly.pth` 只读复用 `.venv-cu130/Lib/site-packages` 的基础依赖，在自身目录安装新版 frontend / embedded-docs / kitchen / aimdo。原 H3 环境未升级，因此这个环境仍依赖项目的 `.venv-cu130`，不是可随意搬走的独立安装包。
- PyTorch 2.11.0+cu130，Transformers 5.17.0，Comfy Kitchen 0.2.35，Comfy Aimdo 0.5.5，Frontend 1.53.6，Embedded Docs 0.5.12。
- 官方通用模板包保持原有 0.11.57：镜像缺少新版所需的 `media-assets-02`，没有强行安装不完整依赖。本次四份工作流已独立导出并实跑，模板版本提醒不影响它们。
- 启动使用 PyTorch attention、DynamicVRAM、2 GiB reserve；API 云节点及自定义节点关闭，只监听本机。运行时 HF/Transformers 设置为离线。
- 图像权重单独位于 `tools/qwen21/models`。原 H3 源码、模型与生产工作流未更改。

| 组件 | 文件 | 大小 |
|---|---|---:|
| 生成模型 | qwen_image_2.1_int8_convrot.safetensors | 7,256,783,064 字节 |
| 编码器 | qwen3vl_8b_w4a8.safetensors | 6,312,105,364 字节 |
| VAE | qwen_image_2.1_vae_bf16.safetensors | 675,509,688 字节 |

权重来自 Comfy-Org 官方仓库，HF revision `ace0edeb3791a594ddfa36ed5f41a178a394e921`。最初取得 ModelScope 元数据并尝试下载，随后续传切换到 HF CDN；两个官方渠道的三个文件 SHA256 均一致，完整文件均已校验。

## 原图与记录

- [四图预览](../runs/qwen21-20260921/contact-sheet.jpg)
- [人物原图](../runs/qwen21-20260921/images/01_portrait.png)
- [中文海报](../runs/qwen21-20260921/images/02_chinese_poster.png)
- [透明提灯原始 PNG](../runs/qwen21-20260921/images/03_transparent_lantern.png)
- [人物编辑结果](../runs/qwen21-20260921/images/04_portrait_edit.png)
- [模型校验记录](../runs/qwen21-20260921/model-verification.json)
- [实际运行环境](../runs/qwen21-20260921/environment.json)
- [样例任务目录](../runs/qwen21-20260921/jobs/)：每项含 API/编辑器工作流、prompt ID、完整 history、资源采样、输出 SHA256、参考图路径与 SHA256。

结果执行成功不等于所有细节均合格。本轮证实 16GB 显卡可以运行以上四个 1K 例子；2K、十参考图、量化与 BF16 的画质差异未测试。
