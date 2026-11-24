import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from h3_director.backend.handoff import collect_context, export_paths, folder_name, delivery_contract
from h3_director.backend.project import Store, digest, read
from h3_director.backend.runner import Runner


class AudioHandoffTests(unittest.TestCase):
    def test_named_export_paths_are_safe_unique_and_resumable(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p={'id':'project-id','name':'预制爱 / 先导:120s'}
            first={'id':'hash-one','created':1789992893};second={'id':'hash-two','created':1789992893}
            a=export_paths(root/'exports',p,first,root);b=export_paths(root/'exports',p,second,root)
            self.assertNotEqual(a['folder'],b['folder'])
            self.assertEqual(export_paths(root/'exports',p,first,root),a)
            self.assertIn('预制爱 - 先导-120s',a['folder']);self.assertNotIn(first['id'],a['folder'])
            for key in ('folder','archive','deliveryRoot'):Path(a[key]).relative_to(root)
            self.assertEqual(Path(b['folder']).name,Path(a['folder']).name+'-2')
            self.assertTrue(Path(a['archive']).name.startswith('预制爱 - 先导-120s-剪辑素材包-'))
            self.assertEqual(folder_name('CON.txt'),'项目-CON.txt')
            self.assertEqual(folder_name('..'),'未命名项目')
            self.assertNotIn('/',folder_name('../../escape'))
            self.assertLessEqual(len(folder_name('中'*100)),48)

    def test_legacy_package_id_never_becomes_delivery_folder(self):
        with tempfile.TemporaryDirectory() as td:
            contract=delivery_contract(Path(td)/'afcb7d71d9ff',{'name':'仿真父母'},Path(td))
            self.assertNotIn('afcb7d71d9ff',contract['root'])
            self.assertEqual(Path(contract['root']).parent,Path(td)/'成片/仿真父母')
            self.assertFalse(contract['overwriteExisting'])

    def test_context_requires_exact_source_version_and_preserves_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); folder = root/'export'; folder.mkdir()
            for version, text in [('v3', '旧版台词'), ('v4', '当前台词')]:
                parent = root/'原创项目/测试'/version; parent.mkdir(parents=True)
                (parent/'03-分镜.md').write_text(text, encoding='utf-8')
                (parent/'04-装配规范.md').write_text(version+'\n完整台词。', encoding='utf-8')
                (parent/'05-字幕.srt').write_text('1\n00:00:01,000 --> 00:00:02,000\n原文', encoding='utf-8')
                (parent/'01-old-api.py').write_text('do not bundle', encoding='utf-8')
                (parent/'.env').write_text('do not bundle', encoding='utf-8')
            rows, warnings = collect_context([{'name':'03-分镜.md','text':'当前台词'}], folder, root)
            self.assertEqual(len(rows), 2); self.assertFalse(warnings)
            for row in rows:
                self.assertEqual((folder/row['file']).read_bytes(), Path(row['source']).read_bytes())
                self.assertIn('v4', row['source'])
                self.assertEqual(digest(folder/row['file']), row['sha256'])

    def test_ambiguous_context_not_guessed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name in ['v3','v4']:
                folder = root/'原创项目'/name; folder.mkdir(parents=True)
                (folder/'分镜.md').write_text('相同原文', encoding='utf-8')
            rows, warnings = collect_context([{'name':'分镜.md','text':'相同原文'}], root/'export', root)
            self.assertFalse(rows); self.assertEqual(len(warnings), 1)

    def test_export_audio_contract_zip_and_originals_are_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            store = Store(td); runner = Runner(store, start=False); p = store.create('声音交接')
            source = Path(td)/'original.mp4'; source.write_bytes(b'preserve original media')
            version = dict(id='v1',files=[dict(path=str(source),sha256=digest(source))],prompt='采用的生成提示词',review=None)
            p['shots'] = [dict(id='s001', name='镜头', info='信息', seconds=5, selected='v1', versions=[version], originalPrompt='逐字原文')]
            p['sources'] = [dict(name='未存于素材库.md',text='必须听见的台词。\r\n逐字保留。\n',role='storyboard')]
            store.save(p); before = copy.deepcopy(p)
            job = runner.enqueue(p['id'], 'export'); runner.execute(job)
            after = store.get(p['id']); export = after['exports'][-1]
            self.assertEqual(after['shots'], before['shots']); self.assertEqual(after['sources'], before['sources'])
            self.assertEqual(source.read_bytes(), b'preserve original media')
            with zipfile.ZipFile(export['path']) as z:
                self.assertIsNone(z.testzip())
                m = json.loads(z.read('edit-manifest.json'))
                self.assertEqual(m['delivery'],export['delivery'])
                self.assertIn('成片',m['delivery']['root']);self.assertIn('声音交接',m['delivery']['root'])
                self.assertNotIn(job['id'],export['folder']);self.assertNotIn(job['id'],m['delivery']['root'])
                self.assertEqual(Path(m['delivery']['finalVideo']).parent.name,'视频')
                brief=z.read('TRAE-剪辑任务.md').decode('utf-8')
                self.assertIn(m['delivery']['root'],brief);self.assertIn('v002',brief)
                self.assertTrue(m['audioProduction']['localOnly'])
                self.assertEqual(m['audioProduction']['requiredTracks'], ['dialogue','sfx','music'])
                self.assertEqual(m['audioProduction']['generationStages'], ['design','clone','sfx','music'])
                self.assertEqual(m['audioReview'], 'pending')
                self.assertEqual(m['shots'][0]['originalPrompt'], '逐字原文')
                self.assertEqual(z.read('media/s001.mp4'), source.read_bytes())
                self.assertEqual(z.read('source-1.md'), before['sources'][0]['text'].encode('utf-8'))
                template = json.loads(z.read('audio-config.template.json'))
                self.assertEqual(template['source_video_sha256'], digest(source))
                for stage in ['design','clone','sfx','music']:
                    self.assertEqual(template[stage]['jobs'], [])
                self.assertEqual(template['design']['text'], '')
                for artifact in m['workflow'] + m['sources']:
                    self.assertEqual(digest(Path(export['folder'])/artifact['file']), artifact['sha256'])
                    self.assertIn(artifact['file'], z.namelist())
                self.assertFalse(any('.env' in name for name in z.namelist()))


if __name__ == '__main__': unittest.main()
