"""Phase 12: the run manifest records what the committed results were produced from."""

import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import make_manifest  # noqa: E402

MANIFEST_PATH = ROOT / make_manifest.OUT


class ManifestTests(unittest.TestCase):
    def test_text_hash_ignores_line_endings(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            lf, crlf = Path(tmp) / "lf.txt", Path(tmp) / "crlf.txt"
            lf.write_bytes(b"a\nb\n")
            crlf.write_bytes(b"a\r\nb\r\n")
            self.assertEqual(make_manifest.text_sha256(lf), make_manifest.text_sha256(crlf))

    def test_locked_hashes_match_the_lock_document(self):
        built = make_manifest.build(with_checkpoints=False)
        self.assertEqual(len(built["locked_test_files"]), 5)
        for path, digest in built["locked_test_files"].items():
            self.assertEqual(built["inputs"][path], digest, path)

    def test_sources_and_seeds_are_recorded(self):
        built = make_manifest.build(with_checkpoints=False)
        self.assertEqual(set(built["sources"]), {"data/raw/archive_3.zip", "data/raw/archive_4.zip"})
        self.assertEqual(built["seeds"]["distilbert_training"], [13, 42, 7])
        self.assertEqual(built["seeds"]["phase11_transformer_seeds"], [13, 42, 7])
        self.assertTrue(all(len(v) == 40 for v in
                            (built["models"]["distilbert_base"]["revision"], built["models"]["minilm"]["revision"])))

    def test_latency_files_are_left_out(self):
        built = make_manifest.build(with_checkpoints=False)
        self.assertFalse([p for p in built["results"] if "latency" in p])

    @unittest.skipUnless(MANIFEST_PATH.is_file(), "results/run_manifest.json not written yet")
    def test_committed_manifest_matches_the_repository(self):
        committed = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        built = make_manifest.build(with_checkpoints=False)
        for section in ("environment", "seeds", "sources", "locked_test_files", "inputs", "results"):
            self.assertEqual(built[section], committed[section], section)
        self.assertEqual(len(committed["models"]["distilbert_checkpoints"]["sha256"]), 6)

    @unittest.skipUnless(MANIFEST_PATH.is_file(), "results/run_manifest.json not written yet")
    def test_checkpoints_match_when_present(self):
        committed = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["models"]["distilbert_checkpoints"]["sha256"]
        nlu = json.loads((ROOT / "configs" / "nlu_transformer.json").read_text(encoding="utf-8"))
        for key, digest in committed.items():
            seed, task = key.removeprefix("seed").split("/")
            path = ROOT / nlu["checkpoints"].format(seed=seed, task=task) / "model.safetensors"
            if not path.exists():
                self.skipTest("checkpoints are not on this machine")
            h = hashlib.sha256()
            with path.open("rb") as f:
                for block in iter(lambda: f.read(1 << 20), b""):
                    h.update(block)
            self.assertEqual(h.hexdigest(), digest, key)


if __name__ == "__main__":
    unittest.main()
