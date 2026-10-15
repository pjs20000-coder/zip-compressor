import os, tempfile, unittest, zipfile, struct, zlib
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core

class CoreTests(unittest.TestCase):
    def test_codec_roundtrip(self):
        for data in (b'', b'abc', b'A'*10000, bytes(range(256))*40, '한글 파일명 테스트'.encode()*100):
            packed=core.pjs_compress(data,123)
            self.assertEqual(core.pjs_decompress(packed,len(data)),data)
    def test_pjs_file_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); src=base/'입력 폴더'; src.mkdir(); (src/'한글.txt').write_text('압축 테스트\n'*100,encoding='utf-8')
            (src/'empty.bin').write_bytes(b''); (src/'sub').mkdir(); (src/'sub'/'data.bin').write_bytes(bytes(range(256))*10)
            archive=base/'test.pjs'; out=base/'out'
            core.create_pjs(src,archive); core.extract_pjs(archive,out)
            self.assertEqual((out/src.name/'한글.txt').read_bytes(),(src/'한글.txt').read_bytes())
            self.assertEqual((out/src.name/'empty.bin').read_bytes(),b'')
            self.assertEqual((out/src.name/'sub'/'data.bin').read_bytes(),(src/'sub'/'data.bin').read_bytes())
    def test_zip_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); src=base/'src'; src.mkdir(); (src/'a.txt').write_text('zip works',encoding='utf-8')
            archive=base/'a.zip'; out=base/'out'; core.create_zip(src,archive); core.extract_zip(archive,out)
            self.assertEqual((out/'src'/'a.txt').read_text(encoding='utf-8'),'zip works')

    def test_pjs3_fast_format_roundtrip_and_incompressible_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            # Repetitive data should compress significantly with zlib.
            repetitive = base / 'repetitive.txt'
            repetitive.write_bytes((b'PJS compressor performance test\n' * 30000))
            archive = base / 'repetitive.pjs'
            restored = base / 'restored'
            core.create_pjs(repetitive, archive)
            self.assertEqual(archive.read_bytes()[:4], b'PJS3')
            core.extract_pjs(archive, restored)
            self.assertEqual((restored / repetitive.name).read_bytes(), repetitive.read_bytes())
            self.assertLess(archive.stat().st_size, repetitive.stat().st_size // 5)

            # Random data should be stored uncompressed rather than expanded by a codec.
            random_file = base / 'random.bin'
            random_file.write_bytes(os.urandom(256 * 1024))
            random_archive = base / 'random.pjs'
            core.create_pjs(random_file, random_archive)
            with random_archive.open('rb') as f:
                f.seek(9)
                kind, name_len = struct.unpack('<BH', f.read(3))
                f.seek(name_len, 1)
                raw_size, packed_size, _ = struct.unpack('<QQI', f.read(20))
            self.assertEqual(kind, 2)
            self.assertEqual(raw_size, packed_size)
            random_out = base / 'random-out'
            core.extract_pjs(random_archive, random_out)
            self.assertEqual((random_out / random_file.name).read_bytes(), random_file.read_bytes())

    def test_legacy_pjs2_still_extracts(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            raw = b'legacy PJS2 compatibility test ' * 500
            name = 'legacy.txt'
            packed = core.transform_payload(core.pjs_compress(raw, core.filename_seed(name)), name)
            archive = base / 'legacy.pjs'
            with archive.open('wb') as f:
                f.write(b'PJS2')
                f.write(struct.pack('<BI', 2, 1))
                encoded_name = name.encode('utf-8')
                f.write(struct.pack('<BH', 0, len(encoded_name)))
                f.write(encoded_name)
                f.write(struct.pack('<QQI', len(raw), len(packed), zlib.crc32(raw) & 0xffffffff))
                f.write(packed)
            out = base / 'out'
            core.extract_pjs(archive, out)
            self.assertEqual((out / name).read_bytes(), raw)

    def test_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError): core.safe_output_path(td,'../evil.txt')

if __name__=='__main__': unittest.main()
