"""Decode generated audio/video, report integrity and produce a contact sheet."""
import argparse
from fractions import Fraction
import json
import pathlib

import av
import numpy as np
from PIL import Image, ImageDraw

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=pathlib.Path)
    args = parser.parse_args()
    path = args.video.resolve()
    frames, thumbs, means, deltas = [], [], [], []
    previous = None
    with av.open(str(path)) as container:
        video = container.streams.video[0]
        report = {"file": str(path), "bytes": path.stat().st_size, "width": video.width, "height": video.height,
                  "fps": str(video.average_rate), "video_codec": video.codec_context.name}
        for index, frame in enumerate(container.decode(video=0)):
            pixels = frame.to_ndarray(format="rgb24")
            means.append(float(pixels.mean()))
            if previous is not None:
                deltas.append(float(np.abs(pixels.astype(np.float32) - previous).mean()))
            previous = pixels.astype(np.float32)
            if index % 24 == 0:
                thumbs.append((index, frame.to_image()))
            frames.append(float(frame.time or 0))
    report.update(frames=len(frames), duration_seconds=len(frames) / float(Fraction(report["fps"])),
                  mean_pixel_min=min(means), mean_pixel_max=max(means), mean_frame_difference=float(np.mean(deltas)))
    with av.open(str(path)) as container:
        audio = container.streams.audio[0]
        samples = [frame.to_ndarray().astype(np.float32) for frame in container.decode(audio=0)]
        signal = np.concatenate(samples, axis=-1)
        report["audio"] = {"codec": audio.codec_context.name, "sample_rate": audio.sample_rate,
                           "channels": len(audio.layout.channels), "samples": signal.shape[-1],
                           "rms": float(np.sqrt(np.mean(signal ** 2))), "peak": float(np.max(np.abs(signal))),
                           "all_finite": bool(np.isfinite(signal).all())}
    width, height = 320, round(report["height"] / report["width"] * 320)
    rows = max(1, (len(thumbs) + 2) // 3)
    sheet = Image.new("RGB", (3 * width, rows * (height + 28)), "#151b24")
    draw = ImageDraw.Draw(sheet)
    for slot, (index, picture) in enumerate(thumbs):
        x, y = slot % 3 * width, slot // 3 * (height + 28)
        sheet.paste(picture.resize((width, height)), (x, y))
        draw.text((x + 8, y + height + 5), f"frame {index} | {index / 24:.2f}s", fill="white")
    sheet.save(path.with_suffix(".contact.jpg"), quality=92)
    path.with_suffix(".inspection.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
