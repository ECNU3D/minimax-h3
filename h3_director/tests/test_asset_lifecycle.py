import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from h3_director.backend.project import Store,make_asset,selected,select_version,clear_asset,restore_asset,digest,write,read,current
from h3_director.backend.assets import references,ordered_assets,apply_dependencies
from h3_director.backend.runner import Runner,Human

class AssetLifecycle(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name);self.p=self.store.create('生命周期')
  self.a=make_asset('母版','character','A');self.b=make_asset('换装','character','B');self.p['assets']=[self.b,self.a]
  self.path=Path(self.tmp.name)/'source.png';self.path.write_bytes(b'image')
 def tearDown(self):self.tmp.cleanup()
 def version(self,a,id='v1'):
  v=dict(id=id,prompt=a['prompt'],seed=a['seed'],viewPrompts=[a['sidePrompt'],a['backPrompt']],files=[dict(path=str(self.path),sha256=digest(self.path))],review={'verdict':'human'},humanAccepted=False)
  a['versions'].append(v);a['selected']=id;return v
 def test_pending_dependencies_resolve_without_approval_in_topological_order(self):
  apply_dependencies(self.p,[dict(id='A',referenceAssetIds=[]),dict(id='B',referenceAssetIds=['A'])])
  self.assertEqual([a['id'] for a in ordered_assets(self.p)],['A','B'])
  self.assertEqual(references(self.p,self.b,allow_pending=True),[])
  with self.assertRaisesRegex(ValueError,'先生成上游'):references(self.p,self.b)
  self.version(self.a);self.assertEqual(references(self.p,self.b)[0]['sha256'],digest(self.path))
 def test_cycles_and_invalid_assets_rejected(self):
  for rows in [[dict(id='A',referenceAssetIds=['B']),dict(id='B',referenceAssetIds=['A'])],[dict(id='A',referenceAssetIds=[]),dict(id='B',referenceAssetIds=['missing'])]]:
   with self.assertRaises(ValueError):apply_dependencies(copy.deepcopy(self.p),rows)
 def test_clear_and_restore_preserve_old_files_and_prompt(self):
  v=self.version(self.a);clear_asset(self.a)
  self.assertIsNone(selected(self.a));self.assertEqual(self.a['versions'],[]);self.assertTrue(self.path.exists())
  restore_asset(self.a);self.assertEqual(selected(self.a),v)
 def test_select_version_restores_its_prompt_views_seed_and_model(self):
  old=self.version(self.a);new=copy.deepcopy(old);new.update(id='v2',prompt='Agent 修订后的中文正面',seed=99,viewPrompts=['Agent 侧面','Agent 背面'],generation={'provider':'local','imageMode':'reference','imageVariant':'base','generationRefs':['asset:B:0']});self.a['versions'].append(new)
  select_version(self.a,new,'assets');self.assertEqual(self.a['prompt'],new['prompt']);self.assertEqual(self.a['sidePrompt'],'Agent 侧面');self.assertEqual(self.a['seed'],99);self.assertEqual(self.a['imageVariant'],'base')
  select_version(self.a,old,'assets');self.assertEqual(self.a['prompt'],old['prompt']);self.assertEqual(self.a['seed'],old['seed'])
 def test_automatic_run_skips_existing_failed_or_stale_image_until_cleared(self):
  self.version(self.a);self.a['prompt']='用户改了提示词';self.store.save(self.p);runner=Runner(self.store,start=False)
  job=runner.enqueue(self.p['id'],'assets_auto')
  with patch.object(runner,'generate_review') as generate,patch.object(runner,'review') as review:
   with self.assertRaises(Human):runner.execute(job)
  self.assertEqual([c.args[2]['id'] for c in generate.call_args_list],['B']);review.assert_not_called()
  job['status']='needs_review';clear_asset(self.a);self.store.save(self.p);job=runner.enqueue(self.p['id'],'assets_auto')
  with patch.object(runner,'generate_review') as generate:runner.execute(job)
  self.assertEqual([c.args[2]['id'] for c in generate.call_args_list],['B','A'])
 def test_new_a_is_used_for_b_even_when_a_fails_review(self):
  apply_dependencies(self.p,[dict(id='A',referenceAssetIds=[]),dict(id='B',referenceAssetIds=['A'])]);self.store.save(self.p);runner=Runner(self.store,start=False);job=runner.enqueue(self.p['id'],'assets_auto');seen=[]
  def generate(p,category,item,j):
   if item['id']=='B':seen.extend(references(p,item))
   self.version(item)
   if item['id']=='A':
    from h3_director.backend.runner import QualityReviewRequired
    raise QualityReviewRequired('母版待人工')
  with patch.object(runner,'generate_review',side_effect=generate):
   with self.assertRaises(Human):runner.execute(job)
  self.assertEqual(job['done'],['assets/A','assets/B']);self.assertEqual(seen[0]['sha256'],digest(self.path))
 def test_clearing_upstream_invalidates_dependent_approval(self):
  self.version(self.a);apply_dependencies(self.p,[dict(id='A',referenceAssetIds=[]),dict(id='B',referenceAssetIds=['A'])])
  v=self.version(self.b);v['inputReferences']=references(self.p,self.b);self.assertTrue(current(self.p,'assets',self.b))
  clear_asset(self.a);self.assertFalse(current(self.p,'assets',self.b))
 def test_transient_windows_replace_failure_is_retried(self):
  target=Path(self.tmp.name)/'atomic.json';real=Path.replace;attempts=[]
  def flaky(src,dest):
   attempts.append(str(src))
   if len(attempts)==1:raise PermissionError('temporary file lock')
   return real(src,dest)
  with patch.object(Path,'replace',flaky),patch('h3_director.backend.project.time.sleep'):write(target,{'value':'kept'})
  self.assertEqual(read(target),{'value':'kept'});self.assertEqual(len(attempts),2);self.assertEqual(list(Path(self.tmp.name).glob('*.tmp')),[])

if __name__=='__main__':unittest.main()
