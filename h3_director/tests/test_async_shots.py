"""Exercise the production dispatcher with blocked reviewers, no GPU/model calls."""
import copy
import threading
import unittest
from contextlib import contextmanager
from unittest.mock import patch
import test_shot_batch_review as fixtures
from h3_director.backend.runner import Runner, Stop, selected, shot_clear_targets
from h3_director.backend.project import LOCK


class AsyncShots(unittest.TestCase):
    setUp=fixtures.ShotBatchReview.setUp
    tearDown=fixtures.ShotBatchReview.tearDown
    budget=fixtures.ShotBatchReview.budget
    shot=fixtures.ShotBatchReview.shot

    def review(self,p,category,item,v,folder,job):
        verdict=self.results[item['id']]
        result=dict(verdict=verdict,summary='测试结论',retryAction='reroll' if verdict=='revise' else 'none',revisedPrompt='',revisedViewPrompts=[])
        with LOCK:
            v['review']=result
            self.runner.persist_review(p,category,item,v)
        return result

    @contextmanager
    def adapters(self,review=None,shot=None):
        with patch.object(self.runner,'shot',side_effect=shot or self.shot),patch.object(self.runner,'review',side_effect=review or self.review),patch('h3_director.backend.runner.budget',side_effect=self.budget),patch('h3_director.backend.async_shots.budget',side_effect=self.budget):
            yield

    def batch(self):
        self.results={s['id']:'pass' for s in self.p['shots']}
        return self.runner.enqueue(self.p['id'],'shots_auto')

    def drain(self):
        for _ in range(30):
            a=self.runner.run_once('gpu');b=self.runner.run_once('review')
            if not a and not b:return
        self.fail('dispatcher never settled')

    def test_gpu_advances_while_three_reviews_are_running(self):
        fourth=copy.deepcopy(self.p['shots'][0]);fourth.update(id='s004',name='s004')
        self.p['shots'].append(fourth);self.store.save(self.p)
        job=self.batch();entered=[threading.Event() for _ in range(3)];release=threading.Event();threads=[]
        def blocked(p,c,s,v,f,j):
            if s['id']!='s004':entered[['s001','s002','s026'].index(s['id'])].set()
            if not release.wait(8):raise RuntimeError('test timed out')
            return self.review(p,c,s,v,f,j)
        with self.adapters(review=blocked):
            self.assertTrue(self.runner.run_once())
            try:
                for i in range(3):
                    self.assertTrue(self.runner.run_once())
                    t=threading.Thread(target=self.runner.run_once,args=('review',));threads.append(t);t.start()
                    self.assertTrue(entered[i].wait(3))
                self.assertEqual(self.generated,[('s001',0),('s002',0),('s026',0)])
                self.assertTrue(self.runner.run_once('gpu'))
                self.assertEqual(job['queueSummary']['review']['running'],3)
                self.assertEqual(job['queueSummary']['review']['queued'],1)
                self.assertFalse(self.runner.run_once('review'))
                self.assertFalse(self.runner.run_once('gpu'))
                self.assertEqual(job['status'],'running')
            finally:
                release.set()
                for t in threads:t.join(5)
            self.drain()
        self.assertEqual(job['status'],'success');self.assertEqual(len(job['done']),4)

    def test_existing_video_expansion_persists_once_and_keeps_pending_reviews(self):
        from h3_director.backend.async_shots import schedule
        from h3_director.backend.project import read
        job=self.batch()
        shots=job['snapshot']['shots']
        for shot in shots[:2]:
            version=dict(id='existing-'+shot['id'],files=[],humanAccepted=False)
            shot['versions']=[version];shot['selected']=version['id']
        with self.adapters(),patch.object(self.runner,'save',wraps=self.runner.save) as save:
            self.assertTrue(schedule(self.runner,job,shots))
        self.assertEqual(save.call_count,1)
        self.assertEqual([r['id'] for r in job['pendingShotReviews']],['s001','s002'])
        self.assertEqual(job['done'],['shots/s001','shots/s002'])
        self.assertEqual([t['target'] for t in job['shotTasks']],['s026'])
        saved=next(j for j in read(self.runner.file) if j['id']==job['id'])
        self.assertEqual(saved['pendingShotReviews'],job['pendingShotReviews'])
        self.assertEqual(saved['shotTasks'],job['shotTasks'])

    def test_retry_goes_behind_remaining_shots_and_keeps_budget(self):
        job=self.batch();self.results['s001']='revise';job['productionSettings']={'maxRetries':10}
        with self.adapters():
            self.runner.run_once();self.runner.run_once();self.runner.run_once('review')
            self.assertEqual(job['shotTasks'][-1]['target'],'s001')
            self.assertEqual(job['shotTasks'][-1]['attempt'],1)
            self.drain()
        self.assertEqual(self.generated,[('s001',0),('s002',0),('s026',0),('s001',1)])
        self.assertEqual(len(self.attempts['s001']),2);self.assertEqual(job['status'],'needs_review')
        self.assertEqual(len(job['pendingShotReviews']),1)
        self.assertEqual(job['snapshot']['campaign'],self.p['campaign'])

    def test_independent_jobs_and_new_jobs_precede_retry(self):
        first=self.runner.enqueue(self.p['id'],'shot','s001');self.results={s['id']:'pass' for s in self.p['shots']};self.results['s001']='revise'
        with self.adapters():
            self.runner.run_once();self.runner.run_once()
            second=self.runner.enqueue(self.p['id'],'shot','s002')
            self.runner.run_once('review')
            self.drain()
        self.assertEqual(self.generated,[('s001',0),('s002',0),('s001',1)])
        self.assertEqual(second['status'],'success');self.assertEqual(first['status'],'needs_review')

    def test_pause_during_review_persists_retry_without_dispatch_until_resume(self):
        job=self.batch();self.results['s001']='revise'
        def pause(p,c,s,v,f,j):
            self.runner.control(job['id'],'pause')
            return self.review(p,c,s,v,f,j)
        with self.adapters(review=pause):
            self.runner.run_once();self.runner.run_once();self.runner.run_once('review')
        self.assertEqual(job['status'],'paused');self.assertEqual(len(job['shotTasks']),4)
        self.assertFalse(self.runner.run_once());self.assertFalse(self.runner.run_once('review'))
        with self.adapters():
            self.runner.control(job['id'],'resume');self.results['s001']='pass';self.drain()
        self.assertEqual(job['status'],'success');self.assertEqual(self.generated[-1],('s001',1))

    def test_cancel_running_review_keeps_result_and_never_appends_retry(self):
        job=self.batch();self.results['s001']='revise'
        def cancel(p,c,s,v,f,j):
            self.runner.control(job['id'],'cancel')
            self.assertEqual(job['status'],'running')  # Protect outputs until in-flight worker returns.
            return self.review(p,c,s,v,f,j)
        with self.adapters(review=cancel):
            self.runner.run_once();self.runner.run_once();self.runner.run_once('review');self.drain()
        self.assertEqual(job['status'],'cancelled');self.assertEqual(self.generated,[('s001',0)])
        self.assertEqual(len(job['shotTasks']),3)
        self.assertEqual(selected(self.store.get(self.p['id'])['shots'][0])['review']['verdict'],'revise')

    def test_restart_requires_resume_and_review_does_not_regenerate(self):
        job=self.batch()
        with self.adapters():self.runner.run_once();self.runner.run_once()
        task=job['shotTasks'][0];task['status']='running';task['pid']=123;self.runner.save()
        original_campaign=job['snapshot']['campaign'];self.runner=Runner(self.store,start=False);job=self.runner.jobs[0]
        self.assertEqual(job['status'],'interrupted');self.assertNotIn('pid',job['shotTasks'][0])
        self.assertFalse(self.runner.run_once());self.assertFalse(self.runner.run_once('review'))
        with self.adapters():
            self.runner.control(job['id'],'resume');self.drain()
        self.assertEqual(self.generated,[('s001',0),('s002',0),('s026',0)])
        self.assertEqual(job['snapshot']['campaign'],original_campaign);self.assertEqual(job['status'],'success')

    def test_stop_cancels_waiting_gpu_tasks_and_review_cannot_revive_job(self):
        job=self.batch();self.results['s001']='revise';entered=threading.Event();release=threading.Event()
        def review(*args):
            entered.set();release.wait(5);return self.review(*args)
        def generate(p,s,j,attempt=0):
            if s['id']=='s002':raise Stop('STOP.json')
            return self.shot(p,s,j,attempt)
        with self.adapters(review=review,shot=generate):
            self.runner.run_once();self.runner.run_once()
            t=threading.Thread(target=self.runner.run_once,args=('review',));t.start()
            try:
                self.assertTrue(entered.wait(3));self.runner.run_once();self.assertEqual(job['status'],'STOP')
            finally:release.set();t.join(5)
            self.drain()
        self.assertEqual(job['status'],'STOP');self.assertEqual(job['message'],'STOP.json')
        self.assertEqual(self.generated,[('s001',0)]);self.assertEqual(len(job['shotTasks']),3)

    def test_late_review_does_not_select_or_overwrite_newer_take_or_retry(self):
        job=self.batch();self.results['s001']='revise'
        with self.adapters():
            self.runner.run_once();self.runner.run_once()
            live=self.store.get(self.p['id']);s=live['shots'][0];old=s['selected']
            new=copy.deepcopy(selected(s));new.update(id='newer',prompt='用户改写',review={'verdict':'pass'})
            s['versions'].append(new);s.update(selected='newer',prompt='用户改写');self.store.save(live)
            self.runner.run_once('review');self.drain()
        saved=self.store.get(self.p['id'])['shots'][0]
        self.assertEqual(saved['selected'],'newer');self.assertEqual(saved['prompt'],'用户改写')
        self.assertEqual(selected(saved)['review']['verdict'],'pass')
        self.assertEqual(next(v for v in saved['versions'] if v['id']==old)['review']['verdict'],'revise')
        self.assertEqual(len(job['shotTasks']),3);self.assertEqual(job['status'],'needs_review')

    def test_edits_after_retry_queued_prevent_submission(self):
        job=self.batch();self.results['s001']='revise'
        with self.adapters():
            self.runner.run_once();self.runner.run_once();self.runner.run_once('review')
            live=self.store.get(self.p['id']);live['shots'][0]['prompt']+=' 新修改';self.store.save(live)
            self.drain()
        self.assertEqual(self.generated,[('s001',0),('s002',0),('s026',0)])
        self.assertEqual(job['status'],'needs_review')

    def test_done_and_clear_only_after_review_not_after_generation(self):
        job=self.batch()
        with self.adapters():
            self.runner.run_once();self.runner.run_once()
            self.assertIn('s001',shot_clear_targets(job));self.assertNotIn('shots/s001',job['done'])
            self.runner.run_once('review')
            self.assertNotIn('s001',shot_clear_targets(job));self.assertIn('s002',shot_clear_targets(job))
            self.drain()

    def test_export_waits_for_all_reviews(self):
        job=self.runner.enqueue(self.p['id'],'auto');self.results={s['id']:'pass' for s in self.p['shots']}
        with self.adapters(),patch.object(self.runner,'export') as export:
            for _ in range(4):self.runner.run_once()
            export.assert_not_called()
            for _ in range(3):self.runner.run_once('review')
            export.assert_not_called();self.runner.run_once();export.assert_called_once()

    def test_disabled_review_and_reviewer_failure_preserve_all_videos(self):
        from h3_director.backend.runner import ReviewUnavailable
        job=self.batch();job['autoReview']=False
        with self.adapters():self.drain()
        self.assertEqual(job['status'],'needs_review');self.assertEqual(len(job['pendingShotReviews']),3)
        self.assertTrue(all(t['phase']=='generate' for t in job['shotTasks']))
        # A separate explicit review failure has no authority to regenerate a video.
        job=self.runner.enqueue(self.p['id'],'shot','s001')
        with self.adapters(review=lambda *args:(_ for _ in ()).throw(ReviewUnavailable('审核服务不可用'))):self.drain()
        self.assertEqual(len(job['shotTasks']),1);self.assertEqual(job['status'],'needs_review')

    def test_queued_retry_survives_restart_with_same_attempt_and_campaign(self):
        job=self.batch();self.results['s001']='revise'
        with self.adapters():self.runner.run_once();self.runner.run_once();self.runner.run_once('review')
        task=copy.deepcopy(job['shotTasks'][-1]);self.runner=Runner(self.store,start=False);job=self.runner.jobs[0]
        with self.adapters():
            self.runner.control(job['id'],'resume');self.results['s001']='pass';self.drain()
        self.assertEqual(self.generated,[('s001',0),('s002',0),('s026',0),('s001',1)])
        self.assertEqual(job['shotTasks'][-1]['id'],task['id'])
        self.assertEqual(job['shotTasks'][-1]['attempt'],1);self.assertEqual(job['snapshot']['campaign'],self.p['campaign'])

    def test_cancel_during_generation_preserves_output_but_skips_review(self):
        job=self.batch()
        def cancelled(*args):
            self.runner.control(job['id'],'cancel')
            return self.shot(*args)
        with self.adapters(shot=cancelled):self.drain()
        self.assertEqual(job['status'],'cancelled');self.assertEqual(self.generated,[('s001',0)])
        self.assertIsNotNone(selected(self.store.get(self.p['id'])['shots'][0]))
        self.assertTrue(all(t['phase']=='generate' for t in job['shotTasks']))

    def test_review_only_write_does_not_resurrect_cleared_version(self):
        job=self.batch()
        with self.adapters():self.runner.run_once();self.runner.run_once()
        p=job['snapshot'];s=p['shots'][0];v=selected(s)
        live=self.store.get(p['id']);live['shots'][0].update(versions=[],selected=None);self.store.save(live)
        v['review']={'verdict':'pass'};self.runner.persist_review(p,'shots',s,v)
        self.assertEqual(self.store.get(p['id'])['shots'][0]['versions'],[])

    def test_manual_review_runs_in_review_lane_and_never_blocks_gpu(self):
        job=self.runner.enqueue(self.p['id'],'review','P')
        entered=threading.Event();release=threading.Event()
        def blocked(p,c,s,v,f,j):
            entered.set();release.wait(5);return {'verdict':'pass'}
        with self.adapters(review=blocked):
            t=threading.Thread(target=self.runner.run_once,args=('review',));t.start()
            try:
                self.assertTrue(entered.wait(3))
                video=self.runner.enqueue(self.p['id'],'shot','s001')
                self.runner.run_once();self.runner.run_once()
                self.assertEqual(self.generated,[('s001',0)]);self.assertEqual(job['status'],'running')
            finally:release.set();t.join(5)
            self.drain()
        self.assertEqual(job['status'],'success');self.assertEqual(video['status'],'success')

    def test_new_take_from_queued_snapshot_preserves_earlier_review(self):
        job=self.batch()
        with self.adapters():
            self.runner.run_once();self.runner.run_once()
            stale=copy.deepcopy(job['snapshot']);self.runner.run_once('review')
        item=stale['shots'][0];old=item['selected'];new=copy.deepcopy(selected(item));new.update(id='newer',review=None)
        self.runner.add_version(stale,'shots',item,new)
        saved=self.store.get(self.p['id'])['shots'][0]
        self.assertEqual(saved['selected'],'newer')
        self.assertEqual(next(v for v in saved['versions'] if v['id']==old)['review']['verdict'],'pass')


if __name__=='__main__':unittest.main()
