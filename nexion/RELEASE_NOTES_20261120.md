# NEXION v0.3.0 — 2026-11-20

- 이전 v0.2.9에서 발견한 journal SQLite commit 이후 anchor 갱신 전 중단 사례를 대상으로 읽기 전용 evidence_triage 모듈 추가.
- 외부에서 이미 보관된 HMAC witness를 입력으로 받는 독립 검토 모형. witness 발행 및 독립 보관, 인증 주체는 구현하지 않음.
- 유효성 검사: 증빙 HMAC, 앵커 HMAC, 저널 해시 사슬, checkpoint, 권한 DB 철회 상태 및 witness 논리 상태.
- 단일 이벤트 지연과 이전 pending 의도가 일치하는 경우 POSSIBLE_POST_COMMIT_ANCHOR_LAG 후보로 분류하되 **원인은 확정하지 않음**.
- 모든 진단 결과에서 전송과 복구 권한을 False로 고정. 실제 쓰기·복구·재참여·외부통신 기능 추가 없음.
- 기존 165개 + 신규 18개 = **183개 로컬 테스트 통과**. 5회 반복 **915/915**, Python 3.13.5 구문 검사 통과.
- 기본 main 브랜치와 기존 기능 변경 없음. NEXION은 오프라인 연구용 모형.

## 제한 및 후속 과제

동시에 열리는 두 SQLite DB의 원자적 snapshot, witness 신선도, 별도 서명기관·키 보관 독립성, 재생 공격, 실제 전원 손실·스토리지 내구성, GitHub Actions CI는 미검증/미구현. 신원/참여 동의 검증 없는 권한 회복, 시설 연결, 원격 제어, 구매는 수행하지 않음.

기술 설명 및 재현 절차: EVIDENCE_TRIAGE.md
