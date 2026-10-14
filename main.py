import os
import threading
import zipfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinterdnd2 import DND_FILES, TkinterDnD


def unique_arcname(path, base_dir):
    """Return a ZIP path relative to the selected folder's parent."""
    return os.path.relpath(path, base_dir)


class ZipCompressorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("간단한 파일/폴더 압축 프로그램")
        self.root.geometry("650x430")
        self.root.minsize(620, 410)
        self.root.resizable(True, True)

        self.target_var = tk.StringVar()
        self.output_var = tk.StringVar(value="archive.zip")
        self.status_var = tk.StringVar(value="대기 중...")
        self.busy = False

        self._build_ui()

    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)

        frame_path = ttk.LabelFrame(
            outer, text="1. 압축할 파일 또는 폴더", padding=10
        )
        frame_path.pack(fill="x", pady=(0, 12))
        frame_path.columnconfigure(0, weight=1)

        self.entry_path = ttk.Entry(frame_path, textvariable=self.target_var)
        self.entry_path.grid(row=0, column=0, sticky="ew", padx=(0, 6), ipady=4)

        ttk.Button(
            frame_path, text="파일 선택", command=self.browse_file, width=12
        ).grid(row=0, column=1, padx=(0, 5), sticky="ew")

        ttk.Button(
            frame_path, text="폴더 선택", command=self.browse_folder, width=12
        ).grid(row=0, column=2, sticky="ew")

        # Drag-and-drop support. splitlist handles paths with spaces/braces.
        self.entry_path.drop_target_register(DND_FILES)
        self.entry_path.dnd_bind("<<Drop>>", self.drop_path)
        frame_path.drop_target_register(DND_FILES)
        frame_path.dnd_bind("<<Drop>>", self.drop_path)

        frame_output = ttk.LabelFrame(
            outer, text="2. 저장할 압축 파일", padding=10
        )
        frame_output.pack(fill="x", pady=(0, 12))
        frame_output.columnconfigure(0, weight=1)

        self.entry_output = ttk.Entry(frame_output, textvariable=self.output_var)
        self.entry_output.grid(row=0, column=0, sticky="ew", padx=(0, 6), ipady=4)
        ttk.Button(
            frame_output, text="저장 위치 선택", command=self.choose_output,
            width=14
        ).grid(row=0, column=1, sticky="ew")

        frame_action = ttk.Frame(outer)
        frame_action.pack(fill="x", pady=(2, 8))
        self.status_label = ttk.Label(
            frame_action, textvariable=self.status_var, foreground="#555555"
        )
        self.status_label.pack(side="left", fill="x", expand=True)

        self.run_button = ttk.Button(
            frame_action, text="압축 실행", command=self.start_compression,
            width=14
        )
        self.run_button.pack(side="right")

        self.progress = ttk.Progressbar(outer, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(0, 8))

        guide = (
            "팁: 파일이나 폴더 하나를 위쪽 입력 칸으로 끌어다 놓을 수 있습니다.\n"
            "폴더 압축 시 폴더 이름을 포함한 구조로 저장됩니다."
        )
        ttk.Label(
            outer, text=guide, foreground="#666666", justify="left",
            wraplength=600
        ).pack(anchor="w", pady=(4, 0))

    def browse_file(self):
        path = filedialog.askopenfilename(title="압축할 파일 선택")
        if path:
            self.target_var.set(path)
            self._suggest_output_name(path)

    def browse_folder(self):
        path = filedialog.askdirectory(title="압축할 폴더 선택")
        if path:
            self.target_var.set(path)
            self._suggest_output_name(path)

    def _suggest_output_name(self, path):
        name = os.path.basename(os.path.normpath(path))
        if name:
            self.output_var.set(name + ".zip")

    def choose_output(self):
        target = self.target_var.get().strip()
        initial = self.output_var.get().strip() or "archive.zip"
        if not initial.lower().endswith(".zip"):
            initial += ".zip"

        initial_dir = os.path.dirname(initial) if os.path.dirname(initial) else None
        selected = filedialog.asksaveasfilename(
            title="압축 파일 저장 위치 선택",
            defaultextension=".zip",
            initialfile=os.path.basename(initial),
            initialdir=initial_dir,
            filetypes=[("ZIP 압축 파일", "*.zip")],
        )
        if selected:
            self.output_var.set(selected)

    def drop_path(self, event):
        try:
            paths = self.root.tk.splitlist(event.data)
        except tk.TclError:
            messagebox.showerror("드래그 앤 드롭 오류", "파일 경로를 읽을 수 없습니다.")
            return

        if len(paths) != 1:
            messagebox.showwarning(
                "알림", "한 번에 파일 또는 폴더 하나만 끌어다 놓아주세요."
            )
            return

        path = paths[0]
        if not os.path.exists(path):
            messagebox.showerror("오류", "선택한 파일 또는 폴더가 존재하지 않습니다.")
            return

        self.target_var.set(path)
        self._suggest_output_name(path)

    def start_compression(self):
        if self.busy:
            return

        target = self.target_var.get().strip().strip('"')
        output = self.output_var.get().strip().strip('"')

        if not target or not os.path.exists(target):
            messagebox.showerror("오류", "유효한 파일 또는 폴더를 선택해주세요.")
            return
        if not output:
            messagebox.showerror("오류", "저장할 ZIP 파일의 이름을 입력하거나 위치를 선택해주세요.")
            return

        if not output.lower().endswith(".zip"):
            output += ".zip"

        # If no folder was chosen, save to the current working directory.
        output = os.path.abspath(os.path.expanduser(output))
        target_abs = os.path.abspath(target)

        if os.path.isdir(target_abs):
            try:
                if os.path.commonpath([target_abs, output]) == target_abs:
                    messagebox.showerror(
                        "저장 위치 오류",
                        "압축 결과 ZIP 파일을 압축 대상 폴더 내부에 저장할 수 없습니다.\n"
                        "다른 저장 위치를 선택해주세요."
                    )
                    return
            except ValueError:
                pass

        if os.path.exists(output):
            overwrite = messagebox.askyesno(
                "파일 덮어쓰기 확인",
                f"같은 이름의 파일이 이미 있습니다.\n\n{output}\n\n덮어쓰시겠습니까?"
            )
            if not overwrite:
                return

        output_dir = os.path.dirname(output)
        if output_dir and not os.path.isdir(output_dir):
            messagebox.showerror("저장 위치 오류", "지정한 저장 폴더가 존재하지 않습니다.")
            return

        self.busy = True
        self.run_button.config(state="disabled")
        self.progress.configure(value=0, maximum=100)
        self.status_var.set("압축 준비 중...")

        thread = threading.Thread(
            target=self._compress_worker, args=(target_abs, output), daemon=True
        )
        thread.start()

    def _compress_worker(self, target, output):
        try:
            if os.path.isfile(target):
                files_to_add = [target]
                base_dir = os.path.dirname(target)
            else:
                base_dir = os.path.dirname(target)
                files_to_add = []
                for current, dirs, files in os.walk(target):
                    dirs.sort()
                    for filename in sorted(files):
                        full_path = os.path.join(current, filename)
                        # Never include the output ZIP in its own archive.
                        if os.path.abspath(full_path) != os.path.abspath(output):
                            files_to_add.append(full_path)

            total = max(len(files_to_add), 1)
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
                for index, full_path in enumerate(files_to_add, start=1):
                    if os.path.isfile(target):
                        arcname = os.path.basename(full_path)
                    else:
                        # Include the selected folder's name in the ZIP structure.
                        arcname = unique_arcname(full_path, base_dir)
                    zipf.write(full_path, arcname)
                    percent = int(index * 100 / total)
                    self.root.after(0, self._update_progress, percent, index, total)

            self.root.after(0, self._compression_done, output, len(files_to_add))
        except Exception as exc:
            self.root.after(0, self._compression_failed, str(exc))

    def _update_progress(self, percent, current, total):
        self.progress.configure(value=percent)
        self.status_var.set(f"압축 중... {percent}% ({current}/{total}개 파일)")

    def _compression_done(self, output, count):
        self.busy = False
        self.run_button.config(state="normal")
        self.progress.configure(value=100)
        self.status_var.set("압축 완료!")
        messagebox.showinfo(
            "성공",
            f"압축이 완료되었습니다.\n파일 수: {count}\n저장 경로: {output}"
        )

    def _compression_failed(self, error):
        self.busy = False
        self.run_button.config(state="normal")
        self.status_var.set("오류 발생")
        messagebox.showerror("압축 오류", f"압축 중 오류가 발생했습니다:\n{error}")


def main():
    root = TkinterDnD.Tk()
    ZipCompressorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
