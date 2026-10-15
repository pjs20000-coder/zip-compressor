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
PJS 파일은 전용 형식이며 암호화가 아닙니다. 기존 프로젝트와 PJS 알고리즘을 호환되게 유지하려고 했지만, 실제 사용자 파일에 적용하기 전에는 복사본으로 검증하세요. 기존 PJS 샘플이 있다면 테스트 대상으로 추가해 호환성을 확인하는 것이 좋습니다.
