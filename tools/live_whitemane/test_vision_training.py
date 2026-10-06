"""Offline admission, leakage, token preservation, and frozen-head correctness."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from . import vision_dataset as dataset
from . import vision_train as trainer

CONFIG = Path(__file__).resolve().parents[2] / 'experiments/configs/client_harness/vision_task_head_sft_v1.json'


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.data = dataset.generate(json.loads(CONFIG.read_text()))

    def test_group_holdouts_and_every_task_action_covered(self):
        self.assertTrue(dataset.validate_splits(self.data['splits']))
        actions = [set(self.data['audit']['by_task_action'][split])
                   for split in ('train', 'validation', 'test')]
        self.assertEqual(actions[0], actions[1]); self.assertEqual(actions[1], actions[2])
        self.assertEqual(len(actions[0]), 33)
        self.assertEqual(self.data['audit']['verified_visual_examples'], 0)

    def test_synthetic_never_gets_unrelated_pixels(self):
        splits = copy.deepcopy(self.data['splits'])
        splits['train'][0]['state']['image'] = '/tmp/unrelated.png'
        with self.assertRaisesRegex(ValueError, 'pixels'):
            dataset.validate_splits(splits)

    def test_duplicate_and_group_leak_are_rejected(self):
        splits = copy.deepcopy(self.data['splits'])
        splits['test'].append(splits['train'][0])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            dataset.validate_splits(splits)
        splits = copy.deepcopy(self.data['splits'])
        splits['test'][0]['group_id'] = splits['train'][0]['group_id']
        with self.assertRaisesRegex(ValueError, 'crosses split'):
            dataset.validate_splits(splits)

    def test_valid_visual_sft_is_still_not_rlvr(self):
        row = self.visual_row()
        self.assertEqual(dataset.admit_visual(row), {'admitted': True, 'failures': [], 'rlvr_eligible': False})

    def test_unknown_assistance_stale_and_post_action_inputs_rejected(self):
        for mutate, failure in ((lambda r: r.pop('assistance'), 'assistance_unknown_or_present'),
            (lambda r: r['frame'].update(timestamp=8.), 'stale_or_post_action_input'),
            (lambda r: r.update(action_timestamp=9.), 'stale_or_post_action_input'),
            (lambda r: r['frame'].update(runtime_identity='another-client'), 'runtime_identity_mismatch'),
            (lambda r: r['outcome'].update(independently_verified=False), 'no_independent_outcome')):
            row = self.visual_row(); mutate(row)
            admission = dataset.admit_visual(row)
            self.assertFalse(admission['admitted']); self.assertIn(failure, admission['failures'])

    def test_benchmark_and_synthetic_are_not_visual_labels(self):
        for kind in ('synthetic_text_only', 'benchmark_capture'):
            row = self.visual_row(); row['source_kind'] = kind
            self.assertFalse(dataset.admit_visual(row)['admitted'])

    @staticmethod
    def visual_row():
        return {'source_kind': 'verified_real_visual', 'frame': {'sha256': 'a' * 64,
            'immutable_member': 'closed/frame.png', 'runtime_identity': 'owned-client', 'timestamp': 10.},
            'observation': {'runtime_identity': 'owned-client', 'timestamp': 10.1},
            'action_timestamp': 10.2, 'assistance': {'ledger_complete': True, 'manual_interventions': 0},
            'outcome': {'independently_verified': True, 'immutable_member': 'closed/after.json'},
            'label': 'survey', 'question': {'criteria': {'survey': 'Survey', 'observe': 'Wait'}},
            'group_id': 'site/episode/client', 'input_contains_after_action_facts': False}


class HeadTests(unittest.TestCase):
    def test_sdk_head_gradients_and_encoder_freeze(self):
        import torch
        from laya.vlm import VLMDecisionModel
        torch.set_num_threads(2)
        class TinyBackbone(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.config = SimpleNamespace(text_config=SimpleNamespace(hidden_size=64))
                self.vision_model = torch.nn.Identity()
                self.embedding = torch.nn.Embedding(50, 64)
        model = VLMDecisionModel(TinyBackbone(), head_layers=1)
        trainer.freeze_head(model)
        encoder_before = {key: value.clone() for key, value in model.encoder.state_dict().items()}
        scorer_before = model.scorer[-1].weight.detach().clone()
        model.train(); model.encoder.eval()
        rows = [{'feature': torch.randn(12, 64).half(), 'item': {'ids': list(range(12)),
            'markers': [5, 11], 'option_span': (4, 12), 'qtype': 0, 'label': i,
            'pixel_values': None, 'pixel_attention_mask': None, 'n_images': 0}} for i in (0, 1)]
        optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=.001)
        logits, labels = trainer.readout(model, rows, 0)
        loss = torch.nn.functional.cross_entropy(logits, labels)
        self.assertTrue(torch.isfinite(loss))
        loss.backward(); optimizer.step()
        self.assertFalse(torch.equal(scorer_before, model.scorer[-1].weight))
        self.assertTrue(all(torch.equal(value, model.encoder.state_dict()[key])
                            for key, value in encoder_before.items()))
        self.assertTrue(all(p.grad is None for p in model.encoder.parameters()))
        self.assertTrue(all(p.grad is None for p in model.act_head.parameters()))

    def test_pinned_processor_preserves_full_state_and_option_permutation(self):
        from transformers import AutoProcessor
        from laya.preprocess import ImagePrep
        from laya.vlm import VLMAgent
        from huggingface_hub import snapshot_download
        folder = Path(snapshot_download(trainer.MODEL, revision=trainer.REVISION, local_files_only=True))
        cfg = json.loads((folder / 'vlm_agent_config.json').read_text())
        agent = object.__new__(VLMAgent)
        agent.processor = AutoProcessor.from_pretrained(folder / 'processor', local_files_only=True)
        agent.prep = ImagePrep.from_config(cfg, default_backend='processor'); agent.prep.apply(agent.processor)
        agent.processor.laya_readout = cfg['readout']
        agent.cfg = {**cfg, 'max_len': 4096, 'head_max_len': 1536}
        row = dataset.generate(json.loads(CONFIG.read_text()))['splits']['test'][0]
        item, normal = trainer.encode(agent, row)
        reversed_item, reverse = trainer.encode(agent, row, list(reversed(range(len(normal['options'])))))
        self.assertEqual(normal['options'][item['label']], row['label'])
        self.assertEqual(reverse['options'][reversed_item['label']], row['label'])
        self.assertEqual(reverse['options'], normal['options'][::-1])
        self.assertEqual(item['n_images'], 0)
        row['state']['must_not_omit'] = 'complete state ' * 5000
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            trainer.encode(agent, row)


if __name__ == '__main__':
    unittest.main()
