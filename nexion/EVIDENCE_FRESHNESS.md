# NEXION v0.3.2 — 외부 고수위(high-water) 체크포인트의 오프라인 재생·롤백 판별

2026-11-22 · 연구용 모형 · **읽기 전용** · 실서비스 인증기관 및 실제 복구 기능 없음

## 목적 및 변경 범위

v0.3.1의 `evidence_triage.py`는 독립 HMAC witness가 논리 상태와 일치하는지 확인하지만, 공격자가 유효한 옛 witness를 재생한 상황에서 현재 시점을 입증하지는 못한다. 이번 실험의 `nexion/evidence_freshness.py`는 **별도 보관 주체가 더 이상 과거 값으로 되돌리지 않는다고 가정한** 고수위 체크포인트를 추가 입력으로 받아 하한선 위반을 감지한다. 기존 권한 DB·저널·앵커·전송 코드는 변경하지 않는다.

`verify_witness_floor(journal_path, witness_document=..., witness_key=..., floor_document=..., floor_key=..., expected_scope=...)`는 서명된 기존 witness와 실험용 floor를 검증하고 SQLite 저널을 `mode=ro`, `query_only=ON`으로 읽어 전체 해시 체인·head·floor 지점 해시와 대조한다. 파일 생성, 외부 전송, 실물 명령, 동의 갱신, 복구, 키 발급 기능은 없다.

## 외부 floor 형식(연구 전용)

`format = "nexion-external-monotonic-floor-v1"`, `state = {"scope": "nexion-offline-simulation", "min_sequence": 1, "min_digest": "...64자리 소문자 hex..."}`, `mac = HMAC-SHA256(floor_key, canonical_json({"format": format, "state": state}))`.

키는 witness 키와 서로 다른 32바이트 이상의 실험용 키이며 테스트에서만 더미 키를 사용한다. 외부 floor 자체를 생성·보존하는 운영 기능은 구현하지 않는다. `scope`는 호출자에게서 기대한 스트림 식별자와 완전 일치해야 한다. JSON 중복 필드·미확인 필드·MAC 실패·잘못된 범위·키 재사용은 거부한다.

## 판정과 보안 의미

| 결과 | 해석 | 전달/복구 권한 |
|---|---|---|
| `BOUNDED_CONSISTENT` | HMAC 검증된 witness와 전체 로컬 체인이 일치하며 신뢰된 floor 이하로 내려가지 않음 | 모두 거부 |
| `REPLAY_OR_ROLLBACK` | 정상 MAC을 가진 증빙이나 저널이 독립 floor보다 과거 위치를 지칭 | 모두 거부 |
| `UNTRUSTED` | MAC/스키마/범위/경로 오류, 해시 체인 불일치, witness와 저널 불일치 등 | 모두 거부 |

**`BOUNDED_CONSISTENT`는 `FRESH`가 아니다.** 외부 보관자의 실제 독립성, floor의 단조 저장, 신원, 실제 최신성, 원자적 SQLite 스냅샷 및 물리적 보호를 증명하지 않는다. witness·floor·저널을 동시에 이전 상태로 돌릴 수 있거나 외부 floor 키가 탈취되면 순수 소프트웨어 검증만으로 탐지할 수 없다. `withdrawn_digest`/`checkpoint_digest`까지 포함한 전체 권한 DB와의 검증은 기존 `triage_anchor_mismatch`의 별도 책임이며 이 모듈의 단독 결과로 허가를 내릴 수 없다.

## 재현 명령

저장소 루트의 `nexion` 프로젝트 디렉터리에서 다음을 실행한다.

```sh
python -m unittest discover -s tests -p 'test_evidence_freshness.py' -v
python -m unittest discover -s tests -q
python -m compileall -q nexion tests
```

2026-11-22 로컬 Python 실행에서 신규 14개, 전체 201개를 검증하였다. 통과 로그는 연구 패키지에 포함한다. GitHub Actions CI 및 실제 정전·WAL 일관성 검증은 별개다.

## 다음 미해결 과제

독립 floor 보관기관/서명자 신원 인증, 변조 및 다중 파일 동시 롤백 방지, 실제 단조 하드웨어 기반 체크포인트, 다중 SQLite 파일의 원자적 스냅샷, WAL 및 실제 전원 장애에 대한 내구성 검증이 필요하다. 동의·시설별 권한 없는 생산시설 연결, 실물 제어, 외부 연락 및 구매는 금지한다.
