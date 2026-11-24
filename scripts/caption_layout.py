"""Render Chinese captions with measured glyph bounds; reject overflow, never shrink to fit."""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

DEFAULT_FONT = 'C:/Windows/Fonts/msyh.ttc'


def layout(text, width=1344, height=768, font_path=DEFAULT_FONT, size=36,
           side=0.08, bottom=0.09, max_lines=2, max_chars=22, position='bottom', protected=None):
    if not text.strip():
        raise ValueError('Empty caption')
    if position not in ('top', 'bottom'):
        raise ValueError('position must be top or bottom')
    if not 0 <= side < 0.5 or not 0 <= bottom < 0.5 or size <= 0 or max_chars < 1 or max_lines < 1:
        raise ValueError('Invalid caption geometry')
    # No fallback font: missing CJK glyph support must be fixed explicitly.
    font = ImageFont.truetype(str(font_path), size)
    stroke = max(2, round(size / 14))
    margin_x = round(width * side)
    available = width - 2 * margin_x
    canvas = Image.new('RGBA', (width, height))
    draw = ImageDraw.Draw(canvas)
    lines = []
    for paragraph in text.split('\n'):
        line = ''
        for char in paragraph:
            candidate = line + char
            bbox = draw.textbbox((0, 0), candidate, font=font, stroke_width=stroke)
            if line and (bbox[2] - bbox[0] > available or len(candidate) > max_chars):
                lines.append(line)
                line = char
            else:
                line = candidate
        if line:
            lines.append(line)
    if len(lines) > max_lines:
        raise ValueError(f'Caption needs {len(lines)} lines; split into timed clauses (limit {max_lines}), do not shrink font')
    boxes = [draw.textbbox((0, 0), s, font=font, stroke_width=stroke) for s in lines]
    gap = round(size * 0.3)
    total = sum(b[3]-b[1] for b in boxes) + gap * (len(lines)-1)
    margin_y = round(height * bottom)
    top = height - margin_y - total if position == 'bottom' else margin_y
    if top < margin_y or top + total > height - margin_y:
        raise ValueError('Caption exceeds vertical safe area')
    bounds = []
    y = top
    for line, bb in zip(lines, boxes):
        line_width = bb[2] - bb[0]
        if line_width > available:
            raise ValueError('A caption glyph exceeds the available width')
        x = (width - line_width) // 2
        rect = (x, y, x+line_width, y+bb[3]-bb[1])
        for region in protected or []:
            if rect[0] < region[2] and rect[2] > region[0] and rect[1] < region[3] and rect[3] > region[1]:
                raise ValueError(f'Caption intersects protected subject/text region {region}; review top placement or reframe')
        draw.text((x-bb[0], y-bb[1]), line, font=font, fill=(255,255,255,255),
                  stroke_width=stroke, stroke_fill=(0,0,0,220))
        bounds.append(rect)
        y += bb[3]-bb[1]+gap
    actual = canvas.getbbox()
    return canvas, dict(lines=lines, bounds=bounds, alpha_bbox=actual, font=str(font_path),
                        size=size, safe_side=side, safe_bottom=bottom, position=position)


def render_cues(config, out):
    out = Path(out)
    cues = config['cues']
    results = []
    previous_end = -1
    for i, cue in enumerate(cues):
        start, end = float(cue['start']), float(cue['end'])
        if not (0 <= start < end <= config['duration']) or start < previous_end:
            raise ValueError(f'Invalid or overlapping cue {i}')
        previous_end = end
        kwargs = dict(config.get('style', {}))
        kwargs.update(cue.get('layout', {}))
        canvas, info = layout(cue['text'], config['width'], config['height'], **kwargs)
        cps = len(cue['text'].replace('\n','')) / (end-start)
        warnings = []
        if cps > 9:
            warnings.append('Reading speed >9 characters/s; review voice timing or split/re-edit')
        if end-start < 0.8 or end-start > 6:
            warnings.append('Cue outside proposed 0.8–6s range; review rather than silently retime')
        results.append((canvas, dict(index=i, start=start, end=end, text=cue['text'], cps=round(cps,2),
                                    warnings=warnings, **info)))
    # Validate the entire list before writing partial artifacts.
    out.mkdir(parents=True, exist_ok=True)
    for canvas, info in results:
        canvas.save(out / f'cue-{info["index"]:03d}.png')
    report = dict(layout_status='pass', alignment_status=config.get('alignment_status', 'unverified'),
                  note='Geometry only; actual speech sync and subject occlusion need visual/audio review.',
                  cues=[info for _,info in results])
    (out/'layout-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cues', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(render_cues(json.loads(a.cues.read_text(encoding='utf-8-sig')), a.out), ensure_ascii=False))
