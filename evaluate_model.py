"""Measure the toxicity model, honestly.

Two modes:

    python evaluate_model.py            # held-out test split written by training
    python evaluate_model.py --smoke    # hand-written multilingual sanity set

Both respect TOXICITY_BACKEND, so the same command reports the linear model or
the transformer depending on how the app is configured:

    TOXICITY_BACKEND=transformer python evaluate_model.py
"""

from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

from toxicity import MODELS_DIR, get_classifier

HOLDOUT_CSV = os.path.join(MODELS_DIR, "holdout.csv")

# A few obvious cases per script — not a benchmark, just a tripwire for
# "did the model or the preprocessing break entirely?"
SMOKE_SET = [
    # (text, expected_toxic, language)
    ("You are an amazing person, thank you for this", 0, "en"),
    ("shut up you worthless piece of trash, nobody wants you here", 1, "en"),
    ("Great thread, learned a lot today", 0, "en"),
    ("i hope you die you disgusting freak", 1, "en"),
    ("Muchas gracias por compartir, me sirvió mucho", 0, "es"),
    ("eres un idiota de mierda, callate ya", 1, "es"),
    ("Merci beaucoup pour ce partage, très utile", 0, "fr"),
    ("ferme ta gueule sale connard", 1, "fr"),
    ("Vielen Dank für die ausführliche Erklärung", 0, "de"),
    ("du bist ein dummes arschloch, verpiss dich", 1, "de"),
    ("Grazie mille per il tuo lavoro, ottimo articolo", 0, "it"),
    ("sei uno stronzo di merda, vaffanculo", 1, "it"),
    ("Obrigado pela ajuda, ficou muito claro", 0, "pt"),
    ("cala a boca seu idiota de merda", 1, "pt"),
    ("Спасибо большое за подробное объяснение", 0, "ru"),
    ("ты тупой урод, заткнись уже", 1, "ru"),
    ("Дуже дякую за корисну інформацію", 0, "uk"),
    ("ти повний ідіот, замовкни", 1, "uk"),
    ("شكرا جزيلا على هذه المعلومات المفيدة", 0, "ar"),
    ("أنت غبي وحقير اخرس", 1, "ar"),
    ("इस जानकारी के लिए बहुत बहुत धन्यवाद", 0, "hi"),
    ("तू बेवकूफ कमीना है, चुप हो जा", 1, "hi"),
    ("この記事はとても勉強になりました、ありがとう", 0, "ja"),
    ("お前は本当にバカだ、消えろ", 1, "ja"),
    ("感谢分享，这篇文章非常有用", 0, "zh"),
    ("你这个白痴，滚开", 1, "zh"),
    ("Bu paylaşım için çok teşekkür ederim", 0, "tr"),
    ("seni aptal şerefsiz, defol git", 1, "tr"),
    ("Terima kasih banyak atas informasinya", 0, "id"),
    ("dasar bodoh, diam kamu", 1, "id"),
    # obfuscation: these must survive normalization
    ("you are a f*cking idiot", 1, "en"),
    ("y o u   a r e   s c u m", 1, "en"),
    ("sh1t take, you're an 1diot", 1, "en"),
    ("Loooove this so muchhhh", 0, "en"),
]


def report(frame: pd.DataFrame, title: str) -> float:
    """Print an accuracy/F1 table; returns overall accuracy."""
    from sklearn.metrics import accuracy_score, f1_score, roc_auc_score

    truth = frame["is_toxic"].values
    predicted = frame["predicted"].values
    accuracy = accuracy_score(truth, predicted)
    macro_f1 = f1_score(truth, predicted, average="macro", zero_division=0)

    print(f"\n{title}")
    print(f"  rows       {len(frame):,}")
    print(f"  accuracy   {accuracy:.4f}")
    print(f"  macro F1   {macro_f1:.4f}")
    if len(set(truth)) > 1:
        print(f"  ROC-AUC    {roc_auc_score(truth, frame['score'].values):.4f}")

    print(f"\n  {'lang':<6}{'n':>7}{'acc':>9}{'macro F1':>11}")
    for lang, group in sorted(frame.groupby("lang"), key=lambda kv: -len(kv[1])):
        if len(group) < 20:
            continue
        print(
            f"  {lang:<6}{len(group):>7}"
            f"{accuracy_score(group['is_toxic'], group['predicted']):>9.4f}"
            f"{f1_score(group['is_toxic'], group['predicted'], average='macro', zero_division=0):>11.4f}"
        )
    return float(accuracy)


def run_holdout(classifier, limit: int | None) -> int:
    if not os.path.exists(HOLDOUT_CSV):
        print(
            f"No held-out set at {HOLDOUT_CSV}. Run `python train_multilingual.py` "
            "first, or use --smoke."
        )
        return 1
    frame = pd.read_csv(HOLDOUT_CSV).dropna(subset=["text"])
    if limit:
        frame = frame.head(limit)
    results = classifier.analyze_batch(frame["text"].astype(str).tolist())
    frame = frame.assign(
        score=[r.score for r in results],
        predicted=[int(r.is_toxic) for r in results],
    )
    report(frame, f"Held-out test split ({classifier.backend.name} backend)")
    return 0


def run_smoke(classifier) -> int:
    frame = pd.DataFrame(SMOKE_SET, columns=["text", "is_toxic", "lang"])
    results = classifier.analyze_batch(frame["text"].tolist())
    frame = frame.assign(
        score=[r.score for r in results],
        predicted=[int(r.is_toxic) for r in results],
        detected=[r.language for r in results],
    )
    print(f"Multilingual smoke set ({classifier.backend.name} backend)\n")
    print(f"  {'ok':<4}{'lang':<6}{'det':<6}{'score':>8}  text")
    for row in frame.itertuples():
        mark = "✓" if row.predicted == row.is_toxic else "✗"
        print(
            f"  {mark:<4}{row.lang:<6}{row.detected:<6}{row.score:>7.1f}%  "
            f"{row.text[:56]}"
        )
    accuracy = report(frame, "Smoke summary")
    return 0 if accuracy >= 0.8 else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="run the hand-written set")
    parser.add_argument("--limit", type=int, default=None, help="cap held-out rows")
    args = parser.parse_args()

    classifier = get_classifier()
    info = classifier.info
    print(
        f"backend={info['backend']} languages={len(info['languages'])} "
        f"trained_at={info.get('trained_at')}"
    )

    if args.smoke:
        return run_smoke(classifier)
    return run_holdout(classifier, args.limit)


if __name__ == "__main__":
    sys.exit(main())
