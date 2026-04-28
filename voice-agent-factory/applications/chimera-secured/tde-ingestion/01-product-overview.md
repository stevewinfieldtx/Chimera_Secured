# Chimera Secured — Product Overview

## What Chimera Secured Is

Chimera Secured is a behavioral AI security product that detects Business Email Compromise by fingerprinting how each person in an organization writes email. It builds a Communication Personality Profile for every protected user, then scores every outbound email against that profile in real time. If the writing style does not match the account owner, the email is flagged or quarantined before it leaves the organization.

## The Core Problem It Solves

Business Email Compromise costs organizations over 50 billion dollars annually according to the FBI. The most damaging form of BEC is account takeover, which accounts for roughly 80 percent of actual financial losses. In an account takeover attack, the attacker has already stolen valid credentials — through phishing, credential stuffing, or purchasing them on dark web markets. They log into the real Microsoft 365 mailbox, pass every authentication check, and send emails as the real employee. Microsoft Defender, Proofpoint, Mimecast, and every other email security tool on the market sees a fully authenticated session from a legitimate account. They let it through.

Chimera Secured catches what none of these tools can detect because it checks the one thing the attacker cannot fake: the way the real account owner actually writes.

## How It Differs From Existing Email Security

Traditional email security tools focus on authentication — SPF, DKIM, DMARC, certificate checking, sender reputation. These tools verify that the email came from the right server and the right account. They work perfectly against spoofing and phishing from external domains. They are completely blind to an attacker who already has the password.

Chimera Secured is not a replacement for those tools. It is a new layer that sits on top of them. It specifically targets the threat class that authentication-based tools cannot see: a real authenticated session being used by someone who is not the real account owner.

## What It Catches

Chimera Secured catches two specific threat types. First, account takeover — an attacker who has compromised credentials and is sending email from a real mailbox. The attacker is fully authenticated, but their writing patterns differ from the account owner's established behavioral fingerprint. Second, insider misuse — someone inside the organization using another person's account to send unauthorized communications. The same stylometric mismatch reveals the deception.

## What It Does Not Catch

Chimera Secured does not catch inbound spoofing from external domains. It does not catch lookalike domain attacks. It does not catch display-name tricks where an attacker sends from their own email address with a forged display name. These attack types do not originate from within the protected tenant's mailboxes, so Chimera Secured never sees them. SPF, DKIM, and DMARC handle those threats.

Chimera Secured also does not catch the human-at-compromised-machine attack where the actual account owner is typing but has been socially engineered into sending a malicious message. In this case, the writing matches because the real person is actually typing. No stylometric system can detect this, and Chimera Secured does not claim to.

## Who It Is Built For

Chimera Secured is designed for Managed Service Providers and their enterprise customers who run Microsoft 365 environments. It deploys inside the customer's tenant, operates on outbound email only, and integrates with existing Exchange Online infrastructure. MSPs deploy and manage Chimera Secured across their customer base, providing a new security layer that fills a gap no other product addresses.
