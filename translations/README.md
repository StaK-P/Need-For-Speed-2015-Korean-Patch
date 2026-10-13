# NFSKR 한국어 번역 데이터

여기에는 **우리가 작성한 번역과 검수 결과만** 공개해.

- `nfskr-first-release-v1.1.json`: 게임 원본 영어 텍스트 없이 번역 ID와 한국어 텍스트로 구성된 배포용 번역 테이블 (**8,206개 ID**).
- `reviewed/`: 번역 과정의 검수 데이터 (총 10,250개 ID). 원본 게임 문장을 빼고 `string_id`, `scope`, `status`, `ko_text`만 수록했어.
- `원문유지`인 항목은 원문 영어의 무단 배포를 피하기 위해 `ko_text`가 빈 칸이야.
- `terminology.json`, `vehicle-terminology.json`, `category-overrides.csv`: 게임 번역 용어 및 분류 정책.

최종 게임 데이터, 게임의 원본 음성·글꼴·대사, 타사 FBMod는 이 저장소에 포함하지 않아. 실제 플레이용 데이터는 설치기가 사용자의 정품 게임에서 로컬로 생성해.

번역 제안은 [GitHub Issue의 번역 피드백 양식](https://github.com/StaK-P/Need-For-Speed-2015-Korean-Patch/issues/new?template=translation-feedback.yml)으로 보내줘.
