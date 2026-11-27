# NEXION — Three-axis leg kinematics / 3축 다리 기구학 (2026-11-27)

## Research result / 연구 결과
An offline screening model separates the previous virtual hip contact moment into yaw, hip pitch and knee pitch components, and checks a candidate two-link leg's reachable foot positions. This is a rigid, massless-link model, not a physical demonstration of a living organism or a walking robot.
기존 가상 고관절 접촉 모멘트를 세 관절축으로 분해하고 후보 다리의 도달 영역을 검사했다. 실제 보행, 생물학적 생명, 자가복구 실험이 아니다.

Source: [land_joint_screen_20261127.mjs](../research/land_joint_screen_20261127.mjs). Run with Node.js: `node nexion/research/land_joint_screen_20261127.mjs`. Prior static loading: [2026-11-26](./LAND_LOAD_20261126.md).

## Assumptions / 가정
- Two links 45 and 65 mm; yaw and hip pitch axes intersect (no coxa offset); knee-negative branch. Nominal hip-to-foot vector (60, 0, -65) mm. Nominal joint angles: 0, -2.245, -74.382 degrees.
- Candidate limits (degrees): yaw [-45,45], hip pitch [-75,60], knee [-150,-15]. Reject singular endpoints. These are assumed software limits, not actuator specifications.
- Previous support radius 120 mm, hip radius 60 mm, COM height 75 mm, COM offset magnitude 15 mm, friction 0.4, static margin >=20 mm. Contact forces are distributed proportionally to gravity by the prior tripod model.
- Independent foot workspace grid: x=40..80, y=-20..20, z=-75..-40 mm, all step 5 mm. No combined loading of shifted feet is modeled.
- Torques reported are absolute external contact contributions J^T F, not measured motor torques; compensation sign is opposite. Peak values per axis can occur in different conditions. Exclude rejected stance conditions.

## Reproducible numerical evidence / 수치 검증
Executed the research function three times in an isolated JavaScript runtime before committing the same function as a standalone Node.js file. Each run: 2,589 assertions passed, 648 workspace samples (639 reachability passes), 54,432 stance cases, 38,466 eligible stance cases (3 masses x [2592 x 4 + 2454]), 115,398 eligible leg-load evaluations. Repeat results identical. Total assertions: 7,767. Maximum FK error 3.18e-17 m; central-difference Jacobian error 2.01e-11 m/rad; independent axis projection error 5.56e-17 N m; virtual-work power discrepancy 5.56e-17 W at prescribed test joint velocities. These errors measure numerical self-consistency, not manufacturing accuracy. No whole-repository test executed.

| Mass / 질량 | Slope / 경사 | Yaw / 요 | Hip pitch / 고관절 | Knee pitch / 무릎 |
|---|---:|---:|---:|---:|
|1.5 kg|5°|0.0321|0.3669|0.1146|
|2.0 kg|5°|0.0427|0.4892|0.1528|
|2.5 kg|5°|0.0534|0.6115|0.1910|
Units N m. For 2 kg, 5°, virtual hip resultant 0.49277 N m agrees with previous rounded 0.493 N m. Across 2 kg eligible sampled 0–20° cases, individual peaks: yaw 0.1772, hip pitch 0.4903, knee pitch 0.1859 N m. At 20° only 2454/2592 stances pass the prior static criteria; 25/30° have no passes. These are not full-terrain capability claims.

## Limits and next steps / 한계와 다음 단계
The geometry does not include joint housing, shell collision, link mass, dynamic gait, impact, gear loss, actuator heat, soft tissue elasticity, or energy use. A design factor alone cannot bound those unmodeled loads. A 639/648 grid result is not a continuous workspace or gait validation.
다리 하우징과 반투명 외피의 간섭, 링크 자중, 충격, 동적 보행, 감속기 손실, 발열, 소재 피로 및 소비전력은 미검증이다. 다음: 부품 질량 예산 및 연속 토크·전류·열 모델, 이후 충돌 및 동적 보행 검증.

## Scientific reference / 근거
- Lynch and Park, Modern Robotics, section 5.2 (Jacobian transpose statics): https://modernrobotics.northwestern.edu/nu-gm-book-resource/5-2-statics-of-open-chains/
- SPINDER, open-source 18-DoF hexapod and analytical IK (external work, not NEXION): https://doi.org/10.1038/s41598-026-56856-0

## Invitation / 협력 요청
Researchers worldwide may voluntarily review the assumptions, propose reproducible CAD envelope and actuator characterization data, or review the safety model via https://github.com/3DPDKR/AI_OS/issues/1. Do not post private details or equipment credentials. Participation does not grant operational permissions. Project founder designation: 3DPDKR; actual Supabase UUID/MFA binding remains unverified; see [policy](../FOUNDER_AUTHORITY.md).
