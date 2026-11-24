"""Submission boundary checks: no GPU or paid requests."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from generate import ComfyHTTPError
from h3_batch import check_server, execute
from h3_budget import Budget, BudgetStop
from workflow_client import run_job


class SubmissionTests(unittest.TestCase):
    def test_missing_nodes_does_not_charge_or_submit(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            plan=dict(name='s001',inputs={'references':[]},copies=[],workflow={'1':{'class_type':'Missing','inputs':{}}})
            def request(url,route):
                return {'queue_running':[],'queue_pending':[]} if route=='/queue' else {}
            with patch('h3_batch.ROOT',root),patch('h3_batch.request',side_effect=request),patch('h3_batch.run_job') as submit:
                with self.assertRaisesRegex(ValueError,'missing required nodes'):
                    execute([plan],root/'run','unused',1,'campaign')
                submit.assert_not_called()
            self.assertEqual(Budget(root/'runs/h3-budgets/campaign').data['attempts'],{})

    def test_unavailable_model_stops_preflight(self):
        with patch('h3_batch.request',return_value={'UNETLoader':{'input':{'required':{'unet_name':[['available']]}}}}):
            with self.assertRaisesRegex(ValueError,'unavailable model'):
                check_server({'1':{'class_type':'UNETLoader','inputs':{'unet_name':'absent'}}},'unused')

    def test_rejection_is_recorded_and_not_resubmitted(self):
        error=ComfyHTTPError(400,json.dumps({'error':{'type':'missing_node_type'},'node_errors':{}}))
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            plan=dict(name='s001',inputs={'references':[]},copies=[],workflow={})
            with patch('h3_batch.ROOT',root),patch('h3_batch.request',return_value={'queue_running':[],'queue_pending':[]}),patch('workflow_client.request',side_effect=error) as submit:
                with self.assertRaises(ComfyHTTPError):execute([plan],root/'run','unused',1,'campaign')
                self.assertEqual(submit.call_count,1)
                receipt=json.loads((root/'run/s001/submission.json').read_text())
                self.assertEqual(receipt['status'],'rejected')
                with self.assertRaisesRegex(RuntimeError,'Previous submission'):
                    run_job({},root/'run/s001')
                self.assertEqual(submit.call_count,1)
            b=Budget(root/'runs/h3-budgets/campaign')
            self.assertEqual(list(b.data['outcomes'].values()),['rejected'])
            self.assertFalse(b.stop_path.exists())
            self.assertEqual(len(b.data['attempts']['s001']),1)

    def test_transport_ambiguity_still_latches_stop_with_cause(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            plan=dict(name='s001',inputs={'references':[]},copies=[],workflow={})
            with patch('h3_batch.ROOT',root),patch('h3_batch.request',return_value={'queue_running':[],'queue_pending':[]}),patch('workflow_client.request',side_effect=ConnectionResetError('connection reset')) as submit:
                with self.assertRaisesRegex(BudgetStop,'connection reset'):
                    execute([plan],root/'run','unused',1,'campaign')
                with self.assertRaises(BudgetStop):execute([plan],root/'another','unused',1,'campaign')
                self.assertEqual(submit.call_count,1)

    def test_http_500_is_not_definitive_rejection(self):
        self.assertFalse(ComfyHTTPError(500,'{"error":{},"node_errors":{}}').submission_rejected)
        self.assertFalse(ComfyHTTPError(400,'proxy error').submission_rejected)


if __name__=='__main__':unittest.main()
