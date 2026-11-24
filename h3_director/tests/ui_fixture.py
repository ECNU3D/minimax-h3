"""Isolated browser fixture. Worker DISABLED: clicks only enqueue, never generate."""
import copy
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from h3_director.backend.paths import DATA
from h3_director.backend.project import Store,make_asset,selected
from h3_director.backend.runner import Runner
from h3_director.backend.server import Handler

with tempfile.TemporaryDirectory(prefix='h3-director-ui-') as folder:
    store=Store(folder);runner=Runner(store,start=False)
    project=store.create('界面回归 · 模拟队列（不生成）')
    project['assets']=[make_asset(name,'prop',key) for key,name in [('P01','人工采用按钮检查'),('P02','正在生成图片（模拟）'),('P03','待排队图片')]]
    source=Store(DATA).get('fb30ec018c8f')
    version=copy.deepcopy(selected(source['assets'][0]))
    version['humanAccepted']=False;version['review'].update(verdict='human',confidence=.6)
    project['assets'][0]['versions']=[version];project['assets'][0]['selected']=version['id']
    store.save(project)
    job=runner.enqueue(project['id'],'asset','P02')
    job.update(status='running',message='仅模拟运行状态；后台执行器未启动');runner.save()
    server=ThreadingHTTPServer(('127.0.0.1',8322),Handler)
    server.store=store;server.runner=runner
    print('UI fixture http://127.0.0.1:8322/; no generation worker',flush=True)
    try:server.serve_forever()
    finally:server.server_close()
