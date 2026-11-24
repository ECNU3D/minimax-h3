import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from h3_director.backend.project import Store,make_asset,digest
from h3_director.backend.production import configure,reference_readiness
from h3_director.backend.runner import Runner


class StageBatches(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name);self.runner=Runner(self.store,start=False)
  self.p=self.store.create('分阶段制作');self.p['assets']=[make_asset('杯子','prop','P01'),make_asset('未使用资产','prop','P02')]
  self.p['shots']=[dict(id='s001',name='杯子镜头',prompt='<Picture 1> 杯子静止',originalPrompt='杯子静止',refs=['P01'],seconds=8,width=1344,height=768,seed=1,versions=[],selected=None,history=[])]
  self.store.save(self.p)
 def tearDown(self):self.tmp.cleanup()
 def approve(self,human=False):
  a=self.p['assets'][0];path=Path(self.tmp.name)/'reference.png';path.write_bytes(b'test reference')
  a['selected']='v1';a['versions']=[dict(id='v1',prompt=a['prompt'],seed=a['seed'],humanAccepted=human,review=None if human else {'verdict':'pass'},files=[dict(path=str(path),sha256=digest(path))])]
  self.store.save(self.p);return path
 def enqueue(self,kind,options=None):
  with patch('h3_director.backend.runner.agent_runtime'):
   return self.runner.enqueue(self.p['id'],kind,options=options)
 def test_images_only_work_without_shots_and_do_not_export(self):
  self.p['shots']=[];self.store.save(self.p)
  job=self.enqueue('assets_auto',{'imageModel':'base'})
  with patch.object(self.runner,'generate_review') as generate,patch.object(self.runner,'shot') as video,patch.object(self.runner,'export') as export:
   self.runner.execute(job)
  self.assertEqual([c.args[1] for c in generate.call_args_list],['assets','assets']);video.assert_not_called();export.assert_not_called()
  self.assertEqual(job['done'],['assets/P01','assets/P02']);self.assertEqual(job['productionSettings']['scope'],'assets')
 def test_missing_reference_rejects_before_saving_settings_or_job(self):
  before=self.store.get(self.p['id'])
  with self.assertRaisesRegex(ValueError,'请先到参考图页面'):
   self.enqueue('shots_auto',{'videoSeconds':10,'autoReview':False})
  self.assertEqual(self.runner.jobs,[]);self.assertEqual(self.store.get(self.p['id']),before)
 def test_unapproved_reference_cannot_bypass_gate_with_review_disabled(self):
  self.approve();a=self.p['assets'][0]
  for verdict in (None,'human','revise'):
   a['versions'][0]['review']={'verdict':verdict};self.store.save(self.p)
   with self.assertRaisesRegex(ValueError,'尚未审批通过'):self.enqueue('shots_auto',{'autoReview':False})
  self.assertEqual(self.runner.jobs,[])
 def test_manual_acceptance_allows_shots_and_no_asset_or_export_execution(self):
  self.approve(human=True)
  job=self.enqueue('shots_auto',{'videoSeconds':10,'autoReview':False})
  with patch.object(self.runner,'generate_review') as generate,patch.object(self.runner,'asset') as image,patch.object(self.runner,'export') as export:
   self.runner.execute(job)
  self.assertEqual([c.args[1] for c in generate.call_args_list],['shots']);image.assert_not_called();export.assert_not_called()
  self.assertEqual(job['done'],['shots/s001']);self.assertEqual(job['productionSettings']['scope'],'shots')
 def test_agent_pass_allows_references_and_ignores_unused_assets(self):
  self.approve();report=reference_readiness(self.p,verify_hashes=True)
  self.assertTrue(report['ready']);self.assertEqual(report['requiredCount'],1)
  self.assertEqual(self.enqueue('shots_auto')['status'],'queued')
 def test_only_selected_version_approval_counts(self):
  self.approve();a=self.p['assets'][0];v=copy.deepcopy(a['versions'][0]);v.update(id='v2',review=None);a['versions'].append(v);a['selected']='v2';self.store.save(self.p)
  with self.assertRaisesRegex(ValueError,'尚未审批通过'):self.enqueue('shots_auto')
 def test_stale_reference_is_blocked_even_after_manual_acceptance(self):
  self.approve(human=True);self.p['assets'][0]['prompt']+=' 改为蓝色';self.store.save(self.p)
  with self.assertRaisesRegex(ValueError,'已过期'):self.enqueue('shots_auto')
 def test_missing_file_is_blocked(self):
  self.approve().unlink()
  with self.assertRaisesRegex(ValueError,'文件缺失'):self.enqueue('shots_auto')
 def test_tampered_file_is_blocked(self):
  self.approve().write_bytes(b'changed without approval')
  with self.assertRaisesRegex(ValueError,'文件已改变'):self.enqueue('shots_auto')
 def test_queued_reference_is_rechecked_before_any_generation(self):
  path=self.approve();job=self.enqueue('shots_auto',{'autoReview':False});path.write_bytes(b'changed after enqueue')
  with patch.object(self.runner,'generate_review') as generate,patch.object(self.runner,'ensure_local') as service:
   with self.assertRaisesRegex(ValueError,'文件已改变'):self.runner.execute(job)
  generate.assert_not_called();service.assert_not_called();self.assertEqual(job['done'],[])
 def test_scope_configuration_cannot_modify_other_stage(self):
  shots=copy.deepcopy(self.p['shots']);configure(self.p,{'imageModel':'base'},'assets');self.assertEqual(self.p['shots'],shots)
  assets=copy.deepcopy(self.p['assets']);configure(self.p,{'videoSeconds':10},'shots');self.assertEqual(self.p['assets'],assets)
  self.assertEqual(self.p['productionSettingsByScope']['assets']['imageModel'],'base');self.assertEqual(self.p['productionSettingsByScope']['shots']['videoSeconds'],10)
  for scope,options in [('assets',{'videoSeconds':10}),('shots',{'imageModel':'base'})]:
   with self.assertRaises(ValueError):configure(self.p,options,scope)
 def test_missing_assets_are_grouped_with_affected_shots(self):
  self.p['shots'].append({**self.p['shots'][0],'id':'s002'})
  report=reference_readiness(self.p)
  self.assertEqual(len(report['problems']),1);self.assertEqual(report['problems'][0]['shots'],['s001','s002'])
 def test_empty_stage_rejected(self):
  self.p['assets']=[];self.p['shots']=[];self.store.save(self.p)
  for kind in ('assets_auto','shots_auto'):
   with self.assertRaises(ValueError):self.enqueue(kind)

if __name__=='__main__':unittest.main()
