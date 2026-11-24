"""Create an auditable stereo mix and copy the original compressed video stream."""
import argparse
import json
import math
from pathlib import Path
import subprocess

import imageio_ffmpeg
import numpy as np
from scipy.signal import resample_poly
import soundfile as sf

from audio_common import ROOT, sha256, write_json

RATE = 48000

def read(path):
    wave, rate = sf.read(path, dtype='float32', always_2d=True)
    if rate != RATE:
        divisor = math.gcd(rate, RATE)
        wave = resample_poly(wave, RATE//divisor, rate//divisor, axis=0)
    if wave.shape[1] == 1: wave = np.repeat(wave, 2, axis=1)
    return wave[:, :2]

def level(wave, db):
    rms = float(np.sqrt(np.mean(wave.astype(np.float64)**2)))
    return wave * min(10**(db/20)/max(rms,1e-9), 10)

def fade(wave, seconds):
    wave = wave.copy()
    count = min(int(seconds*RATE),len(wave)//2)
    if count:
        ramp = np.linspace(0,1,count)[:,None]
        wave[:count] *= ramp; wave[-count:] *= ramp[::-1]
    return wave

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--run-dir',type=Path,required=True)
    a = p.parse_args(); run = a.run_dir.resolve()
    cfg = json.loads(a.config.read_text(encoding='utf-8'))
    source = ROOT/cfg['source_video']
    if sha256(source) != cfg['source_video_sha256']: raise ValueError('Source video changed')
    duration = json.loads(source.with_suffix('.inspection.json').read_text())['duration_seconds']
    length = round(duration*RATE)
    folder = run/'mix'; folder.mkdir(parents=True,exist_ok=True)
    tracks, records = {}, []
    def place(name, path, db, start=0, source_start=0, seconds=None, fade_seconds=0.2):
        wave = read(path)
        offset = round(source_start*RATE)
        wave = wave[offset:offset+round(seconds*RATE)] if seconds else wave[offset:]
        wave = fade(level(wave,db),fade_seconds)
        track = np.zeros((length,2),dtype=np.float32)
        at = round(start*RATE); count = min(len(wave),length-at)
        track[at:at+count] = wave[:count]
        tracks[name] = track
        records.append(dict(name=name,source=str(path),sha256=sha256(path),target_rms_dbfs=db,
                            start_seconds=start,source_start_seconds=source_start,used_seconds=count/RATE))
    place('wind',run/'sfx/wind_101.wav',-39,fade_seconds=0.5)
    place('birds',run/'sfx/birds_101.wav',-36,fade_seconds=0.4)
    place('music',run/'music/quiet_mystery.wav',-29,seconds=duration,fade_seconds=1.1)
    voice_id = 'narration_1'
    if sf.info(run/f'clone/{voice_id}.wav').duration > duration-0.8:
        voice_id = 'narration_3'
    if sf.info(run/f'clone/{voice_id}.wav').duration > duration-0.8:
        raise ValueError('Narration does not fit; choose a shorter line instead of cutting speech.')
    place('voice',run/f'clone/{voice_id}.wav',-21,start=0.4,fade_seconds=0.03)
    # Align the strongest 10 ms transient of the generated single contact sound.
    # This is a first audition cue, not a measured video-to-audio sync model.
    contact = run/'sfx/lantern_303.wav'
    foley = read(contact)
    energy = np.mean(foley[:len(foley)//480*480].reshape(-1,480,2)**2,axis=(1,2))
    peak_time = int(np.argmax(energy))*0.01
    contact_source_start = max(0,peak_time-0.05)
    place('contact',contact,-28,start=7.85,source_start=contact_source_start,seconds=0.8,fade_seconds=0.01)
    # Smooth voice-driven music ducking; raw generated music remains untouched.
    activity = np.max(np.abs(tracks['voice']),axis=1)>0.008
    envelope = np.convolve(activity.astype(np.float32)[::480],np.ones(21)/21,mode='same')
    envelope = np.repeat(envelope,480)[:length]
    tracks['music'] *= (1-0.55*envelope[:,None])
    for name, wave in tracks.items(): sf.write(folder/(name+'.wav'),wave,RATE,subtype='PCM_24')
    mixed = sum(tracks.values())
    mix_peak = float(np.max(np.abs(mixed)))
    peak_gain = min(1,10**(-2/20)/max(mix_peak,1e-9))
    mixed *= peak_gain
    master = folder/'master.wav'
    sf.write(master,mixed,RATE,subtype='PCM_24')
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    output = folder/'greenhouse_audio_test.mp4'
    subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-y','-i',str(source),'-i',str(master),
        '-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','320k','-ar',str(RATE),
        '-t',str(duration),'-movflags','+faststart',str(output)],check=True)
    def video_hash(path):
        return subprocess.check_output([ffmpeg,'-v','error','-i',str(path),'-map','0:v:0','-c:v','copy',
            '-f','hash','-hash','sha256','-'],text=True).strip()
    original_hash, output_hash = video_hash(source), video_hash(output)
    if original_hash != output_hash: raise ValueError('Compressed video stream changed')
    subprocess.run([ffmpeg,'-v','error','-y','-i',str(source),'-map','0:a:0','-ar',str(RATE),
                    str(folder/'original_h3_audio.wav')],check=True)
    analysis = subprocess.run([ffmpeg,'-hide_banner','-i',str(master),'-af',
        'loudnorm=I=-18:TP=-1.5:LRA=11:print_format=json','-f','null','-'],capture_output=True,text=True,check=True)
    (folder/'loudness-analysis.txt').write_text(analysis.stderr,encoding='utf-8')
    write_json(folder/'mix.json',dict(status='success',subjective_review='pending_user_review',duration=duration,
        sample_rate=RATE,tracks=records,water_in_mix=False,narration_id=voice_id,peak_gain=peak_gain,
        peak=float(np.max(np.abs(mixed))),compressed_video_hash=original_hash,
        video_stream_unchanged=True,output=str(output),sha256=sha256(output),
        contact_peak_source_seconds=peak_time,contact_alignment='manual video inspection + audio energy peak; audition required',
        stems=[dict(path=str(folder/(name+'.wav')),sha256=sha256(folder/(name+'.wav'))) for name in tracks]))
    print('MIX_COMPLETE',str(output),flush=True)

if __name__ == '__main__': main()
