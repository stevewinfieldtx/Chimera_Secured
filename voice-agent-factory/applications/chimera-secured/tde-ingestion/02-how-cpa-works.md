# How CPA Works — The Communication Personality Analyzer

## What CPA Is

CPA stands for Communication Personality Analyzer. It is the core engine inside Chimera Secured that builds behavioral fingerprints from email and scores new messages against them. CPA reads a user's sent email history, extracts stylometric features from each message, trains machine learning classifiers, and produces a Communication Personality Profile. That CPP is then used to score every outbound email the user sends, returning a probability that the real account owner wrote it.

## The Enrollment Process

Enrollment is how CPA builds a Communication Personality Profile for a new user. The MSP or administrator triggers enrollment through the CPA dashboard or API, providing the user's email address. CPA connects to the Microsoft 365 tenant via the Graph API and pulls the user's sent email history — up to 2,000 most recent sent items. It needs a minimum of 30 usable emails, where usable means at least 15 words after preprocessing. Enrollment typically takes 30 to 120 seconds depending on mailbox size.

## What Happens During Enrollment

CPA processes the user's emails through several stages. First, preprocessing normalizes whitespace, strips signatures, and cleans formatting artifacts. Then PII scrubbing removes personally identifiable information so that raw email content is never stored. CPA extracts a 2,149-dimension feature vector from each email — this captures writing style at a level far below conscious awareness.

The feature vector has three components. Character n-grams, which are sliding windows of 3 to 5 characters processed through TF-IDF, contribute 2,000 dimensions. These capture subliminal patterns in how someone combines letters and spaces — patterns that survive even when the topic changes completely. Function word frequencies add 131 dimensions from a fixed lexicon of topic-independent words like "the," "however," "actually," and "therefore." How often someone uses these words is an unconscious habit that varies between writers but stays consistent for each individual. Structural features add 18 dimensions covering sentence length statistics, punctuation rates, pronoun usage patterns, contraction rates, and paragraph organization.

## TW Bucketing — Formality-Aware Classification

People write differently depending on who they are emailing. A message to your CEO reads differently than a message to your team Slack channel. CPA accounts for this through TW bucketing, which sorts each recipient into one of three formality tiers. TW Plus is the formal tier for executives, external contacts, and important stakeholders. TW Zero is the neutral tier for peers and everyday colleagues. TW Minus is the casual tier for close collaborators and informal exchanges.

CPA automatically classifies each recipient based on observed patterns in the training emails. It trains a separate XGBoost classifier for each formality tier, so scoring compares like with like. When a new outbound email arrives for scoring, CPA predicts which tier applies to the recipient and routes the email to the appropriate classifier.

## The XGBoost Classifiers

Each TW bucket gets its own binary classifier built on XGBoost with calibrated probability output. The classifier is trained to distinguish between the account owner's writing and a diverse background corpus of 500 synthetic email-style texts representing how a generic person might write. During scoring, the classifier outputs a calibrated probability between 0 and 1 representing how likely it is that the account owner wrote the email.

Calibration uses CalibratedClassifierCV with sigmoid (Platt scaling), which means the output probabilities are meaningful. A score of 0.85 genuinely means the model is 85 percent confident the real user wrote it. This matters for production deployment because downstream decision rules depend on the probabilities being well-calibrated, not just directionally correct.

## How Scoring Works

When someone sends an email from a protected mailbox, CPA intercepts it and runs the scoring pipeline. CPA loads the sender's cached CPP, preprocesses the email body, determines which TW bucket applies to the recipient, extracts the 2,149-dimension feature vector, and passes it through the appropriate calibrated classifier. The result is a p_authentic score between 0 and 1.

A p_authentic above 0.7 means the email is consistent with the sender's established writing patterns — authentic. Between 0.4 and 0.7 means some anomalies were detected — uncertain, worth reviewing. Below 0.4 means the writing does not match the account owner's patterns — suspicious, likely not the real person.

Scoring also includes a confidence value that reflects how reliable the score is. Confidence is higher when the recipient has been explicitly labeled into a TW bucket, when the matching classifier had plenty of training data, and when the email is long enough to provide a strong style signal. Short emails under 15 words receive reduced confidence because there is less writing to analyze.

## Data Sovereignty in CPA

Email bodies never leave the customer's environment. Not to Chimera Secured's servers, not transiently, not in any form. The CPP, which is an abstract mathematical fingerprint with no reconstructible email content, is the only object that crosses the tenant boundary, and only when its content hash changes, to an optional Railway-side mirror that the tenant can disable. All scoring happens locally inside the tenant against the local CPP. This is an architectural guarantee, not a policy promise.
