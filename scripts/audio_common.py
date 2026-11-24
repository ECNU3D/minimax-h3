"""Records reproducible audio outputs and sampled process/GPU resource usage."""
import hashlib
import json
import subprocess
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()

def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)

def fingerprint(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def completed(folder, job, identity):
    record = folder / (job['id'] + '.json')
    if not record.exists(): return False
    info = json.loads(record.read_text(encoding='utf-8'))
    if info.get('identity') != fingerprint(identity):
        raise ValueError(f"Changed inputs for {record}; use a new run directory.")
    return info.get('status') == 'success' and Path(info['output']).exists() and sha256(info['output']) == info['sha256']

def save_audio(folder, job, identity, wave, sample_rate, seconds, extra=None):
    import numpy as np
    import soundfile as sf
    wave = np.asarray(wave, dtype=np.float32)
    if wave.ndim == 1: wave = wave[:, None]
    if not np.isfinite(wave).all() or len(wave) == 0: raise ValueError('Invalid waveform')
    peak = float(np.max(np.abs(wave)))
    rms = float(np.sqrt(np.mean(wave.astype(np.float64)**2)))
    if rms < 1e-7: raise ValueError('Silent waveform')
    path = folder / (job['id'] + '.wav')
    folder.mkdir(parents=True, exist_ok=True)
    # Float WAV preserves the raw waveform, including any model overshoots.
    sf.write(path, wave, sample_rate, subtype='FLOAT')
    info = dict(status='success', subjective_review='pending_user_review', identity=fingerprint(identity), inputs=identity,
                output=str(path.resolve()), sha256=sha256(path), sample_rate=sample_rate,
                channels=wave.shape[1], duration=len(wave)/sample_rate, generation_seconds=seconds,
                peak=peak, rms=rms, samples_over_full_scale=int(np.sum(np.abs(wave)>1)), **(extra or {}))
    write_json(folder / (job['id'] + '.json'), info)
    print('AUDIO_COMPLETE', job['id'], round(info['duration'], 3), flush=True)

class Monitor:
    """Samples total GPU memory and current process RAM every two seconds."""
    def __init__(self):
        self.samples = []
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._poll, daemon=True)
    def _poll(self):
        import psutil
        process = psutil.Process()
        while not self.stop.is_set():
            row = dict(time=time.time(), process_rss=process.memory_info().rss,
                       system_available=psutil.virtual_memory().available)
            try:
                values = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used,utilization.gpu', '--format=csv,noheader,nounits'], text=True, timeout=8).strip().split(',')
                row.update(gpu_used_mib=int(values[0]), gpu_utilization=int(values[1]))
            except (OSError, subprocess.SubprocessError, ValueError): pass
            self.samples.append(row)
            self.stop.wait(2)
    def __enter__(self): self.thread.start(); return self
    def __exit__(self, *args): self.stop.set(); self.thread.join(timeout=10)
