import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from h3_director.backend.codex_bridge import codex_executable

class CodexPath(unittest.TestCase):
 def test_path_preferred(self):
  with patch('h3_director.backend.codex_bridge.shutil.which',return_value='configured-codex'):
   self.assertEqual(codex_executable(),'configured-codex')
 def test_desktop_install_without_path(self):
  with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'LOCALAPPDATA':folder}),patch('h3_director.backend.codex_bridge.shutil.which',return_value=None):
   binary=Path(folder)/'OpenAI/Codex/bin/version/codex.exe';binary.parent.mkdir(parents=True);binary.write_bytes(b'fixture')
   self.assertEqual(codex_executable(),str(binary))
 def test_missing_install_reports_error(self):
  with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'LOCALAPPDATA':folder}),patch('h3_director.backend.codex_bridge.shutil.which',return_value=None):
   with self.assertRaisesRegex(RuntimeError,'未找到'):codex_executable()
