"""Offline checks for the dedicated profile and legacy compatibility."""
import unittest
from types import SimpleNamespace
from generate import graph


class ProfileTests(unittest.TestCase):
    def args(self):
        return SimpleNamespace(prompt_file=None, seconds=5, references=['ref.png'],
            comfy_references=['ref.png'], width=1344, height=768, int8=True,
            image=None, base=False, memory_efficient_sage=True, head_chunks=4,
            ffn_chunks=8, seed=1, steps=4, crop_720p=False, crop_1080p=False, name='test')

    def test_legacy_graph_unchanged_when_profile_omitted(self):
        args = self.args()
        before = graph(args)
        args.profile = 'legacy-ref2v-4step'
        self.assertEqual(before, graph(args))
        self.assertEqual(before['10']['inputs']['steps'], 4)

    def test_native_profile_conditioning_and_diagnostic_wiring(self):
        args = self.args(); args.profile = 'ref2v-768p-8step'
        g = graph(args)
        self.assertEqual(g['10']['inputs']['steps'], 8)
        self.assertEqual(g['9']['inputs']['sampler_name'], 'euler')
        self.assertIn('768p', g['6']['inputs']['lora_name'])
        self.assertEqual(g['33']['inputs']['shift_video'], 12.0)
        self.assertEqual(g['33']['inputs']['shift_audio'], 3.0)
        self.assertEqual(g['5']['inputs']['vae'], g['12']['inputs']['vae'])
        self.assertEqual(g['7']['inputs']['model'], g['10']['inputs']['model'])
        selected = [n['inputs'] for n in g.values() if n['class_type']=='ImageFromBatch']
        self.assertEqual([x['batch_index'] for x in selected], [0,24,48,72,96,123])
        self.assertTrue(all(x['image']==['12',0] for x in selected))
        args.width = 1920
        with self.assertRaises(ValueError): graph(args)

    def test_pdd_uses_one_distill_and_preserves_baseline_recipe(self):
        args = self.args(); args.profile = 'ref2v-768p-8step'
        baseline = graph(args)
        args.profile = 'ref2v-pdd-8step'
        candidate = graph(args)
        loras = [n for n in candidate.values() if n['class_type']=='LoraLoaderModelOnly']
        self.assertEqual(len(loras), 1)
        self.assertEqual(loras[0]['inputs']['lora_name'], 'MiniMax-H3-Ref2VA-Acc-8Step_pruned_comfy.safetensors')
        candidate['6']['inputs']['lora_name'] = baseline['6']['inputs']['lora_name']
        self.assertEqual(candidate, baseline)


if __name__ == '__main__': unittest.main()
