import copy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from h3_director.backend.project import Store,make_asset
from h3_director.backend.importer import import_source,apply_parse
from h3_director.backend.runner import Runner

class PairedAndQueue(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(self.temp.name);self.runner=Runner(self.store,start=False)
        self.p=self.store.create('排队测试');self.p['assets']=[make_asset('甲','prop','P01'),make_asset('乙','prop','P02')];self.store.save(self.p)
    def tearDown(self):self.temp.cleanup()
    def test_queue_multiple_images_and_freeze_prompts(self):
        first=self.runner.enqueue(self.p['id'],'asset','P01');first['status']='running'
        second=self.runner.enqueue(self.p['id'],'asset','P02')
        self.assertEqual(second['status'],'queued')
        with self.assertRaisesRegex(ValueError,'已经排队'):self.runner.enqueue(self.p['id'],'asset','P01')
        live=self.store.get(self.p['id']);live['assets'][0]['prompt']='修改后的中文提示词';self.store.save(live)
        third=self.runner.enqueue(self.p['id'],'asset','P01')
        self.assertNotEqual(first['snapshot']['assets'][0]['prompt'],third['snapshot']['assets'][0]['prompt'])
        self.assertTrue(self.runner.can_edit(self.p['id'],'asset','P01'))
        self.assertFalse(self.runner.can_edit(self.p['id'],'documents'))
    def test_finished_job_preserves_new_edits_and_other_takes(self):
        j=self.runner.enqueue(self.p['id'],'asset','P01');item=j['snapshot']['assets'][0]
        live=self.store.get(self.p['id']);live['assets'][0].update(prompt='后续修改',versions=[{'id':'newer','prompt':'后续修改'}]);self.store.save(live)
        item['versions'].append({'id':'job-output','prompt':item['prompt']});item['selected']='job-output'
        self.runner.persist_item(j['snapshot'],'assets',item)
        result=self.store.get(self.p['id'])['assets'][0]
        self.assertEqual(result['prompt'],'后续修改');self.assertEqual({v['id'] for v in result['versions']},{'newer','job-output'})
    def test_interrupted_or_flow_blocks_new_jobs(self):
        j=self.runner.enqueue(self.p['id'],'asset','P01');j['status']='interrupted'
        with self.assertRaises(ValueError):self.runner.enqueue(self.p['id'],'asset','P02')
        self.assertFalse(self.runner.can_edit(self.p['id'],'asset','P02'))
    def test_accept_unrelated_asset_while_generating(self):
        self.runner.enqueue(self.p['id'],'asset','P01')
        self.assertTrue(self.runner.can_edit(self.p['id'],'accept','P02'))
        self.assertFalse(self.runner.can_edit(self.p['id'],'accept','P01'))
    def test_restart_reconciles_inflight_before_dispatching_queue(self):
        first=self.runner.enqueue(self.p['id'],'asset','P01');first['status']='running'
        second=self.runner.enqueue(self.p['id'],'asset','P02')
        self.runner.save();restarted=Runner(self.store,start=False)
        self.assertIsNone(restarted.next_queued())
        restarted.control(first['id'],'resume')
        self.assertEqual(restarted.next_queued()['id'],first['id'])
        restarted.jobs[0]['status']='success'
        self.assertEqual(restarted.next_queued()['id'],second['id'])
    def test_pair_keeps_exact_chinese_reference_and_provenance(self):
        docs=[dict(id='r',name='参考.md',role='references',text='## 蓝杯\n蓝色陶瓷杯，灰底，保留杯身文字。'),
              dict(id='s',name='分镜.md',role='storyboard',text='## 分镜 1\n@蓝杯 放在桌上。')]
        source=import_source(docs);lines=source['text'].splitlines();ref=lines.index(docs[0]['text'].splitlines()[1])+1;shot=lines.index('@蓝杯 放在桌上。')+1
        result=dict(sourceSha256=hashlib.sha256(source['text'].encode()).hexdigest(),style='不应追加的风格',assets=[dict(id='P01',name='杯子',kind='prop',description='杯子',generationPrompt='不能覆盖原稿',aliases=['蓝杯'],promptVariants=[dict(label='主参考',role='main',startLine=ref,endLine=ref)])],shots=[dict(number=1,name='镜头',seconds=8,scene='',refs=['P01'],info='',warnings=[],promptStartLine=shot,promptEndLine=shot)])
        p={};apply_parse(p,source,result);a=p['assets'][0]
        self.assertEqual(a['prompt'],'蓝色陶瓷杯，灰底，保留杯身文字。')
        self.assertEqual(a['promptSource']['filename'],'参考.md');self.assertEqual(a['promptSource']['lines'],[2,2])
        self.assertIn('<Picture 1> 放在桌上。',p['shots'][0]['prompt'])
    def test_latest_document_per_role_and_chinese_defaults(self):
        docs=[dict(id=str(i),role=role,name=role,text=str(i)) for i,role in enumerate(['references','storyboard','references'])]
        source=import_source(docs);self.assertEqual({d['id'] for d in source['documents']},{'1','2'})
        self.assertIn('以图 1',make_asset('人','character')['sidePrompt'])

    def test_episode_numbers_restart_and_reference_headings_are_not_shots(self):
        source=import_source([
            dict(id='r',name='参考.md',role='references',text='## 分镜1首帧\n室内全景。'),
            dict(id='s',name='分镜.md',role='storyboard',text='# 第一集\n### 分镜1\n人物进入房间。\n# 第二集\n### 分镜1\n人物离开房间。')])
        lines=source['text'].splitlines()
        rows=[dict(number=1,name='分镜1',seconds=8,scene='',refs=[],info='',warnings=[],promptStartLine=lines.index(t)+1,promptEndLine=lines.index(t)+1) for t in ['人物进入房间。','人物离开房间。']]
        result=dict(sourceSha256=hashlib.sha256(source['text'].encode()).hexdigest(),assets=[],shots=rows)
        p={};apply_parse(p,source,result)
        self.assertEqual([s['id'] for s in p['shots']],['s001','s002'])
        self.assertEqual([s['sourceNumber'] for s in p['shots']],[1,1])
        self.assertEqual([s['section'] for s in p['shots']],['第一集','第二集'])
        self.assertEqual(p['shots'][1]['sourceLocation']['lines'],[6,6])
        result['shots']=rows[:1]
        with self.assertRaisesRegex(ValueError,'覆盖'):apply_parse({},source,result)

if __name__=='__main__':unittest.main()
