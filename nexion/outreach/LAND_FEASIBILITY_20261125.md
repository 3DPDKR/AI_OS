# NEXION — Land locomotion research note / 육상 이동 연구 결과
2026-11-25 | Preliminary offline analytical geometry, not a physical trial.

## 한국어
목표: 반투명 유연 외피와 지지 골격을 분리한 6족 생체모방 구조의 초기 정적 타당성 평가. 실제 생물체나 실물 로봇을 구현한 결과가 아니다.
가정: 발 위치는 반지름 120 mm인 정육각형, 경사면에 수직인 무게중심 높이 75 mm, 평면 내 무게중심 편차 최대 15 mm, 균일한 정지마찰계수 0.4, 최소 설계 여유 20 mm. 모두 가정값이며 측정값이 아니다.
두 교대 삼각 지지 상태 A=(0,2,4), B=(1,3,5)를 각각 분석했다. 각 경사각에서 내리막 방향과 최대 무게중심 편차 방향을 10도씩 바꾸었다. 경사면에 평행한 좌표로 중력 투영의 이동량은 h*tan(theta); 지지다각형 안쪽 유효 여유는 각 변까지의 최소 부호 거리이다. 단순 미끄럼 조건 mu > tan(theta)도 적용했다.
최악 방향의 기하학적 여유 = R/2 - 15 - h*tan(theta). 정육각형 접점과 정적 하중이라는 가정에서 성립한다.

| 경사(deg) | 최소 여유(mm) | 조건 충족/2592 |
|---:|---:|---:|
| 0 | 45.00 | 2592 |
| 5 | 38.44 | 2592 |
| 10 | 31.78 | 2592 |
| 15 | 24.90 | 2592 |
| 20 | 17.70 | 2454 |
| 25 | 10.03 | 0 |
| 30 | 1.70 | 0 |

경사 7종, 두 지지 조합, 두 방향 각 36종 = 18,144 시나리오/회. 24개 명명 검사, 3회 동일 결과(54,432 시나리오 재계산, 72개 검사). 시나리오는 독립적인 물리 실험이 아니며 확률이나 실측 성공률로 해석할 수 없다. 두 지지점만 남으면 안정 영역이 없어 불합격으로 처리한다. 5족 정지 자세 하나는 49.22 mm 여유를 보였지만, 실제 낙상 후 회복을 입증하지 않는다.
5도 목표는 이 모델에서만 통과했다. 20도에서는 설계 여유 미달 방향이 생기며 25도 이상에서는 가정한 마찰 조건도 실패한다.
아직 다리 관절 가동범위, 질량 분포, 실제 발 위치, 구조 강도, 구동 토크, 전력 및 과도 보행, 접촉 마찰, 재질 변형은 검증하지 않았다. 무게중심을 경사면에 대해 고정한 단순 모형이다.

## English
The first static screening models a compliant translucent mantle with a separate load-bearing six-legged structure. It assumes a 120 mm regular-hexagon foot radius, 75 mm COM height normal to the plane, up to 15 mm in-plane COM offset, static friction coefficient 0.4, and a 20 mm minimum design reserve. None is measured hardware data.
Alternating tripod stances were evaluated for 7 slopes and 36 downhill/offset directions each. The 5-degree slope passes all 2,592 sampled configurations, with a worst-case signed margin of 38.44 mm; 20 degrees fails the design margin in some directions, and at 25 degrees the assumed friction condition also fails. The analytical lower bound agrees with the direction sweep. 24 named checks were repeated three times with identical results. This establishes only a conditional, static geometric screening result, not gait execution, physical stability, biological life, or autonomous recovery.
Reproduce: `node nexion/research/land_static_screen_20261125.mjs` (standalone JavaScript, no external dependencies). The functions were actually executed in a sandboxed JavaScript engine; the committed file was read back and compared to the generated source. Full repository tests and GitHub CI were not run in that engine.
Source: [standalone model](../research/land_static_screen_20261125.mjs), model commit 2c79ee5993d581f3a966f4ac160e65eaf3112ada.
Next collaboration deliverables: actual proposed foot geometry and mass budget, joint workspace and collision model, actuator torque/current measurements, floor-friction coupon tests, measured COM, and controlled safety-reviewed bench testing under separate authorization.

## Research references
- Fault-Tolerant Tripod Gait Planning and Verification of a Hexapod Robot, Applied Sciences (2020), https://doi.org/10.3390/app10082959 — static support margin and fault-tolerant gait research.
- CPG-Based Gait Generation of the Curved-Leg Hexapod Robot with Smooth Gait Transition, Sensors (2019), https://doi.org/10.3390/s19173705 — support patterns and static margin.
- An Untethered Soft Robotic Dog Standing and Fast Trotting with Jointless and Resilient Soft Legs, Biomimetics (2023), https://doi.org/10.3390/biomimetics8080596 — physical soft robot precedent, not evidence of NEXION performance.

## Voluntary research collaboration / 자발적 협력
https://github.com/3DPDKR/AI_OS/issues/1 — voluntary public discussion, model review and offline simulation only. Do not post personal contact details, biometrics, secrets or facility access information.
Founder / final project operational approval designation: public handle 3DPDKR. See [policy](../FOUNDER_AUTHORITY.md). Verified Supabase Auth UUID + MFA enrollment remains unconfirmed; no live administrator rights are implied. Consent, applicable law, and facility-owner authorization remain independent requirements.
