import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image,ImageChops

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from h3_director.backend.project import Store,make_asset,digest
from h3_director.backend.assets import references,settings,mask_reference
from h3_director.backend.production import configure
from h3_director.backend.runner import Runner
from qwen_image_pipeline import build,composite_exact,sampling_seed,EDIT_PROFILE

class QwenImages(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.store=Store(self.root/'data');self.p=self.store.create('Qwen test')
  self.a=make_asset('原图','prop','P1');self.p['assets']=[self.a]
  for name,color in [('base',(25,60,90,123)),('mask',(0,0,0,255)),('generated',(240,30,0,255))]:
   im=Image.new('RGBA',(64,96),color)
   if name=='mask':im.paste((255,255,255,255),(12,20,32,70))
   path=self.root/(name+'.png');im.save(path);self.a['inputs'].append(dict(id=name,path=str(path),sha256=digest(path),label=name))
  self.a.update(imageMode='inpaint',generationRefs=['input:P1:base'],editMask='input:P1:mask')
 def tearDown(self):self.temp.cleanup()
 def test_default_and_valid_region_inputs(self):
  self.assertEqual(make_asset('x','prop')['imageVariant'],'qwen21')
  self.assertEqual(references(self.p,self.a)[0]['key'],'input:P1:base')
  self.assertEqual(settings(self.a)['editMask'],'input:P1:mask')
 def test_mask_missing_empty_dimensions_and_tampering_rejected(self):
  for issue in ('missing','empty','dimensions','tampered'):
   with self.subTest(issue=issue):
    a=copy.deepcopy(self.a)
    if issue=='missing':a['editMask']=None
    else:
     f=a['inputs'][1];path=Path(f['path']);Image.new('L',(32,32) if issue=='dimensions' else (64,96),0 if issue=='empty' else 255).save(path)
     if issue!='tampered':f['sha256']=digest(path)
    with self.assertRaises(ValueError):references({**self.p,'assets':[a]},a)
 def test_other_models_and_multiple_bases_rejected(self):
  for key,value in [('imageVariant','base'),('provider','codex'),('generationRefs',['input:P1:base','input:P1:generated'])]:
   with self.subTest(key=key),self.assertRaises(ValueError):references(self.p,{**self.a,key:value})
 def test_composite_preserves_every_unselected_rgba_pixel(self):
  out=self.root/'out.png';composite_exact(self.root/'base.png',self.root/'generated.png',self.root/'mask.png',out)
  with Image.open(out) as im:
   self.assertEqual(im.getpixel((0,0)),(25,60,90,123));self.assertEqual(im.getpixel((20,30)),(240,30,0,255))
   for y in range(96):
    for x in range(64):
     if not (12<=x<32 and 20<=y<70):self.assertEqual(im.getpixel((x,y)),(25,60,90,123))
 def test_graph_records_base_then_mask_and_correct_model(self):
  refs=references(self.p,self.a);mask=mask_reference(self.p,self.a,refs)
  with patch('qwen_image_pipeline.input_image',side_effect=lambda r:Path(r['path']).name):
   g,prompt=build(dict(width=64,height=96,seed=2,name='prop'),'改为红色',refs,mask)
  self.assertIn('2.1',g['1']['inputs']['unet_name']);self.assertEqual(g['20']['inputs']['image'],'base.png');self.assertEqual(g['21']['inputs']['image'],'mask.png')
  self.assertIn('白色区域',prompt);self.assertEqual(g['5']['inputs']['height'],96)
 def test_reference_seed_is_reproducible_but_independent_of_parent_noise(self):
  stage=dict(width=64,height=96,seed=20260917,name='character_front')
  refs=references(self.p,self.a);mask=mask_reference(self.p,self.a,refs)
  seed=sampling_seed(stage,refs,mask)
  self.assertNotEqual(seed,stage['seed']);self.assertEqual(seed,sampling_seed(stage,copy.deepcopy(refs),mask))
  self.assertEqual(sampling_seed(stage,[]),stage['seed'])
  self.assertEqual(sampling_seed(stage,refs,mask,'legacy-v1'),stage['seed'])
  for altered in ({**stage,'seed':12},{**stage,'name':'character_back'}):
   self.assertNotEqual(seed,sampling_seed(altered,refs,mask))
  self.assertNotEqual(seed,sampling_seed(stage,[{**refs[0],'sha256':'different'}],mask))
  self.assertNotEqual(seed,sampling_seed(stage,refs,{**mask,'sha256':'different'}))
  with patch('qwen_image_pipeline.input_image',return_value='base.png'):
   old,_=build(stage,'原提示词',refs,profile='legacy-v1');new,_=build(stage,'原提示词',refs)
  self.assertEqual(old['6']['inputs']['seed'],20260917)
  self.assertNotEqual(new['6']['inputs']['seed'],20260917)
  self.assertEqual(old['6']['inputs']['steps'],new['6']['inputs']['steps'])
 def test_regenerate_preserves_versions_and_reaches_all_assets(self):
  self.a.update(imageMode='text',generationRefs=[])
  v=dict(id='old',prompt=self.a['prompt'],seed=self.a['seed'],files=[],humanAccepted=True)
  self.a.update(versions=[v],selected='old',imageVariant='base');self.store.save(self.p)
  runner=Runner(self.store,start=False)
  with patch('h3_director.backend.runner.agent_runtime'):
   job=runner.enqueue(self.p['id'],'assets_auto',options=dict(imageModel='qwen21',regenerateAssets=True,autoReview=False))
  live=self.store.get(self.p['id']);self.assertEqual(live['assets'][0]['versions'],[v]);self.assertEqual(live['assets'][0]['imageVariant'],'qwen21')
  with patch.object(runner,'generate_review') as generate:runner.execute(job)
  self.assertEqual(generate.call_count,1);self.assertEqual(job['done'],['assets/P1'])
 def test_regenerate_not_allowed_for_video(self):
  with self.assertRaises(ValueError):configure(self.p,{'regenerateAssets':True},scope='shots')

if __name__=='__main__':unittest.main()
