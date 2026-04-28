# Competitive Positioning and Value Proposition

## The Market Gap

Every email security product on the market today answers the same question: did this email come from an authorized source? SPF checks the sending server. DKIM checks the cryptographic signature. DMARC enforces alignment between the two. Microsoft Defender adds reputation scoring and threat intelligence. Proofpoint and Mimecast add advanced inbound filtering with sandboxing and URL rewriting.

None of these products answer a different question: is the person typing actually the person who owns the account? When an attacker has valid credentials and logs into a real M365 mailbox, every one of these checks passes. The email comes from the right server, with the right signature, from a fully authenticated session. The attacker sends a wire transfer instruction to the finance team, and it sails through every security layer because technically it is a legitimate email from a legitimate account.

Chimera Secured is the only product that answers the behavioral question. It checks whether the writing style in the email matches the account owner's established patterns. This is a fundamentally new layer of defense that does not exist anywhere else in the market.

## Why Existing Tools Cannot Add This

Adding behavioral analysis to an existing inbound email filter is architecturally impossible for a critical reason. Behavioral analysis requires a trained profile of the person who wrote the email. For outbound email, that person is inside the organization and their profile is available locally. For inbound email, that person is outside the organization and their profile would need to come from somewhere else — which violates data sovereignty principles and requires cross-organization trust infrastructure that does not exist.

Chimera Secured's architecture is specifically designed around this constraint. It operates on outbound email only, where the sender's CPP is always available locally, and scoring happens entirely within the customer's environment. No other vendor has built their architecture this way because they all started from the inbound-filtering paradigm.

## The ROI Conversation

The average BEC loss per incident is approximately 125,000 dollars according to FBI data. Account takeover — the specific threat Chimera Secured addresses — represents roughly 80 percent of successful BEC attacks by dollar volume. A single prevented account takeover incident pays for Chimera Secured deployment across an entire organization for years.

For MSPs, the math is even more compelling. One BEC incident in a customer environment damages the MSP's reputation and may trigger liability discussions. Preventing that incident preserves the customer relationship and positions the MSP as offering best-in-class protection. Chimera Secured gives the MSP a concrete answer to the inevitable post-breach question: what were you doing to protect against this?

## How Chimera Secured Competes

Chimera Secured does not compete against existing email security tools. It complements them. The pitch is never "replace Defender" or "drop Proofpoint." The pitch is: you have every authentication layer in place, and attackers are still getting through because they steal credentials. Add the behavioral layer. Now you are checking both the technical identity and the human identity.

This positioning makes Chimera Secured additive to the MSP's existing security stack rather than disruptive. The MSP does not need to rip and replace anything. They add Chimera Secured on top of whatever they already run, and the customer gets protection against a threat class that was previously unaddressed.

## WinTech Partners and NYN Impact

Chimera Secured is developed by NYN Impact, an operating company under WinTech Partners. WinTech Partners is the parent platform company that also operates OppIntelAI, a competitive intelligence platform, and other technology properties. The Chimera Secured technology leverages behavioral AI research originally developed for communication analysis and applies it specifically to the email security problem.
