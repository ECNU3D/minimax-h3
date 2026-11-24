"""Offline regression checks for costly duplicate submissions and caption clipping."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from caption_layout import layout, render_cues
from h3_budget import Budget, BudgetStop
from h3_batch import prepare, execute
from workflow_client import run_job, sha256, save_json


class ProductionTests(unittest.TestCase):
    def test_budget_persists_across_runs_and_variants(self):
        with tempfile.TemporaryDirectory() as td:
            b = Budget(td)
            b.reserve('ep03_s07b', 'run-1')
            b.finish('ep03_s07b', 'run-1', True)
            b = Budget(td)
            b.reserve('ep03_s07c', 'run-2')
            b.finish('ep03_s07c', 'run-2', True)
            with self.assertRaises(BudgetStop):
                Budget(td).reserve('ep03_s07e', 'run-3')
            with self.assertRaises(BudgetStop):
                Budget(td).check()

    def test_three_failed_shots_latch_stop(self):
        with tempfile.TemporaryDirectory() as td:
            b = Budget(td)
            for i in range(3):
                b.reserve(f'ep01_s0{i}', str(i))
                if i < 2:
                    b.finish(f'ep01_s0{i}', str(i), False)
                else:
                    with self.assertRaises(BudgetStop):
                        b.finish(f'ep01_s0{i}', str(i), False)
            self.assertEqual(Budget(td).data['failure_count'], 3)

    def test_ambiguous_submission_cannot_reserve_twice(self):
        with tempfile.TemporaryDirectory() as td:
            Budget(td).reserve('ep01_s01', 'same-run')
            with self.assertRaises(BudgetStop):
                Budget(td).reserve('ep01_s01', 'same-run')

    def test_timeout_latches_without_a_second_submission(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            plan = dict(name='ep01_s01', inputs={'references': []}, copies=[], workflow={}, fingerprint='test')
            def pending(_graph, folder, _url, timeout):
                save_json(folder/'job.json', dict(status='running', prompt_id='still-running'))
                raise TimeoutError('poll limit reached')
            with patch('h3_batch.ROOT', root), patch('h3_batch.request', return_value={'queue_running': [], 'queue_pending': []}), patch('h3_batch.run_job', side_effect=pending) as runner:
                with self.assertRaises(BudgetStop):
                    execute([plan], root/'run1', 'unused', 1, 'test-campaign')
                with self.assertRaises(BudgetStop):
                    execute([plan], root/'run2', 'unused', 1, 'test-campaign')
                self.assertEqual(runner.call_count, 1)
                state = json.loads((root/'run1/ep01_s01/job.json').read_text())
                self.assertEqual(state['prompt_id'], 'still-running')

    def test_two_execution_errors_across_directories_stop_campaign(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            plan = dict(name='ep01_s01', inputs={'references': []}, copies=[], workflow={}, fingerprint='test')
            def failed(_graph, folder, _url, timeout):
                save_json(folder/'job.json', dict(status='error', prompt_id=folder.parent.name))
                raise RuntimeError('execution_error')
            with patch('h3_batch.ROOT', root), patch('h3_batch.request', return_value={'queue_running': [], 'queue_pending': []}), patch('h3_batch.run_job', side_effect=failed) as runner:
                with self.assertRaisesRegex(RuntimeError, 'execution_error'):
                    execute([plan], root/'run1', 'unused', 1, 'test-campaign')
                with self.assertRaises(BudgetStop):
                    execute([plan], root/'run2', 'unused', 1, 'test-campaign')
                with self.assertRaises(BudgetStop):
                    execute([plan], root/'run3', 'unused', 1, 'test-campaign')
                self.assertEqual(runner.call_count, 2)

    def test_completed_job_is_reused_from_record_not_filename(self):
        import hashlib
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            video = folder/'actual_00007_.mp4'
            video.write_bytes(b'test output hash')
            graph = {'1': {'class_type': 'SaveVideo', 'inputs': {}}}
            save_json(folder/'job.json', dict(status='success', prompt_id='saved',
                graph_sha256=hashlib.sha256(json.dumps(graph,sort_keys=True).encode()).hexdigest(),
                files=[dict(path=str(video), sha256=sha256(video))]))
            with patch('workflow_client.request', side_effect=AssertionError('Must not submit')):
                self.assertEqual(run_job(graph, folder)['files'][0]['path'], str(video))
                video.write_bytes(b'corrupt')
                with self.assertRaises(ValueError):
                    run_job(graph, folder)

    def test_tag_mismatch_fails_before_submission(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root/'prompt.txt').write_text('Person <Picture 2>',encoding='utf-8')
            (root/'spec.json').write_text(json.dumps([dict(name='s01',prompt=str(root/'prompt.txt'),refs=['a','b','c'],seed=1)]))
            with self.assertRaisesRegex(ValueError, 'Picture tags'):
                prepare(root/'spec.json')

    def test_long_chinese_caption_fails_instead_of_clipping(self):
        with self.assertRaisesRegex(ValueError, 'split into timed clauses'):
            layout('我教计算机，上班跟学生打交道，下班跟锅碗瓢盆打交道。20年，我的人生就是学校和厨房之间那条路。')

    def test_safe_area_uses_actual_glyph_bounds(self):
        im, info = layout('上班跟学生打交道\n下班跟锅碗瓢盆打交道')
        x1,y1,x2,y2 = im.getbbox()
        self.assertGreaterEqual(x1, round(1344*.08))
        self.assertLessEqual(x2, 1344-round(1344*.08))
        self.assertLessEqual(y2, 768-round(768*.09))
        with self.assertRaisesRegex(ValueError, 'protected'):
            layout('不要遮住这个位置', protected=[(0,600,1344,768)])

    def test_invalid_timing_writes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)/'out'
            with self.assertRaises(ValueError):
                render_cues(dict(width=1344,height=768,duration=2,cues=[dict(start=1,end=3,text='字幕')]),out)
            self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
