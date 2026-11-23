# NEXION v0.3.3 — 2026-11-23

- **검증 목표:** SQLite 권한 DB·철회 저널·앵커·witness·floor 동시 롤백을 로컬 시뮬레이션에서 재현하고 탐지 가능/불가능 조건을 구분한다.
- **변경:** tests/test_joint_rollback_limits.py 신규 8개 회귀 테스트, JOINT_ROLLBACK_LIMITS.md 및 이 변경 이력 문서 추가. 기존 실행 소스와 권한 API는 그대로 유지한다.
- **핵심 발견:** 실제 철회가 있었더라도 모든 증빙과 외부 floor가 함께 과거로 롤백되면 관측 입력이 철회가 한 번도 없었던 역사와 같아져 BOUNDED_CONSISTENT를 얻는다. 이는 FRESH/승인 판정이 아니다.
- **독립성 대조군:** 외부 최신 floor가 보존된다면 과거 journal/witness는 REPLAY_OR_ROLLBACK으로 식별된다. 모든 판정은 전송/복구 권한을 허용하지 않는다.
- **로컬 검증:** Python 3.13.5, 기존 201개 + 신규 8개 = 209개 테스트 통과, 전체 테스트 5회 반복 1,045/1,045 통과, compileall 통과. 일부 기존 SQLite 연결 ResourceWarning은 남는다.
- **보안 한계:** 진짜 독립 보관자나 하드웨어 단조 보장은 구현되지 않았다. 실제 파일시스템 전원 손실, 다중 SQLite 원자성, GitHub Actions CI는 검증하지 않았다.
- **범위 제한:** 실서비스 승인, 자동 동의 복구, 실제 설비 제어, 외부 연락, 구매, 물리적 제작 없음. 기본 main 브랜치 불변.
