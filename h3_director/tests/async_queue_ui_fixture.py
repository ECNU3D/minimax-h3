"""Static isolated queue preview. No worker threads, GPU submissions or model calls."""
import copy
from http.server import ThreadingHTTPServer
from test_async_shots import AsyncShots
from h3_director.backend.server import Handler
from h3_director.backend.async_shots import choose, summary, append_task
from h3_director.backend.project import LOCK

fixture=AsyncShots();fixture.setUp()
try:
    fourth=copy.deepcopy(fixture.p['shots'][0]);fourth.update(id='s004',name='下一镜 · 等待生成')
    fixture.p['shots'].append(fourth);fixture.p['name']='异步队列 · 界面测试';fixture.store.save(fixture.p)
    job=fixture.batch()
    with fixture.adapters():
        for _ in range(4):fixture.runner.run_once()
    with LOCK:
        for _ in range(3):choose(fixture.runner,'review')
        extra=append_task(job,fourth);extra.update(attempt=1,message='Agent 建议重生成，已追加生成队列末尾')
        summary(job);fixture.runner.save()
    server=ThreadingHTTPServer(('127.0.0.1',8322),Handler)
    server.store=fixture.store;server.runner=fixture.runner
    print('Async queue UI fixture: http://127.0.0.1:8322/?project='+fixture.p['id']+'&view=jobs',flush=True)
    try:server.serve_forever()
    finally:server.server_close()
finally:fixture.tearDown()
