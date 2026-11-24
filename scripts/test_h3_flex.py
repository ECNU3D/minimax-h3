"""Flex opt-in isolation and a genuinely paired comparison contract."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from h3_batch import prepare
from h3_flex_config import PROFILE, LORA, SIGMAS
from test_h3_768p import ProfileTests
from generate import graph


class FlexTests(unittest.TestCase):
    def test_pair_changes_only_adapter_sampler_schedule_and_extra_audio_export(self):
        args=ProfileTests().args();args.profile='ref2v-768p-8step'
        baseline=graph(args)
        args.profile=PROFILE;args.comfy_audio_references=[]
        flex=graph(args)
        self.assertEqual(flex['9']['inputs']['sampler_name'],'lcm')
        self.assertEqual(flex['10'],dict(class_type='ManualSigmas',inputs=dict(sigmas=SIGMAS)))
        self.assertEqual(flex['6']['inputs']['lora_name'],LORA)
        self.assertEqual(len([n for n in flex.values() if n['class_type']=='LoraLoaderModelOnly']),1)
        self.assertEqual(len(SIGMAS.split(','))-1,6)
        flex.pop('19')
        for key in ('6','9','10'):flex[key]=copy.deepcopy(baseline[key])
        self.assertEqual(flex,baseline)

    def test_batch_records_adapter_and_actual_settings_and_same_shot_name(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);refs=[]
            for i in range(3):
                p=root/f'{i}.png';Image.new('RGB',(32,32)).save(p);refs.append(str(p))
            prompt=root/'prompt.txt';prompt.write_text('<Picture 1> <Picture 2> <Picture 3> walks.',encoding='utf-8')
            job=dict(name='same_shot',prompt=str(prompt),refs=refs,seed=1,seconds=5,width=1344,height=768,profile='ref2v-768p-8step')
            spec=root/'spec.json';spec.write_text(json.dumps([job]),encoding='utf-8');a=prepare(spec)[0]
            job['profile']=PROFILE;spec.write_text(json.dumps([job]),encoding='utf-8');b=prepare(spec)[0]
            for k in ('name','prompt','references','seed','seconds','width','height'):self.assertEqual(a['inputs'][k],b['inputs'][k])
            self.assertNotEqual(a['fingerprint'],b['fingerprint'])
            self.assertEqual(b['inputs']['steps'],6)
            self.assertEqual(b['inputs']['scheduler'],'ManualSigmas')
            self.assertIn('h3-flex-models-manifest.json',b['inputs']['model_manifests'])

    def test_invalid_input_fails_before_gpu_submission(self):
        args=ProfileTests().args();args.profile=PROFILE;args.width=960
        with self.assertRaises(ValueError):graph(args)
        args.width=1344;args.base=True
        with self.assertRaises(ValueError):graph(args)


if __name__=='__main__':unittest.main()
