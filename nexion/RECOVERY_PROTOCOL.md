# NEXION v0.2.7 — 승인 기반 복구 *계획* 상태 머신 (오프라인)

**2026-11-17 · 연구용 Python/SQLite, 외부 통신·장비 연결 없음**

## 이번 단계에서 무엇을 해결했나

v0.2.6의 `assess_recovery()`는 권한 DB와 저널의 모순을 탐지하지만, 운영자가 어떤 상태를 확인하고 승인해야 하는지 기술적 절차가 없었습니다. v0.2.7은 **복구 계획 작성 → 다른 검토자의 증빙 참조 제출 → 명시적 승인 → 실행 불가능한 작업지시서 발행**이라는 작은 단계만 검증합니다. **DB 또는 저널에 복구 변경을 적용하는 기능은 의도적으로 없습니다.**

| 진단 상태 | 계획 여부 | 작업지시 내용 | 자동 실행 |
|---|---|---|---|
| `PENDING_COMMITTED` | 가능 | 권한 DB가 이미 철회 상태인지 독립 확인 후 누락 저널 이벤트 기록 *제안* | 불가 |
| `PENDING_UNCOMMITTED` | 가능 | 권한 DB 롤백이 실제 확정됐는지 독립 확인 후 미완료 의도 해제 *제안* | 불가 |
| `CLEAN` | 불필요 | 복구하지 않음 | 불가 |
| `DIVERGED` | 거부 | 이력 격리 및 별도 조사 | 불가 |
| `UNTRUSTED` | 거부 | 서명된 별도 백업 확인 전 중단 | 불가 |

## 안전 불변식

1. 초안/검토/승인/작업지시서 조회는 **읽기 전용**입니다. 기존 권한 DB·철회 저널·앵커를 수정하거나 메시지를 보내지 않습니다.
2. 검토자는 초안 작성자와 달라야 합니다. 승인자도 작성자와 달라야 합니다. 다만 **문자열 레이블일 뿐 실제 사람의 신원 검증이나 외부 동의 확인이 아닙니다.**
3. 증빙 참조는 필수이나 **참조 자체를 독립 검증하지 않습니다.** 따라서 승인 완료는 데이터 수정 권한이나 실설비 권한을 의미하지 않습니다.
4. 승인 전후 매번 재검증하며 권한 DB 행·메시지·저널 이벤트·저널 헤드·노드 체크포인트가 바뀌거나 HMAC 앵커 검증에 실패하면 작업지시서 조회를 거부합니다.
5. 초안은 최대 60분 유효(기본 15분)하고, 지정된 생성 전/만료 후 시각에 거부합니다.
6. 상태 전이는 `NEW → REVIEWED → APPROVED`, 또는 `NEW/REVIEWED → REJECTED`만 허용합니다. 거절한 요청은 승인할 수 없습니다. 재시작 시 승인은 복구되지 않습니다.
7. 발행 가능한 모든 작업지시서에서 `execute_automatically`, `may_reactivate_participant`, `delivery_permitted`는 `False`입니다.

## 테스트 재현

```bash
cd nexion
python -m unittest discover -s tests -p 'test_recovery_protocol.py' -v
python -m unittest discover -s tests -q
```

## 실행하지 않는 읽기 전용 예제

```python
from datetime import datetime, timezone
from nexion.recovery_protocol import draft_recovery, RecoveryReviewSession
# store: 기존 ConsentStore 객체
# journal: RevocationJournal.open_for_review(...)로 확인한 기록 핸들
now = datetime.now(timezone.utc)
plan = draft_recovery(store, journal, at=now)
session = RecoveryReviewSession(plan, requested_by="requester-label")
session.review(store, journal, reviewed_by="reviewer-label",
               evidence_reference="offline-ticket-123", at=now)
order = session.approve(store, journal, approved_by="reviewer-label", at=now)
assert not order.execute_automatically
```

**주의:** 의도적으로 `journal.finish_withdrawal()`이나 `abort_withdrawal()`을 자동 호출하지 않습니다. 실제 데이터를 복구하기 전에는 신원 확인 가능한 승인, 증빙 원본의 독립 검증, 권한 DB/저널의 교차 트랜잭션 안정성, 복구 단계별 중단 후 재시작 방침 등이 필요합니다.

## 확인되지 않은 보안 속성 / 한계

- SQLite가 분리되어 있어 두 DB를 읽는 동안의 교차 DB 원자적 스냅샷을 보장하지 않습니다. 다른 프로세스가 상태를 변경하는 실서비스 상황에서 TOCTOU 문제가 남습니다.
- 운영자 레이블, 증빙 참조, 승인 상태는 단일 프로세스 메모리의 **비인증 모형**입니다. 코드를 직접 제어하는 공격자를 방어하지 못합니다. 사용자 승인 자체를 실제로 취득한 것은 아닙니다.
- 지문은 해시 기반 변경 감지이고, 권한 DB 서명이나 독립 신뢰 루트가 아닙니다. 권한 DB·저널·앵커·키를 모두 공격자가 조작하는 경우를 막지 못합니다.
- 승인은 재시작하면 유실됩니다(안전상 기본 거부). 영구 감사 로그 및 정확한 한 번 실행은 구현하지 않았습니다.
- 작성 가능한 실제 복구 커밋/롤백 프로토콜은 다음 단계이며, **철회된 참여자가 자동 활성화되면 안 됩니다.**
- GitHub CI, 서버간 연결, 외부 참여자 연락, 실물 제어, 구매는 이 단계의 검증 대상이 아닙니다.
