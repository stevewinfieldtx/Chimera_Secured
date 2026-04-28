# Chimera Secured — What The Product Actually Is

**Canonical. Read this before touching anything.**

## One sentence

Chimera Secured intercepts emails LEAVING a user's outbox and checks whether the writing style matches the account owner's CPP. If it doesn't match, the account has been taken over.

## What we catch

**Account takeover only.** An attacker has logged into a real M365 mailbox (phished password, bought credentials, bypassed MFA) and is sending email AS the real user FROM the real user's account. Every authentication check passes because the attacker IS authenticated. Only the writing style reveals that the person at the keyboard isn't the real owner.

## What we do NOT catch, and do not claim to catch

- **External spoofing** — attacker outside forges the From: header. Not from our customer's outbox. Not our problem. SPF/DKIM/DMARC handle this.
- **Lookalike domains** — attacker sends from steve@winteehpartners.com. Not from our customer's outbox. Inbound filters handle this.
- **Display-name tricks** — "Steve CEO" <random@gmail.com>. Not from our customer's outbox.

If an attack doesn't originate from a mailbox inside the protected tenant, Chimera Secured does not see it and does not claim to see it.

## Where the scoring happens

On **outbound** mail. Exchange Online transport rule / connector / Graph hook that intercepts every email being sent from within the tenant. Scores it against the sender's CPP. Returns allow / warn / quarantine.

There is no inbound scoring in v1. Inbound is a different product.

## Where CPPs come from

Each protected user in the pilot tenant gets a CPP built from their sent items. Initial backfill reads the whole sent folder. Incremental refresh reads new sent items on a schedule (nightly is fine — writing style changes slowly).

CPP building IS scheduled / background work. Outbound scoring is NOT — it's real-time, in the send path.

## Common Claude failure mode to watch for

Past Claude sessions repeatedly tried to re-architect this as inbound scoring because "BEC detection" sounds like something that checks incoming mail. It doesn't. We are specifically the account-takeover layer, on outbound only. If a future Claude proposes scoring inbound mail, or CPPs of external senders, or anything that isn't "score outbound against the outbox owner's CPP" — it's wrong. Stop and re-read this file.

## Pilot pitch in plain English

"Every security tool on the market checks if an email is authenticated. We check if the *person who wrote the email* is actually the person who owns the account. Account takeover is the 80% of real BEC loss, and nothing else catches it, because by the time the attacker sends that wire transfer email they already have the password."
