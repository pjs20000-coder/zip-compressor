import os
import json
import hashlib
import struct
import zlib
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinterdnd2 import DND_FILES, TkinterDnD

PJS_MAGIC = b"PJS2"
PJS_LEGACY_MAGIC = b"PJS1"
PJS_VERSION = 2
PJS_BLOCK_SIZE = 4096
MAX_WINDOW = 65535
MAX_MATCH = 258
MIN_MATCH = 3
MAX_CANDIDATES = 64


# -------------------- Custom PJS lossless codec --------------------
# Token groups use one control byte for up to 8 tokens.
# Control bit 1 = literal byte; bit 0 = match (offset: uint16 LE, length-3: uint8).
# This is a learning-oriented custom LZ77-style codec, not a security feature.

def pjs_compress(data: bytes, seed: int = 0) -> bytes:
    out = bytearray()
    positions = {}
    i = 0
    n = len(data)

    def add_position(pos):
        if pos + 1 >= n:
            return
        key = data[pos:pos + 2]
        bucket = positions.setdefault(key, [])
        bucket.append(pos)
        # Bound memory and search work.
        while bucket and (pos - bucket[0] > MAX_WINDOW or len(bucket) > 256):
            bucket.pop(0)

    while i < n:
        control_pos = len(out)
        out.append(0)
        control = 0

        for bit_index in range(8):
            if i >= n:
                break

            best_len = 0
            best_offset = 0
            if i + MIN_MATCH <= n:
                key = data[i:i + 2]
                candidates = positions.get(key, [])
                checked = 0
                # Filename-derived seed changes which recent candidates are examined first.
                # This is deterministic obfuscation, not cryptographic protection.
                ordered = list(reversed(candidates))
                if ordered:
                    rotate = seed % len(ordered)
                    ordered = ordered[rotate:] + ordered[:rotate]
                for candidate in ordered:
                    offset = i - candidate
                    if offset <= 0:
                        continue
                    if offset > MAX_WINDOW:
                        break
                    checked += 1
                    if checked > MAX_CANDIDATES:
                        break
                    limit = min(MAX_MATCH, n - i)
                    length = 2
                    while length < limit and data[candidate + length] == data[i + length]:
                        length += 1
                    if length >= MIN_MATCH and length > best_len:
                        best_len = length
                        best_offset = offset
                        if length == limit:
                            break

            if best_len >= MIN_MATCH:
                out.extend(struct.pack("<HB", best_offset, best_len - MIN_MATCH))
                end = i + best_len
                while i < end:
                    add_position(i)
                    i += 1
            else:
                control |= (1 << bit_index)
                out.append(data[i])
                add_position(i)
                i += 1

        out[control_pos] = control

    return bytes(out)


def pjs_decompress(data: bytes, expected_size: int) -> bytes:
    out = bytearray()
    i = 0

    while i < len(data):
        control = data[i]
        i += 1
        for bit_index in range(8):
            if i >= len(data):
                break
            if control & (1 << bit_index):
                out.append(data[i])
                i += 1
            else:
                if i + 3 > len(data):
                    raise ValueError("PJS 데이터가 손상되었습니다(압축 토큰이 잘림).")
                offset, length_code = struct.unpack_from("<HB", data, i)
                i += 3
                length = length_code + MIN_MATCH
                if offset == 0 or offset > len(out):
                    raise ValueError("PJS 데이터가 손상되었습니다(잘못된 참조 위치).")
                for _ in range(length):
                    out.append(out[-offset])

            if len(out) > expected_size:
                raise ValueError("PJS 데이터가 헤더에 기록된 원본 크기를 초과합니다.")

    if len(out) != expected_size:
        raise ValueError(
            f"원본 크기가 일치하지 않습니다. 예상: {expected_size}바이트, 복원: {len(out)}바이트"
        )
    return bytes(out)



def filename_seed(archive_name: str) -> int:
    """Stable, public filename-derived parameter; deliberately not a secret key."""
    normalized = archive_name.replace("\\", "/").encode("utf-8", errors="strict")
    digest = hashlib.blake2s(normalized, digest_size=4, person=b"PJSname").digest()
    return int.from_bytes(digest, "little")


def transform_payload(data: bytes, archive_name: str) -> bytes:
    """Reversible filename-dependent byte scrambling. This is NOT encryption."""
    name_bytes = archive_name.replace("\\", "/").encode("utf-8", errors="strict")
    out = bytearray(len(data))
    # A fresh deterministic stream per 4 KiB block makes each block depend on its index.
    for block_index, start in enumerate(range(0, len(data), PJS_BLOCK_SIZE)):
        chunk = data[start:start + PJS_BLOCK_SIZE]
        stream = bytearray()
        counter = 0
        while len(stream) < len(chunk):
            material = (b"PJS2-scramble\0" + len(name_bytes).to_bytes(4, "little") +
                        name_bytes + block_index.to_bytes(8, "little") +
                        counter.to_bytes(4, "little"))
            stream.extend(hashlib.blake2s(material, digest_size=32).digest())
            counter += 1
        for j, value in enumerate(chunk):
            out[start + j] = value ^ stream[j]
    return bytes(out)


def iter_source_entries(source_path):
    """Yield (archive_path, filesystem_path, is_directory)."""
    source_path = os.path.abspath(source_path)
    if os.path.isfile(source_path):
        yield os.path.basename(source_path), source_path, False
        return

    base_parent = os.path.dirname(source_path)
    for current, dirs, files in os.walk(source_path):
        dirs.sort()
        rel_dir = os.path.relpath(current, base_parent).replace(os.sep, "/")
        yield rel_dir.rstrip("/") + "/", current, True
        for name in sorted(files):
            full = os.path.join(current, name)
            rel = os.path.relpath(full, base_parent).replace(os.sep, "/")
            yield rel, full, False


def write_pjs(source_path, output_path, progress_callback=None):
    entries = list(iter_source_entries(source_path))
    with open(output_path, "wb") as out:
        out.write(PJS_MAGIC)
        out.write(struct.pack("<BI", PJS_VERSION, len(entries)))

        total = max(len(entries), 1)
        for index, (arcname, fullpath, is_dir) in enumerate(entries, 1):
            name_bytes = arcname.encode("utf-8")
            if len(name_bytes) > 65535:
                raise ValueError("경로가 너무 깁니다: " + arcname)

            seed = filename_seed(arcname)
            if is_dir:
                raw = b""
                packed = b""
            else:
                with open(fullpath, "rb") as f:
                    raw = f.read()
                packed = transform_payload(pjs_compress(raw, seed), arcname)

            crc = zlib.crc32(raw) & 0xFFFFFFFF
            out.write(struct.pack("<BH", 1 if is_dir else 0, len(name_bytes)))
            out.write(name_bytes)
            out.write(struct.pack("<QQI", len(raw), len(packed), crc))
            out.write(packed)

            if progress_callback:
                progress_callback(int(index * 100 / total), index, total)


def safe_output_path(destination, archive_name):
    # Normalize archive separators and reject path traversal / absolute paths.
    name = archive_name.replace("\\", "/")
    if name.startswith("/") or (len(name) >= 2 and name[1] == ":"):
        raise ValueError("압축 파일에 절대 경로가 포함되어 있어 해제를 중단했습니다.")
    parts = [p for p in name.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise ValueError("압축 파일에 상위 폴더 이동 경로가 포함되어 있습니다.")
    result = os.path.abspath(os.path.join(destination, *parts))
    dest_abs = os.path.abspath(destination)
    if os.path.commonpath([dest_abs, result]) != dest_abs:
        raise ValueError("안전하지 않은 출력 경로입니다.")
    return result


def read_exact(stream, size):
    data = stream.read(size)
    if len(data) != size:
        raise ValueError("PJS 파일이 손상되었거나 중간에 잘렸습니다.")
    return data


def extract_pjs(archive_path, destination, progress_callback=None):
    os.makedirs(destination, exist_ok=True)
    with open(archive_path, "rb") as f:
        magic = read_exact(f, 4)
        if magic not in (PJS_MAGIC, PJS_LEGACY_MAGIC):
            raise ValueError("올바른 PJS 파일이 아닙니다.")
        version, count = struct.unpack("<BI", read_exact(f, 5))
        if magic == PJS_LEGACY_MAGIC and version != 1:
            raise ValueError(f"지원하지 않는 PJS 버전입니다: {version}")
        if magic == PJS_MAGIC and version != PJS_VERSION:
            raise ValueError(f"지원하지 않는 PJS 버전입니다: {version}")
        if count > 1_000_000:
            raise ValueError("파일 항목 수가 비정상적으로 많습니다.")

        total = max(count, 1)
        for index in range(1, count + 1):
            entry_type, name_len = struct.unpack("<BH", read_exact(f, 3))
            name = read_exact(f, name_len).decode("utf-8")
            raw_size, packed_size, expected_crc = struct.unpack("<QQI", read_exact(f, 20))
            output_path = safe_output_path(destination, name)

            if entry_type == 1:
                os.makedirs(output_path, exist_ok=True)
                # Directories should not carry payload.
                if packed_size:
                    f.seek(packed_size, os.SEEK_CUR)
            elif entry_type == 0:
                if packed_size > os.path.getsize(archive_path):
                    raise ValueError("압축 데이터 크기가 비정상적입니다.")
                packed = read_exact(f, packed_size)
                if magic == PJS_MAGIC:
                    packed = transform_payload(packed, name)
                    raw = pjs_decompress(packed, raw_size)
                else:
                    raw = pjs_decompress(packed, raw_size)
                actual_crc = zlib.crc32(raw) & 0xFFFFFFFF
                if actual_crc != expected_crc:
                    raise ValueError(f"파일 검증에 실패했습니다: {name}")
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, "wb") as out:
                    out.write(raw)
            else:
                raise ValueError("알 수 없는 PJS 항목 유형입니다.")

            if progress_callback:
                progress_callback(int(index * 100 / total), index, total)


# -------------------- GUI --------------------

class PJSCompressorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PJS / ZIP 압축 관리자")
        self.root.geometry("700x470")
        self.root.minsize(660, 440)
        self.source_var = tk.StringVar()
        self.output_var = tk.StringVar(value="archive.zip")
        self.mode_var = tk.StringVar(value="compress")
        self.format_var = tk.StringVar(value="zip")
        self.status_var = tk.StringVar(value="대기 중...")
        self.busy = False
        self.build_ui()

    def build_ui(self):
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)

        mode_frame = ttk.LabelFrame(outer, text="1. 작업 선택", padding=8)
        mode_frame.pack(fill="x", pady=(0, 10))
        ttk.Radiobutton(mode_frame, text="압축", variable=self.mode_var, value="compress",
                        command=self.mode_changed).pack(side="left", padx=(4, 18))
        ttk.Radiobutton(mode_frame, text="압축 해제", variable=self.mode_var, value="extract",
                        command=self.mode_changed).pack(side="left", padx=4)

        source_frame = ttk.LabelFrame(outer, text="2. 파일 또는 폴더 선택", padding=10)
        source_frame.pack(fill="x", pady=(0, 10))
        source_frame.columnconfigure(0, weight=1)
        self.source_entry = ttk.Entry(source_frame, textvariable=self.source_var)
        self.source_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6), ipady=4)
        ttk.Button(source_frame, text="파일 선택", width=12, command=self.browse_file).grid(
            row=0, column=1, padx=(0, 5), sticky="ew")
        ttk.Button(source_frame, text="폴더 선택", width=12, command=self.browse_folder).grid(
            row=0, column=2, sticky="ew")
        self.source_entry.drop_target_register(DND_FILES)
        self.source_entry.dnd_bind("<<Drop>>", self.drop_path)
        source_frame.drop_target_register(DND_FILES)
        source_frame.dnd_bind("<<Drop>>", self.drop_path)

        format_frame = ttk.LabelFrame(outer, text="3. 압축 형식", padding=8)
        format_frame.pack(fill="x", pady=(0, 10))
        ttk.Radiobutton(format_frame, text="ZIP (일반 호환)", variable=self.format_var,
                        value="zip").pack(side="left", padx=(4, 18))
        ttk.Radiobutton(format_frame, text="PJS (전용 무손실 포맷)", variable=self.format_var,
                        value="pjs").pack(side="left", padx=4)

        output_frame = ttk.LabelFrame(outer, text="4. 저장 파일명 또는 압축 해제 폴더", padding=10)
        output_frame.pack(fill="x", pady=(0, 10))
        output_frame.columnconfigure(0, weight=1)
        self.output_entry = ttk.Entry(output_frame, textvariable=self.output_var)
        self.output_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6), ipady=4)
        self.output_button = ttk.Button(output_frame, text="위치 선택", width=14,
                                        command=self.choose_output)
        self.output_button.grid(row=0, column=1, sticky="ew")

        action_frame = ttk.Frame(outer)
        action_frame.pack(fill="x", pady=(0, 7))
        ttk.Label(action_frame, textvariable=self.status_var).pack(side="left", fill="x", expand=True)
        self.run_button = ttk.Button(action_frame, text="실행", width=14, command=self.start)
        self.run_button.pack(side="right")

        self.progress = ttk.Progressbar(outer, maximum=100, mode="determinate")
        self.progress.pack(fill="x", pady=(0, 8))
        ttk.Label(
            outer,
            text="PJS2는 파일명 기반 데이터 변환을 사용합니다. 이는 분석 방해용 난독화이며 암호화나 보안 보장은 아닙니다.",
            foreground="#666666", wraplength=650
        ).pack(anchor="w", pady=(4, 0))
        self.mode_changed()

    def mode_changed(self):
        if self.mode_var.get() == "compress":
            self.output_button.configure(text="저장 위치 선택")
            self.run_button.configure(text="압축 실행")
            self.format_frame_state(True)
        else:
            self.output_button.configure(text="폴더 선택")
            self.run_button.configure(text="압축 해제")
            # Format radio stays enabled: selected format tells which archive to read.
            self.format_frame_state(True)

    def format_frame_state(self, enabled):
        # ttk radiobuttons remain selectable; extraction validates actual file signature/extension.
        pass

    def browse_file(self):
        if self.mode_var.get() == "extract":
            path = filedialog.askopenfilename(
                title="압축 파일 선택",
                filetypes=[("압축 파일", "*.zip *.pjs"), ("모든 파일", "*.*")]
            )
        else:
            path = filedialog.askopenfilename(title="압축할 파일 선택")
        if path:
            self.source_var.set(path)
            if self.mode_var.get() == "compress":
                self.output_var.set(os.path.splitext(os.path.basename(path))[0] +
                                    (".pjs" if self.format_var.get() == "pjs" else ".zip"))
            else:
                self.output_var.set(os.path.splitext(path)[0] + "_압축해제")

    def browse_folder(self):
        if self.mode_var.get() == "extract":
            messagebox.showinfo("안내", "압축 해제할 파일은 '파일 선택'으로 지정해주세요.")
            return
        path = filedialog.askdirectory(title="압축할 폴더 선택")
        if path:
            self.source_var.set(path)
            self.output_var.set(os.path.basename(os.path.normpath(path)) +
                                (".pjs" if self.format_var.get() == "pjs" else ".zip"))

    def drop_path(self, event):
        try:
            paths = self.root.tk.splitlist(event.data)
        except tk.TclError:
            messagebox.showerror("오류", "끌어다 놓은 경로를 읽을 수 없습니다.")
            return
        if len(paths) != 1:
            messagebox.showwarning("알림", "한 번에 파일 또는 폴더 하나만 선택해주세요.")
            return
        path = paths[0]
        if not os.path.exists(path):
            messagebox.showerror("오류", "선택한 경로가 존재하지 않습니다.")
            return
        if self.mode_var.get() == "extract" and not os.path.isfile(path):
            messagebox.showwarning("알림", "압축 해제 모드에서는 ZIP 또는 PJS 파일을 놓아주세요.")
            return
        self.source_var.set(path)
        if self.mode_var.get() == "compress":
            base = os.path.basename(os.path.normpath(path))
            self.output_var.set(base + (".pjs" if self.format_var.get() == "pjs" else ".zip"))
        else:
            self.output_var.set(os.path.splitext(path)[0] + "_압축해제")

    def choose_output(self):
        if self.mode_var.get() == "extract":
            folder = filedialog.askdirectory(title="압축 해제할 폴더 선택")
            if folder:
                self.output_var.set(folder)
            return
        extension = ".pjs" if self.format_var.get() == "pjs" else ".zip"
        initial = self.output_var.get().strip() or ("archive" + extension)
        selected = filedialog.asksaveasfilename(
            title="압축 파일 저장 위치 선택",
            defaultextension=extension,
            initialfile=os.path.basename(initial),
            filetypes=[("PJS 파일", "*.pjs"), ("ZIP 파일", "*.zip"), ("모든 파일", "*.*")]
        )
        if selected:
            self.output_var.set(selected)

    def start(self):
        if self.busy:
            return
        source = self.source_var.get().strip().strip('"')
        output = self.output_var.get().strip().strip('"')
        if not source or not os.path.exists(source):
            messagebox.showerror("오류", "유효한 파일 또는 폴더를 선택해주세요.")
            return
        if not output:
            messagebox.showerror("오류", "저장 파일명 또는 압축 해제 폴더를 지정해주세요.")
            return

        mode = self.mode_var.get()
        fmt = self.format_var.get()
        if mode == "compress":
            ext = ".pjs" if fmt == "pjs" else ".zip"
            if not output.lower().endswith(ext):
                output += ext
            output = os.path.abspath(os.path.expanduser(output))
            if os.path.isdir(source):
                try:
                    if os.path.commonpath([os.path.abspath(source), output]) == os.path.abspath(source):
                        messagebox.showerror("저장 위치 오류", "압축 결과 파일을 대상 폴더 안에 저장할 수 없습니다.")
                        return
                except ValueError:
                    pass
            if os.path.exists(output) and not messagebox.askyesno(
                "덮어쓰기 확인", f"파일이 이미 존재합니다.\n{output}\n덮어쓰시겠습니까?"
            ):
                return
            if not os.path.isdir(os.path.dirname(output) or os.getcwd()):
                messagebox.showerror("오류", "저장 폴더가 존재하지 않습니다.")
                return
        else:
            if not os.path.isfile(source):
                messagebox.showerror("오류", "압축 해제할 ZIP 또는 PJS 파일을 선택해주세요.")
                return
            output = os.path.abspath(os.path.expanduser(output))
            if os.path.exists(output) and os.listdir(output):
                if not messagebox.askyesno("폴더 확인", "선택한 압축 해제 폴더가 비어 있지 않습니다. 계속하시겠습니까?"):
                    return
            if os.path.splitext(source)[1].lower() == ".pjs":
                fmt = "pjs"
            elif os.path.splitext(source)[1].lower() == ".zip":
                fmt = "zip"
            else:
                messagebox.showerror("형식 오류", "파일 확장자가 .zip 또는 .pjs인지 확인해주세요.")
                return

        self.busy = True
        self.run_button.configure(state="disabled")
        self.progress.configure(value=0)
        self.status_var.set("작업 준비 중...")
        threading.Thread(target=self.worker, args=(mode, fmt, source, output), daemon=True).start()

    def worker(self, mode, fmt, source, output):
        try:
            callback = lambda pct, cur, total: self.root.after(
                0, self.update_progress, pct, cur, total
            )
            if mode == "compress":
                if fmt == "pjs":
                    write_pjs(source, output, callback)
                else:
                    import zipfile
                    entries = list(iter_source_entries(source))
                    total = max(len(entries), 1)
                    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
                        for index, (arcname, fullpath, is_dir) in enumerate(entries, 1):
                            arcname = arcname.replace("\\", "/")
                            if is_dir:
                                zf.writestr(arcname if arcname.endswith("/") else arcname + "/", "")
                            else:
                                zf.write(fullpath, arcname)
                            callback(int(index * 100 / total), index, total)
                self.root.after(0, self.done, f"압축이 완료되었습니다.\n\n저장 경로:\n{output}")
            else:
                os.makedirs(output, exist_ok=True)
                if fmt == "pjs":
                    extract_pjs(source, output, callback)
                else:
                    import zipfile
                    with zipfile.ZipFile(source, "r") as zf:
                        infos = zf.infolist()
                        total = max(len(infos), 1)
                        dest_abs = os.path.abspath(output)
                        for index, info in enumerate(infos, 1):
                            out_path = safe_output_path(dest_abs, info.filename)
                            if info.is_dir():
                                os.makedirs(out_path, exist_ok=True)
                            else:
                                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                                with zf.open(info, "r") as src, open(out_path, "wb") as dst:
                                    while True:
                                        chunk = src.read(1024 * 1024)
                                        if not chunk:
                                            break
                                        dst.write(chunk)
                            callback(int(index * 100 / total), index, total)
                self.root.after(0, self.done, f"압축 해제가 완료되었습니다.\n\n저장 폴더:\n{output}")
        except Exception as exc:
            self.root.after(0, self.failed, str(exc))

    def update_progress(self, percent, current, total):
        self.progress.configure(value=percent)
        self.status_var.set(f"작업 중... {percent}% ({current}/{total})")

    def done(self, text):
        self.busy = False
        self.run_button.configure(state="normal")
        self.progress.configure(value=100)
        self.status_var.set("완료")
        messagebox.showinfo("완료", text)

    def failed(self, error):
        self.busy = False
        self.run_button.configure(state="normal")
        self.status_var.set("오류 발생")
        messagebox.showerror("오류", f"작업 중 오류가 발생했습니다:\n{error}")


def main():
    root = TkinterDnD.Tk()
    PJSCompressorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
