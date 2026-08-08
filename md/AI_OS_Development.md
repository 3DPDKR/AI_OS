# AI OS Development Spec

## Core goal
AI OS is a result-oriented multi-agent operating system. Agents collaborate only as needed to produce the best final result; continuous AI discussion is not the goal.

## Main UI
- 채팅: 사용자 질문, 대화, 최종 결과
- AI 대화방: 현재 Topic/Task에 연결된 Agent 작업 및 검증 과정
- 기록: Conversation/Result/Evidence
- 설정: Provider, API/인증, 사용량, 저장공간, Cloud, 보안

## Agent architecture
Agent and AI Provider are separate concepts.

`Agent -> Capability -> Provider/Model`

Initial Agents:
- Planner
- Researcher
- Reasoner
- Coder
- Vision
- Translator
- Evidence
- Navigator
- Synthesizer
- Quality Gate

Only required Agents are activated for a Task. Each Agent has limits such as maxSteps, provider calls, elapsed time, tokens and cost.

## Provider policy
- Provider ON/OFF is controlled in Settings.
- OFF Provider must never be called by Router.
- Free AI is preferred.
- Paid API usage is OFF by default.
- Provider failure triggers fallback when possible.
- Provider capability and health are tracked separately from Agent roles.

## Usage / quota / cost monitor
Paid and free AI usage must be visible in Settings.

Provider usage model:
- providerId
- modelId
- quotaSource: provider / localEstimate / unavailable
- usedRequests
- requestLimit
- remainingRequests
- inputTokens
- outputTokens
- usedCost
- budgetLimit
- remainingBudget
- currency
- resetAt
- lastUpdatedAt

Rules:
1. If the Provider exposes an official usage/quota API, display the real value.
2. If no official quota API is available, AI OS records requests/tokens and displays an explicitly labeled estimated usage/cost.
3. Never present an estimate as an official remaining balance.
4. If remaining quota is low, Router can prefer another enabled free Provider.
5. When a configured hard budget is reached, paid calls are blocked.
6. Support global monthly budget and per-Provider budget.
7. Free Providers should show request/rate-limit/reset information when obtainable.

Example UI:

```text
OpenAI API                 ON
사용량   $7.42 / $20.00
남음     $12.58
[████████░░] 63%
갱신     8월 31일

Gemini                     ON
무료 할당량
오늘 132 / 250 요청
남음 118
```

## Cost Guard
Modules:
- ProviderQuota
- UsageMonitor
- CostGuard

Default:
- paidApiEnabled = false
- freeFirst = true
- hardCostGuard = true

CostGuard blocks a paid request when paid API is disabled or its configured hard limit has been reached.

## Storage
Local-Light by default. Keep only necessary cache/index/recent task data locally. Old conversations, evidence, attachments and full AI-room traces may be archived to optional free cloud storage. Secrets are never stored in ordinary workspace/cloud files.

## Smartphone development
- PC not required
- GitHub is source of truth
- GitHub Actions builds Android APK
- Smartphone is development console and real-device test target
- Google Drive can be used as optional project documentation/archive storage

## Build policy
Before APK output:
- flutter pub get
- flutter analyze
- flutter build apk --debug
- upload APK artifact

Creator: Daehyun Kang
