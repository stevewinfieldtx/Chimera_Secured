# Frequently Asked Questions and Objection Handling

## General Product Questions

### What is Chimera Secured in one sentence?
Chimera Secured detects account takeover by comparing each outbound email against the sender's behavioral fingerprint, catching attackers who have valid credentials but cannot replicate the real person's writing style.

### How is this different from Microsoft Defender for Office 365?
Microsoft Defender checks authentication, sender reputation, and known threat signatures. It verifies that the email came from an authorized server and a valid account. Chimera Secured checks something fundamentally different — whether the person typing is actually the account owner. When an attacker logs in with stolen credentials, Defender sees a legitimate authenticated session and lets the email through. Chimera Secured detects the writing style mismatch and flags it.

### How is this different from Proofpoint or Mimecast?
Proofpoint and Mimecast focus on inbound email protection — scanning incoming messages for phishing links, malicious attachments, and suspicious sender patterns. Chimera Secured operates on outbound email, which is a completely different threat surface. These products are complementary, not competitive. An organization should run both an inbound filter and Chimera Secured's outbound behavioral analysis.

### Does Chimera Secured replace our existing email security?
No. Chimera Secured is a new layer that sits on top of existing email security infrastructure. It specifically targets the gap that authentication-based tools cannot cover. Think of it as adding behavioral verification on top of technical verification.

### What about emails that are very short, like just "OK" or "Thanks"?
Very short emails under 15 words receive a reduced confidence score. There is not enough writing to reliably determine authorship from style alone. CPA still scores them but signals to the downstream system that the style evidence is weaker. This is by design — honest uncertainty is better than false confidence.

### How many emails does someone need before CPA can build a profile?
CPA needs a minimum of 30 usable sent emails, where usable means at least 15 words after preprocessing and cleanup. In practice, most active email users easily exceed this threshold. Someone who has been using their mailbox for even a few weeks typically has hundreds of usable sent items.

### How long does enrollment take?
Enrollment typically takes 30 to 120 seconds per user, depending on mailbox size. CPA pulls up to 2,000 recent sent items, preprocesses them, trains the classifiers across formality tiers, and produces the CPP. The process is fully automated — the administrator just provides the email address and CPA handles the rest.

### Can writing style actually identify a person?
Yes. Stylometry — the statistical analysis of writing style — is an established field with decades of academic research. Every person has unconscious patterns in how they construct sentences, use punctuation, choose function words, and organize paragraphs. These patterns form a behavioral fingerprint that is extremely difficult to consciously replicate. CPA captures this fingerprint across 2,149 dimensions of analysis — far more than any human could consciously control or mimic.

## Security and Privacy Questions

### Does Chimera Secured read our emails?
CPA reads sent email history during enrollment to build the behavioral fingerprint. After enrollment, the raw email content is discarded — only the mathematical model (the CPP) is retained. The CPP cannot be reverse-engineered to reconstruct any email content. During real-time scoring, CPA processes each outbound email to extract features, scores it, and does not store the email content.

### Where does our email data go?
Nowhere. Email bodies never leave the customer's environment. The CPP, which is an abstract mathematical fingerprint containing no readable text, is the only artifact that can optionally be mirrored to an external service, and the customer controls whether this mirroring is enabled. All scoring happens locally.

### Is this GDPR compliant?
The data sovereignty architecture was designed with regulatory compliance in mind. Email content stays in-tenant. The CPP contains no personally identifiable information and no reconstructible content. The system processes data for a legitimate security purpose. Specific GDPR compliance should be confirmed by the customer's legal counsel for their jurisdiction, but the architectural design minimizes data exposure by keeping everything in the customer's control.

### What happens if CPA goes down?
If CPA is unavailable, emails flow normally. In warn mode, no alerts are generated until CPA is restored. In enforce mode with an Exchange transport rule, the rule should be configured with a timeout that allows emails to pass if CPA does not respond within the configured window. CPA downtime means temporary loss of behavioral scoring, not disruption of email delivery.

## Technical Questions

### What are the 7 analysis layers?
Chimera Secured uses seven analysis layers that produce the 2,149-dimension behavioral fingerprint. Character n-grams (2,000 dimensions) capture subliminal patterns in letter and space combinations that persist across topics. Function word frequencies (131 dimensions) measure unconscious usage of topic-independent words like "the," "however," and "actually." Structural features (18 dimensions) capture sentence length statistics, punctuation rates, pronoun usage, and paragraph organization. TW bucketing adds formality-aware classification so comparisons account for how people write differently to different audiences. XGBoost classification with calibrated probabilities ensures scores are meaningful, not just directional. Background corpus comparison provides the baseline for distinguishing the account owner's style from generic writing. And confidence scoring integrates multiple quality signals to indicate how reliable each verdict is.

### What is a Communication Personality Profile?
A CPP, specifically a CPP-E for email, is a trained machine learning model that captures a person's unique writing signature. It consists of a fitted TF-IDF vectorizer trained on the user's own emails, up to three calibrated XGBoost classifiers (one per formality tier), a TW predictor that routes recipients to the appropriate classifier, and aggregate voice statistics. The CPP contains no email text — it is a mathematical model that can score new text but cannot reconstruct the text it was trained on.

### How accurate is the scoring?
During pilot evaluation, Chimera Secured demonstrates the ability to correctly identify the account owner's writing with 80 percent or higher accuracy across enrolled users. Accuracy improves with more training data and longer emails. The system provides both a probability score and a confidence value so that administrators can make informed decisions based on the strength of the evidence.

### Can an attacker fool the system by studying someone's writing style?
Consciously mimicking 2,149 dimensions of writing behavior simultaneously is practically impossible. The character n-gram features alone capture patterns at a level below conscious awareness — things like the frequency of specific three-character sequences across all writing. An attacker would need to match thousands of subliminal patterns while simultaneously crafting a convincing email. Academic stylometry research consistently shows that conscious style imitation fails against multi-dimensional statistical analysis.

### What if someone's writing style changes over time?
CPA supports incremental profile refresh. Writing style changes slowly — a nightly refresh cycle captures natural drift without losing the core behavioral fingerprint. If a person's style changes dramatically (for example, after a stroke or if they start using AI writing tools extensively), the CPP can be re-enrolled from scratch with current emails.

## MSP-Specific Questions

### How much work is deployment?
About 30 minutes from clone to first enrolled user. The MSP runs a single docker compose command, fills in four environment variables, creates one Azure AD app registration, and the system is operational. A detailed quickstart guide walks through every step with copy-pasteable commands.

### Do I need to be an email security expert to deploy this?
No. The system is designed for MSP generalists. If you can create an Azure AD app registration and run Docker, you can deploy Chimera Secured. The dashboard provides a browser-based interface for all ongoing management. The API provides automation options for MSPs who want to integrate enrollment and monitoring into their existing workflows.

### What ongoing management is required?
Day-to-day management is minimal. The system runs autonomously once deployed. The MSP monitors the dashboard for flagged emails, reviews and refines recipient labels as needed, enrolls new users when onboarding employees, and re-enrolls users if a profile refresh is needed. The CPA dashboard provides all management functionality through the browser.

### Can I white-label this for my customers?
The current pilot deployment is Chimera Secured branded. White-labeling discussions are part of the partner agreement for MSPs who demonstrate successful pilot deployments and commit to scaled rollout.
