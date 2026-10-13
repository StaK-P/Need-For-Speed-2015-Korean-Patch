# 소스 빌드 / 개발 가이드

이 저장소에는 설치기·병합기 Python 소스와 C# 보조 도구, 번역 테이블을 공개했습니다. 그러나 공개한 소스만으로 **즉시 동일한 바이너리를 빌드할 수 있는 것은 아닙니다.** 실제 동작에는 공식 도구 및 유효한 정품 게임 데이터가 필요합니다.

## 개발에 필요한 것

- Windows 10/11 x64 및 Python 3.12
- Python 패키지: `customtkinter`, `Pillow`, `fonttools`, `lz4`, `pyinstaller` 등
- 공식 [Frosty Toolsuite 1.0.6.3](https://github.com/CadeEvs/FrostyToolsuite/releases/tag/v1.0.6.3)
- 개발/검증 시 [Frosty Flammenwerfer Plugin](https://github.com/shoushou1106/FrostyFlammenwerferPlugin)
- [SUIT](https://github.com/sun-typeface/SUIT), [SUITE](https://github.com/sun-typeface/SUITE), [Pretendard](https://github.com/orioncactus/pretendard) 등 OFL 글꼴
- 사용자가 합법적으로 소유하고 설치한 NFS 2015의 원본 데이터
- Frosty SDK를 이용하여 로컬에서 빌드한 `native/` C# 도구 실행 파일

## 핵심 구성

| 경로 | 설명 |
|---|---|
| `tools/nfskr_setup_gui.py` | 설치 프로그램 진입점 및 자체검사 |
| `tools/nfskr_modern_ui.py` | GUI, 프로필·모드 선택, GitHub 피드백 링크 |
| `tools/nfskr_setup_flow.py` | 병합·검증·설치 흐름 |
| `tools/nfskr_installer_core.py` | 프로필 갱신, 체크섬, 백업·롤백 |
| `tools/nfskr_composite.py` | 기존 모드와 한글 리소스 병합 |
| `tools/nfskr_local_assets.py` | 로컬 폰트 및 한국어 패치 데이터 생성 |
| `native/` | 로컬 분석·검증용 C# 도구 소스 |
| `tests/` | 테스트 코드 |
| `translations/` | 원본 영어 문장을 포함하지 않은 한국어 번역·검수 데이터 |

## 재현 순서

1. 저장소를 클론하고 Windows Python 가상환경을 생성합니다.
2. `tools/setup-toolchain.ps1`, `tools/fetch-fonts.ps1`을 참고해 공식 공급처의 외부 의존성을 **별도 `.external/` 폴더**에 준비합니다.
3. `native/` 소스를 사용자 로컬 Frosty SDK에 맞춰 컴파일하고, 해당 실행 파일을 `work/locale-extract/runtime/`에 배치합니다.
4. `python tools/build_nfskr_release_payload.py`를 실행해 배포 가능한 데이터만 확인하세요.
5. `powershell -ExecutionPolicy Bypass -File tools/build_nfskr_setup_final.ps1`로 PyInstaller Windows 실행 파일을 생성하고 테스트하세요.

개발·테스트 예제 일부에는 이전 QA 환경의 경로나 해시가 남아 있을 수 있습니다. 별도의 시스템에서 사용하려면 환경과 버전에 맞춰 수정하고, **타사 바이너리/게임 원문을 공개 저장소에 커밋하지 마세요.**

번역 피드백은 [전용 GitHub Issue 양식](https://github.com/StaK-P/Need-For-Speed-2015-Korean-Patch/issues/new?template=translation-feedback.yml)에서 받을 수 있습니다.
