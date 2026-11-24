"""Check delivered audio/video integrity; do not substitute metrics for listening."""
import argparse
import json
from pathlib import Path
import av
import numpy as np
import soundfile as sf
from audio_common import ROOT, sha256, write_json

def main():
    p=argparse.ArgumentParser();p.add_argument('--run-dir',type=Path,default=ROOT/'runs/audio_film_test')
    p.add_argument('--config',type=Path,default=ROOT/'configs/audio-film-test.json')
    a=p.parse_args();run=a.run_dir.resolve()
    cfg=json.loads(a.config.read_text(encoding='utf-8'))
    rows=[]
    for stage in ['design','clone','sfx','music']:
        for job in cfg[stage]['jobs']:
            path=run/stage/(job['id']+'.wav')
            record=json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
            wave,rate=sf.read(path,always_2d=True)
            assert sha256(path)==record['sha256'],path
            assert np.isfinite(wave).all(),path
            assert np.sqrt(np.mean(wave**2))>1e-7,path
            duration=len(wave)/rate
            target=job['seconds'] if stage=='sfx' else cfg['music']['duration'] if stage=='music' else None
            if target is not None: assert abs(duration-target)<0.1,(path,duration,target)
            assert abs(duration-record['duration'])<1e-8,path
            rows.append(dict(path=str(path),duration=duration,rate=rate,channels=wave.shape[1],
                finite=True,sha256_verified=True,non_silent=True,samples_above_full_scale=int(np.sum(np.abs(wave)>1))))
    mix=json.loads((run/'mix/mix.json').read_text(encoding='utf-8'))
    assert mix['video_stream_unchanged']
    video=Path(mix['output'])
    assert sha256(video)==mix['sha256']
    with av.open(str(video)) as c:
        vs=c.streams.video[0]
        info=dict(width=vs.width,height=vs.height,fps=str(vs.average_rate),frames=sum(1 for _ in c.decode(video=0)))
    with av.open(str(ROOT/cfg['source_video'])) as c:
        vs=c.streams.video[0]
        expected=dict(width=vs.width,height=vs.height,fps=str(vs.average_rate),frames=sum(1 for _ in c.decode(video=0)))
    assert info==expected,(info,expected)
    with av.open(str(video)) as c:
        audio_frames=list(c.decode(audio=0))
        audio=np.concatenate([f.to_ndarray() for f in audio_frames],axis=1)
        assert np.isfinite(audio).all()
        assert np.max(np.abs(audio))<1.0
    write_json(run/'validation.json',dict(status='passed',generated_audio_count=len(rows),
        audio=rows,video=info,decoded_aac_peak=float(np.max(np.abs(audio))),
        subjective_quality='not established by these checks; user listening required'))
    print('VALIDATED',len(rows),'generated clips; video',info)

if __name__=='__main__':main()
