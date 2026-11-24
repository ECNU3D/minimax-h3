import copy,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from h3_director.backend.project import Store,make_asset,digest,selected
from h3_director.backend.runner import Runner,Human,Stop,Paused,ReviewUnavailable

class ShotBatchReview(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.store=Store(self.temp.name);self.runner=Runner(self.store,start=False)
  self.p=self.store.create('分镜集中审核');a=make_asset('参考','prop','P');f=Path(self.temp.name)/'image';f.write_bytes(b'image')
  a['versions']=[dict(id='reference',prompt=a['prompt'],seed=a['seed'],files=[dict(path=str(f),sha256=digest(f))],review={'verdict':'pass'})];a['selected']='reference';self.p['assets']=[a]
  self.p['shots']=[dict(id=k,name=k,prompt='<Picture 1> 固定机位',refs=['P'],seconds=5,width=1344,height=768,seed=1,history=[],versions=[],selected=None) for k in ('s001','s002','s026')]
  self.store.save(self.p);self.generated=[];self.attempts={};self.results={'s001':'human','s002':'error','s026':'pass'}
 def tearDown(self):self.temp.cleanup()
 def budget(self,p):return {'ledger':{'attempts':self.attempts},'stop':None}
 def shot(self,p,s,j,attempt=0):
  self.generated.append((s['id'],attempt));self.attempts.setdefault(s['id'],[]).append({})
  folder=Path(self.temp.name)/s['id']/str(attempt);folder.mkdir(parents=True,exist_ok=True);f=folder/'video';f.write_bytes(b'video')
  v=dict(id=s['id']+'_'+str(attempt),prompt=s['prompt'],seed=s['seed'],files=[dict(path=str(f),sha256=digest(f))],references=[selected(p['assets'][0])['files'][0]],review=None,humanAccepted=False)
  self.runner.add_version(p,'shots',s,v);return v,folder
 def review(self,p,category,s,v,folder,j):
  r=self.results[s['id']]
  if r=='error':raise ReviewUnavailable('审核返回字段缺失')
  v['review']=dict(verdict=r,summary='测试结论',retryAction='reroll' if r=='revise' else 'none',retryReason='随机偏差',revisedPrompt='',revisedViewPrompts=[])
  self.runner.persist_item(p,'shots',s);return v['review']
 def run_batch(self,j):
  with patch.object(self.runner,'shot',side_effect=self.shot),patch.object(self.runner,'review',side_effect=self.review),patch('h3_director.backend.runner.budget',side_effect=self.budget):self.runner.execute(j)
 def test_review_human_and_error_continue_through_shot026(self):
  j=self.runner.enqueue(self.p['id'],'shots_auto')
  with self.assertRaisesRegex(Human,'分镜批量处理完成，2 个镜头'):self.run_batch(j)
  self.assertEqual(self.generated,[('s001',0),('s002',0),('s026',0)]);self.assertEqual(j['done'],['shots/s001','shots/s002','shots/s026'])
  self.assertEqual(j['progress'],100);self.assertNotIn('pendingReviews',j);self.assertEqual(len(j['pendingShotReviews']),2)
 def test_exhausted_retry_and_submission_budget_continue_without_third_submit(self):
  self.results={'s001':'revise','s002':'pass','s026':'pass'}
  j=self.runner.enqueue(self.p['id'],'shots_auto');j['productionSettings']={'maxRetries':10}
  with self.assertRaisesRegex(Human,'分镜批量处理完成，1 个镜头'):self.run_batch(j)
  self.assertEqual(self.generated,[('s001',0),('s001',1),('s002',0),('s026',0)]);self.assertEqual(len(self.attempts['s001']),2)
 def test_new_batch_retains_existing_unapproved_video_and_generates_remaining(self):
  self.shot(self.p,self.p['shots'][0],{'id':'existing'});self.generated=[]
  self.results={'s001':'error','s002':'pass','s026':'pass'};j=self.runner.enqueue(self.p['id'],'shots_auto')
  with self.assertRaisesRegex(Human,'1 个镜头'):self.run_batch(j)
  self.assertEqual(self.generated,[('s002',0),('s026',0)])
 def test_stale_video_without_budget_is_retained_and_other_shots_continue(self):
  self.shot(self.p,self.p['shots'][0],{'id':'existing'});self.p['shots'][0]['prompt']+=' 新提示词';self.store.save(self.p)
  self.attempts['s001']=[{},{}];self.generated=[];self.results={'s001':'error','s002':'pass','s026':'pass'}
  j=self.runner.enqueue(self.p['id'],'shots_auto')
  with self.assertRaisesRegex(Human,'1 个镜头'):self.run_batch(j)
  self.assertEqual(self.generated,[('s002',0),('s026',0)]);self.assertIn('已有素材继续保留',j['pendingShotReviews'][0]['reason'])
 def test_generation_failure_stop_pause_and_uncertainty_are_not_swallowed(self):
  for error in (RuntimeError('ComfyUI 断开'),Stop('STOP'),Human('结果不明确'),Paused()):
   j=dict(id='test',kind='shots_auto',snapshot=copy.deepcopy(self.p),done=[],paused=False,autoReview=True)
   with patch.object(self.runner,'shot',side_effect=error) as generate:
    with self.assertRaises(type(error)):self.runner.execute(j)
   self.assertEqual(generate.call_count,1);self.assertEqual(j['done'],[])
 def test_full_pipeline_keeps_image_gate_and_does_not_export_unapproved_video(self):
  j=self.runner.enqueue(self.p['id'],'auto')
  with patch.object(self.runner,'export') as export:
   with self.assertRaisesRegex(Human,'分镜批量处理完成'):self.run_batch(j)
  export.assert_not_called();self.assertIn('shots/s026',j['done'])
 def test_disabled_auto_review_finishes_all_shots_then_hands_off(self):
  j=self.runner.enqueue(self.p['id'],'shots_auto',auto_review=False)
  with self.assertRaisesRegex(Human,'3 个镜头'):self.run_batch(j)
  self.assertEqual(len(self.generated),3)

if __name__=='__main__':unittest.main()
