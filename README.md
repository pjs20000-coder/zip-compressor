# PJSCompressor — Fresh Rebuild

새로 구성한 PJS/ZIP 압축 관리 프로그램입니다. 기존 `tkinterdnd2` 외부 의존성을 제거하고 Python 표준 라이브러리만으로 GUI와 압축 처리를 구성했습니다.

## 포함 기능
- 파일 또는 폴더를 ZIP으로 압축
- 파일 또는 폴더를 PJS2로 압축
- ZIP/PJS 파일 압축 해제
- 진행률 표시 및 오류 진단 로그
- ZIP/PJS 압축 해제 경로 탐색 방지
- 기존 PJS1 읽기 및 PJS2 형식 호환 로직 유지

## 로컬 실행
Python 3.10 이상 권장.

```bash
python main.py
python -m unittest discover -s tests -v
```

## GitHub Actions
프로젝트를 저장소 루트에 복사하고 `main` 브랜치에 push하거나 Actions에서 `Build PJSCompressor Windows`를 수동 실행하세요. 테스트 통과 후 두 아티팩트가 생성됩니다.

- `PJSCompressor-Diagnostic-Windows`: 콘솔이 있는 진단용 실행 파일
- `PJSCompressor-GUI-Windows`: 콘솔 없는 GUI 실행 파일

## 진단 로그
Windows에서 `%LOCALAPPDATA%\PJSCompressor\diagnostic.log`에 기록합니다. 시작 직후 실패해도 GUI 초기화 이전 단계부터 로그 기록을 시도합니다.

## 중요
PJS 파일은 전용 형식이며 암호화가 아닙니다. 새로 생성하는 PJS 파일은 PJS3 형식입니다. 이 프로그램은 기존 PJS1/PJS2 파일도 읽을 수 있지만, 구버전의 다른 프로그램이 PJS3를 지원한다고 보장할 수 없습니다. PJS는 암호화가 아닙니다. 실제 사용자 파일에 적용하기 전에는 복사본으로 검증하세요.


## 드래그 앤 드롭

프로그램 창 안으로 파일 또는 폴더를 끌어 놓으면 원본 경로가 자동으로 입력됩니다. `.zip` 또는 `.pjs` 파일을 놓으면 압축 해제 모드로 자동 전환합니다. 여러 항목을 한 번에 놓으면 첫 번째 항목만 선택되므로 나머지는 개별적으로 놓아 주세요. EXE 아이콘 위에 파일을 놓아 실행하는 방식은 지원하지 않습니다.
