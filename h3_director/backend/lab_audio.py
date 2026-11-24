"""Decode evidence for listening comparisons. No quality verdict or resampling."""
import math
import av
import numpy as np


def inspect_audio(path):
    with av.open(str(path)) as container:
        stream=next((s for s in container.streams if s.type=='audio'),None)
        if stream is None:raise ValueError('素材没有音轨')
        arrays=[];rate=None;channels=None
        for frame in container.decode(stream):
            rate=frame.sample_rate;channels=len(frame.layout.channels)
            a=frame.to_ndarray()
            if a.dtype.kind in 'iu':
                info=np.iinfo(a.dtype);a=a.astype(np.float64)
                if info.min==0:a-= (info.max+1)/2
                a/= max(abs(info.min),info.max+1 if info.min==0 else info.max)
                if info.min==0:a*=2
            else:a=a.astype(np.float64)
            if not frame.format.is_planar:a=a.reshape(-1,channels).T
            if not np.isfinite(a).all():raise ValueError('音轨包含无效数值')
            arrays.append(a)
            if sum(x.shape[1] for x in arrays)>rate*60:raise ValueError('音轨超过 60 秒')
        if not arrays:raise ValueError('音轨为空')
        a=np.concatenate(arrays,axis=1);peak=float(np.max(np.abs(a)));rms=float(np.sqrt(np.mean(a*a)))
        wave=[round(float(np.max(np.abs(x))),5) for x in np.array_split(a,min(160,a.shape[1]),axis=1)]
        return dict(sampleRate=rate,channels=channels,duration=round(a.shape[1]/rate,4),
                    peakDb=round(20*math.log10(peak),2) if peak else None,
                    rmsDb=round(20*math.log10(rms),2) if rms else None,
                    clippedSamples=int(np.sum(np.abs(a)>=.9999)),waveform=wave)
