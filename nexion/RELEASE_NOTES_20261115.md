# NEXION v0.2.5 로컬 검증 보고 — 2026-11-15

**새 단계:** 선택형 HMAC-SHA256 로컬 앵커를 통해 저널 단일 파일의 변조/이전 상태 복원을 감지하고 차단합니다.

- 신규 모듈 `nexion/journal_anchor.py`
- 수정: `nexion/revocation_journal.py`, `nexion/distributed_consent.py`
- 신규 `tests/test_journal_anchor.py`: 16개 장애/회귀 테스트
- 기존 모드 및 기존 노드 기능 유지, 추가 라이브러리 없음
- 동의 기반 오프라인 소프트웨어 시뮬레이션만 실행

로컬 Python unittest 전체 **107개 통과**, 5회 반복 **535/535 통과**, 구문 컴파일 검사 통과. GitHub CI 및 실제 장비 시험은 별개이며 실행했다고 주장하지 않습니다.

관련 문서: `ANCHOR.md`.
