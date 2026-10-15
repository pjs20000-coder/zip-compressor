# PJSCompressor PJS4 — 비밀번호 암호화 프로토타입

## 포함 기능

- 파일 또는 폴더를 ZIP으로 압축한 뒤 PJS4로 암호화
- 프로그램 창 안으로 파일/폴더를 끌어다 놓는 드래그 앤 드롭 지원 (EXE 아이콘에 드롭하는 방식은 아님)
- PJS4 파일을 비밀번호로 복호화하고 안전하게 압축 해제
- Argon2id(128 MiB, 3회 반복, 병렬도 2)로 비밀번호에서 키 유도
- AES-256-GCM 인증 암호화
- 1 MiB 단위 청크 암호화로 대용량 파일의 전체 메모리 적재 방지
- 암호문 변조 검출, 잘못된 비밀번호 처리
- ZIP 경로 탈출, 심볼릭 링크, 중복 경로에 대한 기본 방어
- GitHub Actions Windows EXE 빌드

## 주의: PJS3와 호환되지 않습니다

이 프로토타입은 새 `PJS4` 포맷입니다. 기존 `PJS1`, `PJS2`, `PJS3` 파일을 읽거나 기존 앱의 모든 기능을 대체하지 않습니다. 실제 기존 프로젝트에 적용할 때는 기존 형식을 유지한 채 PJS4를 추가하고, GUI의 형식 판별과 복원 분기를 별도로 연결해야 합니다.

## 드래그 앤 드롭

프로그램을 실행한 뒤 창 안의 드롭 영역이나 프로그램 창에 파일 또는 폴더를 끌어다 놓으세요. 한 번에 하나의 항목만 지원합니다. 복원 모드에서는 `.pjs` 파일 하나를 드롭합니다.

## 실행

Python 3.10 이상 권장:

```powershell
python -m pip install -r requirements.txt
python main.py
```

## 테스트

```powershell
python -m unittest discover -s tests -v
```

## Windows EXE 빌드

GitHub Actions 워크플로는 Node.js 24를 지원하는 `actions/checkout@v7`, `actions/setup-python@v7`, `actions/upload-artifact@v7`을 사용합니다. PyInstaller 빌드 시 `tkinterdnd2` 패키지 리소스를 함께 수집합니다. 공식 액션 설명: [checkout](https://github.com/actions/checkout), [setup-python](https://github.com/actions/setup-python), [upload-artifact](https://github.com/actions/upload-artifact).


GitHub 저장소의 `main` 브랜치에 파일을 올린 뒤 Actions에서 `Build PJSCompressor PJS4 Windows`를 실행합니다. 결과물은 `PJSCompressor-PJS4-Windows` 아티팩트로 제공됩니다.

## 보안상 중요한 점

- 비밀번호는 1자 이상이면 사용할 수 있습니다. 다만 짧은 비밀번호는 추측 공격에 취약하므로 긴 고유 비밀번호 사용을 권장합니다.
- 비밀번호를 잊으면 복구할 수 없습니다. 비밀번호 관리 및 백업 절차를 별도로 마련하세요.
- 이 코드는 검증된 라이브러리를 사용하지만, 전문 보안 감사 또는 침투 테스트를 받은 제품은 아닙니다.
- PJS4는 비밀번호를 모르는 사람이 파일을 단순히 zlib 해제해서 원본을 얻지 못하게 하는 설계입니다. 다만 비밀번호가 약하면 오프라인 추측 공격을 받을 수 있습니다.
- EXE를 배포하기 전 실제 Windows 환경에서 테스트하고, 보안 경고가 나타나면 우회하지 말고 파일과 빌드 과정을 검사하세요.
- 현재 형식은 암호화된 데이터의 파일명/메타데이터를 숨기지만, 외부 PJS 파일 크기와 PJS4 시그니처 등 일부 정보는 노출됩니다.
