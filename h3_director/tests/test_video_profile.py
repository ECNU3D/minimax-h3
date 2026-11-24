import copy
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from h3_director.backend.project import Store,make_asset,clear_shot,restore_shot,read,write
from h3_director.backend.runner import Runner
from h3_director.backend.production import VIDEO_PROFILE,configure

class VideoProfile(unittest.TestCase):
 def test_production_graph_matches_approved_lab_baseline(self):
  from scripts.generate import graph
  from scripts.h3_lab_config import DEFAULTS
  args=SimpleNamespace(profile=VIDEO_PROFILE,references=['ref.png'],comfy_references=['ref.png'],
   comfy_audio_references=[],width=1344,height=768,base=False,int8=True,prompt_file=None,
   seconds=12,seed=20260920,image=None,memory_efficient_sage=True,head_chunks=4,ffn_chunks=8,
   steps=None,crop_720p=False,crop_1080p=False,name='baseline',lab_settings=dict(DEFAULTS))
  production=graph(args)
  self.assertEqual(production['9']['inputs']['sampler_name'],'euler')
  self.assertEqual(production['10']['inputs'],dict(model=['31',0],scheduler='simple',steps=8,denoise=1.0))
  self.assertEqual(production['33']['inputs'],dict(model=['6',0],shift_video=12.0,shift_audio=3.0))
  self.assertEqual(production['6']['inputs']['strength_model'],1.0)
  args.profile='ref2v-lab'
  baseline=graph(args)
  # The lab also saves an audition FLAC; all video/audio generation nodes must match.
  baseline.pop('19')
  self.assertEqual(production,baseline)
  args.profile=VIDEO_PROFILE;args.width=768;args.height=1344
  portrait=graph(args)
  self.assertEqual((portrait['5']['inputs']['width'],portrait['5']['inputs']['height']),(768,1344))
  portrait['5']['inputs'].update(width=1344,height=768)
  self.assertEqual(portrait,production)
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name);self.runner=Runner(self.store,start=False)
  self.p=self.store.create('768p test');a=make_asset('reference','prop','P')
  a.update(selected='ref',versions=[dict(id='ref',prompt=a['prompt'],seed=a['seed'],files=[dict(path=str(Path(self.tmp.name)/'ref.png'),sha256='x')],humanAccepted=True)])
  self.p['assets']=[a]
  self.s=dict(id='s001',name='shot',prompt='<Picture 1> still',refs=['P'],seed=1,seconds=5,width=1344,height=768,versions=[],selected=None,history=[])
  self.p['shots']=[self.s];self.store.save(self.p)
 def tearDown(self):self.tmp.cleanup()
 def version(self):
  f=Path(self.tmp.name)/'old.mp4';f.write_bytes(b'old preserved')
  v=dict(id='old',prompt=self.s['prompt'],seed=1,seconds=5,width=1344,height=768,files=[dict(path=str(f),sha256='old')],references=[{'sha256':'x'}])
  self.s.update(versions=[v],selected='old');return f
 def test_new_single_and_batch_jobs_use_default_profile(self):
  for kind in ['shot','preflight','auto','shots_auto','shot_auto']:
   with patch('h3_director.backend.production.require_references'):
    job=self.runner.enqueue(self.p['id'],kind,'s001' if kind in ('shot','preflight','shot_auto') else None)
   self.assertEqual(job['snapshot']['videoProfile'],VIDEO_PROFILE)
   with patch.object(self.runner,'command'):
    self.runner.shot(job['snapshot'],job['snapshot']['shots'][0],job,preflight=True)
   spec=read(self.store.folder/'runs'/job['id']/'s001_v0/spec.json')[0]
   self.assertEqual(spec['profile'],VIDEO_PROFILE);self.assertEqual((spec['width'],spec['height']),(1344,768))
   job['status']='cancelled'
 def test_existing_spec_is_not_rewritten_on_resume(self):
  job=self.runner.enqueue(self.p['id'],'shot','s001')
  folder=self.store.folder/'runs'/job['id']/'s001_v0';spec=[dict(name='s001',seconds=5,legacy=True)]
  write(folder/'spec.json',spec)
  with patch.object(self.runner,'command'):self.runner.shot(job['snapshot'],job['snapshot']['shots'][0],job,preflight=True)
  self.assertEqual(read(folder/'spec.json'),spec)
 def test_portrait_settings_reach_single_and_batch_specs(self):
  self.s['videoResolution']='portrait';self.store.save(self.p)
  single=self.runner.enqueue(self.p['id'],'preflight','s001')
  self.assertEqual(single['videoDimensions'],[768,1344])
  self.s['videoResolution']='landscape';self.store.save(self.p)
  single['status']='cancelled'
  for job in (single,self.runner.enqueue(self.p['id'],'auto',options={'videoResolution':'portrait','autoReview':False})):
   self.assertEqual(job['snapshot']['shots'][0]['videoResolution'],'portrait')
   with patch.object(self.runner,'command'):
    self.runner.shot(job['snapshot'],job['snapshot']['shots'][0],job,preflight=True)
   spec=read(self.store.folder/'runs'/job['id']/'s001_v0/spec.json')[0]
   self.assertEqual((spec['width'],spec['height'],spec['profile']),(768,1344,VIDEO_PROFILE))
  self.assertEqual(job['productionSettings']['videoResolution'],'portrait')
 def test_single_shots_queue_with_frozen_inputs_and_unrelated_edits(self):
  second=copy.deepcopy(self.s);second['id']='s002';self.p['shots'].append(second);self.store.save(self.p)
  first=self.runner.enqueue(self.p['id'],'shot','s001');first['status']='running'
  queued=self.runner.enqueue(self.p['id'],'shot','s002')
  self.assertEqual(queued['status'],'queued')
  with self.assertRaisesRegex(ValueError,'已经排队'):self.runner.enqueue(self.p['id'],'shot_auto','s002')
  self.assertTrue(self.runner.can_edit(self.p['id'],'shot','s001'))
  self.assertTrue(self.runner.can_edit(self.p['id'],'asset','P'))
  self.assertTrue(self.runner.can_edit(self.p['id'],'accept','P'))
  self.assertFalse(self.runner.can_edit(self.p['id'],'accept','s001'))
  self.assertFalse(self.runner.can_edit(self.p['id'],'clear-shot','s002'))
  original=copy.deepcopy(queued['snapshot'])
  live=self.store.get(self.p['id']);live['shots'][1]['prompt']='updated <Picture 1>';self.store.save(live)
  next_version=self.runner.enqueue(self.p['id'],'shot','s002')
  self.assertEqual(queued['snapshot'],original)
  self.assertNotEqual(next_version['snapshot']['shots'][1]['prompt'],original['shots'][1]['prompt'])
  shot=queued['snapshot']['shots'][1];shot['versions']=[dict(id='take')];shot['selected']='take'
  self.runner.persist_item(queued['snapshot'],'shots',shot)
  self.assertEqual(self.store.get(self.p['id'])['shots'][1]['prompt'],'updated <Picture 1>')
  first['status']='success'
  self.assertEqual(self.runner.next_queued()['id'],queued['id'])
 def test_shot_queue_preflight_review_pause_resume_and_restart(self):
  self.version();self.store.save(self.p)
  first=self.runner.enqueue(self.p['id'],'shot','s001')
  preflight=self.runner.enqueue(self.p['id'],'preflight','s001')
  review=self.runner.enqueue(self.p['id'],'review','P')
  self.assertEqual(review['status'],'queued')
  with self.assertRaisesRegex(ValueError,'已经排队'):self.runner.enqueue(self.p['id'],'preflight','s001')
  self.runner.control(first['id'],'pause');self.runner.control(first['id'],'resume')
  self.assertEqual(first['status'],'queued')
  first['status']='running';self.runner.save()
  restarted=Runner(self.store,start=False)
  self.assertIsNone(restarted.next_queued())
  self.assertFalse(restarted.can_edit(self.p['id'],'shot','s001'))
  restarted.control(first['id'],'resume')
  self.assertEqual(restarted.next_queued()['id'],first['id'])
  with patch('h3_director.backend.runner.budget',return_value={'stop':True}):
   with self.assertRaisesRegex(ValueError,'STOP'):restarted.enqueue(self.p['id'],'shot','s001')
 def test_single_auto_locks_its_reference_versions_and_flows_stay_exclusive(self):
  job=self.runner.enqueue(self.p['id'],'shot_auto','s001')
  self.assertFalse(self.runner.can_edit(self.p['id'],'select','P'))
  self.assertTrue(self.runner.can_edit(self.p['id'],'shot','s001'))
  for kind in ['auto','shots_auto','assets_auto','parse','export']:
   with self.assertRaises(ValueError):self.runner.enqueue(self.p['id'],kind)
  job['status']='success'
  with patch('h3_director.backend.production.require_references'):
   self.runner.enqueue(self.p['id'],'shots_auto')
  with self.assertRaises(ValueError):self.runner.enqueue(self.p['id'],'shot','s001')
 def test_http_shot_queue_and_edit_while_running(self):
  import json
  import threading
  import urllib.request
  from http.server import ThreadingHTTPServer
  from h3_director.backend.server import Handler
  second=copy.deepcopy(self.s);second['id']='s002';self.p['shots'].append(second);self.store.save(self.p)
  server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.store=self.store;server.runner=self.runner
  thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  def call(path,data=None):
   request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/'+path,
    data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
   with urllib.request.urlopen(request) as response:return json.load(response)
  try:
   first=call('jobs',dict(projectId=self.p['id'],kind='shot',target='s001'))
   self.runner.jobs[0]['status']='running'
   updated=call(f'projects/{self.p["id"]}/shot',dict(id='s002',prompt='edited <Picture 1>',revision=self.p['revision']))
   self.assertEqual(updated['shots'][1]['prompt'],'edited <Picture 1>')
   second=call('jobs',dict(projectId=self.p['id'],kind='shot_auto',target='s002'))
   listing=call('jobs');queued=next(j for j in listing if j['id']==second['id'])
   self.assertEqual(queued['status'],'queued');self.assertIn('P',queued['ownedTargets'])
   self.assertNotIn('snapshot',queued)
   self.assertEqual(next(j for j in listing if j['id']==first['id'])['status'],'running')
  finally:server.shutdown();server.server_close();thread.join()
 def test_manual_clear_preserves_files_and_starts_one_round_for_consecutive_clears(self):
  path=self.version();old=copy.deepcopy(self.s);campaign=self.p['campaign']
  ledger={'attempts':{'s001':['first','second']},'failure_count':0};before=copy.deepcopy(ledger)
  clear_shot(self.p,self.s,ledger)
  self.assertNotEqual(self.p['campaign'],campaign);self.assertEqual(ledger,before);self.assertTrue(path.exists())
  self.assertFalse(self.s['versions']);self.assertIsNone(self.s['selected'])
  fresh=self.p['campaign'];other=copy.deepcopy(old);other['id']='s002';clear_shot(self.p,other,{})
  self.assertEqual(self.p['campaign'],fresh)
  restore_shot(self.s);self.assertEqual(self.s['versions'],old['versions']);self.assertEqual(self.s['selected'],'old')
 def test_clear_is_scoped_to_unfinished_shot_writes(self):
  from h3_director.backend.runner import shot_clear_targets
  self.version()
  other=copy.deepcopy(self.s);other.update(id='s002',versions=[],selected=None)
  self.p['shots'].append(other);self.store.save(self.p)
  job=self.runner.enqueue(self.p['id'],'shot','s002')
  for state in ('queued','running','paused','interrupted'):
   job['status']=state
   self.assertTrue(self.runner.can_edit(self.p['id'],'clear-shot','s001'))
   self.assertFalse(self.runner.can_edit(self.p['id'],'clear-shot','s002'))
  for kind in ('asset','assets_auto','preflight','dependencies','export'):
   job.update(kind=kind,target='s001')
   self.assertTrue(self.runner.can_edit(self.p['id'],'clear-shot','s001'))
  job.update(kind='review',target='s001')
  self.assertFalse(self.runner.can_edit(self.p['id'],'clear-shot','s001'))
  job.update(kind='shots_auto',target=None,done=[])
  self.assertEqual(shot_clear_targets(job),['s002'])
  job['retryStates']={'shots/s001':{'attempt':0}}
  self.assertEqual(set(shot_clear_targets(job)),{'s001','s002'})
  job['done']=['shots/s001','shots/s002']
  self.assertEqual(shot_clear_targets(job),[])
 def test_http_clear_during_other_generation_preserves_snapshot_and_budget(self):
  import json
  import threading
  import urllib.request
  from http.server import ThreadingHTTPServer
  from h3_director.backend.server import Handler
  path=self.version();other=copy.deepcopy(self.s);other.update(id='s002',versions=[],selected=None)
  self.p['shots'].append(other);self.store.save(self.p)
  job=self.runner.enqueue(self.p['id'],'shot','s002');job['status']='running'
  before=copy.deepcopy(job);ledger={'attempts':{'s001':['first','second']},'failure_count':1};old_ledger=copy.deepcopy(ledger)
  server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.store=self.store;server.runner=self.runner
  thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:
   with patch('h3_director.backend.local_service.probe',side_effect=AssertionError('unrelated GPU queue is irrelevant')),patch('h3_director.backend.server.budget',return_value={'ledger':ledger,'stop':None}):
    request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/projects/{self.p["id"]}/clear-shot',
     data=json.dumps(dict(id='s001',revision=self.p['revision'])).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request) as response:result=json.load(response)
   self.assertEqual(result['shots'][0]['versions'],[])
   self.assertEqual(result['shots'][0]['clearedBatches'][-1]['selected'],'old')
   self.assertNotEqual(result['campaign'],before['snapshot']['campaign'])
   self.assertEqual(job,before);self.assertEqual(ledger,old_ledger);self.assertTrue(path.exists())
   # Completing the unrelated shot cannot resurrect the archived video.
   shot=job['snapshot']['shots'][1];shot.update(versions=[dict(id='new')],selected='new')
   self.runner.persist_item(job['snapshot'],'shots',shot)
   live=self.store.get(self.p['id'])
   self.assertEqual(live['shots'][0]['versions'],[]);self.assertEqual(live['campaign'],result['campaign'])
  finally:server.shutdown();server.server_close();thread.join()
 def test_configuration_leaves_existing_video_alone_and_sets_missing_to_768p(self):
  self.version();self.s['width']=768;self.s['height']=1344
  missing=copy.deepcopy(self.s);missing.update(id='s002',versions=[],selected=None);self.p['shots'].append(missing)
  configure(self.p,{'videoSeconds':10,'videoResolution':'landscape'},'shots')
  self.assertEqual((self.s['width'],self.s['height'],self.s['seconds']),(768,1344,5))
  self.assertEqual((missing['width'],missing['height'],missing['seconds']),(1344,768,10))
  self.assertEqual(self.p['videoProfile'],VIDEO_PROFILE)
  with self.assertRaises(ValueError):configure(self.p,{'regenerateShots':True},'shots')
 def test_batch_preserves_stale_video_even_with_unused_budget(self):
  self.version();self.s['prompt']+=' changed';self.store.save(self.p)
  with patch('h3_director.backend.production.require_references'):
   job=self.runner.enqueue(self.p['id'],'shots_auto')
   with patch.object(self.runner,'generate_review') as generate,patch.object(self.runner,'finish_shot_reviews'):
    self.runner.execute(job)
  generate.assert_not_called()

if __name__=='__main__':unittest.main()
