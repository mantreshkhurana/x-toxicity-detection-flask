"""Multilingual toxicity scoring engine.

Everything that turns raw text into a toxicity score lives here so that
training (`train_multilingual.py`) and inference (`app.py`) share exactly the
same normalization — a mismatch between the two is the single most common way
a text classifier silently loses accuracy.

Two interchangeable backends:

* ``linear``      TF-IDF (word + character n-grams) feeding a soft-voting
                  ensemble of calibrated linear models. ~50 MB of RAM, a few
                  hundred microseconds per post, runs anywhere.
* ``transformer`` A fine-tuned XLM-RoBERTa classifier from the Hugging Face
                  hub. Noticeably more accurate, needs `torch` +
                  `transformers` and roughly 1-3 GB of RAM.

Pick one with the ``TOXICITY_BACKEND`` environment variable
(``auto`` | ``linear`` | ``transformer``); ``auto`` uses the transformer when
its dependencies are importable and falls back to the linear model otherwise.
"""

from __future__ import annotations

import os
import pickle
import re
import unicodedata
from dataclasses import dataclass, asdict
from functools import lru_cache
from typing import Iterable, Sequence

MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
VECTORIZER_PATH = os.path.join(MODELS_DIR, "vectorizer.pkl")
MODEL_PATH = os.path.join(MODELS_DIR, "toxicity_model.pkl")
META_PATH = os.path.join(MODELS_DIR, "model_meta.pkl")

DEFAULT_TRANSFORMER_ID = "textdetox/xlmr-large-toxicity-classifier"
DEFAULT_THRESHOLD = 50.0


# --------------------------------------------------------------------------
# text normalization
# --------------------------------------------------------------------------

_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_MENTION_RE = re.compile(r"@\w+")
_HASHTAG_RE = re.compile(r"#(\w+)")
_REPEAT_RE = re.compile(r"(.)\1{2,}", re.DOTALL)
# "f u c k" written out letter by letter; matched on single spaces only so the
# wider gap between words ("y o u  a r e") still separates them
_SPACED_LETTERS_RE = re.compile(r"(?<![a-z])(?:[a-z] ){2,}[a-z](?![a-z])")
_WS_RE = re.compile(r"\s+")

# characters with no business inside a word: soft hyphens, zero-width joiners,
# bidi overrides and friends are a classic filter-evasion trick.
_INVISIBLE_RE = re.compile("[\u00ad\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]")

# digits/symbols standing in for letters, only replaced when they sit between
# two letters (so "covid19" and "3 people" survive, "sh1t" and "f4ggot" do not)
_LEET_MAP = {
    "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b",
    "@": "a", "$": "s", "!": "i", "|": "l", "*": "",
}
_LEET_INTERIOR_RE = re.compile(r"(?<=[a-z])([0134578@$!|*])(?=[a-z])")

# Cyrillic/Greek look-alikes used to smuggle Latin words past word filters
_HOMOGLYPHS = str.maketrans({
    "а": "a", "в": "b", "е": "e", "к": "k", "м": "m", "н": "h", "о": "o",
    "р": "p", "с": "c", "т": "t", "у": "y", "х": "x", "і": "i", "ѕ": "s",
    "ј": "j", "α": "a", "ε": "e", "ο": "o", "ρ": "p", "τ": "t", "υ": "u",
    "ν": "v", "κ": "k", "ι": "i",
})
_LATIN_RE = re.compile(r"[a-z]")
_CYRILLIC_GREEK_RE = re.compile(r"[Ͱ-ϿЀ-ӿ]")


def _defeat_homoglyphs(token: str) -> str:
    """Fold Cyrillic/Greek look-alikes to Latin in mixed-script tokens only."""
    if _LATIN_RE.search(token) and _CYRILLIC_GREEK_RE.search(token):
        return token.translate(_HOMOGLYPHS)
    return token


def normalize_text(text) -> str:
    """Canonical form fed to both training and inference.

    Lowercases, strips URLs/mentions, unwraps hashtags, and undoes the common
    obfuscations (repeated characters, leetspeak, censoring symbols, spaced-out
    letters, homoglyphs) that people use to slip abuse past naive filters.
    """
    if text is None:
        return ""
    text = str(text)
    if not text.strip():
        return ""

    text = unicodedata.normalize("NFKC", text)
    text = _INVISIBLE_RE.sub("", text)
    text = text.lower()

    text = _URL_RE.sub(" ", text)
    text = _MENTION_RE.sub(" ", text)
    text = _HASHTAG_RE.sub(r"\1", text)

    # "loooool" -> "lool"; keeps the emphasis signal, kills vocabulary blowup
    text = _REPEAT_RE.sub(r"\1\1", text)

    # "f u c k   y o u" -> "fuck you", before whitespace is collapsed and the
    # double space that separates the two words is lost
    text = _SPACED_LETTERS_RE.sub(lambda m: m.group(0).replace(" ", ""), text)

    tokens = []
    for token in text.split():
        token = _defeat_homoglyphs(token)
        if _LATIN_RE.search(token):
            token = _LEET_INTERIOR_RE.sub(lambda m: _LEET_MAP[m.group(1)], token)
        tokens.append(token)

    return _WS_RE.sub(" ", " ".join(tokens)).strip()


# --------------------------------------------------------------------------
# language detection
# --------------------------------------------------------------------------

# Unicode block -> ISO code. Scripts that map 1:1 to a language are resolved
# here without any statistics at all.
_SCRIPT_RANGES = (
    ("am", 0x1200, 0x137F),   # Ethiopic
    ("hy", 0x0530, 0x058F),   # Armenian
    ("he", 0x0590, 0x05FF),   # Hebrew
    ("ar", 0x0600, 0x06FF),   # Arabic
    ("ar", 0x0750, 0x077F),
    ("th", 0x0E00, 0x0E7F),   # Thai
    ("lo", 0x0E80, 0x0EFF),   # Lao
    ("bo", 0x0F00, 0x0FFF),   # Tibetan
    ("my", 0x1000, 0x109F),   # Myanmar
    ("ka", 0x10A0, 0x10FF),   # Georgian
    ("km", 0x1780, 0x17FF),   # Khmer
    ("hi", 0x0900, 0x097F),   # Devanagari
    ("bn", 0x0980, 0x09FF),   # Bengali
    ("pa", 0x0A00, 0x0A7F),   # Gurmukhi
    ("gu", 0x0A80, 0x0AFF),   # Gujarati
    ("or", 0x0B00, 0x0B7F),   # Odia
    ("ta", 0x0B80, 0x0BFF),   # Tamil
    ("te", 0x0C00, 0x0C7F),   # Telugu
    ("kn", 0x0C80, 0x0CFF),   # Kannada
    ("ml", 0x0D00, 0x0D7F),   # Malayalam
    ("si", 0x0D80, 0x0DFF),   # Sinhala
    ("el", 0x0370, 0x03FF),   # Greek
    ("ru", 0x0400, 0x04FF),   # Cyrillic (ru stands in for the whole family)
    ("ko", 0xAC00, 0xD7AF),   # Hangul
    ("ja", 0x3040, 0x30FF),   # Hiragana + Katakana
    ("zh", 0x4E00, 0x9FFF),   # CJK ideographs
)

# Function words are the cheapest reliable signal for Latin-script languages.
_LATIN_STOPWORDS = {
    "en": {"the", "and", "you", "that", "for", "with", "this", "your", "have", "not", "are", "what", "just", "like", "was", "they", "about", "from", "would"},
    "es": {"que", "los", "las", "por", "con", "para", "una", "como", "esto", "pero", "más", "eres", "muy", "todo", "está", "porque", "del", "eso"},
    "fr": {"les", "des", "une", "que", "pour", "pas", "vous", "avec", "dans", "est", "sur", "mais", "tout", "plus", "comme", "être", "cette", "sont"},
    "de": {"und", "der", "die", "das", "ist", "nicht", "ich", "mit", "für", "auf", "ein", "eine", "sie", "sich", "auch", "dass", "aber", "noch"},
    "it": {"che", "non", "per", "una", "sono", "come", "questo", "anche", "più", "sei", "della", "solo", "tutto", "perché", "quando", "essere"},
    "pt": {"que", "não", "uma", "com", "para", "você", "por", "mais", "está", "como", "isso", "mas", "seu", "são", "quando", "porque", "muito"},
    "nl": {"het", "een", "van", "niet", "dat", "zijn", "voor", "met", "maar", "ook", "aan", "wat", "heeft", "worden", "deze"},
    "pl": {"nie", "jest", "się", "tego", "jak", "czy", "tylko", "przez", "które", "jego", "ale", "być", "tym", "gdy"},
    "tr": {"bir", "için", "değil", "daha", "çok", "gibi", "ile", "ama", "kadar", "sen", "ben", "olan", "bu"},
    "id": {"yang", "dan", "tidak", "untuk", "dengan", "dari", "ini", "itu", "sudah", "kamu", "adalah", "juga", "saya"},
    "vi": {"không", "của", "được", "những", "người", "một", "này", "cho", "với", "thì", "còn", "như"},
    "ro": {"este", "care", "pentru", "mai", "sunt", "nu", "din", "sau", "dar", "când", "foarte"},
    "sv": {"och", "att", "det", "som", "inte", "för", "med", "har", "den", "till", "man"},
    "fi": {"että", "olen", "sinä", "mutta", "kuin", "niin", "hän", "ovat", "vain", "voi"},
    "cs": {"jsem", "není", "aby", "jako", "ale", "když", "tak", "také", "jsou", "této"},
    "hu": {"hogy", "nem", "egy", "meg", "van", "csak", "mint", "már", "vagy", "ezt"},
}

_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)

# Characters that all but pin down a Latin-script language. Short posts are
# where statistical detectors are weakest, and these cost one scan to check.
_DIACRITIC_HINTS = (
    ("tr", "ğışĞİŞ"),
    ("pl", "łżźęąćńŁŻŹĘĄĆŃ"),
    ("ro", "țșȚȘ"),
    ("cs", "řůěŘŮĚ"),
    ("hu", "őűŐŰ"),
    ("vi", "ơưạảấầẩẫậắằẳẵặẹẻẽếềểễệọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ"),
)


# Cyrillic is shared by a dozen languages; these letters are not. Belarusian is
# checked before Ukrainian because both use "і" but only Belarusian uses "ў".
_CYRILLIC_HINTS = (
    ("be", "ў"),
    ("mk", "ѓќѕ"),
    ("sr", "ђћ"),
    ("uk", "їєґі"),
)

_CYRILLIC_LANGS = {"ru", "uk", "be", "bg", "mk", "sr", "kk", "ky", "mn", "tt"}


def _refine_cyrillic(text: str) -> str:
    """Split the Cyrillic bucket: decisive letters first, then `langdetect`."""
    lowered = text.lower()
    for lang, marks in _CYRILLIC_HINTS:
        if any(mark in lowered for mark in marks):
            return lang
    detect = _langdetect()
    if detect is not None:
        try:
            guess = detect(text)[:2]
            if guess in _CYRILLIC_LANGS:
                return guess
        except Exception:
            pass
    return "ru"


# Latin has letters well outside the basic block: Vietnamese lives in Latin
# Extended Additional, and phonetic/medieval extensions sit higher still.
_LATIN_RANGES = (
    (0x0000, 0x024F),
    (0x1E00, 0x1EFF),
    (0x2C60, 0x2C7F),
    (0xA720, 0xA7FF),
    (0xAB30, 0xAB6F),
)


def _script_language(text: str) -> str | None:
    counts: dict[str, int] = {}
    for ch in text:
        if not ch.isalpha():
            continue
        code = ord(ch)
        if any(lo <= code <= hi for lo, hi in _LATIN_RANGES):
            counts["__latin__"] = counts.get("__latin__", 0) + 1
            continue
        for lang, lo, hi in _SCRIPT_RANGES:
            if lo <= code <= hi:
                counts[lang] = counts.get(lang, 0) + 1
                break
        else:
            # a script this function doesn't model — let the caller fall
            # through to the statistical detector instead of guessing
            counts["__other__"] = counts.get("__other__", 0) + 1
    if not counts:
        return None
    top = max(counts, key=counts.get)
    if top in {"__latin__", "__other__"}:
        return None
    # Japanese text is mostly Han with a kana sprinkling; kana wins the tie.
    if top == "zh" and counts.get("ja", 0) > 0:
        return "ja"
    if top == "ru":
        return _refine_cyrillic(text)
    return top


def _latin_language(text: str) -> str:
    words = set(_WORD_RE.findall(text))
    if not words:
        return "und"
    best, best_hits = "en", 0
    for lang, stops in _LATIN_STOPWORDS.items():
        hits = len(words & stops)
        if hits > best_hits:
            best, best_hits = lang, hits
    return best if best_hits else "en"


@lru_cache(maxsize=1)
def _langdetect():
    """`langdetect` if installed — better than the heuristic, optional."""
    try:
        from langdetect import DetectorFactory, detect

        DetectorFactory.seed = 0
        return detect
    except Exception:
        return None


def detect_language(text) -> str:
    """Best-effort ISO 639-1 code for `text`; ``und`` when there is nothing to go on.

    Non-Latin scripts are resolved from Unicode blocks (exact and free). Latin
    text goes through `langdetect` when available, otherwise a function-word
    heuristic.
    """
    if not text:
        return "und"
    text = str(text)
    by_script = _script_language(text)
    if by_script:
        return by_script
    if len(text.strip()) < 3:
        return "und"
    for lang, marks in _DIACRITIC_HINTS:
        if any(mark in text for mark in marks):
            return lang
    detect = _langdetect()
    if detect is not None:
        try:
            return detect(text)[:2]
        except Exception:
            pass
    return _latin_language(text.lower())


# --------------------------------------------------------------------------
# backends
# --------------------------------------------------------------------------


class LinearBackend:
    """TF-IDF + soft-voting linear ensemble loaded from ``models/*.pkl``."""

    name = "linear"

    def __init__(self, vectorizer_path=VECTORIZER_PATH, model_path=MODEL_PATH):
        with open(vectorizer_path, "rb") as f:
            self.vectorizer = pickle.load(f)
        with open(model_path, "rb") as f:
            self.model = pickle.load(f)

    def predict_proba(self, normalized: Sequence[str]) -> list[float]:
        if not normalized:
            return []
        matrix = self.vectorizer.transform(normalized)
        return [float(p) for p in self.model.predict_proba(matrix)[:, 1]]


class TransformerBackend:
    """Fine-tuned XLM-R (or any HF sequence classifier) scoring toxicity."""

    name = "transformer"

    def __init__(self, model_id=None, batch_size=16, max_length=256):
        import torch  # noqa: F401  (imported for side effects / availability)
        from transformers import (
            AutoModelForSequenceClassification,
            AutoTokenizer,
        )

        self.torch = __import__("torch")
        self.model_id = model_id or os.getenv("TOXICITY_MODEL_ID", DEFAULT_TRANSFORMER_ID)
        self.batch_size = batch_size
        self.max_length = max_length
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_id)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.model_id)
        self.model.eval()
        self.toxic_index = self._find_toxic_index()

    def _find_toxic_index(self) -> int:
        labels = getattr(self.model.config, "id2label", None) or {}
        for idx, label in labels.items():
            if str(label).lower() in {"toxic", "toxicity", "hate", "offensive", "label_1"}:
                return int(idx)
        return 1 if len(labels) > 1 else 0

    def predict_proba(self, texts: Sequence[str]) -> list[float]:
        if not texts:
            return []
        scores: list[float] = []
        with self.torch.no_grad():
            for start in range(0, len(texts), self.batch_size):
                chunk = list(texts[start:start + self.batch_size])
                encoded = self.tokenizer(
                    chunk,
                    truncation=True,
                    padding=True,
                    max_length=self.max_length,
                    return_tensors="pt",
                )
                logits = self.model(**encoded).logits
                probs = self.torch.softmax(logits, dim=-1)[:, self.toxic_index]
                scores.extend(float(p) for p in probs)
        return scores


def _transformer_available() -> bool:
    from importlib.util import find_spec

    return find_spec("torch") is not None and find_spec("transformers") is not None


# --------------------------------------------------------------------------
# classifier
# --------------------------------------------------------------------------


@dataclass
class ToxicityResult:
    text: str
    score: float          # 0-100 probability that the text is toxic
    is_toxic: bool
    language: str
    threshold: float

    def as_dict(self) -> dict:
        return asdict(self)


class ToxicityClassifier:
    """Language-aware toxicity scorer.

    The decision threshold is tuned per language during training (see
    `train_multilingual.py`) because a single global cut-off systematically
    over-flags languages the model is less sure about.
    """

    def __init__(self, backend=None, meta=None):
        self.meta = meta if meta is not None else _load_meta()
        self.backend = backend if backend is not None else _build_backend()
        override = os.getenv("TOXICITY_THRESHOLD")
        self._forced_threshold = float(override) if override else None
        self._thresholds = {
            lang: float(value)
            for lang, value in (self.meta.get("thresholds") or {}).items()
        }
        self._global_threshold = float(
            self.meta.get("global_threshold") or DEFAULT_THRESHOLD
        )
        # A transformer's calibration has nothing to do with the linear
        # model's, so per-language cut-offs only apply to the backend they
        # were tuned on.
        self._use_tuned = (
            self.backend.name == "linear"
            and self.meta.get("backend", "linear") == "linear"
        )

    # -- thresholds --------------------------------------------------------
    def threshold_for(self, language: str) -> float:
        if self._forced_threshold is not None:
            return self._forced_threshold
        if not self._use_tuned:
            return DEFAULT_THRESHOLD
        return self._thresholds.get(language, self._global_threshold)

    # -- scoring -----------------------------------------------------------
    def analyze_batch(self, texts: Iterable[str]) -> list[ToxicityResult]:
        texts = list(texts)
        if not texts:
            return []
        if self.backend.name == "transformer":
            # The model was trained on raw text; de-obfuscation still helps,
            # but URLs/mentions are dropped only for the linear model, whose
            # vocabulary would otherwise fill up with handles.
            payload = [normalize_text(t) or str(t or "") for t in texts]
        else:
            payload = [normalize_text(t) for t in texts]
        probabilities = self.backend.predict_proba(payload)

        results = []
        for text, prob in zip(texts, probabilities):
            score = round(prob * 100, 2)
            language = detect_language(text)
            threshold = self.threshold_for(language)
            results.append(
                ToxicityResult(
                    text=text,
                    score=score,
                    is_toxic=score >= threshold,
                    language=language,
                    threshold=round(threshold, 2),
                )
            )
        return results

    def analyze(self, text: str) -> ToxicityResult:
        return self.analyze_batch([text])[0]

    def score(self, text: str) -> float:
        return self.analyze(text).score

    def is_toxic(self, text: str) -> bool:
        return self.analyze(text).is_toxic

    # -- introspection -----------------------------------------------------
    @property
    def info(self) -> dict:
        return {
            "backend": self.backend.name,
            "model_id": getattr(self.backend, "model_id", None),
            "languages": self.meta.get("languages", []),
            "n_samples": self.meta.get("n_samples"),
            "macro_f1": self.meta.get("macro_f1"),
            "accuracy": self.meta.get("accuracy"),
            "roc_auc": self.meta.get("roc_auc"),
            "global_threshold": self._global_threshold,
            "trained_at": self.meta.get("trained_at"),
        }


def _load_meta() -> dict:
    if os.path.exists(META_PATH):
        try:
            with open(META_PATH, "rb") as f:
                return pickle.load(f)
        except Exception as exc:  # corrupt pickle shouldn't take the app down
            print(f"[toxicity] could not read {META_PATH}: {exc}")
    return {}


def _build_backend():
    choice = (os.getenv("TOXICITY_BACKEND") or "auto").strip().lower()

    if choice == "transformer":
        return TransformerBackend()

    if choice == "auto" and _transformer_available() and os.getenv("TOXICITY_MODEL_ID"):
        # Only auto-upgrade when a model id was pinned explicitly: silently
        # downloading a multi-gigabyte checkpoint on first boot is rude.
        try:
            return TransformerBackend()
        except Exception as exc:
            print(f"[toxicity] transformer backend unavailable ({exc}); using linear model")

    if not (os.path.exists(VECTORIZER_PATH) and os.path.exists(MODEL_PATH)):
        raise FileNotFoundError(
            f"No trained model found in {MODELS_DIR}. "
            "Run `python train_multilingual.py` first."
        )
    return LinearBackend()


@lru_cache(maxsize=1)
def get_classifier() -> ToxicityClassifier:
    """Process-wide singleton; loading the model twice wastes ~50 MB."""
    return ToxicityClassifier()


__all__ = [
    "ToxicityClassifier",
    "ToxicityResult",
    "LinearBackend",
    "TransformerBackend",
    "detect_language",
    "get_classifier",
    "normalize_text",
]
