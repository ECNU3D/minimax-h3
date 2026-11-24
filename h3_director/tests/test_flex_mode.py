"""Director selection, frozen jobs and lab controls for the optional Flex mode."""
import copy
from pathlib import Path
import tempfile
import unittest
from h3_director.backend.production import VIDEO_PROFILE,FLEX_PROFILE,FLEX_MODEL,configure,selected_profile
from h3_director.backend.project import Store,read
from h3_director.backend.runner import Runner
from h3_director.backend.lab import plan,effective_settings


class FlexMode(unittest.TestCase):
    def test_default_is_preserved_and_batch_keeps_explicit_flex(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Store(tmp).create('flex test')
            self.assertEqual(selected_profile(p),VIDEO_PROFILE)
            configure(p,dict(videoModel=FLEX_MODEL),'shots')
            self.assertEqual(selected_profile(p),FLEX_PROFILE)
            self.assertEqual(configure(p,{},'shots')['videoModel'],FLEX_MODEL)
            self.assertEqual(selected_profile(Store(tmp).create('new default')),VIDEO_PROFILE)

    def test_lab_preserves_controls_and_saves_actual_flex_graph(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);runner=Runner(Store(tmp),start=False);e=runner.lab.create('flex')
            p=root/'ref.png';Image.new('RGB',(32,32)).save(p)
            runner.lab.copy_reference(e,p,'reference');e.update(prompt='<Picture 1> waves.',videoProfile=FLEX_PROFILE)
            before=copy.deepcopy(e['settings']);result=plan(runner,e,root/'planned')
            self.assertEqual(result['inputs']['profile'],FLEX_PROFILE)
            self.assertEqual(result['workflow']['9']['inputs']['sampler_name'],'lcm')
            self.assertIn('19',result['workflow'])
            self.assertEqual(e['settings'],before)
            self.assertEqual(effective_settings(e)['steps'],6)
            e['videoProfile']=VIDEO_PROFILE
            self.assertEqual(effective_settings(e),before)


if __name__=='__main__':unittest.main()
