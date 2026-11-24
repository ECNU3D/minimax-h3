import copy
import errno
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch,MagicMock
from urllib.error import URLError
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from h3_director.backend import local_service
from h3_director.backend.project import Store,make_asset,current
from h3_director.backend.production import configure
from h3_director.backend.runner import Runner

class AutoProduction(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name);self.runner=Runner(self.store,start=False)
  self.p=self.store.create('自动设置');self.p['assets']=[make_asset('杯','prop','P01')]
  self.p['shots']=[dict(id='s001',name='杯',prompt='<Picture 1> 杯子静止',originalPrompt='杯子静止',refs=['P01'],seconds=8,width=1344,height=768,seed=1,versions=[],selected=None,history=[])]
  self.store.save(self.p)
 def tearDown(self):self.tmp.cleanup()
 def test_configuration_persists_and_reaches_job_snapshot(self):
  options=dict(imageModel='base',videoModel='h3_ref2va_int8_turbo',videoResolution='portrait',videoSeconds=10,agentProvider='codex',agentModel='gpt-5.6-sol',agentThinking='high',autoReview=False)
  with patch('h3_director.backend.runner.agent_runtime'):
   job=self.runner.enqueue(self.p['id'],'auto',options=options,revision=self.p['revision'])
  saved=self.store.get(self.p['id']);snapshot=job['snapshot']
  self.assertEqual(saved['assets'][0]['imageVariant'],'base');self.assertEqual(snapshot['shots'][0]['width'],768);self.assertEqual(snapshot['shots'][0]['height'],1344);self.assertEqual(snapshot['shots'][0]['seconds'],10)
  self.assertEqual(job['productionSettings']['agentProvider'],'codex');self.assertFalse(job['autoReview']);self.assertEqual(snapshot['campaign'],self.p['campaign'])
  saved['assets'][0]['imageVariant']='distilled';self.store.save(saved);self.assertEqual(snapshot['assets'][0]['imageVariant'],'base')
 def test_rejected_settings_leave_project_and_queue_unchanged(self):
  before=copy.deepcopy(self.store.get(self.p['id']))
  for options in [dict(imageModel='unknown'),dict(videoSeconds=20),dict(videoModel='other'),dict(videoResolution='bad')]:
   with self.assertRaises(ValueError):self.runner.enqueue(self.p['id'],'auto',options=options)
  self.assertEqual(self.store.get(self.p['id']),before);self.assertEqual(self.runner.jobs,[])
 def test_existing_usable_assets_keep_model_and_mode(self):
  a=self.p['assets'][0];a['versions']=[dict(id='keep',prompt=a['prompt'],seed=a['seed'],files=[{'sha256':'hash'}])];a['selected']='keep'
  s=self.p['shots'][0];s['versions']=[dict(id='shot',prompt=s['prompt'],seed=s['seed'],seconds=8,width=1344,height=768,references=[{'sha256':'hash'}])];s['selected']='shot'
  configure(self.p,dict(imageModel='codex',videoModel='h3_ref2va_int8_turbo',videoResolution='portrait',videoSeconds=10))
  self.assertEqual(a['provider'],'local');self.assertEqual(s['width'],1344);self.assertEqual(s['seconds'],8)
 def test_video_dimension_changes_invalidate_reuse(self):
  s=self.p['shots'][0];a=self.p['assets'][0];a.update(selected='a',versions=[dict(id='a',files=[{'sha256':'x'}])]);s.update(selected='s',versions=[dict(id='s',prompt=s['prompt'],seed=s['seed'],references=[{'sha256':'x'}],width=1344,height=768)])
  self.assertTrue(current(self.p,'shots',s));s['width']=768;self.assertFalse(current(self.p,'shots',s))
 def test_service_reuses_online_busy_queue_without_start(self):
  queue={'queue_running':[[1,'other']],'queue_pending':[]}
  with patch.object(local_service,'probe',return_value=queue),patch.object(local_service.subprocess,'Popen') as start:
   self.assertEqual(local_service.ensure_running(self.tmp.name,lambda _:None),queue);start.assert_not_called()
 def test_service_starts_once_and_waits_ready(self):
  offline=URLError(ConnectionRefusedError(errno.ECONNREFUSED,'refused'));ready={'queue_running':[],'queue_pending':[]};messages=[]
  with patch.object(local_service,'probe',side_effect=[offline,offline,ready]),patch.object(local_service,'startup_alive',return_value=False),patch.object(local_service.time,'sleep'),patch.object(local_service.subprocess,'Popen') as start:
   start.return_value.poll.return_value=None
   self.assertEqual(local_service.ensure_running(self.tmp.name,messages.append),ready);self.assertEqual(start.call_count,1)
   args=start.call_args.args[0];self.assertIn('-Cuda13',args);self.assertIn('-SageAttention',args);self.assertIn('-KJNodes',args)
   self.assertTrue(any('就绪' in m for m in messages))
 def test_no_restart_when_inflight_or_response_is_ambiguous(self):
  for allow,error in [(False,URLError(ConnectionRefusedError(errno.ECONNREFUSED,'refused'))),(True,URLError(TimeoutError('timeout')))]:
   with patch.object(local_service,'probe',side_effect=error),patch.object(local_service.subprocess,'Popen') as start:
    with self.assertRaises(local_service.ServiceUnavailable):local_service.ensure_running(self.tmp.name,lambda _:None,allow_start=allow)
    start.assert_not_called()
 def test_already_starting_waits_without_duplicate_launcher(self):
  offline=URLError(ConnectionRefusedError(errno.ECONNREFUSED,'refused'));ready={'queue_running':[],'queue_pending':[]}
  with patch.object(local_service,'probe',side_effect=[offline,ready]),patch.object(local_service,'startup_alive',return_value=True),patch.object(local_service.subprocess,'Popen') as start:
   local_service.ensure_running(self.tmp.name,lambda _:None);start.assert_not_called()
 def test_start_failure_and_timeout_are_readable(self):
  offline=URLError(ConnectionRefusedError(errno.ECONNREFUSED,'refused'))
  with patch.object(local_service,'probe',side_effect=offline),patch.object(local_service,'startup_alive',return_value=False),patch.object(local_service.subprocess,'Popen') as start:
   start.return_value.poll.return_value=1
   with self.assertRaisesRegex(local_service.ServiceUnavailable,'启动失败'):local_service.ensure_running(self.tmp.name,lambda _:None)
  with patch.object(local_service,'probe',side_effect=offline),patch.object(local_service,'startup_alive',return_value=True):
   with self.assertRaisesRegex(local_service.ServiceUnavailable,'未就绪'):local_service.ensure_running(self.tmp.name,lambda _:None,timeout=0)
 def test_codex_images_do_not_start_comfy(self):
  j=self.runner.enqueue(self.p['id'],'asset','P01');a=j['snapshot']['assets'][0];a['provider']='codex'
  with patch.object(self.runner,'codex_asset',return_value='codex'),patch.object(self.runner,'ensure_local') as start:
   self.assertEqual(self.runner.asset(j['snapshot'],a,j),'codex');start.assert_not_called()
 def test_recorded_jobs_forbid_auto_restart(self):
  j=self.runner.enqueue(self.p['id'],'asset','P01');folder=self.store.folder/'runs'/j['id']/'P01_v0/jobs/front';folder.mkdir(parents=True);(folder/'job.json').write_text('{}')
  with patch.object(local_service,'ensure_running') as ensure:
   self.runner.ensure_local(j);self.assertFalse(ensure.call_args.kwargs['allow_start'])
if __name__=='__main__':unittest.main()
