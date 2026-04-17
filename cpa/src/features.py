"""
Stylometric feature extraction.

Three parallel feature sets, concatenated into one vector per email:

  1. Character n-grams (3-to-5 char sliding windows) via TF-IDF.
     Fine-grained subliminal style signal that survives topic changes.
  2. Function-word frequency (150-word lexicon).
     Topic-independent markers of unconscious usage patterns.
  3. Structural features (sentence length stats, punctuation rate,
     pronoun usage, contraction rate, paragraph organization).
     What's happening at the shape level.

Design notes for next-Claude:
  - The TF-IDF vectorizer is FITTED on the user's training corpus during
    enrollment, then pickled into the CPP-E. At scoring time we load the
    fitted vectorizer and transform-only. Do not refit at scoring time.
  - Function-word lexicon is fixed at module load (not per-user). It's a
    closed set of English function words from the stylometry literature.
  - Structural features are normalized (rates per 1000 words, ratios) so
    short and long emails are comparable.
  - Returns a single dense numpy array per email. Char n-grams come from
    a sparse source but we densify for XGBoost; CHAR_NGRAM_MAX_FEATURES
    caps the width so this stays tractable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

import numpy as np
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer

from config import CHAR_NGRAM_MAX_FEATURES, CHAR_NGRAM_RANGE


# ---- Function-word lexicon ----------------------------------------------

# Standard ~150-word English function-word list drawn from stylometric
# literature. Small closed class of words whose frequency varies with
# author but not with topic.
FUNCTION_WORDS = (
    "a", "about", "above", "after", "again", "against", "all", "am", "an",
    "and", "any", "are", "as", "at", "be", "because", "been", "before",
    "being", "below", "between", "both", "but", "by", "can", "could", "did",
    "do", "does", "doing", "don", "down", "during", "each", "few", "for",
    "from", "further", "had", "has", "have", "having", "he", "her", "here",
    "hers", "herself", "him", "himself", "his", "how", "i", "if", "in",
    "into", "is", "it", "its", "itself", "just", "me", "more", "most", "my",
    "myself", "no", "nor", "not", "now", "of", "off", "on", "once", "only",
    "or", "other", "our", "ours", "ourselves", "out", "over", "own", "same",
    "she", "should", "so", "some", "such", "than", "that", "the", "their",
    "theirs", "them", "themselves", "then", "there", "these", "they", "this",
    "those", "through", "to", "too", "under", "until", "up", "very", "was",
    "we", "were", "what", "when", "where", "which", "while", "who", "whom",
    "why", "will", "with", "would", "you", "your", "yours", "yourself",
    "yourselves", "also", "actually", "really", "well", "yeah", "ok", "okay",
    "thanks", "please", "sorry", "however", "therefore", "though", "although",
    "since", "while", "whereas",
)

FUNCTION_WORD_INDEX = {w: i for i, w in enumerate(FUNCTION_WORDS)}
FUNCTION_WORD_COUNT = len(FUNCTION_WORDS)

# Tokenizer for function-word counting. Lowercases and splits on whitespace/punct.
_TOKENIZE_RE = re.compile(r"[a-zA-Z']+")

# Sentence-split regex. Good enough for stylometry; we're not doing NLP.
_SENT_SPLIT_RE = re.compile(r"[.!?]+")

# Contraction detector: "don't", "it's", "I'd", "we'll"
_CONTRACTION_RE = re.compile(r"\b\w+'(?:s|t|d|ll|ve|re|m)\b", re.IGNORECASE)

# First/second/third person pronoun sets
FIRST_PERSON = frozenset({"i", "me", "my", "mine", "myself", "we", "us", "our", "ours", "ourselves"})
SECOND_PERSON = frozenset({"you", "your", "yours", "yourself", "yourselves"})
THIRD_PERSON = frozenset({"he", "him", "his", "she", "her", "hers", "it", "its", "they", "them", "their", "theirs"})


# ---- Structural features ------------------------------------------------

# Fixed-order list of the structural feature names. The order is the feature-
# vector order; do not shuffle without bumping the CPP format version.
STRUCTURAL_FEATURE_NAMES = (
    "sent_length_mean",
    "sent_length_std",
    "word_length_mean",
    "word_length_std",
    "punct_per_1000",
    "comma_per_1000",
    "exclaim_per_1000",
    "question_per_1000",
    "uppercase_ratio",
    "digit_ratio",
    "contraction_rate",
    "first_person_rate",
    "second_person_rate",
    "third_person_rate",
    "paragraph_count",
    "line_count",
    "word_count",
    "avg_words_per_paragraph",
)


def _structural_features(text: str) -> np.ndarray:
    """Compute the structural feature vector for one email. Returns float array."""
    if not text or not text.strip():
        return np.zeros(len(STRUCTURAL_FEATURE_NAMES), dtype=np.float32)

    tokens = _TOKENIZE_RE.findall(text)
    word_count = max(len(tokens), 1)
    char_count = max(len(text), 1)

    sentences = [s.strip() for s in _SENT_SPLIT_RE.split(text) if s.strip()]
    sent_lengths = [len(_TOKENIZE_RE.findall(s)) for s in sentences] or [0]

    word_lengths = [len(t) for t in tokens] or [0]

    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]

    first = sum(1 for t in tokens if t.lower() in FIRST_PERSON)
    second = sum(1 for t in tokens if t.lower() in SECOND_PERSON)
    third = sum(1 for t in tokens if t.lower() in THIRD_PERSON)

    punct_count = sum(1 for c in text if c in ".,!?;:")
    comma_count = text.count(",")
    exclaim_count = text.count("!")
    question_count = text.count("?")
    upper_count = sum(1 for c in text if c.isupper())
    digit_count = sum(1 for c in text if c.isdigit())
    contraction_count = len(_CONTRACTION_RE.findall(text))

    features = [
        float(np.mean(sent_lengths)),
        float(np.std(sent_lengths)) if len(sent_lengths) > 1 else 0.0,
        float(np.mean(word_lengths)),
        float(np.std(word_lengths)) if len(word_lengths) > 1 else 0.0,
        (punct_count / word_count) * 1000.0,
        (comma_count / word_count) * 1000.0,
        (exclaim_count / word_count) * 1000.0,
        (question_count / word_count) * 1000.0,
        upper_count / char_count,
        digit_count / char_count,
        contraction_count / word_count,
        first / word_count,
        second / word_count,
        third / word_count,
        float(len(paragraphs)),
        float(len(text.splitlines())),
        float(word_count),
        float(word_count / max(len(paragraphs), 1)),
    ]
    return np.array(features, dtype=np.float32)


def _function_word_features(text: str) -> np.ndarray:
    """Function-word frequency vector. Counts normalized by token count."""
    vec = np.zeros(FUNCTION_WORD_COUNT, dtype=np.float32)
    if not text:
        return vec
    tokens = [t.lower() for t in _TOKENIZE_RE.findall(text)]
    if not tokens:
        return vec
    for t in tokens:
        idx = FUNCTION_WORD_INDEX.get(t)
        if idx is not None:
            vec[idx] += 1.0
    vec /= len(tokens)
    return vec


# ---- Feature extractor ---------------------------------------------------

@dataclass
class FeatureExtractor:
    """
    Fits a char-ngram TF-IDF vectorizer on a training corpus, then transforms
    new emails into the concatenated feature vector (char-ngrams + function
    words + structural).

    Lifecycle:
        extractor = FeatureExtractor()
        extractor.fit(training_texts)     # call once during enrollment
        X = extractor.transform(texts)    # call many times at scoring time

    The fitted char_vectorizer is what makes this per-user: different users
    have different high-weight character n-grams. Pickle the whole
    FeatureExtractor into the CPP-E.
    """

    char_vectorizer: TfidfVectorizer | None = None

    def fit(self, texts: Iterable[str]) -> "FeatureExtractor":
        text_list = [t or "" for t in texts]
        self.char_vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=CHAR_NGRAM_RANGE,
            max_features=CHAR_NGRAM_MAX_FEATURES,
            sublinear_tf=True,
            lowercase=True,
        )
        self.char_vectorizer.fit(text_list)
        return self

    def transform(self, texts: Iterable[str]) -> csr_matrix:
        if self.char_vectorizer is None:
            raise RuntimeError("FeatureExtractor.transform called before fit")
        text_list = [t or "" for t in texts]

        # Char n-grams (sparse)
        char_X = self.char_vectorizer.transform(text_list)

        # Function-word frequencies (dense → sparse)
        fn_X = np.stack([_function_word_features(t) for t in text_list], axis=0)
        fn_X = csr_matrix(fn_X)

        # Structural features (dense → sparse)
        st_X = np.stack([_structural_features(t) for t in text_list], axis=0)
        st_X = csr_matrix(st_X)

        # Concatenate into one feature matrix: [char_ngrams | function_words | structural]
        return hstack([char_X, fn_X, st_X]).tocsr()

    def fit_transform(self, texts: Iterable[str]) -> csr_matrix:
        text_list = list(texts)
        self.fit(text_list)
        return self.transform(text_list)

    @property
    def feature_dim(self) -> int:
        """Total width of the feature vector."""
        if self.char_vectorizer is None:
            raise RuntimeError("feature_dim called before fit")
        char_width = len(self.char_vectorizer.vocabulary_)
        return char_width + FUNCTION_WORD_COUNT + len(STRUCTURAL_FEATURE_NAMES)
