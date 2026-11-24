from pathlib import Path
import sys
import unittest
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from h3_director.backend.agent import provider,runtime

class AgentProvider(unittest.TestCase):
    def test_legacy_default(self):
        self.assertEqual(provider({}),'deepseek')
        self.assertEqual(runtime({}),{'agentProvider':'deepseek'})
        with self.assertRaises(ValueError):provider({'agentProvider':'other'})
    def test_sol_high_default_and_cleanup(self):
        client=MagicMock();client.request.side_effect=[{'account':{'type':'chatgpt'}},{'data':[{'model':'gpt-5.6-sol','supportedReasoningEfforts':[{'reasoningEffort':'high'}]}]}]
        with patch('h3_director.backend.codex_bridge.Client',return_value=client):
            self.assertEqual(runtime({'agentProvider':'codex'}),dict(agentProvider='codex',agentModel='gpt-5.6-sol',agentThinking='high'))
        client.close.assert_called_once()
    def test_model_specific_effort_validation(self):
        with patch('h3_director.backend.agent.catalog',return_value=[dict(id='chosen',thinking=['low','high'])]):
            self.assertEqual(runtime(dict(agentProvider='codex',agentModel='chosen',agentThinking='low'))['agentThinking'],'low')
            with self.assertRaisesRegex(ValueError,'Thinking'):runtime(dict(agentProvider='codex',agentModel='chosen',agentThinking='ultra'))
            with self.assertRaisesRegex(ValueError,'不支持所选模型'):runtime(dict(agentProvider='codex',agentModel='missing'))
    def test_api_key_account_is_rejected_without_fallback(self):
        client=MagicMock();client.request.return_value={'account':{'type':'apiKey'}}
        with patch('h3_director.backend.codex_bridge.Client',return_value=client):
            with self.assertRaisesRegex(ValueError,'登录 ChatGPT'):runtime({'agentProvider':'codex'})
        client.close.assert_called_once()
