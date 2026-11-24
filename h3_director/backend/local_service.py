"""Start the installed local service only before generation, never restart in-flight work."""
import errno
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import urllib.error
import urllib.request
from .paths import ROOT

URL='http://127.0.0.1:8188'
START_LOCK=threading.Lock()

class ServiceUnavailable(RuntimeError): pass

def probe():
    with urllib.request.urlopen(URL+'/queue',timeout=3) as response:
        result=json.load(response)
    if not isinstance(result.get('queue_running'),list) or not isinstance(result.get('queue_pending'),list):
        raise ServiceUnavailable('8188 端口响应不是有效的 ComfyUI 队列，请检查本地服务。')
    return result

def refused(error):
    reason=getattr(error,'reason',error)
    return getattr(reason,'winerror',None)==10061 or getattr(reason,'errno',None) in (errno.ECONNREFUSED,10061)

def startup_alive():
    """Check the recorded launcher without sending signals to a Windows process."""
    try: pid=int((ROOT/'logs/comfy.pid').read_text().strip())
    except (OSError,ValueError):return False
    if os.name!='nt':return False
    import ctypes
    from ctypes import wintypes
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];api.OpenProcess.restype=wintypes.HANDLE
    api.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    api.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=api.OpenProcess(0x1000,False,pid)
    if not handle:return False
    try:
        code=wintypes.DWORD()
        return bool(api.GetExitCodeProcess(handle,ctypes.byref(code))) and code.value==259
    finally:api.CloseHandle(handle)

def ensure_running(folder,update,checkpoint=lambda:None,allow_start=True,timeout=90,peer_url=None):
    with START_LOCK:
        checkpoint()
        if peer_url:
            from .qwen_service import release_other
            release_other(peer_url)
        try:return probe()
        except (urllib.error.URLError,OSError) as error:
            if not refused(error):raise ServiceUnavailable('ComfyUI 无法响应，请检查本机 8188 服务与日志；未自动重启。') from error
        if not allow_start:
            raise ServiceUnavailable('ComfyUI 连接已断开；本任务已有生成或在途记录，保留原任务等待对账，不自动重启。')
        folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
        log=folder/'comfy-startup.log';started=time.monotonic();launcher=None
        update('ComfyUI 未运行，正在启动本地生成服务…')
        with log.open('a',encoding='utf-8') as output:
            if not startup_alive():
                env={k:v for k,v in os.environ.items() if 'API_KEY' not in k};env['PYTHONUTF8']='1'
                launcher=subprocess.Popen(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'start.ps1'),
                    '-Cuda13','-SageAttention','-KJNodes','-VramHeadroom','8','-DisablePinnedMemory'],cwd=ROOT,env=env,
                    stdout=output,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            while time.monotonic()-started<timeout:
                checkpoint()
                try:
                    result=probe();update('ComfyUI 已就绪，继续制作');return result
                except (urllib.error.URLError,OSError):pass
                if launcher and launcher.poll() not in (None,0):
                    raise ServiceUnavailable('ComfyUI 启动失败，请查看 '+str(log)+' 和 logs/comfy.stderr.log；尚未提交生成。')
                update(f'正在等待 ComfyUI 就绪 · {int(time.monotonic()-started)} 秒（最多 {timeout} 秒）')
                time.sleep(1)
        raise ServiceUnavailable(f'ComfyUI 在 {timeout} 秒内未就绪，未提交生成。请查看 logs/comfy.stderr.log；未终止服务或自动重复启动。')
