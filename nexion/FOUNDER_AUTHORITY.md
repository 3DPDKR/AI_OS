# NEXION — Founder and Final Operational Approval Authority

**Status:** Project policy declaration, 2026-11-24. This file documents intent; it is NOT proof that an identity has been authenticated or that a live authorization system is configured.

## Project founder / 최종 운영 승인권자
- **Designation:** NEXION Founder and Final Operational Approval Authority (창립자·최종 운영 승인권자).
- **Public project handle:** `3DPDKR` (the GitHub repository owner handle).
- **Legal name and voice biometric:** not stored here or published. GitHub login is not proof of a person's legal identity.
- **Ownership claim:** project governance only. No claim to authority over third-party equipment, users, factories, model providers, or infrastructure.

## Identity registration requirements
1. The founder must sign in to a specifically configured NEXION Supabase Auth account under direct control.
2. The founder must complete MFA enrollment and identity binding; the verified `auth.users.id` UUID must be recorded by a protected administrator enrollment process.
3. A single protected administrator record can designate the founder after proof of account control, and a successful MFA assurance check (AAL2) must be required for privileged actions.
4. No privileges derive from voice recognition, displayed name, GitHub comments, prompts, or claims such as "I am the founder".
5. Any recovery or replacement must have strong authentication and immutable audit logs; other collaborators cannot grant themselves founder privileges.
6. Until administrator enrollment is complete, **there is no active founder identity binding and privileged commands are denied**.

## Governance boundaries
- The founder makes final product/research roadmap and operational approval decisions on resources for which this project has authorization.
- Volunteers may communicate, propose experiments, and withdraw their participation.
- Safety constraints, laws, independent users' consent, and facility operators' permission still apply. A founder instruction does not override them.
- Experimental AI autonomy may select safe offline research goals but cannot change governance privileges or grant itself live external access.

## Known, verified vs. pending
- GitHub handle `3DPDKR`: observed as the owner of `3DPDKR/AI_OS`.
- NEXION Supabase project exists, but the actual founder's authenticated Supabase user UUID and registered MFA were NOT verified during this declaration.
- Voice enrollment is NOT implemented.
- Do not publish a legal name, email address, phone, private keys, or biometric templates in GitHub.

## Next tasks
- Create a secure private owner enrollment flow in Supabase.
- Make public participant registration strictly lower-privileged.
- Implement and test deny-by-default RLS and privileged-operation MFA gates before enabling any administrator commands.
