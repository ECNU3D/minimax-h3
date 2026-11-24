"""Run the real batch/retry code with deterministic image and reviewer adapters."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from h3_director.backend.assets import references
from h3_director.backend.project import Store,make_asset,digest,selected
from h3_director.backend.runner import Runner,Human,Paused,Stop,QualityReviewRequired,ReviewUnavailable,HARNESS
from h3_director.backend.production import configure


class BatchReview(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name);self.runner=Runner(self.store,start=False)
  self.p=self.store.create('集中审核');self.p['assets']=[make_asset(n,'prop',n) for n in ('A','B','C')]
  self.store.save(self.p);self.generated=[];self.inputs={};self.verdicts={'A':'human','B':'pass','C':'revise'}
 def tearDown(self):self.tmp.cleanup()
 def image(self,p,a,j,attempt=0):
  self.generated.append((a['id'],attempt));self.inputs[a['id']]=references(p,a)
  folder=Path(self.tmp.name)/a['id']/str(attempt);folder.mkdir(parents=True,exist_ok=True)
  file=folder/'image.png';file.write_bytes((a['id']+str(attempt)).encode())
  version=dict(id=j['id']+'_'+a['id']+f'_{attempt}',prompt=a['prompt'],seed=a['seed'],files=[dict(path=str(file),sha256=digest(file))],review=None,humanAccepted=False,inputReferences=self.inputs[a['id']])
  self.runner.add_version(p,'assets',a,version);return version,folder
 def review(self,p,category,item,v,folder,j):
  verdict=self.verdicts[item['id']]
  v['review']=dict(verdict=verdict,summary='测试视觉问题',revisedPrompt='修改后的中文图片提示词' if verdict=='revise' else '')
  self.runner.persist_item(p,category,item);return v['review']
 def run_batch(self,job):
  with patch.object(self.runner,'asset',side_effect=self.image),patch.object(self.runner,'review',side_effect=self.review):
   self.runner.execute(job)
 def test_all_images_finish_before_collective_review_with_bounded_retries(self):
  job=self.runner.enqueue(self.p['id'],'assets_auto')
  with self.assertRaisesRegex(Human,'2 个资产待集中人工审核'):self.run_batch(job)
  self.assertEqual(self.generated,[('A',0),('B',0),('C',0),('C',1)])
  self.assertEqual(job['done'],['assets/A','assets/B','assets/C']);self.assertEqual(job['progress'],100)
  self.assertEqual([r['id'] for r in job['pendingReviews']],['A','C'])
  self.assertEqual(job['stage'],'manual_review')
  live=self.store.get(self.p['id']);self.assertEqual([len(a['versions']) for a in live['assets']],[1,1,2])
  self.assertFalse(any(selected(a)['humanAccepted'] for a in live['assets']))
  restored=Runner(self.store,start=False);self.assertEqual(restored.jobs[0]['pendingReviews'],job['pendingReviews'])
 def test_b_uses_a_unapproved_input_and_remaining_images_finish(self):
  # B explicitly pins the existing A version, as the image-input UI does.
  self.image(self.p,self.p['assets'][0],{'id':'existing'},0);self.generated=[]
  a=self.p['assets'][0];b=self.p['assets'][1]
  b.update(imageMode='reference',generationRefs=['version:A:existing_A_0:0']);self.store.save(self.p)
  self.verdicts['C']='pass';job=self.runner.enqueue(self.p['id'],'assets_auto')
  with self.assertRaisesRegex(Human,'1 个资产待集中人工审核'):self.run_batch(job)
  self.assertEqual(self.generated,[('B',0),('C',0)])
  self.assertEqual(self.inputs['B'][0]['sha256'],selected(a)['files'][0]['sha256'])
  self.assertIsNone(selected(job['snapshot']['assets'][0])['review'])
  self.assertEqual(job['done'],['assets/A','assets/B','assets/C'])
 def test_full_auto_finishes_all_images_but_does_not_submit_video(self):
  self.p['shots']=[dict(id='s001',name='镜头1',prompt='<Picture 1> 杯子',refs=['B'],seconds=8,width=1344,height=768,seed=1,selected=None,versions=[])]
  self.store.save(self.p);job=self.runner.enqueue(self.p['id'],'auto')
  with patch.object(self.runner,'shot') as shot,patch.object(self.runner,'export') as export:
   with self.assertRaisesRegex(Human,'待集中人工审核'):self.run_batch(job)
  self.assertEqual(job['done'],['assets/A','assets/B','assets/C']);shot.assert_not_called();export.assert_not_called()
 def test_single_image_keeps_its_review_status(self):
  job=self.runner.enqueue(self.p['id'],'asset','A')
  with self.assertRaises(QualityReviewRequired):self.run_batch(job)
  self.assertEqual(self.generated,[('A',0)]);self.assertNotIn('pendingReviews',job)
 def test_review_disabled_still_finishes_all_images_for_manual_review(self):
  job=self.runner.enqueue(self.p['id'],'assets_auto',auto_review=False)
  with patch.object(self.runner,'review') as review,patch.object(self.runner,'asset',side_effect=self.image):
   with self.assertRaisesRegex(Human,'3 个资产待集中人工审核'):self.runner.execute(job)
  review.assert_not_called();self.assertEqual(len(job['done']),3);self.assertEqual(len(job['pendingReviews']),3)
 def test_all_pass_completes_normally(self):
  self.verdicts={k:'pass' for k in self.verdicts};job=self.runner.enqueue(self.p['id'],'assets_auto');self.run_batch(job)
  self.assertEqual(len(job['done']),3);self.assertNotIn('pendingReviews',job)
 def test_review_timeout_keeps_a_available_to_b_and_finishes_batch_without_retry(self):
  self.p['assets'][1].update(imageMode='reference',generationRefs=['asset:A:0']);self.store.save(self.p)
  self.verdicts={k:'pass' for k in self.verdicts};job=self.runner.enqueue(self.p['id'],'assets_auto')
  original=self.review
  def review(p,category,item,v,folder,j):
   if item['id']=='A':raise ReviewUnavailable('视觉审核超时')
   return original(p,category,item,v,folder,j)
  with patch.object(self.runner,'asset',side_effect=self.image),patch.object(self.runner,'review',side_effect=review):
   with self.assertRaisesRegex(Human,'1 个资产待集中人工审核'):self.runner.execute(job)
  self.assertEqual(self.generated,[('A',0),('B',0),('C',0)])
  self.assertEqual(self.inputs['B'][0]['sha256'],selected(job['snapshot']['assets'][0])['files'][0]['sha256'])
  self.assertEqual(job['done'],['assets/A','assets/B','assets/C']);self.assertEqual(job['retryStates']['assets/A']['attempt'],0)
  self.assertIn('超时',job['pendingReviews'][0]['reason']);self.assertIsNone(selected(job['snapshot']['assets'][0])['review'])
 def test_review_timeout_persists_error_and_does_not_invent_verdict(self):
  job=self.runner.enqueue(self.p['id'],'asset','A');p=job['snapshot'];a=p['assets'][0]
  v,folder=self.image(p,a,job);v['files'][0]['label']='prop'
  with patch.object(self.runner,'command',side_effect=ReviewUnavailable('视觉审核超时')):
   with self.assertRaises(ReviewUnavailable):self.runner.review(p,'assets',a,v,folder,job)
  saved=selected(self.store.get(p['id'])['assets'][0]);self.assertIsNone(saved['review']);self.assertEqual(saved['reviewError']['kind'],'timeout')
 def test_timeout_exit_is_special_only_for_reviewer_and_success_clears_error(self):
  from h3_director.backend.project import write
  job=self.runner.enqueue(self.p['id'],'asset','A');p=job['snapshot'];a=p['assets'][0]
  v,folder=self.image(p,a,job);v['files'][0]['label']='prop'
  with self.assertRaises(ReviewUnavailable):self.runner.command([sys.executable,'-c','raise SystemExit(30)',HARNESS],folder,job)
  with self.assertRaises(RuntimeError):self.runner.command([sys.executable,'-c','raise SystemExit(30)'],folder,job)
  v['reviewError']={'kind':'timeout'}
  def completed(*args):write(folder/'review.json',dict(verdict='human',summary='实际模型结论',confidence=.8,issues=[],limitations=[],retryAction='none',retryReason='交人工',revisedPrompt='',revisedViewPrompts=[]))
  with patch.object(self.runner,'command',side_effect=completed):self.runner.review(p,'assets',a,v,folder,job)
  saved=selected(self.store.get(p['id'])['assets'][0]);self.assertNotIn('reviewError',saved);self.assertEqual(saved['review']['verdict'],'human')
 def test_real_failures_and_uncertain_results_are_not_swallowed(self):
  for error in (RuntimeError('生成失败'),Human('结果尚未明确'),Stop('STOP'),Paused()):
   with self.subTest(error=type(error).__name__):
    job=dict(id='test',snapshot=self.p,kind='assets_auto',done=[],autoReview=True,paused=False)
    with patch.object(self.runner,'generate_review',side_effect=error) as generate:
     with self.assertRaises(type(error)):self.runner.execute(job)
    self.assertEqual(generate.call_count,1);self.assertEqual(job['done'],[])

 def test_all_reviewer_failures_continue_batch_without_guessing_retry(self):
  from h3_director.backend.project import write
  for mode in ('missing_decision','invalid_decision','invalid_json','network','missing_output'):
   with self.subTest(mode=mode):
    p=self.store.create(mode);p['assets']=[make_asset(n,'prop',n) for n in ('A','B','C')]
    p['assets'][1].update(imageMode='reference',generationRefs=['asset:A:0']);self.store.save(p)
    job=self.runner.enqueue(p['id'],'assets_auto');self.generated=[]
    def image(*args):
     v,folder=self.image(*args);v['files'][0]['label']='prop';return v,folder
    def command(args,folder,j):
     result=dict(verdict='pass',confidence=.9,summary='符合要求',issues=[],limitations=[],retryAction='none',retryReason='无需重试',revisedPrompt='',revisedViewPrompts=[])
     if folder.parent.name=='A':
      if mode=='network':raise RuntimeError('review API 503')
      if mode=='missing_output':
       (folder/'review.json').unlink(missing_ok=True);return
      if mode=='invalid_json':(folder/'review.json').write_text('{invalid');return
      if mode=='missing_decision':result.pop('retryAction');result.pop('retryReason')
      if mode=='invalid_decision':result.update(retryAction='reroll',revisedPrompt='不应执行的修改')
     write(folder/'review.json',result)
    with patch.object(self.runner,'asset',side_effect=image),patch.object(self.runner,'command',side_effect=command):
     with self.assertRaisesRegex(Human,'1 个资产待集中人工审核'):self.runner.execute(job)
    self.assertEqual(self.generated,[('A',0),('B',0),('C',0)])
    self.assertEqual(job['done'],['assets/A','assets/B','assets/C'])
    self.assertEqual(job['retryStates']['assets/A']['attempt'],0);self.assertNotIn('retryEvents',job)
    a=selected(self.store.get(p['id'])['assets'][0]);self.assertIsNone(a['review']);self.assertEqual(a['reviewError']['kind'],'failed')
    self.assertEqual(self.inputs['B'][0]['sha256'],a['files'][0]['sha256'])

 def test_reviewer_stop_pause_and_unknown_execution_remain_terminal(self):
  for error in (Stop('STOP'),Paused(),Human('在途结果未知')):
   job=dict(id='control',retryStates={},productionSettings={},snapshot=self.p)
   a=self.p['assets'][0];v,folder=self.image(self.p,a,job);v['files'][0]['label']='prop'
   with patch.object(self.runner,'command',side_effect=error):
    with self.assertRaises(type(error)):self.runner.review(self.p,'assets',a,v,folder,job)
 def test_resume_skips_finished_assets_and_preserves_review_list(self):
  job=self.runner.enqueue(self.p['id'],'assets_auto');original=self.runner.checkpoint
  def checkpoint(j):
   if j['done']==['assets/A']:raise Paused()
   original(j)
  with patch.object(self.runner,'checkpoint',side_effect=checkpoint):
   with self.assertRaises(Paused):self.run_batch(job)
  self.assertEqual(job['done'],['assets/A']);self.assertEqual(len(job['pendingReviews']),1)
  with self.assertRaisesRegex(Human,'2 个资产待集中人工审核'):self.run_batch(job)
  self.assertEqual(self.generated.count(('A',0)),1);self.assertEqual(len(job['pendingReviews']),2)
 def test_existing_manual_acceptance_does_not_reenter_review(self):
  self.image(self.p,self.p['assets'][0],{'id':'existing'},0);selected(self.p['assets'][0])['humanAccepted']=True;self.store.save(self.p)
  self.generated=[];self.verdicts={'B':'pass','C':'pass'};job=self.runner.enqueue(self.p['id'],'assets_auto');self.run_batch(job)
  self.assertEqual(self.generated,[('B',0),('C',0)]);self.assertNotIn('pendingReviews',job)
 def test_configurable_retry_limit_zero_and_three(self):
  for limit in (0,3):
   with self.subTest(limit=limit):
    self.p=self.store.create('重试阈值');self.p['assets']=[make_asset('A','prop','A')];configure(self.p,{'maxRetries':limit},'assets');self.store.save(self.p)
    job=self.runner.enqueue(self.p['id'],'assets_auto');job['productionSettings']=self.p['productionSettings'];self.verdicts['A']='revise';self.generated=[]
    with self.assertRaisesRegex(Human,'集中人工审核'):self.run_batch(job)
    self.assertEqual(len(self.generated),limit+1);self.assertEqual(len(job.get('retryEvents',[])),limit)
    self.assertEqual(job['retryStates']['assets/A']['attempt'],limit)
 def test_reroll_keeps_all_prompts_and_changes_seed(self):
  self.p['assets']=self.p['assets'][:1];self.store.save(self.p);job=self.runner.enqueue(self.p['id'],'assets_auto')
  original=dict(self.p['assets'][0]);base_review=self.review
  def reroll(*args):
   result=base_review(*args);result.update(verdict='revise',retryAction='reroll',retryReason='提示词已清楚，手部随机畸变',revisedPrompt='',revisedViewPrompts=[]);return result
  self.review=reroll
  with self.assertRaisesRegex(Human,'集中人工审核'):self.run_batch(job)
  final=self.store.get(self.p['id'])['assets'][0]
  for field in ('prompt','sidePrompt','backPrompt'):self.assertEqual(final[field],original[field])
  self.assertEqual(final['seed'],original['seed']+1);self.assertEqual(job['retryEvents'][0]['action'],'reroll')
  self.assertEqual([v['prompt'] for v in final['versions']],[original['prompt']]*2)
 def test_agent_revision_reaches_next_generation_and_preserves_prior_version(self):
  self.p['assets']=self.p['assets'][:1];self.store.save(self.p);job=self.runner.enqueue(self.p['id'],'assets_auto');original=self.p['assets'][0]['prompt']
  base_review=self.review
  def revise(*args):
   result=base_review(*args);result.update(verdict='revise',retryAction='revise_prompt',retryReason='正面构图需要更明确',revisedPrompt='中文新正面',revisedViewPrompts=['中文新侧面','中文新背面']);return result
  self.review=revise
  with self.assertRaises(Human):self.run_batch(job)
  asset=self.store.get(self.p['id'])['assets'][0]
  self.assertEqual([v['prompt'] for v in asset['versions']],[original,'中文新正面'])
  self.assertEqual(asset['sidePrompt'],'中文新侧面');self.assertEqual(asset['backPrompt'],'中文新背面')
  self.assertEqual(job['retryEvents'][0]['before']['prompt'],original)
 def test_pause_between_retries_does_not_reset_limit(self):
  self.p['assets']=self.p['assets'][:1];self.store.save(self.p);job=self.runner.enqueue(self.p['id'],'assets_auto');self.verdicts['A']='revise'
  def checkpoint(j):
   if j.get('retryStates',{}).get('assets/A',{}).get('attempt')==1:raise Paused()
  with patch.object(self.runner,'checkpoint',side_effect=checkpoint):
   with self.assertRaises(Paused):self.run_batch(job)
  self.assertEqual(self.generated,[('A',0)])
  restored=Runner(self.store,start=False);job=restored.jobs[-1];self.runner=restored
  with self.assertRaises(Human):self.run_batch(job)
  self.assertEqual(self.generated,[('A',0),('A',1)]);self.assertEqual(len(job['retryEvents']),1)
 def test_invalid_limit_leaves_settings_unchanged(self):
  before=self.store.get(self.p['id'])
  for value in (-1,11,True,1.5,'2',None):
   with self.assertRaises(ValueError):self.runner.enqueue(self.p['id'],'assets_auto',options={'maxRetries':value})
  self.assertEqual(before,self.store.get(self.p['id']));self.assertEqual(self.runner.jobs,[])
 def test_reroll_cannot_smuggle_prompt_edits(self):
  self.p['assets']=self.p['assets'][:1];self.store.save(self.p);job=self.runner.enqueue(self.p['id'],'assets_auto')
  base_review=self.review
  def invalid(*args):
   result=base_review(*args);result.update(verdict='revise',retryAction='reroll',revisedPrompt='不应应用');return result
  self.review=invalid
  with self.assertRaises(Human):self.run_batch(job)
  self.assertEqual(self.generated,[('A',0)]);self.assertNotIn('retryEvents',job)
 def test_existing_failed_version_is_preserved_until_explicit_clear(self):
  self.p['assets']=self.p['assets'][:1];self.store.save(self.p);self.image(self.p,self.p['assets'][0],{'id':'existing'});self.generated=[]
  self.verdicts['A']='revise';job=self.runner.enqueue(self.p['id'],'assets_auto')
  with self.assertRaises(Human):self.run_batch(job)
  self.assertEqual(self.generated,[]);self.assertEqual(len(self.store.get(self.p['id'])['assets'][0]['versions']),1)
 def test_video_budget_caps_large_user_retry_limit(self):
  self.image(self.p,self.p['assets'][0],{'id':'existing'})
  s=dict(id='S',name='视频',prompt='<Picture 1> 杯子',refs=['A'],seconds=8,width=1344,height=768,seed=1,versions=[],selected=None,history=[])
  self.p['shots']=[s];self.store.save(self.p);job=self.runner.enqueue(self.p['id'],'shot','S');job['productionSettings']={'maxRetries':10}
  v=dict(id='video',prompt=s['prompt'],seed=1,files=[]);self.verdicts['S']='revise'
  with patch.object(self.runner,'shot',return_value=(v,Path(self.tmp.name))) as shot,patch.object(self.runner,'review',side_effect=self.review),patch('h3_director.backend.runner.budget',return_value={'ledger':{'attempts':{'S':[{},{}]}}}):
   with self.assertRaisesRegex(Human,'两次提交额度'):self.runner.execute(job)
  self.assertEqual(shot.call_count,1);self.assertNotIn('retryEvents',job)
 def test_video_revision_with_invalid_picture_tags_is_not_submitted(self):
  self.image(self.p,self.p['assets'][0],{'id':'existing'})
  s=dict(id='S',name='视频',prompt='<Picture 1> 杯子',refs=['A'],seconds=8,width=1344,height=768,seed=1,versions=[],selected=None,history=[])
  self.p['shots']=[s];self.store.save(self.p);job=self.runner.enqueue(self.p['id'],'shot','S')
  v=dict(id='video',prompt=s['prompt'],seed=1,files=[])
  review=dict(verdict='revise',summary='构图偏差',retryAction='revise_prompt',retryReason='修订构图',revisedPrompt='<Picture 2> 杯子',revisedViewPrompts=[])
  with patch.object(self.runner,'shot',return_value=(v,Path(self.tmp.name))) as shot,patch.object(self.runner,'review',return_value=review),patch('h3_director.backend.runner.budget',return_value={'ledger':{'attempts':{'S':[{}]}}}):
   with self.assertRaisesRegex(Human,'标签不合法'):self.runner.execute(job)
  self.assertEqual(shot.call_count,1);self.assertNotIn('retryEvents',job)
 def test_video_reroll_retains_prompt_and_prepares_next_seed(self):
  self.image(self.p,self.p['assets'][0],{'id':'existing'})
  s=dict(id='S',name='视频',prompt='<Picture 1> 杯子',refs=['A'],seconds=8,width=1344,height=768,seed=1,versions=[],selected=None,history=[])
  self.p['shots']=[s];self.store.save(self.p);job=self.runner.enqueue(self.p['id'],'shot','S')
  v=dict(id='video',prompt=s['prompt'],seed=1,files=[])
  review=dict(verdict='revise',summary='随机变形',retryAction='reroll',retryReason='指令清楚，仅重新抽卡',revisedPrompt='',revisedViewPrompts=[])
  with patch.object(self.runner,'shot',side_effect=[(v,Path(self.tmp.name)),Paused()]) as shot,patch.object(self.runner,'review',return_value=review),patch('h3_director.backend.runner.budget',return_value={'ledger':{'attempts':{'S':[{}]}}}):
   with self.assertRaises(Paused):self.runner.execute(job)
  event=job['retryEvents'][0];self.assertEqual(event['before']['prompt'],event['after']['prompt']);self.assertEqual(event['after']['seed'],2)
  self.assertEqual(shot.call_args.kwargs,{});self.assertEqual(shot.call_args.args[-1],1)

if __name__=='__main__':unittest.main()
