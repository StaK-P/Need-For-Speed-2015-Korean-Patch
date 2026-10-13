# 한국어 번역 데이터

이 디렉터리에는 NFSKR 프로젝트에서 직접 작성한 **한국어 번역과 검수 결과**를 공개합니다.

- `nfskr-first-release-v1.1.json`: 게임의 원본 영어 문장을 제외한 번역 문자열 ID와 한국어 텍스트로 구성되어 있으며, 총 **8,206개 ID**를 포함합니다.
- `reviewed/`: 번역 검수 과정에서 사용한 10,250개 ID의 공개용 기록입니다. 게임 원문과 내부 검수 메모를 제외하고 `string_id`, `scope`, `status`, `ko_text` 네 개의 열만 제공합니다.
- `원문유지`로 분류된 항목은 원본 영어 문장의 재배포를 방지하기 위해 `ko_text`를 빈 값으로 표시했습니다.
- `terminology.json`, `vehicle-terminology.json`, `category-overrides.csv`: 번역 과정에서 작성한 용어 및 항목 분류 기준입니다.

게임 원본의 음성·글꼴·영문 대사, 게임 파일 및 타사 FBMod는 저장소에 포함되어 있지 않습니다. 게임용 리소스는 설치 프로그램이 사용자의 정품 게임 설치를 기반으로 **로컬에서 생성**합니다.

번역의 정확성이나 자연스러움에 대한 개선 의견은 [번역 피드백 이슈 양식](https://github.com/StaK-P/Need-For-Speed-2015-Korean-Patch/issues/new?template=translation-feedback.yml)에 남겨 주세요.
