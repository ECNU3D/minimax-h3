"""Isolated prompt optimizer UI; no generation/model workers, fixture candidates only."""
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from h3_director.backend.project import Store
from h3_director.backend.runner import Runner
from h3_director.backend.server import Handler
from h3_director.backend.lab_templates import create_case
from h3_director.backend.prompt_optimizer import complete

with tempfile.TemporaryDirectory(prefix='h3-optimizer-ui-') as folder:
 runner=Runner(Store(folder),start=False)
 e=create_case(runner.lab,'zh_solo');e['name']='优化与回退 · 独立界面测试';runner.lab.save(e)
 row=runner.optimizer.create(dict(scope='lab',owner=e['id'],target='shot',revision=e['revision'],language='zh'))
 candidate=complete(e).replace('detailed_description:','detailed_description:\n固定机位，保持人物居中。',1)
 with patch.object(runner.optimizer,'invoke',return_value=dict(prompt=candidate,changes=['明确固定机位与人物位置'],warnings=['这是界面测试候选，未调用模型。'],model='UI fixture')):runner.optimizer.run(row['id'])
 server=ThreadingHTTPServer(('127.0.0.1',8322),Handler);server.store=runner.store;server.runner=runner
 print('Optimizer UI fixture http://127.0.0.1:8322/?view=lab',flush=True)
 try:server.serve_forever()
 finally:server.server_close()
