import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from h3_director.backend.project import Store,read
from h3_director.backend.runner import Runner
from h3_director.backend.validate_import import validate

class WorkspaceProgress(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.store=Store(self.temp.name);self.runner=Runner(self.store,start=False);self.p=self.store.create('可恢复')
 def tearDown(self):self.temp.cleanup()
 def test_restore_preserves_sources_campaign_versions_and_files(self):
  p=self.p;p['sources']=[{'text':'原文'}];p['assets']=[{'versions':[{'id':'original'}]}];self.store.save(p)
  file=self.store.path(p['id']).parent/'asset.png';file.write_bytes(b'original media')
  self.store.trash(p['id']);self.assertEqual(self.store.list(),[])
  with self.assertRaises(FileNotFoundError):self.store.get(p['id'])
  self.assertEqual(self.store.list(deleted=True)[0]['id'],p['id'])
  restored=self.store.restore(p['id'])
  for key in ('sources','assets','campaign'):self.assertEqual(restored[key],p[key])
  self.assertEqual(file.read_bytes(),b'original media')
 def test_deleted_job_cannot_resume(self):
  j=self.runner.enqueue(self.p['id'],'parse');j['status']='failed';self.store.trash(self.p['id'])
  with self.assertRaises(FileNotFoundError):self.runner.control(j['id'],'resume')
 def test_resume_uses_current_provider_preserving_production_inputs(self):
  j=self.runner.enqueue(self.p['id'],'parse');j.update(status='failed',events=[{'stage':'parse','event':'failed'}],finishedAt=123)
  old_source=copy.deepcopy(j['snapshot']['sources']);old_campaign=j['snapshot']['campaign']
  live=self.store.get(self.p['id']);live.update(agentProvider='codex',agentModel='gpt-5.6-luna',agentThinking='medium');self.store.save(live)
  self.runner.control(j['id'],'resume')
  self.assertEqual(j['snapshot']['agentProvider'],'codex');self.assertEqual(j['snapshot']['agentModel'],'gpt-5.6-luna');self.assertEqual(j['snapshot']['agentThinking'],'medium')
  self.assertEqual(j['snapshot']['sources'],old_source);self.assertEqual(j['snapshot']['campaign'],old_campaign)
  self.assertEqual(j['attempts'][0]['status'],'failed');self.assertEqual(j['events'],[]);self.assertNotIn('finishedAt',j)
 def test_failed_parse_cannot_replace_new_generated_assets(self):
  j=self.runner.enqueue(self.p['id'],'parse');j['status']='failed'
  live=self.store.get(self.p['id']);live['assets']=[{'versions':[{'id':'keep'}]}];self.store.save(live)
  with self.assertRaisesRegex(ValueError,'已有生成素材'):self.runner.control(j['id'],'resume')
 def test_parse_completion_preserves_newer_project_settings(self):
  import hashlib
  from unittest.mock import patch
  from h3_director.backend.project import write
  from h3_director.backend.importer import import_source
  self.p['sources']=[dict(id='s',name='empty.md',text='没有需要生成的素材。')];self.store.save(self.p)
  j=self.runner.enqueue(self.p['id'],'parse');live=self.store.get(self.p['id']);live['agentProvider']='codex';self.store.save(live)
  source=import_source(j['snapshot']['sources']);folder=self.store.folder/'runs'/j['id']
  write(folder/'parse-output.json',dict(sourceSha256=hashlib.sha256(source['text'].encode()).hexdigest(),provider='deepseek',thinking='max',assets=[],shots=[]))
  with patch.object(self.runner,'command') as command:self.runner.execute(j);command.assert_not_called()
  self.assertEqual(self.store.get(self.p['id'])['agentProvider'],'codex')
 def test_live_subprocess_events_persist_before_exit(self):
  j=self.runner.enqueue(self.p['id'],'parse');folder=self.store.folder/'test'
  script='import json,time;print(json.dumps({"type":"director.progress","stage":"parse","event":"started"},separators=(",",":")),flush=True);time.sleep(2.5)'
  worker=threading.Thread(target=self.runner.command,args=([sys.executable,'-c',script],folder,j));worker.start()
  deadline=time.time()+2.2
  while not j.get('events') and time.time()<deadline:time.sleep(.05)
  self.assertTrue(j.get('events'));self.assertTrue(worker.is_alive())
  self.assertEqual(read(self.runner.file)[0]['events'][0]['stage'],'parse');worker.join()
 def test_protocol_omits_unknown_fields_and_limits_history(self):
  j=self.runner.enqueue(self.p['id'],'parse')
  for _ in range(205):self.runner.event(j,dict(type='director.progress',stage='parse',event='started',reasoning='PRIVATE',prompt='PRIVATE'))
  self.assertEqual(len(j['events']),200);self.assertNotIn('PRIVATE',json.dumps(j['events']))
 def test_validation_names_bad_asset_and_leaves_source_untouched(self):
  import hashlib
  source=dict(id='test',name='参考.md',text='正文\n\n')
  result=dict(sourceSha256=hashlib.sha256(source['text'].encode()).hexdigest(),assets=[dict(id='R05',name='人',kind='character',description='人',promptVariants=[dict(role='back',label='背面',startLine=2,endLine=2)])],shots=[])
  before=copy.deepcopy(result);v=validate(dict(source=source,result=result))
  self.assertFalse(v['ok']);self.assertIn('R05 / back',v['error']);self.assertIn('2–2',v['error']);self.assertEqual(result,before)
if __name__=='__main__':unittest.main()
