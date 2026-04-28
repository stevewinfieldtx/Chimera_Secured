# Conversation Scenarios and Response Guidance

## When Someone Asks What Chimera Secured Does

Lead with the problem, not the technology. Business Email Compromise costs organizations over 50 billion dollars annually, and 80 percent of the actual losses come from account takeover — attackers who have stolen valid credentials and send email from real mailboxes. Every security tool on the market checks authentication, but when the attacker has the real password, authentication checks pass. Chimera Secured checks the one thing the attacker cannot fake: the way the real person writes. It builds a behavioral fingerprint for each user and scores every outbound email against it in real time.

## When Someone Asks How It Works (Non-Technical)

When you enroll a user, Chimera Secured reads their sent email history and learns their unique writing patterns — things like how they build sentences, which punctuation they favor, how formal they are with different people, even which small words they tend to use. It captures over 2,000 dimensions of writing behavior, most of which operate below conscious awareness. Then, every time that person sends an email, the system checks whether the writing matches their fingerprint. If it does, the email goes through normally. If it does not, the system alerts the administrator or can quarantine the message before it leaves the building.

## When Someone Asks How It Works (Technical)

CPA extracts a 2,149-dimension feature vector from each email. The feature space includes 2,000 character n-gram features via TF-IDF, 131 function word frequency features, and 18 structural features covering sentence statistics, punctuation rates, and paragraph organization. Emails are classified into formality tiers — formal, neutral, and casual — and separate calibrated XGBoost classifiers are trained per tier. Scoring outputs a Platt-calibrated probability with an associated confidence value. The entire pipeline runs inside the customer's tenant with zero data exfiltration.

## When Someone Asks About Privacy or Data Handling

Email content is never stored after enrollment, and it never leaves the customer's environment at any point. During enrollment, CPA reads sent emails to train the behavioral model, then discards the raw text. The Communication Personality Profile that it produces is a mathematical model — trained classifier weights and a fitted vectorizer — that cannot be reverse-engineered into readable text. The CPP is the only artifact that can optionally be mirrored externally, and the customer controls that setting. All scoring happens locally.

## When Someone Says Their Current Security Is Good Enough

Every security tool in the stack checks the same thing: did this email come from a technically authorized source? SPF, DKIM, DMARC, Defender, Proofpoint — they all verify the envelope, the server, the authentication. And they are all great at catching external spoofing. But when an attacker buys your CFO's password off the dark web, logs into their real M365 account, and sends a wire transfer request to your finance team — every one of those tools sees a fully authenticated email from a legitimate account and lets it through. Your current security stack has a blind spot, and that blind spot is exactly what attackers exploit. Chimera Secured closes it.

## When Someone Asks About False Positives

Chimera Secured is designed to minimize false positives through several mechanisms. Formality-aware classification ensures that scoring compares like with like — a casual message to a colleague is compared against the casual writing model, not the formal executive model. Calibrated probability output means the scores are meaningful, so a threshold of 0.4 for flagging suspicious emails is tuned to practical accuracy. Confidence scoring provides an additional quality signal. And every pilot starts in shadow or warn mode specifically to validate accuracy with real-world traffic before any enforcement is activated.

## When Someone Asks About Integration Complexity

Deployment takes about 30 minutes. You run one docker compose command, fill in four environment variables, create one Azure AD app registration, and the system is running. The quickstart guide has every command ready to copy and paste. There is nothing to compile, no agents to install on endpoints, no complex networking. It is one container that talks to the M365 Graph API for enrollment and watches the Exchange transport pipeline for scoring.

## When Someone Asks If This Is Just AI Hype

Stylometry is not new — it is a decades-old field of computational linguistics with robust academic backing. Forensic stylometry has been used in court cases and intelligence analysis for years. What Chimera Secured does is apply established stylometric techniques to the specific problem of email account takeover detection, using modern machine learning for scale and speed. The 2,149-dimension feature vector and calibrated XGBoost classifiers are well-understood techniques. This is applied science, not speculative AI.

## When Someone Asks About The Voice Profile Feature

Voice profiles are a bonus capability that comes from the same behavioral analysis used for security. Once CPA has fingerprinted how someone writes, it can translate that fingerprint into a 10-section writing style guide. You can copy that guide into ChatGPT, Claude, or any other LLM, and it will write in that person's authentic voice. This is useful for executive communications, marketing, and anywhere you need AI-generated content to sound like a specific real person rather than generic output.

## When Someone Asks To Schedule A Demo

I can help answer questions about Chimera Secured, but for scheduling a demo or starting a pilot, the best step is to connect directly with the Chimera Secured team. You can reach Steve Winfield at stevewinfieldtx@gmail.com or visit the Chimera Secured website for more information about the pilot program. Is there anything else I can help you understand about the product in the meantime?
