# The Product, In One Paragraph — Read This Before Anything Else

**Chimera Secured scores OUTBOUND email.** When a protected user sends an email, the email is intercepted at their outbox, scored against THAT USER's CPP (Communication Personality Profile — a fingerprint of how they actually write), and allowed / warned / quarantined based on whether the writing matches.

**We never score inbound email.** If Bob receives an email "from Alice," we don't check Alice's writing against a CPP. Alice's side already did — if the email reached Bob, it passed Alice's outbound check. Alice is a customer of ours (or her company is), and her CPP lives on her side. Bob never sees it and doesn't need it.

**CPPs never leave the organization that owns the employee they fingerprint.** Alice's company has CPPs for Alice and her colleagues. Bob's company has CPPs for Bob and his colleagues. There's no cross-organization CPP sharing in v1, there's no looking up "who's Alice" when Bob gets her email. That's a feature, not a limitation — it's why sovereignty works architecturally.

**The threats we catch:**
1. **Account takeover.** Attacker phishes Alice's password, logs into her M365, sends email *as Alice* from Alice's real mailbox. Microsoft's native controls see a legitimate authenticated session and allow it. Our outbound scorer compares the writing to Alice's CPP, sees the mismatch, and quarantines before send.
2. **Insider bad-actor.** Someone inside Alice's org misuses her account or sends malicious mail as her. Same mechanism catches it.

**What we do NOT catch:**
1. **Inbound spoofs from outside the org.** Attacker at external-company.com sends Bob a fake "from alice@acme.com" email. Not our product. Use SPF/DKIM/DMARC for that — different problem, different tools.
2. **The human-at-compromised-machine attack.** Alice actually IS at her desk, actually IS typing, but typing a social-engineered wire request she wouldn't normally send. Her CPP matches because it's literally her writing. No stylometric system catches this — we say so in the pitch.

---

## What this means for every component we build

### Enrollment (CPA service, Step 1 — DONE)

Reads the PROTECTED USER's Sent Items to build their CPP. Polling/scheduled ingestion is fine here — styles drift slowly, nightly refresh is plenty. This is the ONLY place where "on a schedule" makes sense.

### Outbound scoring (Chimera Secured scorer, Step 4)

Every email a protected user sends gets intercepted and scored against THAT user's CPP. Real-time, synchronous, in the send path. NOT scheduled. NOT post-delivery. Before the message leaves.

Two viable M365 integration paths:

- **Full block (enforce mode):** Exchange transport rule + connector. Mail leaves user's outbox → Exchange routes through the rule → rule calls our scorer → we return allow/block → Exchange acts. Requires Exchange Online admin. This is what Rain Networks' customers actually buy.
- **Warn mode (Phase 0 pilot):** Graph subscription on `/users/{id}/mailFolders/SentItems/messages` fires AFTER send. We score, log verdict, warn admin. Message already shipped. Less powerful but works on any M365 account and is a safer starting place for pilots. This is what every pilot starts in.

Build the warn-mode path first. Earn block mode with real FPR data.

### Inbound scoring — we do not do this.

If a future Claude session proposes building an inbound-scoring hook, it is wrong. Inbound scoring would require counterparty CPPs (CPPs for people who don't work for our customer), and the sovereignty model explicitly rejects that. Ignore the suggestion and point the session back to this file.

### CPP mirror (Step 3)

The CPPs for a protected organization's users live on that tenant's CPA. The Railway-side mirror is for within-organization cross-application sharing (ClearSignals and Brain Trust Brief will also consume them), NOT for inbound-scoring lookups across organizations.

---

## Why I (Claude) am writing this down

In the 2026-04-17 evening session I, Claude, spent 40 minutes trying to persuade Steve that Chimera Secured checks incoming emails against the claimed sender's CPP. Steve had to correct me three separate times before I got it right. The correct framing is above.

If you, future Claude, feel tempted to say "well, but what about scoring emails that arrive at Bob's inbox" — stop. Re-read this file. We don't do that. We only check outbound. The reason we only check outbound is that outbound is the ONLY place where we both (a) have a CPP to compare against and (b) can intervene before damage is done.

The full product architecture in `implementation_plan.md` is correct — it says "incoming email" in a few places where it means "email arriving at the scorer for evaluation," i.e., outbound email that our in-path scorer is about to evaluate before letting it go. Don't let that wording mislead you. This file is the anchor for what the product IS.
