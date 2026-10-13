# 소스 빌드 및 개발 안내

이 저장소에는 NFSKR에서 직접 작성한 설치기·병합기 Python 소스, C# 보조 도구 및 번역 테이블을 공개했습니다. 다만 공개 소스만으로 **동일한 실행 파일을 즉시 빌드할 수 있는 상태는 아닙니다.** 실제 빌드에는 외부 도구와 사용자가 합법적으로 소유한 정품 게임 데이터가 필요합니다.

## 필요한 개발 환경

- Windows 10/11 x64 및 Python 3.12
- Python 패키지: `customtkinter`, `Pillow`, `fonttools`, `lz4`, `pyinstaller` 등
- [Frosty Toolsuite 1.0.6.3](https://github.com/CadeEvs/FrostyToolsuite/releases/tag/v1.0.6.3)
- 개발 및 리소스 검증용 [Frosty Flammenwerfer Plugin](https://github.com/shoushou1106/FrostyFlammenwerferPlugin)
- [SUIT](https://github.com/sun-typeface/SUIT), [SUITE](https://github.com/sun-typeface/SUITE), [Pretendard](https://github.com/orioncactus/pretendard) 등 OFL 글꼴
- 정품 Need for Speed (2015) 설치 데이터
- 로컬 Frosty SDK 환경에서 컴파일한 `native/` C# 보조 도구 실행 파일

## 주요 소스 구성

| 경로 | 설명 |
|---|---|
| `tools/nfskr_setup_gui.py` | 설치 프로그램 진입점 및 자체 검사 |
| `tools/nfskr_modern_ui.py` | GUI, 프로필·모드 선택, GitHub 피드백 링크 |
| `tools/nfskr_setup_flow.py` | 병합·검증·설치 흐름 |
| `tools/nfskr_installer_core.py` | Frosty 프로필 업데이트, 체크섬 검증, 백업 및 복원 |
| `tools/nfskr_composite.py` | 기존 모드와 한국어 리소스 병합 |
| `tools/nfskr_local_assets.py` | 로컬 글꼴 및 한국어 패치 데이터 생성 |
| `native/` | 로컬 분석·검증용 C# 소스 |
| `tests/` | 설치와 리소스 병합 테스트 |
| `translations/` | 원본 영어 게임 대사를 제외한 한국어 번역·검수 자료 |

## 빌드 절차

1. 저장소를 클론하고 Windows에서 Python 가상환경을 구성해 주세요.
2. `tools/setup-toolchain.ps1` 및 `tools/fetch-fonts.ps1`을 참고하여 공식 배포처의 외부 의존성을 **별도 `.external/` 디렉터리**에 준비해 주세요.
3. `native/` C# 소스를 로컬 Frosty SDK에 맞춰 컴파일하고 실행 파일을 `work/locale-extract/runtime/`에 배치해 주세요.
4. `python tools/build_nfskr_release_payload.py`로 배포 가능한 데이터만 포함되었는지 확인해 주세요.
5. `powershell -ExecutionPolicy Bypass -File tools/build_nfskr_setup_final.ps1`로 Windows 실행 파일을 빌드한 뒤 관련 테스트를 수행해 주세요.

개발 및 테스트용 일부 소스에는 기존 QA 환경의 경로나 체크섬이 포함되어 있을 수 있습니다. 다른 환경에서 실행하실 때는 해당 경로와 게임 버전을 먼저 확인해 주세요.

게임 원본 추출 파일, 외부 라이브러리의 무단 복제본 또는 타사 모드 바이너리는 공개 저장소에 추가하지 말아 주세요.

번역 관련 개선 의견은 [GitHub 번역 피드백 양식](https://github.com/StaK-P/Need-For-Speed-2015-Korean-Patch/issues/new?template=translation-feedback.yml)에 남겨 주세요.
