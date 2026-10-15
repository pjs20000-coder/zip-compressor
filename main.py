from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

from core import compress_to_pjs, decompress_pjs

APP_TITLE = "PJSCompressor PJS4 — 비밀번호 보호"

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("690x410")
        self.root.minsize(620, 380)
        self.mode = tk.StringVar(value="compress")
        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.password = tk.StringVar()
        self.confirm_password = tk.StringVar()
        self.status = tk.StringVar(value="파일 또는 폴더를 선택해 주세요.")
        self.events: queue.Queue = queue.Queue()
        self._build()
        self.root.after(100, self._poll_events)

    def _build(self):
        frame = ttk.Frame(self.root, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="PJSCompressor PJS4", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 5))
        ttk.Label(frame, text="비밀번호 기반 암호화 · 기존 PJS1/PJS2/PJS3와 호환되지 않는 새 형식", foreground="#555555").grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 14))
        mode_frame = ttk.Frame(frame)
        mode_frame.grid(row=2, column=0, columnspan=3, sticky="w", pady=(0, 12))
        ttk.Radiobutton(mode_frame, text="압축 + 암호화", value="compress", variable=self.mode, command=self._mode_changed).pack(side="left", padx=(0, 18))
        ttk.Radiobutton(mode_frame, text="복호화 + 압축 해제", value="decompress", variable=self.mode, command=self._mode_changed).pack(side="left")
        ttk.Label(frame, text="입력 파일 / 폴더").grid(row=3, column=0, sticky="w", pady=5)
        ttk.Entry(frame, textvariable=self.input_path).grid(row=3, column=1, sticky="ew", padx=8, pady=5)
        self.input_file_btn = ttk.Button(frame, text="파일 선택", command=self._choose_input_file)
        self.input_file_btn.grid(row=3, column=2, sticky="ew", pady=5)
        self.input_folder_btn = ttk.Button(frame, text="폴더 선택", command=self._choose_input_folder)
        self.input_folder_btn.grid(row=4, column=2, sticky="ew", pady=5)
        ttk.Label(frame, text="출력 위치").grid(row=5, column=0, sticky="w", pady=5)
        ttk.Entry(frame, textvariable=self.output_path).grid(row=5, column=1, sticky="ew", padx=8, pady=5)
        self.output_btn = ttk.Button(frame, text="저장 위치 선택", command=self._choose_output)
        self.output_btn.grid(row=5, column=2, sticky="ew", pady=5)
        ttk.Label(frame, text="비밀번호").grid(row=6, column=0, sticky="w", pady=5)
        ttk.Entry(frame, textvariable=self.password, show="*").grid(row=6, column=1, columnspan=2, sticky="ew", padx=8, pady=5)
        self.confirm_label = ttk.Label(frame, text="비밀번호 확인")
        self.confirm_label.grid(row=7, column=0, sticky="w", pady=5)
        self.confirm_entry = ttk.Entry(frame, textvariable=self.confirm_password, show="*")
        self.confirm_entry.grid(row=7, column=1, columnspan=2, sticky="ew", padx=8, pady=5)
        ttk.Label(frame, text="권장: 16자 이상의 고유한 비밀번호. 분실하면 복원할 수 없습니다.", foreground="#8a3b12").grid(row=8, column=0, columnspan=3, sticky="w", pady=(5, 10))
        self.run_btn = ttk.Button(frame, text="압축 및 암호화", command=self._run)
        self.run_btn.grid(row=9, column=0, sticky="ew", pady=(2, 10))
        ttk.Label(frame, textvariable=self.status, wraplength=600).grid(row=10, column=0, columnspan=3, sticky="w", pady=5)
        frame.columnconfigure(1, weight=1)
        self._mode_changed()

    def _mode_changed(self):
        compressing = self.mode.get() == "compress"
        self.run_btn.configure(text="압축 및 암호화" if compressing else "복호화 및 압축 해제")
        if compressing:
            self.confirm_label.grid()
            self.confirm_entry.grid()
            self.input_folder_btn.configure(state="normal")
        else:
            self.confirm_label.grid_remove()
            self.confirm_entry.grid_remove()
            self.input_folder_btn.configure(state="disabled")
        self.output_path.set("")
        self.status.set("압축할 파일/폴더를 선택해 주세요." if compressing else "복원할 PJS4 파일을 선택해 주세요.")

    def _choose_input_file(self):
        if self.mode.get() == "decompress":
            path = filedialog.askopenfilename(title="PJS4 파일 선택", filetypes=[("PJS4 files", "*.pjs"), ("All files", "*.*")])
        else:
            path = filedialog.askopenfilename(title="압축할 파일 선택")
        if path:
            self.input_path.set(path)
            if self.mode.get() == "compress":
                p = Path(path)
                self.output_path.set(str(p.with_name(p.name + ".pjs")))
            else:
                self.output_path.set(str(Path(path).with_suffix("")))

    def _choose_input_folder(self):
        path = filedialog.askdirectory(title="압축할 폴더 선택")
        if path:
            self.input_path.set(path)
            p = Path(path)
            self.output_path.set(str(p.with_name(p.name + ".pjs")))

    def _choose_output(self):
        if self.mode.get() == "compress":
            path = filedialog.asksaveasfilename(title="PJS4 저장 위치", defaultextension=".pjs", filetypes=[("PJS4 files", "*.pjs")])
        else:
            path = filedialog.askdirectory(title="압축 해제 폴더 선택")
        if path:
            self.output_path.set(path)

    def _run(self):
        source = self.input_path.get().strip()
        output = self.output_path.get().strip()
        password = self.password.get()
        if not source or not output:
            messagebox.showwarning("입력 필요", "입력 파일/폴더와 출력 위치를 선택해 주세요.")
            return
        if not password:
            messagebox.showwarning("비밀번호 필요", "비밀번호를 입력해 주세요.")
            return
        if self.mode.get() == "compress":
            if password != self.confirm_password.get():
                messagebox.showwarning("비밀번호 확인", "두 비밀번호가 일치하지 않습니다.")
                return
            if len(password) < 12:
                messagebox.showwarning("비밀번호가 짧습니다", "최소 12자 이상이 필요합니다. 16자 이상의 고유한 문구를 권장합니다.")
                return
        if self.mode.get() == "decompress" and Path(output).exists() and any(Path(output).iterdir()):
            if not messagebox.askyesno("폴더 확인", "출력 폴더가 비어 있지 않습니다. 기존 파일은 덮어쓰지 않으며, 충돌 시 작업이 중단될 수 있습니다. 계속하시겠습니까?"):
                return
        self.run_btn.configure(state="disabled")
        self.status.set("작업 중입니다. 큰 파일은 시간이 걸릴 수 있습니다.")
        action = self.mode.get()
        threading.Thread(target=self._worker, args=(action, source, output, password), daemon=True).start()

    def _worker(self, action, source, output, password):
        try:
            if action == "compress":
                result = compress_to_pjs(source, output, password)
                self.events.put((True, f"암호화 완료: {result}"))
            else:
                result = decompress_pjs(source, output, password)
                self.events.put((True, f"복원 완료: {result}"))
        except Exception as exc:
            self.events.put((False, str(exc)))

    def _poll_events(self):
        try:
            while True:
                success, message = self.events.get_nowait()
                self.run_btn.configure(state="normal")
                self.status.set(message)
                if success:
                    messagebox.showinfo("완료", message)
                else:
                    messagebox.showerror("작업 실패", message)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

def main():
    root = tk.Tk()
    App(root)
    root.mainloop()

if __name__ == "__main__":
    main()
