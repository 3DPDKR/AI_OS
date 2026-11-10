# NEXION Consent & Peer Collaboration v0.1.0
Run with Python 3.9+ (standard library only):

    cd nexion
    python -m unittest discover -s tests -v
    python -m nexion.consent_demo

## Implemented in offline reference implementation
- Explicit positive agreement and scoped opt-in
- Two-stage consent with a 48-hour confirmation token
- Random token-based access and withdrawal; hashed tokens in SQLite
- Two-way peer messaging ONLY after both participants opt into peer_chat
- Revocation deletes private messages and blocks access
- Non-content audit events

## Not yet built
Public website, real email identity verification, verified organization authority, live cross-node networking, moderation, external outreach, machine connection, auto-production or AI self-deployment. Local demo reveals confirmation tokens to the caller and does NOT prove the email belongs to the claimant.

## Authorized cooperation roadmap
1. Publish project description and invite consenting researchers to opt in.
2. Add verified email provider and production authentication with independent audit.
3. Connect communication services only for consenting participants.
4. Permit facility-specific, human-verified sandbox simulations only.
5. Continue independent testing before proposing any physical machine action.

Scope facility_review is only discussion and does not authorize equipment commands.
