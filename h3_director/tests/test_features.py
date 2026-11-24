import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from h3_director.backend.assets import references,settings
from h3_director.backend.codex_bridge import normalize_usage,generate
from h3_director.backend.importer import apply_parse
from h3_director.backend.project import make_asset,write,read,digest,current
from h3_director.backend.project import Store
from h3_director.backend.runner import Runner

class Features(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.folder=Path(self.temp.name)
        self.a=make_asset('杯子','prop','P01'); self.p={'assets':[self.a]}
        file=self.folder/'input.png'; file.write_bytes(b'image-content')
        self.a['inputs']=[dict(id='i1',path=str(file),sha256=digest(file))]
    def tearDown(self): self.temp.cleanup()
    def test_reference_order_and_hash(self):
        self.a.update(imageMode='reference',generationRefs=['input:P01:i1'])
        self.assertEqual(references(self.p,self.a)[0]['key'],'input:P01:i1')
        Path(self.a['inputs'][0]['path']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'修改'): references(self.p,self.a)
    def test_text_ignores_saved_reference_selection(self):
        self.a['generationRefs']=['not-a-path']; self.assertEqual(references(self.p,self.a),[])
    def test_no_arbitrary_paths_or_missing_inputs(self):
        self.a.update(imageMode='reference',generationRefs=['C:/private.png'])
        with self.assertRaises(ValueError):references(self.p,self.a)
        self.a['generationRefs']=[]
        with self.assertRaises(ValueError):references(self.p,self.a)
    def test_provider_change_invalidates_take(self):
        v=dict(id='v',prompt=self.a['prompt'],seed=self.a['seed'],generation=settings(self.a))
        self.a.update(versions=[v],selected='v')
        self.assertTrue(current(self.p,'assets',self.a))
        self.a['provider']='codex';self.assertFalse(current(self.p,'assets',self.a))
    def test_usage_unknown_is_not_zero(self):
        u=normalize_usage({'rateLimits':{'primary':{'usedPercent':23,'windowDurationMins':10080},'secondary':None}})
        self.assertEqual(u['buckets'][0]['windows'][0]['remainingPercent'],77)
        self.assertIsNone(u['imageQuota']);self.assertEqual(len(u['buckets'][0]['windows']),1)
        u=normalize_usage({'rateLimits':{'primary':{}}});self.assertEqual(u['buckets'][0]['windows'],[])
    def test_codex_uncertain_never_resubmits(self):
        write(self.folder/'codex-image.json',{'status':'submitted','turnId':'existing','prompt':'prompt','references':[]})
        with patch('h3_director.backend.codex_bridge.Client') as client:
            with self.assertRaisesRegex(RuntimeError,'不会自动重复'):generate('prompt',[],self.folder)
            client.assert_not_called()
    def fixture(self):
        text='【分镜 1 / 1】建议时长：8秒\n\n@杯子 放在桌上。'
        return {'id':'src','text':text},{'style':'插画','sourceSha256':hashlib.sha256(text.encode()).hexdigest(),
            'assets':[dict(id='P01',name='杯子',kind='prop',description='蓝色陶瓷杯')],
            'shots':[dict(number=1,name='杯子',seconds=8,scene='桌面',refs=['P01'],info='',promptStartLine=3,promptEndLine=3,warnings=[])]}
    def test_plain_markdown_exact_source_and_coverage(self):
        source,result=self.fixture();p={};apply_parse(p,source,result)
        self.assertEqual(p['shots'][0]['originalPrompt'],'@杯子 放在桌上。')
        self.assertIn('<Picture 1> 放在桌上。',p['shots'][0]['prompt'])
        self.assertTrue(p['importReport']['coverageChecked'])
    def test_reject_omission_without_mutating_project(self):
        source,result=self.fixture(); result['shots']=[];p={'assets':['keep']}
        with self.assertRaisesRegex(ValueError,'覆盖'):apply_parse(p,source,result)
        self.assertEqual(p['assets'],['keep'])
    def test_reject_ranges_and_source_changes(self):
        source,result=self.fixture();result['shots'][0]['promptEndLine']=99
        with self.assertRaisesRegex(ValueError,'越界'):apply_parse({},source,result)
        source['text']+='changed'
        with self.assertRaisesRegex(ValueError,'哈希'):apply_parse({},source,result)
    def test_reject_missing_reference(self):
        source,result=self.fixture();result['shots'][0]['refs']=['C99']
        with self.assertRaisesRegex(ValueError,'未定义'):apply_parse({},source,result)
    def test_semantic_audit_blocks_overwrite(self):
        source,result=self.fixture();result['audit']={'verdict':'needs_review','issues':['漏台词']}
        with self.assertRaisesRegex(ValueError,'漏台词'):apply_parse({},source,result)
    def test_raw_script_preserves_source_and_agent_prompt(self):
        source,result=self.fixture();source['text']='她轻轻放下蓝杯。'
        result.update(sourceType='script',sourceSha256=hashlib.sha256(source['text'].encode()).hexdigest(),audit={'verdict':'pass','issues':[]})
        result['shots'][0].update(promptStartLine=1,promptEndLine=1,generationPrompt='固定近景，@杯子 轻轻放到桌上。')
        p={};apply_parse(p,source,result)
        self.assertEqual(p['shots'][0]['originalPrompt'],source['text'])
        self.assertIn('固定近景，<Picture 1>',p['shots'][0]['prompt'])
        self.assertFalse(p['importReport']['coverageChecked'])
    def test_parser_job_reuses_completed_agent_output_on_recovery(self):
        source,result=self.fixture(); result['thinking']='max'; st=Store(self.folder/'store');p=st.create('test',source['text'],'source.md')
        for asset in result['assets']:asset['referenceAssetIds']=[]
        runner=Runner(st,start=False);j=runner.enqueue(p['id'],'parse',p['sources'][0]['id'],False)
        write(st.folder/'runs'/j['id']/'parse-output.json',result)
        with patch.object(runner,'command') as command:runner.execute(j);command.assert_not_called()
        self.assertEqual(st.get(p['id'])['shots'][0]['originalPrompt'],'@杯子 放在桌上。')

    def test_parser_reparses_legacy_output_without_reference_dependencies(self):
        source,result=self.fixture();result['thinking']='max';st=Store(self.folder/'store');p=st.create('test',source['text'],'source.md')
        runner=Runner(st,start=False);j=runner.enqueue(p['id'],'parse',None,False)
        folder=st.folder/'runs'/j['id'];write(folder/'parse-output.json',result)
        def fresh_parse(*args):
            self.assertNotIn('repairCandidate',read(folder/'parse-input.json'))
            for asset in result['assets']:asset['referenceAssetIds']=[]
            write(folder/'parse-output.json',result)
        with patch.object(runner,'command',side_effect=fresh_parse) as command:
            runner.execute(j);command.assert_called_once()

if __name__=='__main__':unittest.main()
