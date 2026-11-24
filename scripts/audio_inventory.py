"""Export exact installed packages, code revisions, and measured audio results."""
import json
from pathlib import Path
import subprocess
from audio_common import ROOT, sha256, write_json

def main():
    out=ROOT/'docs/audio-environments';out.mkdir(parents=True,exist_ok=True)
    inventory={}
    for name,repo in [('sfx','MOSS-TTS'),('tts','Qwen3-TTS'),('music','ACE-Step-1.5')]:
        python=ROOT/f'audio/env-{name}/Scripts/python.exe'
        freeze=subprocess.check_output([str(ROOT/'tools/uv.exe'),'pip','freeze','--python',str(python)],text=True)
        (out/(name+'-freeze.txt')).write_text(freeze,encoding='utf-8')
        commit=subprocess.check_output(['git','-C',str(ROOT/'audio'/repo),'rev-parse','HEAD'],text=True).strip()
        changed=subprocess.check_output(['git','-C',str(ROOT/'audio'/repo),'status','--short'],text=True)
        inventory[name]=dict(commit=commit,git_status=changed,python=str(python),freeze=freeze)
    scripts=[*ROOT.glob('scripts/audio_*.py'),ROOT/'configs/audio-film-test.json']
    inventory['workflow_files']=[dict(path=str(p),sha256=sha256(p)) for p in scripts]
    inventory['runtime_ace_model_code']=[dict(path=str(p),sha256=sha256(p)) for p in (ROOT/'audio/models/ace/acestep-v15-sft').glob('*.py')]
    write_json(out/'inventory.json',inventory)
    run=ROOT/'runs/audio_film_test'
    results=[]
    for stage in ['design','clone','sfx','music']:
        for p in (run/stage).glob('*.json'):
            data=json.loads(p.read_text(encoding='utf-8'))
            if 'generation_seconds' in data:
                results.append(dict(stage=stage,id=p.stem,duration=data['duration'],generation_seconds=data['generation_seconds'],
                    sample_rate=data['sample_rate'],channels=data['channels'],peak=data['peak'],rms=data['rms'],
                    cuda_peak_allocated_gib=data['cuda_peak_allocated_bytes']/1024**3))
    write_json(run/'results-summary.json',results)
    print(json.dumps(results,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
