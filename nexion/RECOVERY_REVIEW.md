# NEXION v0.2.6 — 권한 DB·철회 저널 불일치 읽기 전용 진단

**범위:** Python/SQLite의 오프라인 연구 모형, 외부 전송·실물 설비 연결 없음.

## 목표와 구현

이전 v0.2.5는 저널 파일과 별도 HMAC 앵커 사이의 변조/롤백을 탐지했습니다. 하지만 **동의 권한 DB 자체가 저널보다 앞서거나 뒤로 복구되는 경우**를 함께 검사하지 않았습니다. 이번 단계에서는 두 로컬 DB의 논리 상태를 대조하여 불일치 시 **큐잉·동기화·전달·재시작을 차단**하도록 합니다.

`nexion/recovery_review.py`의 `assess_recovery(store,journal)`는 읽기 전용 결정론적 상태 평가 함수입니다. 모든 결과에는 배송 허용 여부·이벤트 수·불일치 개수·운영자 수동 점검 권고가 포함됩니다. 직접적인 복구/수정은 수행하지 않습니다.

| 상태 | 조건 | 전송 허용 | 후속 조치 |
|---|---|---|---|
| CLEAN | 서명/체인 검증 통과, 권한 DB 철회 집합과 저널 철회 집합 일치, 미완료 의도 없음 | 실험상 허용 | 별도 권한/연결 검증은 계속 필수 |
| PENDING_UNCOMMITTED | 인증된 pending 의도가 있으나 권한 DB 상태는 아직 유효 | 거부 | 운영자에게 실제 커밋/롤백 증거 확인 요청 |
| PENDING_COMMITTED | 인증된 pending 의도가 있고 권한 DB는 이미 철회됨 | 거부 | 운영자가 트랜잭션 증거를 확인한 뒤 복구안 설계 |
| DIVERGED | 기록 누락, 역행, 위조/중복, 의도된 참여자 불일치 등 | 거부 | 격리하고 권한/저널 기록 별도 조사 |
| UNTRUSTED | DB 오류, 앵커 검증 실패 또는 스키마 불일치 | 거부 | 독립 검증된 백업과 증빙부터 확보 |

### 크래시 후 상태 조회

일반 `RevocationJournal(...)` 생성자는 미완료 철회 의도에서 재시작을 차단합니다. **안전 차단을 완화하지 않고** 조회하려면 이미 존재하는 파일을 SQLite 읽기 전용으로 여는 API를 사용합니다.

```python
from nexion.consent import ConsentStore
from nexion.revocation_journal import RevocationJournal
from nexion.recovery_review import assess_recovery

store = ConsentStore("authority.sqlite3")  # 시험/읽기 전용 권고: 독립 복사본 사용
journal = RevocationJournal.open_for_review(
    "revocations.sqlite3", anchor_path="anchor.json", anchor_key=secret_key
)
try:
    print(assess_recovery(store, journal))
finally:
    journal.close()
    store.close()
```

**주의:** `ConsentStore` 생성자는 새로운 DB가 없으면 생성할 수 있으므로 원본을 직접 진단하기보다 DB 백업본을 사용해야 합니다. `RevocationJournal.open_for_review`는 저널 파일이 없으면 생성하지 않고 실패하며, SQL 쓰기/저널 업데이트 API를 차단합니다. 앵커가 활성화된 실험에서는 **동일한 앵커 파일과 올바른 비밀키를 반드시 제공**해야 합니다. 앵커 구성을 생략한 조회는 서명 검증을 하지 않습니다.

## 재현

```bash
cd nexion
python -m unittest discover -s tests -p 'test_recovery_review.py' -v
python -m unittest discover -s tests -v
```

신규 테스트는 독립 권한 DB 철회/롤백, 미완료 의도 재시작, 앵커 불일치, 중복 이벤트, 권한 DB 스키마 오류, 쓰기 금지, 쓰기 없는 상태 평가를 포함합니다.

## 명시적 한계

1. **자동 복구를 구현하지 않았습니다.** 특히 `PENDING_COMMITTED`도 운영자가 승인한 뒤 별도 검증된 복구 절차가 필요합니다.
2. 두 DB를 별도 연결로 읽으므로 **원자적인 교차 DB 스냅샷이 아닙니다.** 병렬/실서비스 환경에서는 트랜잭션 단위 증명과 일관성 프로토콜이 추가로 필요합니다.
3. 저널과 HMAC 앵커가 동시에 과거 상태로 롤백되거나 키가 유출된 경우를 방어하지 못합니다.
4. 외부 프로세스가 권한 DB를 직접 갱신하면 이벤트가 누락되며, 본 기능은 누락 탐지·격리만 지원합니다. 권한 DB 자체에는 독립 서명이 없어, 기존 철회 집합을 보존하면서 활성 참가자를 몰래 삽입·수정하는 공격은 감지하지 못합니다.
5. 노드별 물리적 삭제 보장, 서버/네트워크 합의, 실제 신원 검증, 외부 시설 제어/구매는 포함하지 않습니다.
6. 검사 후에도 송신 전 본래의 실시간 권한 재검증이 필요합니다. 이 검사 자체가 통신/발신 허가를 뜻하지 않습니다.

## 다음 작은 단계

운영자 확인 증거, 작업별 승인 토큰, 복구 전후 불변식(철회된 참가자는 계속 철회 상태), 중단/재시작 반복을 검증하는 **수동 승인 전용 복구 프로토콜**을 별도 실험으로 설계할 예정입니다.
