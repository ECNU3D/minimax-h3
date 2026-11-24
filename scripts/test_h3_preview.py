"""Preview opt-in isolation, comparison controls, and batch contract checks."""
import hashlib
import json
import unittest

from h3_batch import prepare, ROOT
from h3_preview_config import PROFILES
from generate import graph
from test_h3_768p import ProfileTests


class PreviewTests(unittest.TestCase):
    def test_existing_profiles_keep_identical_graphs(self):
        # Recorded from the pre-preview generator on 2026-10-13.
        snapshots = {
            'legacy-ref2v-4step': 'a9a94a7bce7dac5daa3e24765e2e2b4a6290a96b0de53bab2c96ef51e7442d22',
            'ref2v-768p-8step': '9c4a20540ef97718918574482529e9a1a465d2cd7c4743d1e1c06c52ef862343',
            'ref2v-pdd-8step': 'b3192d82151514247eed516aaa55eff97de339d8627777c7d504ecf29ffd18d9',
        }
        for profile, expected in snapshots.items():
            args = ProfileTests().args(); args.profile = profile
            self.assertEqual(expected, hashlib.sha256(json.dumps(graph(args),sort_keys=True).encode()).hexdigest())

    def test_sparse_pair_changes_only_model_patch(self):
        args = ProfileTests().args(); args.width=960; args.height=544; args.profile=PROFILES[0]
        dense = graph(args)
        args.profile=PROFILES[1]
        sparse = graph(args)
        patch = sparse.pop('34')
        self.assertEqual(patch['inputs']['sink_conditioning'], 'exact_kv_and_rows')
        self.assertEqual(patch['inputs']['selection'], 'sol-attn')
        for key in ('7', '10'):
            self.assertEqual(sparse[key]['inputs']['model'], ['34',0])
            sparse[key]['inputs']['model'] = patch['inputs']['model']
        self.assertEqual(dense, sparse)
        self.assertEqual(dense['10']['inputs']['steps'], 4)
        self.assertEqual(dense['9']['inputs']['sampler_name'], 'euler')
        self.assertEqual(dense['33']['inputs']['shift_video'], 12)

    def test_no_implicit_preview_resolution(self):
        args = ProfileTests().args(); args.profile=PROFILES[0]
        with self.assertRaises(ValueError): graph(args)

    def test_manifest_records_real_parameters_and_changes_fingerprint(self):
        a=prepare(ROOT/'configs/h3-preview-20261013-dense.json')
        b=prepare(ROOT/'configs/h3-preview-20261013-sol.json')
        for left,right in zip(a,b):
            self.assertNotEqual(left['fingerprint'],right['fingerprint'])
            self.assertEqual(left['name'],right['name'])
            self.assertEqual(left['inputs']['prompt'],right['inputs']['prompt'])
            self.assertEqual(left['inputs']['references'],right['inputs']['references'])
            self.assertEqual(right['inputs']['sparse_attention']['selection.tau'],1.3)


if __name__ == '__main__': unittest.main()
