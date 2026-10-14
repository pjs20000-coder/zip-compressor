Python
import os
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
import zipfile


def compress_path(target_path, output_filename, status_label):
  """지정한 파일 또는 폴더를 ZIP 파일로 압축합니다."""
  try:
    if not target_path or not os.path.exists(target_path):
      messagebox.showerror('오류', '유효한 파일 또는 폴더를 선택해주세요.')
      return

    if not output_filename:
      messagebox.showerror('오류', '저장할 압축 파일명을 입력해주세요.')
      return

    if not output_filename.endswith('.zip'):
      output_filename += '.zip'

    status_label.config(text='압축 진행 중...')
    root.update_idletasks()

    with zipfile.ZipFile(
        output_filename, 'w', zipfile.ZIP_DEFLATED
    ) as zipf:
      if os.path.isfile(target_path):
        zipf.write(target_path, os.path.basename(target_path))
      elif os.path.isdir(target_path):
        parent_dir = os.path.dirname(target_path)
        for root_dir, dirs, files in os.walk(target_path):
          for file in files:
            file_path = os.path.join(root_dir, file)
            arcname = os.path.relpath(file_path, parent_dir)
            zipf.write(file_path, arcname)

    status_label.config(text='압축 완료!')
    messagebox.showinfo(
        '성공', f'압축이 성공적으로 완료되었습니다!\n저장 경로: {output_filename}'
    )
  except Exception as e:
    status_label.config(text='오류 발생')
    messagebox.showerror('오류', f'압축 중 오류가 발생했습니다: {e}')


def main():
  global root
  # 드래그 앤 드랍을 지원하는 창 생성
  root = TkinterDnD.Tk()
  root.title('간단한 파일/폴더 압축 프로그램')
  root.geometry('500x380')
  root.resizable(False, False)

  # 1. 파일/폴더 선택 영역
  frame_path = tk.LabelFrame(
      root, text=' 1. 압축할 파일 또는 폴더 ', padx=10, pady=10
  )
  frame_path.pack(fill='both', padx=15, pady=15)

  entry_path = tk.Entry(frame_path, width=45)
  entry_path.pack(side='left', padx=5, ipady=3)

  def browse_file():
    path = filedialog.askopenfilename()
    if path:
      entry_path.delete(0, tk.END)
      entry_path.insert(0, path)

  def browse_folder():
    path = filedialog.askdirectory()
    if path:
      entry_path.delete(0, tk.END)
      entry_path.insert(0, path)

  btn_file = tk.Button(frame_path, text='파일 선택', width=8, command=browse_file)
  btn_file.pack(side='left', padx=2)

  btn_folder = tk.Button(
      frame_path, text='폴더 선택', width=8, command=browse_folder
  )
  btn_folder.pack(side='left', padx=2)

  # 드래그 앤 드랍 이벤트 핸들러
  def drop(event):
    # 드래그 앤 드랍 시 경로에 중괄호가 붙는 현상 제거
    path = event.data.strip('{}')
    entry_path.delete(0, tk.END)
    entry_path.insert(0, path)

  # 입력창 및 프레임에 드래그 앤 드랍 등록
  entry_path.drop_target_register(DND_FILES)
  entry_path.dnd_bind('<<Drop>>', drop)
  frame_path.drop_target_register(DND_FILES)
  frame_path.dnd_bind('<<Drop>>', drop)

  # 2. 저장 파일명 입력 영역
  frame_output = tk.LabelFrame(
      root, text=' 2. 저장할 압축 파일명 입력 ', padx=10, pady=10
  )
  frame_output.pack(fill='both', padx=15, pady=5)

  entry_output = tk.Entry(frame_output, width=54)
  entry_output.pack(side='left', padx=5, ipady=3)
  entry_output.insert(0, 'archive.zip')

  # 3. 실행 및 상태 표시 영역
  frame_action = tk.Frame(root, pady=10)
  frame_action.pack(fill='both', padx=15)

  status_label = tk.Label(frame_action, text='대기 중...', fg='gray')
  status_label.pack(side='left', padx=5)

  btn_run = tk.Button(
      frame_action,
      text='압축 실행',
      bg='#007bff',
      fg='white',
      width=12,
      font=('Arial', 10, 'bold'),
      command=lambda: compress_path(
          entry_path.get().strip(), entry_output.get().strip(), status_label
      ),
  )
  btn_run.pack(side='right', padx=5)

  # 안내 문구
  lbl_guide = tk.Label(
      root,
      text='💡 팁: 압축할 파일이나 폴더를 위 상단 칸에 마우스로 드래그하여 놓을 수도 있습니다.',
      fg='#666',
      font=('Arial', 9),
  )
  lbl_guide.pack(pady=5)

  root.mainloop()


if __name__ == '__main__':
  main()