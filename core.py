"""PJS/ZIP processing core. PJS format logic retained for compatibility."""
from __future__ import annotations
import hashlib
import os
import struct
import zlib
import zipfile
import tempfile
import shutil
from pathlib import Path
from typing import Callable, Iterable

PJS_MAGIC = b"PJS2"
PJS_LEGACY_MAGIC = b"PJS1"
PJS3_MAGIC = b"PJS3"
PJS_VERSION = 2
PJS3_VERSION = 3
PJS_BLOCK_SIZE = 4096
MAX_WINDOW = 65535
MAX_MATCH = 258
MIN_MATCH = 3
MAX_CANDIDATES = 64
Progress = Callable[[int, int, int], None]


def pjs_compress(data: bytes, seed: int = 0) -> bytes:
    out = bytearray(); positions: dict[bytes, list[int]] = {}; i = 0; n = len(data)
    def add_position(pos: int) -> None:
        if pos + 1 >= n: return
        bucket = positions.setdefault(data[pos:pos+2], []); bucket.append(pos)
        while bucket and (pos - bucket[0] > MAX_WINDOW or len(bucket) > 256): bucket.pop(0)
    while i < n:
        control_pos = len(out); out.append(0); control = 0
        for bit_index in range(8):
            if i >= n: break
            best_len = best_offset = 0
            if i + MIN_MATCH <= n:
                candidates = positions.get(data[i:i+2], [])
                ordered = list(reversed(candidates))
                if ordered:
                    rotate = seed % len(ordered); ordered = ordered[rotate:] + ordered[:rotate]
                checked = 0
                for candidate in ordered:
                    offset = i - candidate
                    if offset <= 0: continue
                    if offset > MAX_WINDOW: break
                    checked += 1
                    if checked > MAX_CANDIDATES: break
                    limit = min(MAX_MATCH, n-i); length = 2
                    while length < limit and data[candidate+length] == data[i+length]: length += 1
                    if length >= MIN_MATCH and length > best_len:
                        best_len, best_offset = length, offset
                        if length == limit: break
            if best_len >= MIN_MATCH:
                out.extend(struct.pack('<HB', best_offset, best_len-MIN_MATCH))
                end = i + best_len
                while i < end: add_position(i); i += 1
            else:
                control |= 1 << bit_index; out.append(data[i]); add_position(i); i += 1
        out[control_pos] = control
    return bytes(out)


def pjs_decompress(data: bytes, expected_size: int) -> bytes:
    out = bytearray(); i = 0
    while i < len(data):
        control = data[i]; i += 1
        for bit_index in range(8):
            if i >= len(data): break
            if control & (1 << bit_index): out.append(data[i]); i += 1
            else:
                if i + 3 > len(data): raise ValueError('PJS 데이터가 손상되었습니다(압축 토큰이 잘림).')
                offset, code = struct.unpack_from('<HB', data, i); i += 3; length = code + MIN_MATCH
                if offset == 0 or offset > len(out): raise ValueError('PJS 데이터가 손상되었습니다(잘못된 참조 위치).')
                for _ in range(length): out.append(out[-offset])
            if len(out) > expected_size: raise ValueError('PJS 데이터가 헤더에 기록된 원본 크기를 초과합니다.')
    if len(out) != expected_size:
        raise ValueError(f'원본 크기가 일치하지 않습니다. 예상: {expected_size}바이트, 복원: {len(out)}바이트')
    return bytes(out)


def filename_seed(name: str) -> int:
    normalized = name.replace('\\', '/').encode('utf-8', errors='strict')
    return int.from_bytes(hashlib.blake2s(normalized, digest_size=4, person=b'PJSname').digest(), 'little')


def transform_payload(data: bytes, name: str) -> bytes:
    name_bytes = name.replace('\\', '/').encode('utf-8', errors='strict'); out = bytearray(len(data))
    for block_index, start in enumerate(range(0, len(data), PJS_BLOCK_SIZE)):
        chunk = data[start:start+PJS_BLOCK_SIZE]; stream = bytearray(); counter = 0
        while len(stream) < len(chunk):
            material = (b'PJS2-scramble\0' + len(name_bytes).to_bytes(4,'little') + name_bytes +
                        block_index.to_bytes(8,'little') + counter.to_bytes(4,'little'))
            stream.extend(hashlib.blake2s(material, digest_size=32).digest()); counter += 1
        for j, value in enumerate(chunk): out[start+j] = value ^ stream[j]
    return bytes(out)


def iter_entries(source: str | Path):
    source = os.path.abspath(os.fspath(source))
    if os.path.isfile(source):
        yield os.path.basename(source), source, False; return
    parent = os.path.dirname(source)
    for current, dirs, files in os.walk(source):
        dirs.sort(); rel_dir = os.path.relpath(current, parent).replace(os.sep, '/')
        yield rel_dir.rstrip('/')+'/', current, True
        for name in sorted(files):
            full = os.path.join(current, name)
            yield os.path.relpath(full, parent).replace(os.sep, '/'), full, False


def safe_output_path(destination: str | Path, archive_name: str) -> str:
    name = archive_name.replace('\\','/')
    if name.startswith('/') or (len(name)>=2 and name[1]==':'):
        raise ValueError('압축 파일에 절대 경로가 포함되어 있어 해제를 중단했습니다.')
    parts = [p for p in name.split('/') if p not in ('', '.')]
    if any(p == '..' for p in parts): raise ValueError('압축 파일에 상위 폴더 이동 경로가 포함되어 있습니다.')
    dest = os.path.abspath(os.fspath(destination)); result = os.path.abspath(os.path.join(dest,*parts))
    if os.path.commonpath([dest,result]) != dest: raise ValueError('안전하지 않은 출력 경로입니다.')
    return result


def _read_exact(stream, size: int) -> bytes:
    data = stream.read(size)
    if len(data) != size: raise ValueError('PJS 파일이 손상되었거나 중간에 잘렸습니다.')
    return data


# PJS3 uses zlib (implemented in native code) and a stored-file fallback.
# Entry kinds: 0=zlib-compressed file, 1=directory, 2=stored file.
# PJS1/PJS2 readers are retained below for backward compatibility.
_COMPRESSED_EXTENSIONS = {
    '.7z', '.aac', '.avi', '.avif', '.br', '.bz2', '.cab', '.flac', '.gif',
    '.gz', '.heic', '.heif', '.jpeg', '.jpg', '.lz4', '.m4a', '.m4v', '.mkv',
    '.mov', '.mp3', '.mp4', '.mpeg', '.mpg', '.pdf', '.png', '.rar', '.webm',
    '.webp', '.xz', '.zip', '.zst', '.parquet', '.woff', '.woff2',
    '.docx', '.xlsx', '.pptx', '.odt', '.ods', '.odp', '.apk', '.jar', '.epub', '.iso'
}
_CHUNK_SIZE = 1024 * 1024


def _copy_file_and_crc(source: str, destination, progress=None, done_before=0, total_bytes=0):
    raw_size = 0
    crc = 0
    with open(source, 'rb') as src:
        while True:
            chunk = src.read(_CHUNK_SIZE)
            if not chunk:
                break
            destination.write(chunk)
            raw_size += len(chunk)
            crc = zlib.crc32(chunk, crc)
            if progress and total_bytes:
                progress(min(99, int((done_before + raw_size) * 100 / total_bytes)), done_before + raw_size, total_bytes)
    return raw_size, crc & 0xffffffff


def create_pjs(source: str | Path, output: str | Path, progress: Progress | None = None) -> None:
    """Create a PJS3 archive quickly, preserving the ability to read PJS1/PJS2."""
    entries = list(iter_entries(source))
    output = os.fspath(output)
    total_bytes = sum(os.path.getsize(full) for _, full, is_dir in entries if not is_dir)
    total_bytes = max(total_bytes, 1)
    processed = 0

    with open(output, 'wb') as out:
        out.write(PJS3_MAGIC)
        out.write(struct.pack('<BI', PJS3_VERSION, len(entries)))
        total_entries = max(len(entries), 1)

        for index, (arcname, full, is_dir) in enumerate(entries, 1):
            name = arcname.encode('utf-8')
            if len(name) > 65535:
                raise ValueError('경로가 너무 깁니다: ' + arcname)

            if is_dir:
                out.write(struct.pack('<BH', 1, len(name)))
                out.write(name)
                out.write(struct.pack('<QQI', 0, 0, 0))
            else:
                suffix = Path(full).suffix.lower()
                # Already-compressed formats usually do not benefit from another
                # compression pass. Store them directly to save CPU time.
                if suffix in _COMPRESSED_EXTENSIONS:
                    out.write(struct.pack('<BH', 2, len(name)))
                    out.write(name)
                    meta_pos = out.tell()
                    out.write(struct.pack('<QQI', 0, 0, 0))
                    data_start = out.tell()
                    raw_size, crc = _copy_file_and_crc(full, out, progress, processed, total_bytes)
                    packed_size = out.tell() - data_start
                    end_pos = out.tell()
                    out.seek(meta_pos)
                    out.write(struct.pack('<QQI', raw_size, packed_size, crc))
                    out.seek(end_pos)
                else:
                    # Compress to a disk-backed temporary stream first. If zlib
                    # cannot reduce the size, store the original bytes instead.
                    with tempfile.SpooledTemporaryFile(max_size=16 * 1024 * 1024, mode='w+b') as temp:
                        compressor = zlib.compressobj(level=6)
                        raw_size = 0
                        crc = 0
                        with open(full, 'rb') as src:
                            while True:
                                chunk = src.read(_CHUNK_SIZE)
                                if not chunk:
                                    break
                                raw_size += len(chunk)
                                crc = zlib.crc32(chunk, crc)
                                compressed = compressor.compress(chunk)
                                if compressed:
                                    temp.write(compressed)
                                if progress and total_bytes:
                                    progress(min(99, int((processed + raw_size) * 100 / total_bytes)), processed + raw_size, total_bytes)
                        tail = compressor.flush()
                        if tail:
                            temp.write(tail)
                        crc &= 0xffffffff
                        packed_size = temp.tell()

                        if packed_size < raw_size:
                            kind = 0
                            chosen_size = packed_size
                        else:
                            kind = 2
                            chosen_size = raw_size

                        out.write(struct.pack('<BH', kind, len(name)))
                        out.write(name)
                        out.write(struct.pack('<QQI', raw_size, chosen_size, crc))
                        if kind == 0:
                            temp.seek(0)
                            shutil.copyfileobj(temp, out, length=_CHUNK_SIZE)
                        else:
                            with open(full, 'rb') as src:
                                shutil.copyfileobj(src, out, length=_CHUNK_SIZE)

                processed += os.path.getsize(full)

            if progress:
                if total_bytes > 1:
                    progress(min(99, int(processed * 100 / total_bytes)), processed, total_bytes)
                else:
                    progress(int(index * 100 / total_entries), index, total_entries)

        if progress:
            progress(100, total_bytes, total_bytes)


def extract_pjs(archive: str | Path, destination: str | Path, progress: Progress | None = None) -> None:
    os.makedirs(destination, exist_ok=True)
    archive = os.fspath(archive)
    total_size = os.path.getsize(archive)
    with open(archive, 'rb') as f:
        magic = _read_exact(f, 4)
        if magic not in (PJS_MAGIC, PJS_LEGACY_MAGIC, PJS3_MAGIC):
            raise ValueError('올바른 PJS 파일이 아닙니다.')
        version, count = struct.unpack('<BI', _read_exact(f, 5))
        if magic == PJS_LEGACY_MAGIC and version != 1:
            raise ValueError(f'지원하지 않는 PJS 버전입니다: {version}')
        if magic == PJS_MAGIC and version != PJS_VERSION:
            raise ValueError(f'지원하지 않는 PJS 버전입니다: {version}')
        if magic == PJS3_MAGIC and version != PJS3_VERSION:
            raise ValueError(f'지원하지 않는 PJS 버전입니다: {version}')
        if count > 1_000_000:
            raise ValueError('파일 항목 수가 비정상적으로 많습니다.')

        total = max(count, 1)
        for index in range(1, count + 1):
            kind, name_len = struct.unpack('<BH', _read_exact(f, 3))
            name = _read_exact(f, name_len).decode('utf-8')
            raw_size, packed_size, expected_crc = struct.unpack('<QQI', _read_exact(f, 20))
            out_path = safe_output_path(destination, name)

            if kind == 1:
                os.makedirs(out_path, exist_ok=True)
                if packed_size:
                    f.seek(packed_size, os.SEEK_CUR)
            elif kind in (0, 2):
                if magic != PJS3_MAGIC and kind != 0:
                    raise ValueError('이전 PJS 형식에 잘못된 파일 항목 유형이 있습니다.')
                if packed_size > total_size:
                    raise ValueError('압축 데이터 크기가 비정상적입니다.')
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                crc = 0
                written = 0
                with open(out_path, 'wb') as dst:
                    remaining = packed_size
                    if magic == PJS3_MAGIC and kind == 0:
                        decompressor = zlib.decompressobj()
                        while remaining:
                            chunk = _read_exact(f, min(_CHUNK_SIZE, remaining))
                            remaining -= len(chunk)
                            pending = chunk
                            while pending:
                                raw = decompressor.decompress(pending, _CHUNK_SIZE)
                                pending = decompressor.unconsumed_tail
                                if raw:
                                    dst.write(raw)
                                    written += len(raw)
                                    crc = zlib.crc32(raw, crc)
                                if not pending:
                                    # Drain any buffered output without needing more input.
                                    while True:
                                        extra = decompressor.decompress(b'', _CHUNK_SIZE)
                                        if not extra:
                                            break
                                        dst.write(extra)
                                        written += len(extra)
                                        crc = zlib.crc32(extra, crc)
                        tail = decompressor.flush()
                        if tail:
                            dst.write(tail)
                            written += len(tail)
                            crc = zlib.crc32(tail, crc)
                        if not decompressor.eof:
                            raise ValueError(f'압축 데이터가 불완전합니다: {name}')
                    elif magic == PJS3_MAGIC and kind == 2:
                        while remaining:
                            chunk = _read_exact(f, min(_CHUNK_SIZE, remaining))
                            remaining -= len(chunk)
                            dst.write(chunk)
                            written += len(chunk)
                            crc = zlib.crc32(chunk, crc)
                    else:
                        packed = _read_exact(f, packed_size)
                        if magic == PJS_MAGIC:
                            packed = transform_payload(packed, name)
                        raw = pjs_decompress(packed, raw_size)
                        dst.write(raw)
                        written = len(raw)
                        crc = zlib.crc32(raw, crc)

                if written != raw_size:
                    raise ValueError(f'원본 크기가 일치하지 않습니다: {name} (예상 {raw_size}, 복원 {written})')
                if (crc & 0xffffffff) != expected_crc:
                    raise ValueError(f'파일 검증에 실패했습니다: {name}')
            else:
                raise ValueError('알 수 없는 PJS 항목 유형입니다.')

            if progress:
                progress(int(index * 100 / total), index, total)

def create_zip(source: str | Path, output: str | Path, progress: Progress | None = None) -> None:
    """Create ZIP archives incrementally so large files report live progress."""
    entries = list(iter_entries(source))
    total_entries = max(len(entries), 1)
    total_bytes = sum(os.path.getsize(full) for _, full, is_dir in entries if not is_dir)
    processed = 0
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for index, (name, full, is_dir) in enumerate(entries, 1):
            name = name.replace('\\', '/')
            if is_dir:
                zf.writestr(name if name.endswith('/') else name + '/', '')
            else:
                suffix = Path(full).suffix.lower()
                info = zipfile.ZipInfo(name)
                info.file_size = os.path.getsize(full)
                info.compress_type = zipfile.ZIP_STORED if suffix in _COMPRESSED_EXTENSIONS else zipfile.ZIP_DEFLATED
                with open(full, 'rb') as src, zf.open(info, 'w', force_zip64=True) as dst:
                    while True:
                        chunk = src.read(_CHUNK_SIZE)
                        if not chunk:
                            break
                        dst.write(chunk)
                        processed += len(chunk)
                        if progress and total_bytes:
                            progress(min(99, int(processed * 100 / total_bytes)), processed, total_bytes)
            if progress:
                if total_bytes:
                    progress(min(99, int(processed * 100 / total_bytes)), processed, total_bytes)
                else:
                    progress(int(index * 100 / total_entries), index, total_entries)
    if progress:
        if total_bytes:
            progress(100, total_bytes, total_bytes)
        else:
            progress(100, total_entries, total_entries)

def extract_zip(archive: str | Path, destination: str | Path, progress: Progress | None = None) -> None:
    os.makedirs(destination,exist_ok=True)
    with zipfile.ZipFile(archive,'r') as zf:
        infos = zf.infolist(); total = max(len(infos),1); dest = os.path.abspath(os.fspath(destination))
        for index,info in enumerate(infos,1):
            out_path = safe_output_path(dest,info.filename)
            if info.is_dir(): os.makedirs(out_path,exist_ok=True)
            else:
                os.makedirs(os.path.dirname(out_path),exist_ok=True)
                with zf.open(info,'r') as src, open(out_path,'wb') as dst:
                    while True:
                        chunk = src.read(1024*1024)
                        if not chunk: break
                        dst.write(chunk)
            if progress: progress(int(index*100/total),index,total)
