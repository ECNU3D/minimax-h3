"""Reference sizing is opt-in, fingerprinted, and does not alter old resumable jobs."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image
from h3_batch import prepare
from h3_flex_config import PROFILE


class ReferenceSizeTests(unittest.TestCase):
    def test_opt_in_contract_and_workflow_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            refs = []
            for i in range(3):
                image = root / f'{i}.png'
                Image.new('RGB', (32, 32)).save(image)
                refs.append(str(image))
            prompt = root / 'prompt.txt'
            prompt.write_text('<Picture 1> <Picture 2> <Picture 3>', encoding='utf-8')
            job = dict(name='s001', prompt=str(prompt), refs=refs, seed=1,
                       seconds=5, width=1344, height=768, profile=PROFILE)
            spec = root / 'spec.json'

            def plan():
                spec.write_text(json.dumps([job]), encoding='utf-8')
                return prepare(spec)[0]

            default = plan()
            job['ref_image_size'] = 'match'
            self.assertEqual(default, plan())
            job['ref_image_size'] = 'max'
            maximum = plan()
            self.assertNotEqual(default['fingerprint'], maximum['fingerprint'])
            inputs = copy.deepcopy(maximum['inputs'])
            self.assertEqual(inputs.pop('ref_image_size'), 'max')
            self.assertEqual(default['inputs'], inputs)
            a, b = copy.deepcopy(default['workflow']), copy.deepcopy(maximum['workflow'])
            self.assertEqual(b['5']['inputs']['ref_image_size'], 'max')
            b['5']['inputs']['ref_image_size'] = 'match'
            for node_id in a:
                if 'filename_prefix' in a[node_id]['inputs']:
                    b[node_id]['inputs']['filename_prefix'] = a[node_id]['inputs']['filename_prefix']
            self.assertEqual(a, b)
            job['ref_image_size'] = 'invalid'
            with self.assertRaises(ValueError):
                plan()


if __name__ == '__main__':
    unittest.main()
