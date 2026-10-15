import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from core import compress_to_pjs, decompress_pjs, PJSAuthenticationError, PJSFormatError

PASSWORD = "correct horse battery staple 2026"

class PJS4Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_file_round_trip(self):
        source = self.root / "sample.txt"
        source.write_text("PJS4 test\n" * 500, encoding="utf-8")
        encrypted = self.root / "sample.pjs"
        out = self.root / "out"
        compress_to_pjs(source, encrypted, PASSWORD)
        decompress_pjs(encrypted, out, PASSWORD)
        self.assertEqual((out / "sample.txt").read_bytes(), source.read_bytes())

    def test_folder_round_trip(self):
        folder = self.root / "folder"
        (folder / "nested").mkdir(parents=True)
        (folder / "nested" / "data.bin").write_bytes(os.urandom(20000))
        (folder / "empty").mkdir()
        encrypted = self.root / "folder.pjs"
        out = self.root / "out"
        compress_to_pjs(folder, encrypted, PASSWORD)
        decompress_pjs(encrypted, out, PASSWORD)
        self.assertEqual((out / "folder" / "nested" / "data.bin").read_bytes(), (folder / "nested" / "data.bin").read_bytes())
        self.assertTrue((out / "folder" / "empty").is_dir())

    def test_wrong_password_fails(self):
        source = self.root / "sample.txt"
        source.write_text("secret", encoding="utf-8")
        encrypted = self.root / "sample.pjs"
        compress_to_pjs(source, encrypted, PASSWORD)
        with self.assertRaises(PJSAuthenticationError):
            decompress_pjs(encrypted, self.root / "out", "wrong password 123")

    def test_tamper_fails(self):
        source = self.root / "sample.txt"
        source.write_text("secret", encoding="utf-8")
        encrypted = self.root / "sample.pjs"
        compress_to_pjs(source, encrypted, PASSWORD)
        blob = bytearray(encrypted.read_bytes())
        blob[-1] ^= 0x01
        encrypted.write_bytes(blob)
        with self.assertRaises(PJSAuthenticationError):
            decompress_pjs(encrypted, self.root / "out", PASSWORD)

    def test_short_password_rejected(self):
        source = self.root / "sample.txt"
        source.write_text("x", encoding="utf-8")
        with self.assertRaises(ValueError):
            compress_to_pjs(source, self.root / "sample.pjs", "short")

if __name__ == "__main__":
    unittest.main()
