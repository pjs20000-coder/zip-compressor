# PJSCompressor — 재개발 진단판

Windows용 ZIP/PJS 압축·압축 해제 GUI입니다. 기존 PJS1 읽기 호환성과 PJS2 생성 방식을 유지하는 것을 목표로 합니다.

## 현재 변경 사항
- 기존 PJS/ZIP 코덱 및 화면 기능을 유지했습니다.
- 진단 로그 기록을 GUI 및 `tkinterdnd2` import 이전으로 이동했습니다.
- `tkinterdnd2` 또는 네이티브 드래그 앤 드롭 초기화에 실패해도 기본 파일 선택 GUI를 시작하도록 대체 경로를 추가했습니다.
- 치명적 시작 오류를 로그에 기록하고, 가능한 경우 오류 대화상자에도 표시합니다.
- GitHub Actions는 콘솔이 활성화된 진단 EXE를 생성합니다.

## 실행
```powershell
python -m pip install -r requirements.txt
python main.py
```

## 진단 로그
Windows에서 다음 위치에 기록됩니다:
`%LOCALAPPDATA%\PJSCompressor-diagnostic.log`

## GitHub Actions
저장소의 `main` 브랜치에 올리거나 Actions에서 **Build Windows EXE**를 수동 실행한 뒤, `PJSCompressor-Windows-Diagnostic` artifact를 내려받으세요. 이 버전은 원인 확인용 콘솔이 포함되어 있습니다.

## 주의
- 현재 실행 환경은 Windows가 아니므로 실제 Windows GUI 표시, Tkinter/Tcl 배포, 드래그 앤 드롭 동작은 여기서 직접 검증할 수 없습니다.
- PJS2의 파일명 기반 바이트 변환은 암호화가 아니라 난독화입니다. 민감한 데이터를 보호하는 용도로 사용하지 마세요.
