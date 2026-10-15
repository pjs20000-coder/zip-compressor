import os, tempfile, unittest, zipfile
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
    def test_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError): core.safe_output_path(td,'../evil.txt')

if __name__=='__main__': unittest.main()
