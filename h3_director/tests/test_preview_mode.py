"""Offline director integration: actual batch graphs, frozen queue and mode switching."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from h3_director.backend.project import Store,make_asset,read,write,digest,current
from h3_director.backend.runner import Runner
from h3_director.backend.production import VIDEO_PROFILE,PREVIEW_PROFILE,PREVIEW_MODEL,VIDEO_MODEL,configure
from h3_director.backend.server import Handler,public_project
from h3_director.backend.lab import plan,public_job,enqueue as lab_enqueue


class PreviewMode(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.store=Store(self.root);self.runner=Runner(self.store,start=False)
  from PIL import Image
  ref=self.root/'ref.png';Image.new('RGB',(32,32),'white').save(ref)
  self.ref=ref;self.p=self.store.create('preview integration');a=make_asset('reference','prop','P')
  a.update(selected='v',versions=[dict(id='v',prompt=a['prompt'],seed=a['seed'],files=[dict(path=str(ref),sha256=digest(ref))],humanAccepted=True)])
  self.p['assets']=[a]
  self.s=dict(id='s001',name='shot',prompt='<Picture 1> turns around.',refs=['P'],seed=123,seconds=15,width=1344,height=768,versions=[],selected=None,history=[])
  self.p['shots']=[self.s];self.store.save(self.p)
  self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.store=self.store;self.server.runner=self.runner
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):
  self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
 def call(self,path,data=None):
  req=urllib.request.Request(f'http://127.0.0.1:{self.server.server_port}/api/'+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(req) as r:return json.load(r)
 def switch(self,profile):
  p=self.store.get(self.p['id'])
  return self.call(f'projects/{p["id"]}/video-mode',dict(videoProfile=profile,revision=p['revision']))
 def spec(self,job):
  with patch.object(self.runner,'command') as command:
   self.runner.shot(job['snapshot'],job['snapshot']['shots'][0],job,preflight=True)
  args=command.call_args.args[0]
  self.assertEqual(Path(args[1]).name,'h3_batch.py');self.assertNotIn('--execute',args)
  self.assertEqual(args[args.index('--campaign')+1],self.p['campaign'])
  return Path(args[args.index('--spec')+1])
 def test_http_switch_freezes_single_jobs_and_uses_actual_preview_graph(self):
  default=self.runner.enqueue(self.p['id'],'shot','s001');original=copy.deepcopy(default)
  p=self.switch(PREVIEW_PROFILE)
  self.assertEqual(default,original);self.assertEqual(self.store.get(self.p['id'])['shots'],self.p['shots']);self.assertEqual(p['campaign'],self.p['campaign'])
  preview=self.runner.enqueue(self.p['id'],'shot','s001')
  with self.assertRaisesRegex(ValueError,'已经排队'):self.runner.enqueue(self.p['id'],'shot','s001')
  preview_spec=self.spec(preview);default_spec=self.spec(default)
  sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
  from h3_batch import prepare
  quick=prepare(preview_spec,allow_reference_override=True)[0];quality=prepare(default_spec,allow_reference_override=True)[0]
  self.assertEqual((quick['inputs']['width'],quick['inputs']['height']),(960,544))
  self.assertEqual(quick['workflow']['10']['inputs']['steps'],4)
  self.assertEqual(quick['workflow']['9']['inputs']['sampler_name'],'euler')
  self.assertNotIn('34',quick['workflow'])
  self.assertIn('4step_v0.1',quick['workflow']['6']['inputs']['lora_name'])
  self.assertEqual(quality['workflow']['10']['inputs']['steps'],8)
  self.assertEqual((quality['inputs']['width'],quality['inputs']['height']),(1344,768))
  self.assertEqual(quick['inputs']['references'],quality['inputs']['references'])
  for key in ('prompt','seed','seconds'):self.assertEqual(quick['inputs'][key],quality['inputs'][key])
  self.assertNotEqual(quick['fingerprint'],quality['fingerprint'])
  self.switch(VIDEO_PROFILE)
  for j in self.runner.jobs:j['status']='cancelled'
  back=self.runner.enqueue(self.p['id'],'preflight','s001')
  self.assertEqual(prepare(self.spec(back),allow_reference_override=True)[0]['fingerprint'],quality['fingerprint'])
  self.assertEqual(preview['snapshot']['videoProfile'],PREVIEW_PROFILE)
 def test_old_projects_default_high_and_switch_does_not_rewrite_existing_specs(self):
  for old in (None,'legacy-ref2v-4step'):
   self.p['videoProfile']=old;self.store.save(self.p)
   self.assertEqual(public_project(self.p)['videoProfile'],VIDEO_PROFILE)
   j=self.runner.enqueue(self.p['id'],'preflight','s001');path=self.spec(j);prior=read(path)
   j['snapshot']['videoProfile']=PREVIEW_PROFILE;self.spec(j)
   self.assertEqual(read(path),prior);j['status']='cancelled'
 def test_batch_mode_and_existing_videos_preserved(self):
  original=dict(id='old',prompt=self.s['prompt'],seed=self.s['seed'],seconds=15,width=1344,height=768,profile=VIDEO_PROFILE,files=[],references=[])
  existing=copy.deepcopy(self.s);existing.update(id='s002',versions=[original],selected='old');self.p['shots'].append(existing)
  for scope in ('all','shots'):
   configure(self.p,dict(videoModel=PREVIEW_MODEL),scope)
   self.assertEqual(existing['versions'],[original]);self.assertEqual((existing['width'],existing['height']),(1344,768))
   self.assertEqual((self.s['width'],self.s['height']),(960,544));self.assertEqual(self.p['videoProfile'],PREVIEW_PROFILE)
   configure(self.p,dict(videoModel=VIDEO_MODEL),scope)
   self.assertEqual((self.s['width'],self.s['height']),(1344,768))
  configure(self.p,dict(videoModel=PREVIEW_MODEL),'shots');self.store.save(self.p)
  for kind in ('shot_auto','auto','shots_auto'):
   job=self.runner.enqueue(self.p['id'],kind,'s001' if kind=='shot_auto' else None)
   self.assertEqual(read(self.spec(job))[0]['profile'],PREVIEW_PROFILE);job['status']='cancelled'
  configure(self.p,{},'assets');self.assertEqual(self.p['videoProfile'],PREVIEW_PROFILE)
 def test_invalid_modes_and_stale_revisions_do_not_save(self):
  before=self.store.get(self.p['id'])
  with self.assertRaises(urllib.error.HTTPError):self.switch('ref2v-preview-sol-4step')
  with self.assertRaises(urllib.error.HTTPError):self.call(f'projects/{self.p["id"]}/video-mode',dict(videoProfile=PREVIEW_PROFILE,revision=-1))
  self.assertEqual(self.store.get(self.p['id']),before)
  with self.assertRaises(ValueError):configure(self.p,dict(videoModel=PREVIEW_MODEL,videoResolution='portrait'),'shots')
 def test_preview_output_is_current_and_later_prompt_edits_survive(self):
  job=self.runner.enqueue(self.p['id'],'shot','s001');s=job['snapshot']['shots'][0]
  v=dict(id='preview',prompt=s['prompt'],seed=s['seed'],seconds=s['seconds'],width=960,height=544,profile=PREVIEW_PROFILE,references=[dict(sha256=digest(self.ref))],files=[])
  self.runner.add_version(job['snapshot'],'shots',s,v)
  live=self.store.get(self.p['id']);self.assertTrue(current(live,'shots',live['shots'][0]))
  live['shots'][0]['prompt']+=' new edit';self.store.save(live)
  self.runner.persist_item(job['snapshot'],'shots',s)
  self.assertTrue(self.store.get(self.p['id'])['shots'][0]['prompt'].endswith('new edit'))
 def test_lab_preview_preserves_high_quality_controls_and_records_actual_settings(self):
  e=self.runner.lab.create();e['prompt']='<Picture 1> turns around.';e['settings'].update(steps=20,sampler='res_multistep',turbo=False,shift_audio=2.5)
  self.runner.lab.copy_reference(e,self.ref,'reference');self.runner.lab.save(e)
  before=copy.deepcopy(e['settings']);baseline=plan(self.runner,e,self.root/'before')
  e=self.runner.lab.update(e['id'],dict(videoProfile=PREVIEW_PROFILE),e['revision'])
  j=lab_enqueue(self.runner,e,e['revision'],'preflight');out=public_job(j)
  self.assertEqual(out['settings']['steps'],4);self.assertEqual(out['settings']['shift_audio'],3)
  self.assertEqual(out['videoProfile'],PREVIEW_PROFILE);self.assertEqual(j['snapshot']['settings'],before)
  graph=read(Path(j['folder'])/'workflow.json');self.assertEqual(graph['10']['inputs']['steps'],4);self.assertNotIn('34',graph)
  e=self.runner.lab.update(e['id'],dict(videoProfile=VIDEO_PROFILE),e['revision'])
  after=plan(self.runner,e,self.root/'after');self.assertEqual(after['fingerprint'],baseline['fingerprint'])
  self.assertEqual(e['settings'],before);self.assertEqual(j['snapshot']['videoProfile'],PREVIEW_PROFILE)
 def test_lab_rejects_unsupported_preview_inputs_without_enqueue(self):
  e=self.runner.lab.create();e.update(prompt='A landscape.',videoProfile=PREVIEW_PROFILE)
  with self.assertRaisesRegex(ValueError,'参考图'):lab_enqueue(self.runner,e,e['revision'],'preflight')
  self.runner.lab.copy_reference(e,self.ref,'ref');e['prompt']='<Picture 1> landscape.';e['audioReferences']=[dict(path=str(self.ref),sha256=digest(self.ref),label='audio')]
  with self.assertRaisesRegex(ValueError,'音频参考'):lab_enqueue(self.runner,e,e['revision'],'preflight')
  self.assertEqual(self.runner.jobs,[])

if __name__=='__main__':unittest.main()
