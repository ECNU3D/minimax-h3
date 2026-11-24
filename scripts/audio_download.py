"""Pin and verify public audio-model snapshots; downloads only, never executes repository code."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]

def fetch_json(url, proxy):
    command=['curl.exe','--fail','-L','-sS','--retry','5','--retry-all-errors','--retry-delay','2','--connect-timeout','30']
    if proxy: command += ['--proxy',proxy]
    return json.loads(subprocess.check_output(command+[url],text=True,encoding='utf-8'))

def catalog(repo, proxy):
    folder=ROOT/'docs/audio-models';folder.mkdir(parents=True,exist_ok=True)
    path=folder/(repo.replace('/','--')+'.json')
    if path.exists(): return json.loads(path.read_text(encoding='utf-8'))
    revision=fetch_json('https://huggingface.co/api/models/'+repo,proxy)['sha']
    files=fetch_json(f'https://huggingface.co/api/models/{repo}/tree/{revision}?recursive=true&limit=1000',proxy)
    result=dict(repo=repo,revision=revision,files=[x for x in files if x['type']=='file'])
    path.write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result

def download_file(spec, item, destination, proxy):
    target=destination/item['path'];target.parent.mkdir(parents=True,exist_ok=True)
    candidate=target if target.exists() else target.with_suffix(target.suffix+'.part')
    if not target.exists():
        url=f"https://huggingface.co/{spec['repo']}/resolve/{spec['revision']}/{item['path']}?download=true"
        log=ROOT/'logs'/('audio_'+spec['repo'].replace('/','_')+'_'+item['path'].replace('/','_')+'.log')
        aria=ROOT/'tools/aria2-1.37.0-win-64bit-build1/aria2c.exe'
        command=[str(aria),'--no-conf=true','--continue=true','--max-connection-per-server=4','--split=4','--min-split-size=32M','--file-allocation=none','--max-tries=12','--retry-wait=3','--connect-timeout=30','--timeout=90','--auto-file-renaming=false','--console-log-level=warn','--enable-color=false','--dir='+str(target.parent),'--out='+candidate.name,url]
        if proxy: command.insert(1,'--all-proxy='+proxy)
        print('DOWNLOAD',spec['repo'],item['path'],item['size'],flush=True)
        with log.open('a',encoding='utf-8') as stream:
            for attempt in range(6):
                result = subprocess.run(command,stdout=stream,stderr=stream)
                if result.returncode == 0: break
                time.sleep(3 * (attempt + 1))
            result.check_returncode()
    if candidate.stat().st_size != item['size']: raise ValueError('Size mismatch: '+str(candidate))
    data_hash=hashlib.sha256()
    git_hash=hashlib.sha1(f"blob {item['size']}\0".encode())
    with candidate.open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b''): data_hash.update(chunk);git_hash.update(chunk)
    actual=data_hash.hexdigest()
    if item.get('lfs'):
        if actual!=item['lfs']['oid']: raise ValueError('SHA256 mismatch: '+str(candidate))
    elif git_hash.hexdigest()!=item['oid']: raise ValueError('Git blob hash mismatch: '+str(candidate))
    if candidate != target: candidate.replace(target)
    print('VERIFIED',target,flush=True)
    return dict(path=str(target),source_path=item['path'],bytes=item['size'],sha256=actual)

def main():
    p=argparse.ArgumentParser();p.add_argument('repo');p.add_argument('--dest',type=Path);p.add_argument('--include',action='append',default=[]);p.add_argument('--proxy',default='http://127.0.0.1:7897');a=p.parse_args()
    spec=catalog(a.repo,a.proxy)
    files=[x for x in spec['files'] if not a.include or any(x['path']==s or x['path'].startswith(s.rstrip('/')+'/') for s in a.include)]
    if not a.dest:
        print(json.dumps(dict(repo=a.repo,revision=spec['revision'],files=[(x['path'],x['size']) for x in files]),indent=2));return
    destination=a.dest.resolve();destination.mkdir(parents=True,exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool: verified=list(pool.map(lambda x:download_file(spec,x,destination,a.proxy),files))
    report=dict(repo=spec['repo'],revision=spec['revision'],verified_at=time.time(),files=verified)
    (destination/'snapshot-verified.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('SNAPSHOT COMPLETE',a.repo,flush=True)

if __name__=='__main__':main()
