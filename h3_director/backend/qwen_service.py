"""Start the isolated Qwen image service without restarting existing GPU work."""
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request
from .paths import ROOT
from .local_service import START_LOCK,ServiceUnavailable,refused

URL='http://127.0.0.1:8190'

def request(url,path,data=None):
    req=urllib.request.Request(url+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=10) as response:return json.load(response)

def release_other(url):
    try:q=request(url,'/queue')
    except (urllib.error.URLError,OSError) as error:
        if refused(error):return
        raise ServiceUnavailable('另一图片/视频服务状态不明确，未提交生成：'+url) from error
    if q.get('queue_running') or q.get('queue_pending'):
        raise ServiceUnavailable('其他 GPU 任务正在运行，请等待完成：'+url)
    request(url,'/free',dict(unload_models=True,free_memory=True))

def ensure_running(folder,update,checkpoint=lambda:None,allow_start=True,timeout=120):
    with START_LOCK:
        checkpoint();release_other('http://127.0.0.1:8188')
        try:return request(URL,'/queue')
        except (urllib.error.URLError,OSError) as error:
            if not refused(error):raise ServiceUnavailable('Qwen 服务无法响应，未重启；请检查 8190 服务日志') from error
        if not allow_start:raise ServiceUnavailable('本任务 Qwen 服务连接已断开，保留任务记录，请先核查在途生成')
        folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
        log=folder/'qwen-startup.log'
        update('正在启动 Qwen 2.1 本地图片服务…')
        with log.open('a',encoding='utf-8') as out:
            env={k:v for k,v in os.environ.items() if 'API_KEY' not in k};env['PYTHONUTF8']='1'
            process=subprocess.Popen(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'start-qwen21.ps1')],
                cwd=ROOT,env=env,stdout=out,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            started=time.monotonic()
            while time.monotonic()-started<timeout:
                checkpoint()
                try:
                    result=request(URL,'/queue');update('Qwen 2.1 已就绪');return result
                except (urllib.error.URLError,OSError):pass
                if process.poll() not in (None,0):raise ServiceUnavailable('Qwen 启动失败，请查看 '+str(log))
                update(f'等待 Qwen 2.1 就绪 · {int(time.monotonic()-started)} 秒');time.sleep(1)
        raise ServiceUnavailable('Qwen 启动超时，未提交生成；请检查 '+str(log))
