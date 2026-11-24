# Yingchang Director · Local MiniMax H3 Production Workspace

[简体中文](README.md) · **English**

Yingchang brings scripts, reference assets, shot generation, review, and editorial handoff into one local workspace. Work shot by shot in the browser or have an agent such as Codex run the repository's production scripts directly. Reference images, video shots, and post-production audio can all be generated with local models.

## How to work

| Mode | What you can do |
| --- | --- |
| **Fully local production** | Edit prompts, upload references, and test shots in Shot Lab. Generate images with local Qwen or FLUX models, run H3 through ComfyUI, and produce post-production audio with local scripts. Media, versions, and run records are stored on your machine. |
| **Codex-driven production** | Select Codex as the director agent for a project. It uses your existing local ChatGPT sign-in to parse scripts, check them against the source, and review reference images and sampled video frames. You can separately select Codex Image Gen on an asset to generate images or edit actual reference images. |
| **DeepSeek director agent** | Select DeepSeek on a project for parsing and review. Configure it with your own `DEEPSEEK_API_KEY` in the root `.env` file. |

Codex and DeepSeek process the documents, prompts, or review images required by the selected task. ComfyUI runs H3 video generation locally. You can also have an agent such as Codex call `scripts/h3_batch.py` and `scripts/audio_film_pipeline.py` directly from the repository, using their preflight checks, run records, and recovery workflows. Video production follows per-shot submission budgets and the STOP mechanism. See the [director guide](h3_director/README.md) and [batch production protocol](docs/h3-agent-production.md).

## Image, video, and audio models

| Stage | Model or entry point | What it does |
| --- | --- | --- |
| Local reference images | **Qwen Image 2.1** | The director's default image model. Supports text-to-image, ordered image references, and brush or lasso masking for regional edits. Use it for character views, locations, props, and keyframes. See the [Qwen image workflow](docs/h3-qwen21-images.md). |
| Local reference images | **FLUX.2 Klein 4B Distilled / Base** | Generate or edit references through ComfyUI. Distilled offers fast four-step generation and Base offers a 20-step option. See the [image model guide](docs/image-model-selection.md). |
| Local video and native sound | **MiniMax H3 Ref2VA INT8** | The default is 768p at 24 fps with eight sampling steps, in landscape or portrait. Generate shots with native sound from character, location, and prop references. Shot Lab also accepts audio references and can compare the FLAC and MP4 audio from the same run. See the [Shot Lab guide](docs/h3-shot-lab.md). |
| Local dialogue and narration | **Qwen3-TTS VoiceDesign + Base** | Design a character voice with VoiceDesign, then use Base to reuse an approved voice sample and synthesize individual lines. |
| Local sound effects | **MOSS-SoundEffect v2** | Generate ambience, object contact sounds, and action effects as separate tracks for post-production. |
| Local instrumental score | **ACE-Step 1.5 SFT** | Generate instrumental cues for the scene's mood and duration, then select, edit, and mix them. |

The director's editorial handoff package includes selected shots, source documents, an audio configuration template, and production instructions. The local audio pipeline runs dialogue, effects, and music as separate post-production stages and can deliver stems and a mix. See the [local audio workflow](docs/audio-local-workflow.md) and [audio production skill](skills/local-film-audio/SKILL.md).

## Windows quick start

1. Install Git, Node.js (20.19+ in the 20.x line, or 22.12+), and uv. Clone this repository and place the official `uv.exe` at `tools/uv.exe`. From the repository root, run `./repair-environment.ps1` to create `.venv-cu130`. Local GPU generation requires a CUDA 13-compatible NVIDIA driver.
2. Run `./h3_director/start.ps1` to build and start the director, then open <http://127.0.0.1:8321/>. Open the greenhouse example to see its assets and shots, or start in Shot Lab. For DeepSeek, copy `.env.example` to `.env` and add your key. For Codex, use your existing local Codex sign-in. Image generation requires an account with Image Gen access.
3. For local video generation, install the pinned ComfyUI and KJNodes revisions from the repository root.

   ```powershell
   git clone https://github.com/Comfy-Org/ComfyUI.git ComfyUI
   git -C ComfyUI checkout --detach (Get-Content docs/comfy-commit.txt -TotalCount 1)
   git clone https://github.com/kijai/ComfyUI-KJNodes.git ComfyUI/custom_nodes/ComfyUI-KJNodes
   git -C ComfyUI/custom_nodes/ComfyUI-KJNodes checkout --detach 57105374f47d0fbb49c9c3926fb981702e0a4b5c
   ```

4. Download the weights from Hugging Face using the `revision` and `source_path` in each manifest. If `source_path` is absent, use `path` as the source. Store each file under its `path` inside `ComfyUI/models/` and verify `sha256`.

   | Weights for the default 768p eight-step profile | Manifest |
   | --- | --- |
   | Ref2VA INT8 diffusion model | [INT8 manifest](docs/int8-reference-manifest.json) |
   | 768p Turbo eight-step LoRA | [768p manifest](docs/h3-768p-models-manifest.json) |
   | Text encoder, video VAE, and audio VAE | Entries under `text_encoders/` and `vae/` in the [H3 manifest](docs/models-manifest.json) |

5. Start ComfyUI, then submit a shot from the director. Upload existing references or configure local image generation using the [Qwen image service guide](docs/qwen-image-21-local.md) or the [FLUX model manifest](docs/image-models-manifest.json).

   ```powershell
   ./start.ps1 -Cuda13 -SageAttention -KJNodes -VramHeadroom 8 -DisablePinnedMemory
   ```

   ComfyUI listens at <http://127.0.0.1:8188/>. The Qwen image service runs in a separate environment and listens on port `8190`.

## Workflows and documentation

- Start with a character on white, a complete location image, and a prop on white. Send the three images to H3 in that order. [Three-reference workflow](docs/three-white-reference-workflow.md)
- Manage shot versions, reviews, and editorial handoff. [Director guide](h3_director/README.md) · [Editing and subtitle workflow](docs/video-editing-workflow.md)
- Find deployment notes, audio setup, and reusable agent skills. [Documentation index](docs/README.md) · [Skills directory](skills/)

Install model weights, runtimes, and third-party tools separately. Keep `.env`, account sessions, project media, and generation records in your local workspace.

The source is available under the [MIT License](LICENSE). Bundled third-party material follows its respective licenses.
