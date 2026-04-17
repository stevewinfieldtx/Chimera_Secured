"""
Smoke tests for the CPA service.

These are NOT full unit tests — they are "does the happy path run end-to-end
without throwing" checks. The goal is to catch import errors, signature
mismatches, and obvious logic errors before Steve tries to deploy anything.

Real validation comes from the Enron cross-writer eval (Step 5 in the
build order). That proves the scorer actually detects impersonation. This
file proves the code RUNS.

Run with:
    cd cpa && CPA_DATA_DIR=./test_data pytest tests/ -v

Design notes for next-Claude:
  - Each test uses its own tenant_id so they don't collide in the DB.
  - CPA_DATA_DIR is set via env at invocation time, not in-module, so
    switching between dev and CI is controllable externally.
  - The enrollment test uses the synthetic ("fake") background corpus,
    not the Enron one, because we're not testing quality here, only that
    the pipeline runs.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Make src/ importable when running from repo root
SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

import pytest


# ---- pii_scrub ---------------------------------------------------------

def test_pii_scrub_basic():
    from pii_scrub import scrub
    text = "Email me at alice@example.com or call +1 555-123-4567. See https://example.com for details."
    scrubbed = scrub(text)
    assert "alice@example.com" not in scrubbed
    assert "555-123-4567" not in scrubbed
    assert "https://example.com" not in scrubbed
    assert "__EMAIL__" in scrubbed
    assert "__PHONE__" in scrubbed
    assert "__URL__" in scrubbed


def test_pii_scrub_preserves_prose():
    from pii_scrub import scrub
    text = "I think we should go with the proposal. It's better than the alternative."
    assert scrub(text) == text  # no PII → no change


# ---- preprocessing -----------------------------------------------------

def test_preprocess_strips_signature():
    from preprocessing import preprocess
    raw = """Hi Bob, thanks for the update. I'll review the changes tomorrow morning and get back to you.

Best,
Steve Smith
Senior Engineer
Acme Corporation
555-1234"""
    cleaned, _meta = preprocess(raw)
    assert "Senior Engineer" not in cleaned
    assert "Acme Corporation" not in cleaned
    # Closer preserved (part of style)
    assert "Best" in cleaned


def test_preprocess_strips_quoted_reply():
    from preprocessing import preprocess
    raw = """Sure, I can meet at 3pm tomorrow.

On Monday, April 15, 2026, John Doe wrote:
> Can we schedule a call this week?
> I wanted to discuss the project.
"""
    cleaned, _meta = preprocess(raw)
    assert "Can we schedule" not in cleaned
    assert "Sure, I can meet" in cleaned


def test_preprocess_fallback_when_too_short():
    """If preprocessing strips everything, fall back to less aggressive."""
    from preprocessing import preprocess
    # This has a signature-shaped block that would strip the whole thing
    raw = """Thanks!
Bob"""
    cleaned, meta = preprocess(raw, min_words_to_keep=5)
    # Either we kept the original or we flagged the fallback
    assert cleaned  # not empty


# ---- features ----------------------------------------------------------

def test_feature_extractor_fit_transform():
    from features import FeatureExtractor
    texts = [
        "I think we should proceed with the plan as discussed in yesterday's meeting.",
        "Let's table this for now and revisit after the quarterly review is complete.",
        "The team did a great job handling the crisis, and I appreciate everyone's hard work.",
        "Please review the attached document and let me know your thoughts by end of day.",
    ]
    extractor = FeatureExtractor()
    extractor.fit(texts)
    X = extractor.transform(texts)
    assert X.shape[0] == 4
    assert X.shape[1] == extractor.feature_dim
    # Second transform should work identically
    X2 = extractor.transform(texts[:2])
    assert X2.shape[0] == 2
    assert X2.shape[1] == extractor.feature_dim


def test_feature_extractor_raises_before_fit():
    from features import FeatureExtractor
    extractor = FeatureExtractor()
    with pytest.raises(RuntimeError):
        extractor.transform(["hello world"])


# ---- auto_classify -----------------------------------------------------

def test_auto_classify_consumer_domain():
    from auto_classify import classify_recipient
    result = classify_recipient("someone@gmail.com")
    assert result.tw_bucket == "TW_MINUS"
    assert result.needs_review is True
    assert result.auto_rule == "consumer_domain"


def test_auto_classify_internal_executive():
    from auto_classify import DirectoryEntry, classify_recipient
    dir_map = {
        "ceo@acme.com": DirectoryEntry(
            email="ceo@acme.com", is_internal=True, is_executive=True
        ),
    }
    result = classify_recipient("ceo@acme.com", directory=dir_map)
    assert result.tw_bucket == "TW_PLUS"
    assert result.auto_rule == "internal_executive"
    assert result.needs_review is False


def test_auto_classify_internal_colleague():
    from auto_classify import DirectoryEntry, classify_recipient
    dir_map = {
        "bob@acme.com": DirectoryEntry(email="bob@acme.com", is_internal=True, is_executive=False),
    }
    result = classify_recipient("bob@acme.com", directory=dir_map)
    assert result.tw_bucket == "TW_ZERO"
    assert result.auto_rule == "internal_employee"


def test_auto_classify_unknown_default():
    from auto_classify import classify_recipient
    result = classify_recipient("stranger@somedomain.biz")
    assert result.tw_bucket == "TW_ZERO"
    assert result.needs_review is True
    assert result.auto_rule == "unknown"


def test_country_priors():
    from auto_classify import build_country_priors
    emails = [
        {"recipient_email": "a@company.vn", "word_count": 180},
        {"recipient_email": "b@company.vn", "word_count": 200},
        {"recipient_email": "c@company.vn", "word_count": 150},
        {"recipient_email": "d@company.de", "word_count": 30},
        {"recipient_email": "e@company.de", "word_count": 35},
        {"recipient_email": "f@company.de", "word_count": 25},
    ]
    priors = build_country_priors(emails)
    assert priors.get("vn") == "TW_PLUS"
    assert priors.get("de") == "TW_MINUS"


# ---- classifier --------------------------------------------------------

def test_twhead_fit_and_predict():
    """Train a TWHead on a tiny synthetic corpus and verify it scores."""
    from features import FeatureExtractor
    from classifier import TWHead

    # Positive (target user): breezy, short, contractions
    positives = [
        "hey just wanted to check in on that thing we talked about yesterday",
        "sounds good to me ill send over the notes later tonight probably",
        "yeah no worries at all, happens to everyone sometimes you know",
        "ok just ping me when you get a chance to look at it thanks",
        "cool thanks for handling that one I really appreciate your help",
        "gonna grab lunch soon do you want to join us at the usual place",
        "lol yeah that was kind of a mess, glad we got through it though",
        "hey, did you see the email I sent earlier this morning about the thing",
        "just wanted to follow up, any thoughts on what we discussed last week",
        "ha yeah thats a good point, ill think about it some more tonight",
        "can we push the meeting to tomorrow? got something else that came up",
        "quick one, do you have the link to the doc we were looking at earlier",
        "ok cool, talk later and have a good one, thanks again for the help",
        "so um yeah that didnt go quite as planned but we can fix it easy",
        "awesome thanks so much for jumping on that one so quickly, appreciated",
        "hey just checking if youre around later this afternoon for a quick chat",
        "not sure tbh, might need to sleep on it and get back to you tomorrow",
        "oh yeah good catch i totally missed that, fixing it now thanks again",
        "alright sounds like a plan then, ill see you on thursday hopefully",
        "thanks a bunch, appreciate you taking the time to look at this for me",
        "hey, can we chat tomorrow about the project? free anytime in the afternoon",
        "i think that works great, let me know if you need anything from me",
        "perfect, thats exactly what i was thinking too, lets go with that",
        "no problem at all, happy to help out whenever you need something",
        "hey hows it going? long time no talk, lets catch up sometime soon",
        "got it, will do, talk later and thanks for the update on that",
        "sounds great, ill be there, text me if you need anything else",
        "just a heads up, i might be running a few minutes late today sorry",
        "ok done, let me know if anything else comes up or you need help",
        "hey so i was thinking about what you said and i actually agree with you",
    ]

    # Negatives: formal corporate prose
    negatives = [
        "Please find attached the quarterly report for your review and consideration.",
        "We would like to schedule a meeting to discuss the upcoming initiatives.",
        "Kindly confirm receipt of this message at your earliest convenience please.",
        "Pursuant to our previous discussion, I am forwarding the relevant documentation.",
        "The committee has reviewed the proposal and will respond within five business days.",
        "I am writing to formally request an extension on the project deadline.",
        "In accordance with company policy, all expenditures must be pre-approved.",
        "Attached please find the revised agreement for your review and signature.",
        "We appreciate your attention to this matter and look forward to your response.",
        "Please note that the office will be closed for the holiday next week.",
        "The executive team has approved the budget allocation for the next quarter.",
        "I would appreciate the opportunity to discuss this matter further with you.",
        "Thank you for bringing this issue to our attention in a timely manner.",
        "The contract terms have been finalized and are ready for your approval.",
        "We regret to inform you that your application has not been successful.",
        "Please be advised that the meeting has been rescheduled to next Tuesday.",
        "I trust this email finds you well and in good health this morning.",
        "The deliverables outlined in the statement of work have been completed on time.",
        "Further to our conversation, I have outlined the next steps in the attached memo.",
        "We are pleased to confirm your attendance at the upcoming leadership summit.",
        "As discussed, the revised proposal takes into account the stakeholder feedback.",
        "I would like to formally extend my congratulations on the successful project launch.",
        "The audit findings have been documented and shared with the relevant departments.",
        "Please review the enclosed terms and conditions prior to signing the agreement.",
        "Your prompt attention to the outstanding invoice items would be greatly appreciated.",
        "The strategic plan for the fiscal year has been approved by the board of directors.",
        "We kindly request that all departments submit their budget forecasts by Friday.",
        "Thank you for your patience while we processed your recent service inquiry.",
        "The procurement team will be conducting a vendor review in the coming weeks.",
        "Please ensure that all compliance documentation is up to date before the audit.",
    ]

    extractor = FeatureExtractor().fit(positives + negatives)
    head = TWHead("TW_MINUS", extractor)
    head.fit(positives, negatives)

    # Positive-shaped test sample should score high
    p_auth = head.predict_proba(["hey just checking in on that thing real quick"])
    assert len(p_auth) == 1
    assert 0.0 <= p_auth[0] <= 1.0
    # With such a tight synthetic split, the authentic score should lean positive
    assert p_auth[0] > 0.5

    # Negative-shaped test sample should score low
    p_auth_neg = head.predict_proba([
        "Please find attached the formal document for your review and prompt response."
    ])
    assert p_auth_neg[0] < 0.5


def test_twhead_save_load_roundtrip(tmp_path):
    from features import FeatureExtractor
    from classifier import TWHead

    pos = ["hey whats up"] * 40
    neg = ["Please be advised that the policy has been updated."] * 40
    extractor = FeatureExtractor().fit(pos + neg)
    head = TWHead("TW_ZERO", extractor)
    head.fit(pos, neg)

    path = tmp_path / "head.pkl"
    head.save(path)
    assert path.exists()

    loaded = TWHead.load(path, extractor)
    # Both should score the same input the same way (within rounding)
    orig = float(head.predict_proba(["hey whats up there"])[0])
    new = float(loaded.predict_proba(["hey whats up there"])[0])
    assert abs(orig - new) < 1e-9


def test_tw_predictor_labels():
    from classifier import TWPredictor
    p = TWPredictor()
    p.set_label("alice@acme.com", "TW_PLUS", source="user")
    p.set_label("friend@gmail.com", "TW_MINUS", source="auto")

    pred1 = p.predict("alice@acme.com")
    assert pred1.bucket == "TW_PLUS"
    assert pred1.source == "labeled"

    pred2 = p.predict("friend@gmail.com")
    assert pred2.bucket == "TW_MINUS"
    assert pred2.source == "auto"

    pred3 = p.predict("unknown@nowhere.xyz")
    assert pred3.bucket == "TW_ZERO"
    assert pred3.source == "fallback_zero"


# ---- hashing -----------------------------------------------------------

def test_hash_dict_canonical():
    from hashing import hash_dict
    a = {"x": 1, "y": 2}
    b = {"y": 2, "x": 1}
    assert hash_dict(a) == hash_dict(b)

    c = {"x": 1, "y": 3}
    assert hash_dict(a) != hash_dict(c)


# ---- End-to-end: enrollment + scoring + labeling ----------------------

@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    """Each test gets its own data dir + artifacts dir + DB."""
    data_dir = tmp_path / "cpa_data"
    artifacts_dir = data_dir / "artifacts"
    data_dir.mkdir(parents=True)
    artifacts_dir.mkdir(parents=True)

    monkeypatch.setenv("CPA_DATA_DIR", str(data_dir))
    monkeypatch.setenv("CPA_ARTIFACTS_DIR", str(artifacts_dir))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{data_dir / 'cpa.db'}")
    monkeypatch.setenv("CPA_BACKGROUND_CORPUS", str(data_dir / "bg.pkl"))

    # Force re-import of config and db with the new env
    for mod in ("config", "db", "background_corpus", "enrollment", "scoring", "labels"):
        sys.modules.pop(mod, None)
    return data_dir


def _synthetic_background_corpus(path):
    """Build a tiny background corpus — ~80 generic business-email texts."""
    from background_corpus import BackgroundCorpus
    texts = [
        f"Thank you for your email. I will review the attachment and follow up "
        f"with the team by the end of the week on item {i}."
        for i in range(40)
    ] + [
        f"We have reviewed the proposal and would like to schedule a call to "
        f"discuss the details further on topic number {i}."
        for i in range(40)
    ]
    corpus = BackgroundCorpus()
    corpus.add_raw(texts)
    corpus.save(path)


def _user_sent_emails():
    """Simulated sent-email history for a single user with 3 buckets of style."""
    formal = [
        f"Dear Mr. Johnson, thank you for your patience. Please find attached "
        f"the revised proposal, item reference {i}. I look forward to your response.\n\nRegards,\nSteve"
        for i in range(35)
    ]
    average = [
        f"Hi team, quick update on the project — we're tracking on schedule "
        f"for the milestone next Friday, iteration {i}. Let me know if anything changes. Thanks, Steve"
        for i in range(35)
    ]
    casual = [
        f"hey, got a sec? wanted to run something by you about the thing "
        f"we talked about last week — episode {i} lol. lmk"
        for i in range(35)
    ]
    emails = []
    for body in formal:
        emails.append({"recipient_email": "client@acme.com", "body": body})
    for body in average:
        emails.append({"recipient_email": "teammate@wintechpartners.com", "body": body})
    for body in casual:
        emails.append({"recipient_email": "buddy@gmail.com", "body": body})
    return emails


def test_end_to_end_enrollment_and_scoring(isolated_data_dir, monkeypatch):
    """Build a CPP-E end to end; verify it scores new emails sensibly."""
    from background_corpus import BackgroundCorpus
    from config import BACKGROUND_CORPUS_PATH
    from db import init_schema
    from enrollment import RawEmail, enroll_user
    from scoring import invalidate_cpp_cache, score_email

    init_schema()
    _synthetic_background_corpus(BACKGROUND_CORPUS_PATH)
    corpus = BackgroundCorpus.load(BACKGROUND_CORPUS_PATH)
    assert len(corpus) >= 60

    user_email = "steve@wintechpartners.com"
    raw = [RawEmail(**e) for e in _user_sent_emails()]

    from auto_classify import DirectoryEntry
    directory = {
        "teammate@wintechpartners.com": DirectoryEntry(
            email="teammate@wintechpartners.com",
            is_internal=True, is_executive=False,
        ),
    }

    result = enroll_user(
        tenant_id="test-tenant",
        user_id="steve-user-id",
        user_email=user_email,
        raw_emails=raw,
        directory=directory,
        background_corpus=corpus,
    )

    assert result.training_email_count > 60
    # At least two of three buckets should train with this synthetic corpus
    assert len(result.buckets_trained) >= 2
    # Content hash should be a full SHA-256 hex string
    assert len(result.content_hash) == 64
    assert result.recipient_count == 3  # client, teammate, buddy

    # Score a casual-looking email to the buddy recipient
    invalidate_cpp_cache()
    score_casual = score_email(
        tenant_id="test-tenant",
        user_email=user_email,
        email_body="hey, got a sec to chat about that thing? lmk",
        recipient_email="buddy@gmail.com",
    )
    assert 0.0 <= score_casual.p_authentic <= 1.0
    assert score_casual.confidence > 0.0
    assert score_casual.cpp_version == result.cpp_version

    # Score a formal email to the client — should use a different bucket than casual
    score_formal = score_email(
        tenant_id="test-tenant",
        user_email=user_email,
        email_body=(
            "Dear Ms. Chen, thank you for your patience. Please find attached "
            "the revised quarterly summary. I look forward to your response."
        ),
        recipient_email="client@acme.com",
    )
    assert 0.0 <= score_formal.p_authentic <= 1.0

    # Score with no CPP — different tenant, no enrollment
    score_nocpp = score_email(
        tenant_id="unknown-tenant",
        user_email="nobody@nowhere.com",
        email_body="hello world, this is a test message",
        recipient_email="someone@somewhere.com",
    )
    assert score_nocpp.p_authentic == 0.5
    assert score_nocpp.confidence == 0.0
    assert score_nocpp.tw_source == "no_cpp"


def test_short_email_confidence_penalty(isolated_data_dir):
    """Short emails should reduce confidence, not the raw score."""
    from background_corpus import BackgroundCorpus
    from config import BACKGROUND_CORPUS_PATH
    from db import init_schema
    from enrollment import RawEmail, enroll_user
    from scoring import invalidate_cpp_cache, score_email

    init_schema()
    _synthetic_background_corpus(BACKGROUND_CORPUS_PATH)
    corpus = BackgroundCorpus.load(BACKGROUND_CORPUS_PATH)

    user_email = "steve2@wintechpartners.com"
    raw = [RawEmail(**e) for e in _user_sent_emails()]

    enroll_user(
        tenant_id="test-tenant-2",
        user_id="steve-user-2",
        user_email=user_email,
        raw_emails=raw,
        background_corpus=corpus,
    )
    invalidate_cpp_cache()

    long_result = score_email(
        tenant_id="test-tenant-2",
        user_email=user_email,
        email_body=(
            "hey, got a sec to chat about that thing we were discussing "
            "yesterday afternoon? just wanted to follow up and see if you had "
            "any more thoughts about it before the meeting tomorrow morning"
        ),
        recipient_email="buddy@gmail.com",
    )
    short_result = score_email(
        tenant_id="test-tenant-2",
        user_email=user_email,
        email_body="hey quick q",
        recipient_email="buddy@gmail.com",
    )
    # Short email confidence should be strictly lower
    assert short_result.confidence < long_result.confidence


def test_labeling_queue_and_write(isolated_data_dir):
    """User labels override auto-classification and rise to the top of scoring."""
    from background_corpus import BackgroundCorpus
    from config import BACKGROUND_CORPUS_PATH
    from db import init_schema
    from enrollment import RawEmail, enroll_user
    from labels import get_labeling_queue, labeling_progress, set_label

    init_schema()
    _synthetic_background_corpus(BACKGROUND_CORPUS_PATH)
    corpus = BackgroundCorpus.load(BACKGROUND_CORPUS_PATH)

    raw = [RawEmail(**e) for e in _user_sent_emails()]
    enroll_user(
        tenant_id="test-labels",
        user_id="user-labels",
        user_email="steve3@wintechpartners.com",
        raw_emails=raw,
        background_corpus=corpus,
    )

    queue = get_labeling_queue("test-labels", "user-labels", limit=10)
    assert len(queue) >= 2

    # The consumer-domain recipient (buddy@gmail.com) should be flagged for review
    consumer_flagged = [q for q in queue if q.recipient_email == "buddy@gmail.com"]
    assert len(consumer_flagged) == 1
    assert consumer_flagged[0].needs_review is True
    assert consumer_flagged[0].current_bucket == "TW_MINUS"

    # Override it via /label with fidelity
    updated = set_label(
        tenant_id="test-labels",
        user_id="user-labels",
        recipient_email="buddy@gmail.com",
        fidelity="TW+3",
    )
    assert updated.current_bucket == "TW_PLUS"
    assert updated.label_source == "user"
    assert updated.needs_review is False

    # Progress reflects the user label
    prog = labeling_progress("test-labels", "user-labels")
    assert prog["user_labeled"] >= 1
    assert prog["total_recipients"] == len(queue) or prog["total_recipients"] >= len(queue)


# ---- App endpoints (sanity check) --------------------------------------

def test_app_routes_registered():
    """Just confirm the FastAPI app registered the expected endpoints."""
    from app import app
    paths = {route.path for route in app.routes}
    expected = {
        "/health", "/enroll", "/score", "/cpp-status",
        "/labeling-queue", "/label", "/labeling-progress",
    }
    missing = expected - paths
    assert not missing, f"missing routes: {missing}"
