import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from h3_director.backend.project import Store,make_asset,read
from h3_director.backend.runner import Runner
from h3_director.backend.prompt_optimizer import validate_candidate,complete
from h3_director.backend.server import Handler

PROMPT='''subject_definitions:
<Subject 1> 来自 <Picture 1>，保留人物身份。
summary:
[reference generation] 一个人在室内说话。
retention_analysis:
<Subject 1>: fully_preserved - 保留人物身份。
detailed_description:
[Shot 1] 固定中景，人物 (S1) 说 <d>[Chinese]你好。</d>，5 秒内完成。
overall_soundscape:
低微室内底声。
non_diegetic_music:
N/A'''

class PromptOptimizerTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name);self.runner=Runner(self.store,start=False);self.service=self.runner.optimizer
  self.p=self.store.create('optimizer fixture');a=make_asset('人物','character','P1');self.p['assets']=[a]
  self.shot=dict(id='s001',name='test',prompt=PROMPT,refs=['P1'],seconds=5,seed=7,width=1344,height=768,versions=[],selected=None,history=[])
  self.p['shots']=[self.shot];self.store.save(self.p)
 def tearDown(self):self.tmp.cleanup()
 def create(self):return self.service.create(dict(scope='project',owner=self.p['id'],target='s001',revision=self.store.get(self.p['id'])['revision'],language='zh'))
 def ready(self):
  row=self.create()
  with patch.object(self.service,'invoke',return_value=dict(prompt=PROMPT.replace('固定中景','固定正面中景'),changes=['明确机位'],warnings=[],model='fixture')):self.service.run(row['id'])
  return read(self.service.path(row['id']))
 def test_proposal_apply_rollback_and_no_generation_budget_changes(self):
  before=self.store.get(self.p['id']);row=self.ready()
  self.assertEqual(row['status'],'ready');self.assertEqual(self.store.get(self.p['id']),before);self.assertFalse(self.runner.jobs)
  self.service.apply(row['id']);after=self.store.get(self.p['id'])
  self.assertIn('固定正面中景',after['shots'][0]['prompt']);self.assertEqual(after['campaign'],before['campaign'])
  for field in ('refs','seconds','seed','versions'):self.assertEqual(after['shots'][0][field],before['shots'][0][field])
  self.service.apply(row['id'],True);restored=self.store.get(self.p['id'])
  self.assertEqual(restored['shots'][0]['prompt'],PROMPT);self.assertEqual(len(restored['shots'][0]['promptOptimizationHistory']),2)
 def test_changed_prompt_and_references_prevent_stale_adoption(self):
  row=self.ready();p=self.store.get(self.p['id']);p['shots'][0]['seconds']=6;self.store.save(p)
  with self.assertRaisesRegex(ValueError,'已改变'):self.service.apply(row['id'])
  p['shots'][0]['seconds']=5;p['shots'][0]['prompt']='manual edit';self.store.save(p)
  with self.assertRaisesRegex(ValueError,'已改变'):self.service.apply(row['id'])
 def test_later_manual_edits_not_discarded_by_rollback(self):
  row=self.ready();self.service.apply(row['id']);p=self.store.get(self.p['id']);p['shots'][0]['prompt']+='\n手动修改';self.store.save(p)
  with self.assertRaisesRegex(ValueError,'已改变'):self.service.apply(row['id'],True)
 def test_references_dialogue_structure_and_sound_validation(self):
  source,_,_=self.service.source('project',self.p['id'],'s001')
  for bad in [PROMPT.replace('Picture 1','Picture 2'),PROMPT.replace('你好。','再见。'),PROMPT.replace('summary:','summary中文:'),PROMPT.replace('低微室内底声。','无人声，无对白。')]:
   with self.assertRaises(ValueError):validate_candidate(bad,source)
 def test_duplicates_failures_restart_preserve_original(self):
  row=self.create()
  with self.assertRaisesRegex(ValueError,'已有优化任务'):self.create()
  with patch.object(self.service,'invoke',side_effect=ValueError('fixture failure')):self.service.run(row['id'])
  self.assertEqual(read(self.service.path(row['id']))['status'],'failed')
  nextrow=self.create();restarted=Runner(self.store,start=False)
  self.assertEqual(read(restarted.optimizer.path(nextrow['id']))['status'],'failed')
  self.assertEqual(self.store.get(self.p['id'])['shots'][0]['prompt'],PROMPT)
 def test_lab_three_fields_languages_roundtrip(self):
  e=self.runner.lab.create();parts=validate_candidate(PROMPT,self.service.source('project',self.p['id'],'s001')[0])
  # A text-only experiment must not inherit a fictitious Picture reference.
  e.update({k:v.replace('<Picture 1>','文字设定') for k,v in parts.items()});self.runner.lab.save(e)
  e=self.runner.lab.get(e['id']);before=copy.deepcopy(e)
  row=self.service.create(dict(scope='lab',owner=e['id'],target='shot',revision=e['revision'],language='en'))
  output=complete(e).replace('固定中景','A static medium shot')
  with patch.object(self.service,'invoke',return_value=dict(prompt=output,changes=['测试'],warnings=[],model='fixture')):self.service.run(row['id'])
  self.service.apply(row['id']);after=self.runner.lab.get(e['id'])
  self.assertEqual(after['promptLanguage'],'en');self.assertIn('A static',after['promptVariants']['en']['prompt'])
  self.assertEqual(after['settings'],before['settings']);self.assertEqual(after['campaign'],before['campaign'])
  self.service.apply(row['id'],True);restored=self.runner.lab.get(e['id'])
  for key in ('prompt','soundscape','music','promptLanguage','promptVariants'):self.assertEqual(restored[key],before[key])
 def test_http_roundtrip(self):
  server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.store=self.store;server.runner=self.runner
  thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  def call(path,data=None):
   req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/prompt-optimizations'+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
   with urllib.request.urlopen(req) as response:return json.load(response)
  try:
   row=call('',dict(scope='project',owner=self.p['id'],target='s001',revision=self.p['revision'],language='zh'))
   with patch.object(self.service,'invoke',return_value=dict(prompt=PROMPT,changes=[],warnings=[])):self.service.run(row['id'])
   self.assertEqual(call('/project/'+self.p['id']+'/s001')[0]['status'],'ready')
   self.assertEqual(call('/'+row['id']+'/apply',{})['status'],'applied')
   self.assertEqual(call('/'+row['id']+'/rollback',{})['status'],'rolled_back')
  finally:server.shutdown();server.server_close();thread.join()
