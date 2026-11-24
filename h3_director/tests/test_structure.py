"""Protect launch and path contracts when reorganizing source folders."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.paths import ROOT,APP,DATA,PYTHON,HARNESS

class StructureTests(unittest.TestCase):
    def test_existing_data_and_production_paths_are_preserved(self):
        self.assertEqual(DATA,ROOT/'h3_director/data')
        self.assertTrue((ROOT/'scripts/h3_batch.py').is_file())
        self.assertEqual(PYTHON,ROOT/'.venv-cu130/Scripts/python.exe')
        self.assertTrue(HARNESS.is_file())
    def test_launcher_from_an_unrelated_working_directory(self):
        with tempfile.TemporaryDirectory() as td:
            result=subprocess.run([sys.executable,str(APP/'server.py'),'--help'],cwd=td,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('--data',result.stdout)
    def test_sdk_resolves_from_agent_directory(self):
        result=subprocess.run(['node','--input-type=module','-e',
            "import {Codex} from '@openai/codex-sdk'; console.log(typeof Codex)"],
            cwd=HARNESS.parent,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),'function')

if __name__=='__main__':unittest.main()
