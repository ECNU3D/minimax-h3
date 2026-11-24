import base64
import copy
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.request
from unittest.mock import patch
import wave

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from h3_director.backend.project import Store,make_asset,write,read,digest
from h3_director.backend.runner import Runner
from h3_director.backend.server import Handler
from h3_director.backend.lab import enqueue,plan
from h3_director.backend.lab_audio import inspect_audio
from scripts.h3_lab_config import settings


class ShotLab(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.folder=Path(self.tmp.name)
  self.store=Store(self.folder);self.runner=Runner(self.store,start=False);self.lab=self.runner.lab
  from PIL import Image
  self.ref=self.folder/'ref.png';Image.new('RGB',(32,32),'white').save(self.ref)
  self.wav=self.folder/'voice.wav'
  import numpy as np
  samples=(np.sin(np.arange(32000)*2*np.pi*440/32000)*12000).astype('<i2')
  with wave.open(str(self.wav),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(32000);f.writeframes(samples.tobytes())
  self.e=self.lab.create();self.e['prompt']='detailed_description: <Picture 1> is the scene.'
  self.lab.copy_reference(self.e,self.ref,'scene');self.lab.save(self.e)
 def tearDown(self):self.tmp.cleanup()
 def test_bilingual_cases_preserve_sections_dialogue_and_generation_contract(self):
  import re
  from h3_director.backend.lab_templates import catalog,create_case,prompt_issues
  from h3_director.backend.lab_languages import with_languages
  for t in catalog():
   en,zh=t['variants']['en'],t['variants']['zh']
   self.assertEqual(re.findall(r'(?m)^(\w+):',en['prompt']),re.findall(r'(?m)^(\w+):',zh['prompt']))
   self.assertEqual(re.findall(r'<d>.*?</d>',en['prompt']),re.findall(r'<d>.*?</d>',zh['prompt']))
   self.assertEqual(prompt_issues(zh),[])
  e=create_case(self.lab,'zh_solo');self.assertEqual(e['promptLanguage'],'zh')
  campaign=e['campaign'];cfg=copy.deepcopy(e['settings'])
  en=e['promptVariants']['en'];e=self.lab.update(e['id'],dict(**en,promptLanguage='en',promptVariants=e['promptVariants']),e['revision'])
  e=self.lab.update(e['id'],{'soundscape':'Edited English room tone'},e['revision'])
  zh=e['promptVariants']['zh'];e=self.lab.update(e['id'],dict(**zh,promptLanguage='zh'),e['revision'])
  restored=self.lab.get(e['id']);self.assertEqual(restored['promptVariants']['en']['soundscape'],'Edited English room tone')
  self.assertEqual(restored['campaign'],campaign);self.assertEqual(restored['settings'],cfg)
  # Old English drafts keep edits; adding a paired template never silently replaces them.
  old=dict(e,promptLanguage='en',**en);old.pop('promptVariants');old['prompt']+=' user edit'
  upgraded=with_languages(old);self.assertEqual(upgraded['prompt'],old['prompt']);self.assertIn('zh',upgraded['promptVariants'])
  with self.assertRaises(ValueError):self.lab.update(e['id'],{'promptVariants':{'en':{'prompt':'incomplete'}}},e['revision'])
  group=next(t for t in catalog() if t['id']=='zh_group')
  legacy=self.lab.update(e['id'],group['variants']['en'],e['revision'])
  self.assertEqual(legacy['promptVariants']['zh'],group['variants']['zh'])
 def test_generic_cases_are_complete_independent_and_text_only_ref2va(self):
  from h3_director.backend.lab_templates import catalog,create_case,prompt_issues
  all_cases=catalog();self.assertEqual(len(all_cases),7)
  for t in all_cases:
   with self.subTest(template=t['id']):
    e=create_case(self.lab,t['id']);self.assertEqual(prompt_issues(e),[])
    self.assertEqual(e['references'],[]);self.assertEqual(e['audioReferences'],[]);self.assertNotIn('source',e)
    p=plan(self.runner,e,self.folder/t['id']);g=p['workflow']
    self.assertIn('ref2va',g['1']['inputs']['unet_name']);self.assertEqual(g['5']['class_type'],'MiniMaxH3ReferenceToVideo')
    self.assertEqual(p['inputs']['reference_policy'],'lab_optional_0_to_9');self.assertEqual(p['copies'],[])
    self.assertEqual(g['19']['inputs']['audio'],g['14']['inputs']['audio'])
  self.assertEqual(self.store.list(),[])
  # The default project/CLI policy is not loosened by the lab exception.
  from h3_batch import prepare
  with self.assertRaises(ValueError):prepare(self.folder/all_cases[0]['id']/'spec.json')
  spec=read(self.folder/all_cases[0]['id']/'spec.json');spec[0]['profile']='ref2v-768p-8step';write(self.folder/'production.json',spec)
  with self.assertRaises(ValueError):prepare(self.folder/'production.json',allow_reference_override=True)
 def test_prompt_conflicts_block_before_enqueue_but_can_be_saved_for_editing(self):
  from h3_director.backend.lab_templates import prompt_issues
  self.assertTrue(prompt_issues(self.lab.create()))
  e=self.e;e['prompt']+=' <d>[Chinese]你好。</d>';e['soundscape']='无人声，无对白。'
  self.lab.save(e);self.assertTrue(prompt_issues(e))
  with self.assertRaisesRegex(ValueError,'冲突'):enqueue(self.runner,e,e['revision'],'preflight')
  self.assertEqual(self.runner.jobs,[])
  e['soundscape']='Quiet room tone beneath S1.';e['music']='Piano, no vocals.'
  self.assertEqual(prompt_issues(e),[])
  e['prompt']+='\ndetailed_description: repeated\ndetailed_description: again'
  self.assertTrue(prompt_issues(e))
 def test_import_copies_assets_and_never_changes_project(self):
  p=self.store.create('source');a=make_asset('reference','prop','P')
  a.update(selected='v',versions=[dict(id='v',files=[dict(path=str(self.ref),sha256=digest(self.ref))])]);p['assets']=[a]
  p['shots']=[dict(id='s001',name='single',prompt='<Picture 1> action\noverall_soundscape: Rain.\nnon_diegetic_music: N/A',seed=7,seconds=5,refs=['P'])]
  self.store.save(p);before=copy.deepcopy(p)
  e=self.lab.import_shot(p,'s001');self.assertEqual(p,before);self.assertEqual(self.store.get(p['id']),before)
  self.assertEqual(e['soundscape'],'Rain.');self.assertEqual(e['music'],'N/A');self.assertNotIn('overall_soundscape',e['prompt'])
  self.assertNotEqual(e['references'][0]['path'],str(self.ref));self.assertEqual(digest(e['references'][0]['path']),digest(self.ref))
  self.ref.unlink();self.assertTrue(Path(e['references'][0]['path']).exists())
 def test_lab_graph_baseline_and_twenty_step_no_lora(self):
  result=plan(self.runner,self.e,self.folder/'baseline');g=result['workflow']
  self.assertEqual(g['19']['inputs']['audio'],g['14']['inputs']['audio']);self.assertEqual(g['19']['inputs']['format'],'flac')
  self.assertEqual(g['7']['inputs']['model'],g['10']['inputs']['model']);self.assertEqual(g['33']['inputs']['shift_audio'],3)
  self.assertEqual(g['9']['inputs']['sampler_name'],'euler');self.assertEqual(g['10']['inputs']['steps'],8)
  self.assertEqual(g['4']['inputs']['vae_name'],'minimax_h3_audio_vae_fp32.safetensors');self.assertNotIn('sample_rate',json.dumps(g))
  self.e['settings'].update(turbo=False,steps=20,sampler='res_multistep',shift_audio=2.5)
  other=plan(self.runner,self.e,self.folder/'base');g=other['workflow']
  self.assertNotIn('6',g);self.assertEqual(g['33']['inputs']['model'],['1',0]);self.assertEqual(g['10']['inputs']['steps'],20)
  self.assertNotEqual(other['fingerprint'],result['fingerprint'])
 def test_audio_reference_wiring_and_tag_validation(self):
  self.lab.copy_reference(self.e,self.wav,'voice',audio=True)
  with self.assertRaisesRegex(ValueError,'Audio'):plan(self.runner,self.e,self.folder/'invalid')
  self.e['prompt']+=' <Audio 1> is the voice timbre only.'
  p=plan(self.runner,self.e,self.folder/'audio');self.assertEqual(p['workflow']['5']['inputs']['ref_audios.ref_audio_0'],['40',0])
  self.assertEqual(p['workflow']['5']['inputs']['audio_vae'],['4',0]);self.assertEqual(p['inputs']['audio_references'][0]['sha256'],digest(self.wav))
  self.assertEqual(len(p['copies']),2)
 def test_audio_measurements_decode_real_signal(self):
  evidence=inspect_audio(self.wav);self.assertEqual(evidence['sampleRate'],32000);self.assertEqual(evidence['duration'],1)
  self.assertEqual(evidence['channels'],1);self.assertAlmostEqual(evidence['peakDb'],-8.73,places=1)
  self.assertEqual(evidence['clippedSamples'],0);self.assertEqual(len(evidence['waveform']),160)
 def test_revision_params_and_media_integrity(self):
  for cfg in [dict(shift_audio=float('nan')),dict(steps=2.5),dict(seconds=0),dict(seed=True),dict(audio_cfg=3)]:
   with self.assertRaises(ValueError):settings(cfg)
  with self.assertRaises(ValueError):self.lab.update(self.e['id'],{'notes':'stale'},0)
  Path(self.e['references'][0]['path']).write_bytes(b'changed')
  with self.assertRaisesRegex(ValueError,'改变'):enqueue(self.runner,self.e,self.e['revision'],'run')
  self.assertEqual(self.runner.jobs,[])
 def test_frozen_snapshot_shared_queue_resume_and_budget(self):
  j=enqueue(self.runner,self.e,self.e['revision'],'run');self.e['settings']['shift_audio']=3.5
  self.assertEqual(j['snapshot']['settings']['shift_audio'],3)
  with self.assertRaises(ValueError):enqueue(self.runner,self.e,self.e['revision'],'run')
  j['status']='interrupted';self.assertIsNone(self.runner.next_queued());self.runner.control(j['id'],'resume')
  self.assertEqual(j['status'],'queued');self.assertEqual(j['snapshot']['settings']['shift_audio'],3)
  j['status']='success'
  with patch('h3_director.backend.runner.budget',return_value={'stop':None,'ledger':{'attempts':{'shot':['a','b']}}}):
   with self.assertRaisesRegex(ValueError,'两次'):enqueue(self.runner,self.e,self.e['revision'],'run')
  with patch('h3_director.backend.runner.budget',return_value={'stop':{'reason':'STOP'},'ledger':{}}):
   with self.assertRaisesRegex(ValueError,'STOP'):enqueue(self.runner,self.e,self.e['revision'],'run')
  with patch.object(self.runner,'command') as command:
   self.runner.execute(enqueue(self.runner,self.e,self.e['revision'],'preflight'))
  self.assertNotIn('--execute',command.call_args.args[0])
 def test_http_draft_upload_preflight_isolation_and_ranges(self):
  server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.store=self.store;server.runner=self.runner
  threading.Thread(target=server.serve_forever,daemon=True).start()
  base='http://127.0.0.1:'+str(server.server_port)
  def call(route,data=None):
   req=urllib.request.Request(base+'/api/'+route,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
   with urllib.request.urlopen(req) as r:return json.load(r)
  try:
   templates=call('lab/templates');self.assertEqual(len(templates),7)
   first=call('lab/templates/open',{'templateId':'zh_solo'});again=call('lab/templates/open',{'templateId':'zh_solo'})
   self.assertEqual(first['id'],again['id']);self.assertEqual(first['revision'],again['revision'])
   clone=call('lab',{'templateId':'zh_solo'});self.assertNotEqual(clone['id'],first['id'])
   e=call('lab',{});self.assertEqual(call('projects'),[])
   e=call('lab/'+e['id']+'/upload',dict(revision=e['revision'],filename='scene.png',content=base64.b64encode(self.ref.read_bytes()).decode()))
   e=call('lab/'+e['id']+'/save',dict(revision=e['revision'],changes={'prompt':'<Picture 1> is the scene.'}))
   j=call('lab/'+e['id']+'/preflight',dict(revision=e['revision']));self.assertEqual(j['status'],'queued');self.assertEqual(j['mode'],'preflight')
   req=urllib.request.Request(base+e['references'][0]['url'],headers={'Range':'bytes=0-7'})
   with urllib.request.urlopen(req) as r:self.assertEqual(r.status,206);self.assertEqual(len(r.read()),8)
   result=call('lab/'+e['id']);self.assertEqual(len(result['jobs']),1);self.assertEqual(result['jobs'][0]['settings']['shift_audio'],3)
   with self.assertRaises(urllib.error.HTTPError):call('lab/'+e['id']+'/new-round',dict(revision=e['revision']))
   call('jobs/'+j['id']+'/cancel',{})
   previous=e['campaign'];e=call('lab/'+e['id']+'/new-round',dict(revision=e['revision']));self.assertNotEqual(e['campaign'],previous)
   self.assertEqual(e['rounds'][0]['campaign'],previous)
   self.assertEqual(call('projects'),[])
  finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
