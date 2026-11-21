# NEXION v0.3.1 — Python 패키지 배치 및 실제 실행 경로 검증

2026-11-21 · 오프라인 회귀 테스트 · 기존 동작 API 불변

## 발견 및 원인

v0.3.0에서 `nexion/evidence_triage.py`(저장소 기준) 파일을 생성했으나, 같은 모듈을 사용하는 테스트는 `from nexion.evidence_triage import ...` 로 import한다. 테스트 실행 위치는 저장소 하위 `nexion/` 프로젝트 폴더이고, Python 패키지 디렉터리는 `nexion/nexion/`이다. 따라서 실제 모듈이 있어야 할 GitHub 경로는 `nexion/nexion/evidence_triage.py`이다.

2026-11-21 브랜치 현재 파일 배치를 확인한 결과, GitHub의 기존 v0.3.0 커밋에는 `nexion/nexion/evidence_triage.py`가 없었다. 기존 183개 테스트 통과 기록은 해당 상태의 GitHub 배치에 대한 검증 결과로 간주할 수 없다. 오프라인 패키지 복원 시 변경 전 경로 그대로는 166개 실행 중 test_evidence_triage 로딩 오류가 발생했다.

## 수정

- v0.3.0 소스 바이트를 변경하지 않고 `nexion/nexion/evidence_triage.py`로 이동한다.
- 이전 잘못된 위치 `nexion/evidence_triage.py`는 제거하여 중복/혼동을 방지한다.
- 기존 API, 승인·동의 모델, 외부 기능 또는 기본 `main` 브랜치는 변경하지 않는다.
- `nexion/tests/test_package_layout.py`의 네 가지 회귀 테스트로 실제 import 대상과 독립 CLI 실행을 검증한다.

## 검증 명령

저장소 `experiment/nexion-v0.1.0-20261110` 브랜치에서:

```sh
cd nexion
python -m unittest discover -s tests -p 'test_evidence_triage.py' -q
python -m unittest discover -s tests -p 'test_package_layout.py' -v
python -m unittest discover -s tests -q
python -m compileall -q nexion tests
```

독립 프로세스에서 `test_evidence_triage.py` 18개를 실제 발견·실행하는 것까지 확인한다. 전체 테스트 수는 이전 183개 + 신규 4개 = 187개다. 테스트는 임시 로컬 SQLite만 사용하며, 외부 통신·실설비 연결·권한 복구를 수행하지 않는다.

## 후속 위험

기존 v0.3.0 `triage_anchor_mismatch()`의 witness 신선도 검증, 단조 카운터 및 독립 키 보관은 여전히 미구현. 특히 witness와 보조 증빙을 모두 함께 과거 상태로 돌리는 공격은 별도 신뢰 루트 없이 탐지할 수 없다. GitHub Actions의 Python 테스트 워크플로는 이번 단계에서 추가하지 않았다. 실제 전원 장애·다중 노드 합의와 외부 권한 확인 또한 범위 밖이다.
