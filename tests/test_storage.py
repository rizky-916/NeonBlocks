import json
import tempfile
import unittest
from pathlib import Path

from neonblocks.storage import MAX_FILE_BYTES, MAX_SCORE, HighScoreStore


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "data"
        self.store = HighScoreStore(self.dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_file_is_zero(self):
        self.assertEqual(self.store.load(), 0)

    def test_round_trip(self):
        self.assertTrue(self.store.save(1234))
        self.assertEqual(self.store.load(), 1234)
        # no temp files left behind
        self.assertEqual([p.name for p in self.dir.iterdir()], ["highscore.json"])

    def _write(self, text):
        self.dir.mkdir(parents=True, exist_ok=True)
        self.store.path.write_text(text, encoding="utf-8")

    def test_invalid_content_is_ignored(self):
        for bad in ("not json", "[]", '{"highscore": "999"}', '{"highscore": true}',
                    '{"highscore": -5}', json.dumps({"highscore": MAX_SCORE + 1}),
                    '{"highscore": 1.5}', "{}"):
            with self.subTest(bad=bad):
                self._write(bad)
                self.assertEqual(self.store.load(), 0)

    def test_oversized_file_is_ignored(self):
        self._write('{"highscore": 5}' + " " * MAX_FILE_BYTES)
        self.assertEqual(self.store.load(), 0)

    def test_rejects_non_int(self):
        self.assertFalse(self.store.save("100"))
        self.assertFalse(self.store.save(True))


if __name__ == "__main__":
    unittest.main()
