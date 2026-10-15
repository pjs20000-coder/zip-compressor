"""Password-protected PJS4 format.

PJS4 uses Argon2id to derive a key from the user's password and AES-256-GCM
for authenticated encryption. The archive filename and metadata are inside the
encrypted ZIP payload. PJS4 is a new format and is not compatible with PJS1-3.
"""
from __future__ import annotations

import os
import shutil
import stat
import struct
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"PJS4"
VERSION = 1
SALT_SIZE = 16
NONCE_PREFIX_SIZE = 8
KEY_SIZE = 32
TAG_SIZE = 16
CHUNK_SIZE = 1024 * 1024  # 1 MiB
# Fixed, authenticated format parameters. Do not accept attacker-controlled KDF costs.
ARGON2_TIME_COST = 3
ARGON2_MEMORY_KIB = 131072  # 128 MiB
ARGON2_PARALLELISM = 2
# magic, version, salt, nonce prefix, chunk size
HEADER_STRUCT = struct.Struct(">4sB16s8sI")
RECORD_STRUCT = struct.Struct(">BI")  # final flag, ciphertext length
MAX_ARCHIVE_TOTAL_SIZE = 1 << 40  # safety cap: 1 TiB of extracted data

class PJSFormatError(ValueError):
    """Invalid, damaged, or unsupported PJS4 file."""

class PJSAuthenticationError(ValueError):
    """Password is wrong or encrypted data has been altered."""

def _derive_key(password: str, salt: bytes) -> bytes:
    if not isinstance(password, str) or not password:
        raise ValueError("비밀번호를 입력해 주세요.")
    return hash_secret_raw(
        secret=password.encode("utf-8"), salt=salt,
        time_cost=ARGON2_TIME_COST, memory_cost=ARGON2_MEMORY_KIB,
        parallelism=ARGON2_PARALLELISM, hash_len=KEY_SIZE,
        type=Type.ID, version=19,
    )

def _read_exact(fileobj, size: int) -> bytes:
    parts = bytearray()
    while len(parts) < size:
        block = fileobj.read(size - len(parts))
        if not block:
            raise PJSFormatError("PJS 파일이 잘렸거나 손상되었습니다.")
        parts.extend(block)
    return bytes(parts)

def _make_zip(source: Path, zip_path: Path) -> None:
    source = source.resolve()
    if not source.exists():
        raise FileNotFoundError(f"입력 경로를 찾을 수 없습니다: {source}")
    if source.is_symlink():
        raise ValueError("심볼릭 링크는 입력으로 지원하지 않습니다.")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as zf:
        if source.is_file():
            zf.write(source, arcname=source.name)
            return
        if not source.is_dir():
            raise ValueError("일반 파일 또는 폴더만 압축할 수 있습니다.")
        base = source.parent
        # Store the root folder and empty directories as well as files.
        for item in sorted(source.rglob("*")):
            if item.is_symlink():
                raise ValueError(f"심볼릭 링크는 압축할 수 없습니다: {item}")
            arcname = item.relative_to(base).as_posix()
            if item.is_dir():
                zf.writestr(arcname.rstrip("/") + "/", b"")
            elif item.is_file():
                zf.write(item, arcname=arcname)

def _encrypt_stream(source, destination, password: str) -> None:
    salt = os.urandom(SALT_SIZE)
    nonce_prefix = os.urandom(NONCE_PREFIX_SIZE)
    header = HEADER_STRUCT.pack(MAGIC, VERSION, salt, nonce_prefix, CHUNK_SIZE)
    key = _derive_key(password, salt)
    aes = AESGCM(key)
    destination.write(header)
    index = 0
    current = source.read(CHUNK_SIZE)
    following = source.read(CHUNK_SIZE)
    while True:
        final = not following
        flag = 1 if final else 0
        if index >= 0xFFFFFFFF:
            raise ValueError("파일이 너무 커서 PJS4 청크 제한을 초과했습니다.")
        nonce = nonce_prefix + index.to_bytes(4, "big")
        aad = header + index.to_bytes(8, "big") + bytes([flag]) + len(current).to_bytes(4, "big")
        ciphertext = aes.encrypt(nonce, current, aad)
        destination.write(RECORD_STRUCT.pack(flag, len(ciphertext)))
        destination.write(ciphertext)
        index += 1
        if final:
            break
        current, following = following, source.read(CHUNK_SIZE)

def _decrypt_stream(source, destination, password: str) -> None:
    header = _read_exact(source, HEADER_STRUCT.size)
    magic, version, salt, nonce_prefix, chunk_size = HEADER_STRUCT.unpack(header)
    if magic != MAGIC or version != VERSION:
        raise PJSFormatError("지원하지 않는 PJS 형식입니다. PJS4 파일인지 확인해 주세요.")
    if chunk_size != CHUNK_SIZE:
        raise PJSFormatError("지원하지 않는 PJS4 청크 크기입니다.")
    key = _derive_key(password, salt)
    aes = AESGCM(key)
    index = 0
    saw_final = False
    while True:
        record = source.read(RECORD_STRUCT.size)
        if not record:
            break
        if len(record) != RECORD_STRUCT.size:
            raise PJSFormatError("PJS 파일의 청크 헤더가 손상되었습니다.")
        flag, cipher_len = RECORD_STRUCT.unpack(record)
        if flag not in (0, 1) or cipher_len < TAG_SIZE or cipher_len > CHUNK_SIZE + TAG_SIZE:
            raise PJSFormatError("PJS 파일의 청크 길이가 올바르지 않습니다.")
        plain_len = cipher_len - TAG_SIZE
        if flag == 0 and plain_len != CHUNK_SIZE:
            raise PJSFormatError("PJS 파일의 중간 청크 길이가 올바르지 않습니다.")
        if index >= 0xFFFFFFFF:
            raise PJSFormatError("PJS 파일의 청크 수가 제한을 초과했습니다.")
        ciphertext = _read_exact(source, cipher_len)
        nonce = nonce_prefix + index.to_bytes(4, "big")
        aad = header + index.to_bytes(8, "big") + bytes([flag]) + plain_len.to_bytes(4, "big")
        try:
            plaintext = aes.decrypt(nonce, ciphertext, aad)
        except InvalidTag as exc:
            raise PJSAuthenticationError("비밀번호가 틀렸거나 파일이 변조되었습니다.") from exc
        destination.write(plaintext)
        index += 1
        if flag == 1:
            saw_final = True
            if source.read(1):
                raise PJSFormatError("최종 청크 뒤에 불필요한 데이터가 있습니다.")
            break
    if not saw_final:
        raise PJSFormatError("PJS 파일이 불완전합니다(최종 청크가 없습니다).")

def compress_to_pjs(source_path: str | Path, output_path: str | Path, password: str) -> Path:
    """Compress a file/folder into a password-protected PJS4 file."""
    source = Path(source_path)
    output = Path(output_path)
    if not isinstance(password, str) or not password:
        raise ValueError("비밀번호를 1자 이상 입력해 주세요.")
    output.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() == output.resolve():
        raise ValueError("입력 파일과 출력 파일이 같을 수 없습니다.")
    zip_name = None
    temp_output = None
    try:
        with tempfile.NamedTemporaryFile(prefix="pjs4-", suffix=".zip", delete=False) as tmp:
            zip_name = Path(tmp.name)
        _make_zip(source, zip_name)
        with tempfile.NamedTemporaryFile(prefix=".pjs4-", suffix=".tmp", dir=output.parent, delete=False) as tmp_out:
            temp_output = Path(tmp_out.name)
            with zip_name.open("rb") as zip_in:
                _encrypt_stream(zip_in, tmp_out, password)
            tmp_out.flush()
            os.fsync(tmp_out.fileno())
        os.replace(temp_output, output)
        temp_output = None
        return output
    finally:
        if zip_name:
            zip_name.unlink(missing_ok=True)
        if temp_output:
            temp_output.unlink(missing_ok=True)

def _safe_member_path(root: Path, name: str) -> Path:
    # ZIP member names must be treated as untrusted input.
    normalized = name.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if not normalized or normalized.startswith("/") or pure.is_absolute():
        raise PJSFormatError("압축 파일에 절대 경로가 포함되어 있습니다.")
    if len(normalized) >= 2 and normalized[1] == ":":
        raise PJSFormatError("압축 파일에 드라이브 경로가 포함되어 있습니다.")
    if any(part in ("..", "") for part in normalized.split("/") if part != ""):
        raise PJSFormatError("압축 파일에 안전하지 않은 경로가 포함되어 있습니다.")
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    target = root.joinpath(*parts).resolve()
    root_resolved = root.resolve()
    try:
        if os.path.commonpath([str(root_resolved), str(target)]) != str(root_resolved):
            raise PJSFormatError("압축 해제 경로가 대상 폴더를 벗어납니다.")
    except ValueError as exc:
        raise PJSFormatError("압축 해제 경로가 올바르지 않습니다.") from exc
    return target

def _safe_extract(zip_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    total = 0
    seen: set[str] = set()
    with zipfile.ZipFile(zip_path, "r") as zf:
        bad = zf.testzip()
        if bad is not None:
            raise PJSFormatError(f"내부 압축 데이터가 손상되었습니다: {bad}")
        for info in zf.infolist():
            target = _safe_member_path(root, info.filename)
            key = target.as_posix().casefold()
            if key in seen:
                raise PJSFormatError("중복된 파일 경로가 포함되어 있어 해제를 중단했습니다.")
            seen.add(key)
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise PJSFormatError("심볼릭 링크 항목은 해제할 수 없습니다.")
            total += info.file_size
            if total > MAX_ARCHIVE_TOTAL_SIZE:
                raise PJSFormatError("압축 해제 대상의 총 크기가 허용 한도를 초과합니다.")
            if info.is_dir() or info.filename.endswith(("/", "\\")):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise FileExistsError(f"기존 파일을 덮어쓰지 않도록 중단했습니다: {target}")
            with zf.open(info, "r") as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)

def decompress_pjs(pjs_path: str | Path, output_dir: str | Path, password: str) -> Path:
    """Decrypt and safely extract a PJS4 file to output_dir."""
    source = Path(pjs_path)
    destination = Path(output_dir)
    if not source.is_file():
        raise FileNotFoundError(f"PJS 파일을 찾을 수 없습니다: {source}")
    destination.mkdir(parents=True, exist_ok=True)
    zip_name = None
    try:
        with tempfile.NamedTemporaryFile(prefix="pjs4-decrypted-", suffix=".zip", delete=False) as tmp:
            zip_name = Path(tmp.name)
            with source.open("rb") as encrypted:
                _decrypt_stream(encrypted, tmp, password)
            tmp.flush()
        _safe_extract(zip_name, destination)
        return destination
    finally:
        if zip_name:
            zip_name.unlink(missing_ok=True)
