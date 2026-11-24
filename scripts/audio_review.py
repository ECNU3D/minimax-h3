"""Build compact playback copies and a local listening sheet without changing masters."""
import argparse
import json
from pathlib import Path
import subprocess
import imageio_ffmpeg
from audio_common import ROOT, sha256, write_json

def main():
    p=argparse.ArgumentParser();p.add_argument('--run-dir',type=Path,default=ROOT/'runs/audio_film_test')
    run=p.parse_args().run_dir.resolve()
    previews=run/'previews';previews.mkdir(exist_ok=True)
    ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
    lines=['# 音频测试试听','', '执行成功不等于听感通过，请比较声音自然度、人物声线延续、音效内容和音乐中是否出现意外人声。试听MP3做了有峰值上限的音量调整，便于比较；原始WAV没有改变。','',
           '## 合成试听','',f'![温室音频测试](<{(run/"mix/greenhouse_audio_test.mp4").as_posix()}>)','']
    records=[]
    for stage,title in [('design','三种人物声音，同一段话'),('clone','同一个年轻女声，三句不同台词'),('sfx','独立音效'),('music','30秒纯音乐')]:
        lines += ['## '+title,'']
        for path in sorted((run/stage).glob('*.wav')):
            data=json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
            preview=previews/(stage+'_'+path.stem+'.mp3')
            gain=min(20,0.85/max(data['peak'],1e-9),0.08/max(data['rms'],1e-9))
            subprocess.run([ffmpeg,'-v','error','-y','-i',str(path),'-af',f'volume={gain}',
                            '-c:a','libmp3lame','-b:a','192k',str(preview)],check=True)
            label=path.stem
            text=data['inputs']['job'].get('text') or data['inputs']['job'].get('instruct') or data['inputs']['job'].get('prompt') or data['inputs']['job'].get('caption')
            lines += ['### '+label,'',text,'',f'时长 {data["duration"]:.2f} 秒；生成耗时 {data["generation_seconds"]:.1f} 秒。','',
                      f'![{label}](<{preview.as_posix()}>)','',f'[原始 WAV](<{path.as_posix()}>)','']
            records.append(dict(source=str(path),source_sha256=sha256(path),preview=str(preview),
                                preview_sha256=sha256(preview),audition_gain=gain))
    lines += ['## 评价记录','', '- 默认声线：待用户确认。','- 默认BGM：待用户确认。','- 风/鸟/水的版本选择：待用户确认。','- 提灯接触声与画面同步：待用户确认。','']
    (run/'LISTEN.md').write_text('\n'.join(lines),encoding='utf-8')
    write_json(previews/'manifest.json',records)
    print(str(run/'LISTEN.md'))

if __name__=='__main__':main()
