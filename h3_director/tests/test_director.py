import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch,MagicMock
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.project import ROOT,Store,parse_storyboard,validate_shot,selected,current,read,write
from backend.runner import Runner,Stop,Paused,Human
from backend.server import DEMO_MANIFEST,SAMPLE,demo,public_project

class DirectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.store=Store(self.tmp.name); self.runner=Runner(self.store,start=False)
    def tearDown(self): self.tmp.cleanup()
    def demo_with_media(self):
        if not DEMO_MANIFEST.is_file():
            self.skipTest('requires locally generated greenhouse demo media')
        return demo(self.store,True)
    def test_demo_without_local_media_uses_bundled_prompts(self):
        with patch('backend.server.DEMO_MANIFEST',Path(self.tmp.name)/'missing.json'):
            project=demo(self.store,True)
        self.assertEqual(len(project['assets']),3)
        self.assertTrue(project['shots'][0]['prompt'])
        self.assertIsNone(selected(project['shots'][0]))
    def test_import_preserves_all_27_shots_and_four_references(self):
        if not SAMPLE.is_file():
            self.skipTest('requires a local storyboard fixture')
        text=SAMPLE.read_text(encoding='utf-8-sig')
        p=self.store.create('对面',text)
        self.assertEqual(len(p['shots']),27); self.assertEqual(len(p['assets']),12)
        self.assertEqual(p['shots'][2]['refs'],['C01','C02','S01','P01'])
        self.assertIn('<Picture 4>',p['shots'][2]['prompt']); self.assertEqual(p['sources'][0]['text'],text)
        self.assertEqual(self.store.get(p['id'])['shots'][2]['originalPrompt'],p['shots'][2]['originalPrompt'])
    def test_1_to_9_refs_and_mismatched_tags(self):
        p=self.demo_with_media(); s=p['shots'][0]
        s['refs']=[p['assets'][0]['id']];s['prompt']='<Picture 1> moves'
        self.assertEqual(validate_shot(p,s),[])
        s['prompt']='<Picture 2> moves';self.assertTrue(validate_shot(p,s))
        s['refs']*=10;self.assertTrue(validate_shot(p,s))
    def test_missing_asset_stops_before_enqueue(self):
        p=demo(self.store,False)
        with self.assertRaises(ValueError): self.runner.enqueue(p['id'],'shot','s001')
        self.assertEqual(self.runner.jobs,[])
    def test_changed_prompts_and_references_invalidate_reuse(self):
        p=self.demo_with_media();s=p['shots'][0];self.assertTrue(current(p,'shots',s))
        s['seconds']=8; selected(s)['seconds']=10;self.assertFalse(current(p,'shots',s))
        s['seconds']=10;selected(p['assets'][0])['files'][0]['sha256']='changed';self.assertFalse(current(p,'shots',s))
        a=p['assets'][0];a['prompt']+=' edited';self.assertFalse(current(p,'assets',a))
    def test_duplicate_enqueue_blocked_and_cancel_retains_outputs(self):
        p=self.demo_with_media();j=self.runner.enqueue(p['id'],'export')
        with self.assertRaises(ValueError): self.runner.enqueue(p['id'],'auto')
        self.runner.control(j['id'],'pause');self.assertEqual(j['status'],'paused')
        self.runner.control(j['id'],'cancel');self.assertEqual(j['status'],'cancelled')
        self.assertTrue(selected(self.store.get(p['id'])['shots'][0]))
    def test_restart_never_resubmits_running_job(self):
        p=self.demo_with_media();j=self.runner.enqueue(p['id'],'auto');j['status']='running';self.runner.save()
        recovered=Runner(self.store,start=False)
        self.assertEqual(recovered.jobs[0]['status'],'interrupted');self.assertEqual(recovered.jobs[0]['id'],j['id'])
    def test_exit_20_is_terminal(self):
        p=self.demo_with_media();j=self.runner.enqueue(p['id'],'auto')
        proc=MagicMock();proc.wait.return_value=20;proc.pid=123
        with patch('backend.runner.subprocess.Popen',return_value=proc):
            with self.assertRaises(Stop): self.runner.command(['fake'],Path(self.tmp.name)/'run',j)
        self.assertEqual(proc.wait.call_count,1)
    def test_pause_does_not_begin_generation(self):
        p=demo(self.store,False);j=self.runner.enqueue(p['id'],'auto');j['paused']=True
        with patch.object(self.runner,'generate_review') as gen:
            with self.assertRaises(Paused):self.runner.execute(j)
            gen.assert_not_called()
    def test_video_review_attaches_hashed_frames_references_and_last_frame(self):
        p=self.demo_with_media(); s=p['shots'][0]; v=selected(s)
        j=self.runner.enqueue(p['id'],'review',s['id']); folder=Path(self.tmp.name)/'new-review'
        def reviewed(args,folder,j):
            write(folder/'review.json',dict(verdict='human',summary='offline test only',confidence=.8,issues=[],limitations=[],retryAction='none',retryReason='交人工',revisedPrompt='',revisedViewPrompts=[]))
        with patch.object(self.runner,'command',side_effect=reviewed):
            self.runner.review(p,'shots',s,v,folder,j)
        req=read(folder/'review-input.json'); evidence=req['evidence']
        self.assertEqual(evidence['method'],'sampled-video-frames')
        self.assertFalse(evidence['audioReviewed'])
        self.assertEqual([x['sha256'] for x in req['images'][:len(v['references'])]], [r['sha256'] for r in v['references']])
        self.assertEqual(req['images'][-1]['frameIndex'],evidence['decodedFrames']-1)
        self.assertGreater(evidence['sampledFrames'],10)
        self.assertTrue(all(Path(x['path']).is_file() and len(x['sha256'])==64 for x in req['images']))
    def test_changed_video_never_sent_for_review(self):
        p=self.demo_with_media(); s=p['shots'][0]; v=selected(s); v['files'][0]['sha256']='modified'
        j=self.runner.enqueue(p['id'],'review',s['id'])
        with patch.object(self.runner,'command') as send:
            with self.assertRaisesRegex(ValueError,'哈希不一致'):
                self.runner.review(p,'shots',s,v,Path(self.tmp.name)/'review',j)
            send.assert_not_called()
    def test_auto_reuses_accepted_versions_and_exports_without_gpu(self):
        p=self.demo_with_media()
        for x in p['assets']+p['shots']:selected(x)['humanAccepted']=True
        self.store.save(p);j=self.runner.enqueue(p['id'],'auto')
        with patch.object(self.runner,'generate_review') as gen:
            self.runner.execute(j);gen.assert_not_called()
        p=self.store.get(p['id']);e=p['exports'][0]
        with zipfile.ZipFile(e['path']) as z:
            self.assertIn('TRAE-剪辑任务.md',z.namelist())
            m=json.loads(z.read('edit-manifest.json'));self.assertEqual(len(m['shots']),1);self.assertEqual(m['status'],'draft')
            self.assertFalse(any('.env' in n for n in z.namelist()))
    def test_unknown_visual_result_never_auto_passes(self):
        p=self.demo_with_media();j=self.runner.enqueue(p['id'],'auto')
        with patch.object(self.runner,'review',return_value={'verdict':'human','summary':'insufficient evidence'}),patch.object(self.runner,'shot') as shot:
            with self.assertRaises(Human):self.runner.execute(j)
            shot.assert_not_called()
    def test_media_urls_not_arbitrary_files(self):
        p=public_project(self.demo_with_media())
        self.assertTrue(p['assets'][0]['versions'][0]['files'][0]['url'].startswith('/api/media/'))
        with self.assertRaises(ValueError):self.store.get('../../.env')
    def test_visual_retry_is_bounded_to_two_and_keeps_shot_name(self):
        p=demo(self.store,False);j=self.runner.enqueue(p['id'],'asset','character_front');a=j['snapshot']['assets'][0]
        version={'id':'fake','files':[]}
        with patch.object(self.runner,'asset',return_value=(version,Path(self.tmp.name))) as generate,patch.object(self.runner,'review',return_value={'verdict':'revise','revisedPrompt':'A better one-person front view','summary':'anatomy error'}),patch.object(self.runner,'persist_item'):
            with self.assertRaises(Human):self.runner.generate_review(j['snapshot'],'assets',a,j)
            self.assertEqual(generate.call_count,2)
            self.assertEqual(generate.call_args_list[0].args[1]['id'],'character_front')
            self.assertEqual(generate.call_args_list[1].args[1]['id'],'character_front')

if __name__=='__main__':unittest.main(verbosity=2)
