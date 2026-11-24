"""Protect resume behavior from accidentally accepting stale or altered audio."""
import tempfile
import unittest
from pathlib import Path
from audio_common import completed, fingerprint, sha256, write_json

class ResumeTests(unittest.TestCase):
    def test_verified_output_resumes_but_changed_audio_does_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp); audio = folder/'sample.wav'; audio.write_bytes(b'original')
            identity = {'seed':12,'prompt':'birds'}
            write_json(folder/'sample.json',dict(status='success',identity=fingerprint(identity),
                       output=str(audio),sha256=sha256(audio)))
            self.assertTrue(completed(folder,{'id':'sample'},identity))
            audio.write_bytes(b'altered')
            self.assertFalse(completed(folder,{'id':'sample'},identity))
    def test_changed_prompt_requires_new_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            write_json(folder/'sample.json',dict(status='success',identity=fingerprint({'prompt':'wind'})))
            with self.assertRaisesRegex(ValueError,'Changed inputs'):
                completed(folder,{'id':'sample'},{'prompt':'water'})
    def test_missing_record_is_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(completed(Path(tmp),{'id':'new'},{'seed':1}))

if __name__=='__main__': unittest.main()
