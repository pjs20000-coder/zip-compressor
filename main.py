"""Fresh PJSCompressor GUI using only Python's standard library."""
from __future__ import annotations
import os, sys, traceback, logging, threading, queue
from pathlib import Path

APP_NAME = 'PJSCompressor'

def configure_logging():
    base = os.environ.get('LOCALAPPDATA') or str(Path.home())
    log_dir = Path(base) / APP_NAME
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / 'diagnostic.log'
    except Exception:
        log_file = Path.cwd() / 'PJSCompressor-diagnostic.log'
    logging.basicConfig(filename=str(log_file), level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s', encoding='utf-8')
    logging.info('=== startup === Python=%s frozen=%s exe=%s', sys.version, getattr(sys,'frozen',False), sys.executable)
    return log_file

LOG_PATH = configure_logging()

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    import core
except BaseException:
    logging.exception('Import/init failed')
    raise

class App:
    def __init__(self, root):
        self.root = root
        root.title('PJSCompressor — PJS / ZIP 압축 관리자')
        root.geometry('760x520'); root.minsize(680,470)
        self.events = queue.Queue(); self.busy = False
        self.mode = tk.StringVar(value='compress')
        self.format = tk.StringVar(value='zip')
        self.source = tk.StringVar()
        self.output = tk.StringVar(value='archive.zip')
        self.status = tk.StringVar(value='준비')
        self._build()
        root.after(100, self._poll)
        logging.info('GUI initialized')

    def _build(self):
        outer = ttk.Frame(self.root, padding=16); outer.pack(fill='both', expand=True)
        mode_box = ttk.LabelFrame(outer, text='1. 작업', padding=10); mode_box.pack(fill='x', pady=(0,10))
        ttk.Radiobutton(mode_box,text='압축',variable=self.mode,value='compress',command=self._mode_changed).pack(side='left',padx=(0,20))
        ttk.Radiobutton(mode_box,text='압축 해제',variable=self.mode,value='extract',command=self._mode_changed).pack(side='left')
        src_box = ttk.LabelFrame(outer,text='2. 원본 파일 또는 폴더',padding=10); src_box.pack(fill='x',pady=(0,10)); src_box.columnconfigure(0,weight=1)
        ttk.Entry(src_box,textvariable=self.source).grid(row=0,column=0,sticky='ew',padx=(0,8),ipady=4)
        ttk.Button(src_box,text='파일 선택',command=self._browse_file).grid(row=0,column=1,padx=(0,6))
        ttk.Button(src_box,text='폴더 선택',command=self._browse_folder).grid(row=0,column=2)
        fmt_box=ttk.LabelFrame(outer,text='3. 형식',padding=10); fmt_box.pack(fill='x',pady=(0,10))
        ttk.Radiobutton(fmt_box,text='ZIP — 일반 호환',variable=self.format,value='zip',command=self._format_changed).pack(side='left',padx=(0,20))
        ttk.Radiobutton(fmt_box,text='PJS — 전용 무손실 형식',variable=self.format,value='pjs',command=self._format_changed).pack(side='left')
        out_box=ttk.LabelFrame(outer,text='4. 저장 파일명 또는 압축 해제 폴더',padding=10); out_box.pack(fill='x',pady=(0,12)); out_box.columnconfigure(0,weight=1)
        ttk.Entry(out_box,textvariable=self.output).grid(row=0,column=0,sticky='ew',padx=(0,8),ipady=4)
        ttk.Button(out_box,text='위치 선택',command=self._choose_output).grid(row=0,column=1)
        bottom=ttk.Frame(outer); bottom.pack(fill='x',pady=(0,8))
        ttk.Label(bottom,textvariable=self.status).pack(side='left',fill='x',expand=True)
        self.run_btn=ttk.Button(bottom,text='압축 실행',command=self._start); self.run_btn.pack(side='right')
        self.progress=ttk.Progressbar(outer,maximum=100,mode='determinate'); self.progress.pack(fill='x',pady=(0,12))
        ttk.Label(outer,text='오류 진단 로그: '+str(LOG_PATH),wraplength=710,foreground='#555').pack(anchor='w')
        ttk.Label(outer,text='PJS 형식은 암호화가 아닙니다. 중요한 원본은 별도로 백업하세요.',wraplength=710,foreground='#555').pack(anchor='w',pady=(8,0))

    def _mode_changed(self):
        if self.mode.get()=='compress':
            self.run_btn.configure(text='압축 실행')
        else:
            self.run_btn.configure(text='압축 해제')
        self._suggest_output()

    def _format_changed(self): self._suggest_output()

    def _suggest_output(self):
        src=self.source.get().strip().strip('"')
        if not src: return
        if self.mode.get()=='compress':
            ext='.pjs' if self.format.get()=='pjs' else '.zip'
            base=os.path.basename(os.path.normpath(src))
            if os.path.isfile(src): base=os.path.splitext(base)[0]
            self.output.set(base+ext)
        else:
            self.output.set(os.path.splitext(src)[0]+'_압축해제')

    def _browse_file(self):
        if self.mode.get()=='extract':
            path=filedialog.askopenfilename(title='압축 파일 선택',filetypes=[('압축 파일','*.zip *.pjs'),('모든 파일','*.*')])
        else: path=filedialog.askopenfilename(title='압축할 파일 선택')
        if path: self.source.set(path); self._suggest_output()

    def _browse_folder(self):
        if self.mode.get()=='extract':
            messagebox.showinfo('안내','압축 해제할 파일을 선택해 주세요.'); return
        path=filedialog.askdirectory(title='압축할 폴더 선택')
        if path: self.source.set(path); self._suggest_output()

    def _choose_output(self):
        if self.mode.get()=='extract':
            path=filedialog.askdirectory(title='압축 해제 폴더 선택')
        else:
            ext='.pjs' if self.format.get()=='pjs' else '.zip'
            path=filedialog.asksaveasfilename(title='압축 파일 저장 위치',defaultextension=ext,initialfile=os.path.basename(self.output.get() or 'archive'+ext),filetypes=[('PJS 파일','*.pjs'),('ZIP 파일','*.zip'),('모든 파일','*.*')])
        if path: self.output.set(path)

    def _start(self):
        if self.busy: return
        source=os.path.abspath(os.path.expanduser(self.source.get().strip().strip('"')))
        output=os.path.expanduser(self.output.get().strip().strip('"'))
        if not source or not os.path.exists(source): messagebox.showerror('입력 확인','유효한 원본 파일 또는 폴더를 선택해 주세요.'); return
        if not output: messagebox.showerror('입력 확인','출력 경로를 입력해 주세요.'); return
        mode=self.mode.get(); fmt=self.format.get()
        if mode=='compress':
            ext='.pjs' if fmt=='pjs' else '.zip'
            if not output.lower().endswith(ext): output+=ext
            output=os.path.abspath(output)
            if os.path.isdir(source):
                try:
                    if os.path.commonpath([source,output])==source: messagebox.showerror('경로 확인','압축 결과를 원본 폴더 내부에 저장할 수 없습니다.'); return
                except ValueError: pass
            if not os.path.isdir(os.path.dirname(output)): messagebox.showerror('경로 확인','출력 폴더가 존재하지 않습니다.'); return
            if os.path.exists(output) and not messagebox.askyesno('덮어쓰기 확인',f'파일이 이미 있습니다. 덮어쓰시겠습니까?\n{output}'): return
        else:
            if not os.path.isfile(source): messagebox.showerror('입력 확인','압축 해제할 ZIP 또는 PJS 파일을 선택해 주세요.'); return
            ext=os.path.splitext(source)[1].lower()
            if ext not in ('.zip','.pjs'): messagebox.showerror('형식 확인','파일 확장자가 .zip 또는 .pjs인지 확인해 주세요.'); return
            fmt=ext[1:]; output=os.path.abspath(output)
            if os.path.exists(output) and os.listdir(output) and not messagebox.askyesno('폴더 확인','대상 폴더가 비어 있지 않습니다. 계속하시겠습니까?'): return
        self.busy=True; self.run_btn.configure(state='disabled'); self.progress['value']=0; self.status.set('작업 준비 중…')
        logging.info('start mode=%s format=%s source=%s output=%s',mode,fmt,source,output)
        threading.Thread(target=self._worker,args=(mode,fmt,source,output),daemon=True).start()

    def _worker(self,mode,fmt,source,output):
        try:
            def progress(pct,cur,total): self.events.put(('progress',pct,cur,total))
            if mode=='compress':
                (core.create_pjs if fmt=='pjs' else core.create_zip)(source,output,progress)
                self.events.put(('done',f'압축이 완료되었습니다.\n\n저장 위치:\n{output}'))
            else:
                os.makedirs(output,exist_ok=True)
                (core.extract_pjs if fmt=='pjs' else core.extract_zip)(source,output,progress)
                self.events.put(('done',f'압축 해제가 완료되었습니다.\n\n저장 위치:\n{output}'))
        except BaseException as exc:
            logging.exception('operation failed')
            self.events.put(('error',str(exc),traceback.format_exc()))

    def _poll(self):
        try:
            while True:
                event=self.events.get_nowait(); kind=event[0]
                if kind=='progress':
                    _,pct,cur,total=event; self.progress['value']=pct; self.status.set(f'작업 중… {pct}% ({cur}/{total})')
                elif kind=='done':
                    self.busy=False; self.run_btn.configure(state='normal'); self.progress['value']=100; self.status.set('완료'); messagebox.showinfo('완료',event[1])
                elif kind=='error':
                    self.busy=False; self.run_btn.configure(state='normal'); self.status.set('오류 발생'); messagebox.showerror('작업 오류',event[1]+'\n\n진단 로그에 상세 내용이 기록되었습니다.')
        except queue.Empty: pass
        self.root.after(100,self._poll)


def main():
    logging.info('enter main')
    root=tk.Tk()
    App(root)
    logging.info('enter mainloop')
    root.mainloop()
    logging.info('mainloop ended')

if __name__=='__main__':
    try: main()
    except BaseException:
        logging.exception('fatal startup error')
        try:
            import tkinter.messagebox as mb
            mb.showerror('PJSCompressor 시작 오류',f'프로그램을 시작하지 못했습니다.\n진단 로그: {LOG_PATH}')
        except BaseException: pass
        raise
