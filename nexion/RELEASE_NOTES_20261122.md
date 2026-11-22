# NEXION v0.3.2 — 2026-11-22

- **다음 작은 검증 단계:** 별도로 신뢰하고 단조 보관하는 high-water 체크포인트를 이용해 인증된 구형 witness 재생 및 저널 롤백을 읽기 전용으로 탐지하는 모형.
- 신규 파일: `nexion/evidence_freshness.py`, `tests/test_evidence_freshness.py`, `EVIDENCE_FRESHNESS.md`.
- 기존 실행 경로와 `main` 브랜치를 수정하지 않는 **선택형 연구용 판정 함수**. 모든 결과에서 전송 및 자동 복구 권한을 거부.
- 신규 14개 테스트: 정상 floor/상위 체인, 구형 witness 및 저널 롤백, 위조 MAC, scope·키 오류, 중복 JSON, 해시 체인 손상, 파일 내용 불변 등.
- 로컬 Python 테스트: 전체 201개 및 컴파일 검증. CI 실행 여부는 별도 검증 필요.
- 한계: floor의 실제 독립 보관/단조성은 외부 가정이며, witness와 floor가 함께 롤백되는 공격을 탐지할 수 없음. 실제 서버·생산시설·외부 네트워크·권한 복구에는 사용하지 않음.
