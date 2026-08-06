"""Train the multilingual toxicity classifier.

Merges two public corpora, trains a TF-IDF (word + character n-gram) soft-voting
ensemble of linear models, tunes one decision threshold per language, and
persists the vectorizer, the classifier and a metadata blob to `models/` so
`app.py` can load them at startup instead of training on every boot.

Corpora
    textdetox/multilingual_toxicity_dataset   ~71k rows, 15 languages, balanced
                                              and human-annotated
    FredZhang7/toxi-text-3M                   ~2.9M rows, 55 languages, sampled
                                              per language so English cannot
                                              drown out everything else

Usage
    python train_multilingual.py                    # full run (recommended)
    python train_multilingual.py --preset fast      # textdetox only, ~1 minute
    python train_multilingual.py --max-per-label 20000
    python train_multilingual.py --skip-if-exists   # no-op when models exist
"""

from __future__ import annotations

import argparse
import os
import pickle
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import VotingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    f1_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import FeatureUnion
from sklearn.svm import LinearSVC

from toxicity import META_PATH, MODEL_PATH, MODELS_DIR, VECTORIZER_PATH, normalize_text

TEXTDETOX_ID = "textdetox/multilingual_toxicity_dataset"
TOXI3M_ID = "FredZhang7/toxi-text-3M"
TOXI3M_TRAIN = "train/multilingual-train-deduplicated.csv"
TOXI3M_VALID = "validation/multilingual-validation(new).csv"
COLD_ID = "Fallen03/COLDataset"          # Chinese offensive language
UNSMILE_ID = "smilegate-ai/kor_unsmile"  # Korean hate speech

LEGACY_CSV = os.path.join(MODELS_DIR, "multilingual_toxicity.csv")
HOLDOUT_CSV = os.path.join(MODELS_DIR, "holdout.csv")

RANDOM_STATE = 42
MIN_LANG_SUPPORT = 300      # below this a per-language threshold is noise
HOLDOUT_ROWS = 40000        # what evaluate_model.py reads back


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------


def load_textdetox() -> pd.DataFrame:
    from datasets import load_dataset

    print(f"[data] {TEXTDETOX_ID}")
    ds = load_dataset(TEXTDETOX_ID)
    frames = []
    for lang, split in ds.items():
        frame = split.to_pandas()[["text", "toxic"]].copy()
        frame["lang"] = "hi" if lang == "hin" else lang
        frame = frame.rename(columns={"toxic": "is_toxic"})
        frames.append(frame)
    out = pd.concat(frames, ignore_index=True)
    out["is_toxic"] = out["is_toxic"].astype(int)
    print(f"[data]   {len(out):,} rows / {out['lang'].nunique()} languages")
    return out


def _read_toxi3m(filename: str, max_per_label: int | None) -> pd.DataFrame:
    from huggingface_hub import hf_hub_download

    print(f"[data] {TOXI3M_ID}:{filename}")
    path = hf_hub_download(TOXI3M_ID, filename, repo_type="dataset")

    # 2.9M rows / 1.4 GB: stream it in chunks and keep a per-language,
    # per-label quota so English (88% of the corpus) cannot dominate.
    kept: dict[tuple[str, int], list[pd.DataFrame]] = {}
    counts: dict[tuple[str, int], int] = {}
    reader = pd.read_csv(
        path,
        chunksize=250_000,
        usecols=["text", "is_toxic", "lang"],
        dtype={"text": str, "lang": str},
        on_bad_lines="skip",
    )
    for chunk in reader:
        chunk = chunk.dropna(subset=["text", "is_toxic"])
        chunk["is_toxic"] = pd.to_numeric(chunk["is_toxic"], errors="coerce")
        chunk = chunk.dropna(subset=["is_toxic"])
        chunk["is_toxic"] = chunk["is_toxic"].astype(int)
        # "unknown" is a label, not a language; truncating it to "un" would
        # invent an ISO code and publish it in the supported-language list.
        chunk["lang"] = (
            chunk["lang"].fillna("und").str.lower().str.slice(0, 2).replace({"un": "und"})
        )
        for key, group in chunk.groupby(["lang", "is_toxic"]):
            taken = counts.get(key, 0)
            room = len(group) if max_per_label is None else max_per_label - taken
            if room <= 0:
                continue
            group = group.head(room)
            kept.setdefault(key, []).append(group)
            counts[key] = taken + len(group)
    out = pd.concat([f for frames in kept.values() for f in frames], ignore_index=True)
    print(f"[data]   {len(out):,} rows / {out['lang'].nunique()} languages")
    return out


def load_extras() -> list[pd.DataFrame]:
    """Language-specific corpora for the languages the merged data is thin on.

    Chinese and Korean are the two weakest languages in the big corpora — a
    few hundred rows each — so they get dedicated datasets. A dataset that
    fails to download is skipped rather than taking the whole run down.
    """
    from datasets import load_dataset

    frames = []

    try:  # Chinese: COLDataset, instruction-formatted offensive language
        print(f"[data] {COLD_ID}")
        cold = load_dataset(COLD_ID)["train"].to_pandas()
        cold = cold[cold["output"].astype(str).str.strip().isin(["0", "1"])]
        frames.append(pd.DataFrame({
            "text": cold["input"].astype(str),
            "is_toxic": cold["output"].astype(str).str.strip().astype(int),
            "lang": "zh",
        }))
        print(f"[data]   {len(frames[-1]):,} rows (zh)")
    except Exception as exc:
        print(f"[data]   skipped {COLD_ID}: {exc}")

    try:  # Korean: kor_unsmile, 'clean' == 1 means not hateful
        print(f"[data] {UNSMILE_ID}")
        unsmile = load_dataset(UNSMILE_ID)["train"].to_pandas()
        frames.append(pd.DataFrame({
            "text": unsmile["문장"].astype(str),
            "is_toxic": 1 - unsmile["clean"].astype(int),
            "lang": "ko",
        }))
        print(f"[data]   {len(frames[-1]):,} rows (ko)")
    except Exception as exc:
        print(f"[data]   skipped {UNSMILE_ID}: {exc}")

    return frames


def build_dataset(preset: str, max_per_label: int | None, extras: bool) -> pd.DataFrame:
    frames = [load_textdetox()]
    if preset == "full":
        frames.append(_read_toxi3m(TOXI3M_TRAIN, max_per_label))
    if extras:
        frames.extend(load_extras())
    df = pd.concat(frames, ignore_index=True)

    df["text"] = df["text"].astype(str)
    df["normalized"] = df["text"].map(normalize_text)
    df = df[df["normalized"].str.len() >= 2]

    # Identical text with contradictory labels is pure noise — drop both copies
    # rather than letting the coin-flip decide.
    before = len(df)
    label_spread = df.groupby("normalized")["is_toxic"].transform("nunique")
    df = df[label_spread == 1]
    df = df.drop_duplicates(subset="normalized", keep="first").reset_index(drop=True)
    print(
        f"[data] deduplicated {before:,} -> {len(df):,} rows "
        f"({df['is_toxic'].mean():.1%} toxic, {df['lang'].nunique()} languages)"
    )
    return df


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------


def build_vectorizer(max_word_features: int, max_char_features: int) -> FeatureUnion:
    """Word n-grams catch vocabulary, character n-grams catch morphology.

    The character half is what makes this work across 50+ languages at all:
    it handles agglutinative morphology, unsegmented scripts (zh/ja/th) and
    creative misspellings that word tokens miss entirely.
    """
    word = TfidfVectorizer(
        analyzer="word",
        ngram_range=(1, 2),
        max_features=max_word_features,
        min_df=2,
        max_df=0.9,
        sublinear_tf=True,
        strip_accents=None,
    )
    char = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 5),
        max_features=max_char_features,
        min_df=3,
        max_df=0.9,
        sublinear_tf=True,
    )
    return FeatureUnion([("word", word), ("char", char)], n_jobs=2)


def build_model(n_jobs: int) -> VotingClassifier:
    """Three linear models with different loss functions, averaged.

    They fail on different examples — logistic regression is well calibrated,
    the hinge-loss SVM draws a wider margin, and the modified-Huber SGD is the
    most tolerant of label noise — so the soft vote beats every member.
    """
    logreg = LogisticRegression(
        C=6.0,
        solver="liblinear",
        class_weight="balanced",
        max_iter=3000,
    )
    svm = CalibratedClassifierCV(
        LinearSVC(C=0.5, class_weight="balanced", max_iter=5000),
        method="sigmoid",
        cv=3,
    )
    sgd = SGDClassifier(
        loss="modified_huber",
        alpha=1e-6,
        class_weight="balanced",
        max_iter=30,
        tol=1e-4,
        random_state=RANDOM_STATE,
    )
    return VotingClassifier(
        estimators=[("logreg", logreg), ("svm", svm), ("sgd", sgd)],
        voting="soft",
        weights=[2, 2, 1],
        n_jobs=n_jobs,
    )


# --------------------------------------------------------------------------
# thresholds + metrics
# --------------------------------------------------------------------------


def best_threshold(y_true: np.ndarray, probabilities: np.ndarray) -> tuple[float, float]:
    """Threshold (as a percentage) maximizing F1 on the given slice."""
    grid = np.arange(0.05, 0.96, 0.01)
    best_cut, best_score = 0.5, -1.0
    for cut in grid:
        score = f1_score(y_true, probabilities >= cut, zero_division=0)
        if score > best_score:
            best_cut, best_score = float(cut), float(score)
    return round(best_cut * 100, 2), best_score


def tune_thresholds(frame: pd.DataFrame) -> tuple[float, dict[str, float]]:
    global_cut, global_f1 = best_threshold(
        frame["is_toxic"].values, frame["prob"].values
    )
    print(f"[tune] global threshold {global_cut:.1f}% (val F1 {global_f1:.4f})")

    per_language: dict[str, float] = {}
    for lang, group in frame.groupby("lang"):
        if len(group) < MIN_LANG_SUPPORT or group["is_toxic"].nunique() < 2:
            continue
        cut, score = best_threshold(group["is_toxic"].values, group["prob"].values)
        baseline = f1_score(
            group["is_toxic"].values, group["prob"].values >= global_cut / 100,
            zero_division=0,
        )
        # Only keep a language-specific cut-off when it actually earns its keep.
        if score > baseline + 0.002:
            per_language[lang] = cut
            print(
                f"[tune]   {lang}: {cut:.1f}%  F1 {baseline:.4f} -> {score:.4f} "
                f"(n={len(group)})"
            )
    return global_cut, per_language


def evaluate(frame: pd.DataFrame, global_cut: float, per_language: dict[str, float]):
    cuts = frame["lang"].map(lambda l: per_language.get(l, global_cut)).values / 100
    predictions = (frame["prob"].values >= cuts).astype(int)
    truth = frame["is_toxic"].values

    metrics = {
        "accuracy": float(accuracy_score(truth, predictions)),
        "macro_f1": float(f1_score(truth, predictions, average="macro")),
        "toxic_f1": float(f1_score(truth, predictions, zero_division=0)),
        "roc_auc": float(roc_auc_score(truth, frame["prob"].values)),
    }
    print("\n[eval] overall")
    print(
        f"[eval]   accuracy {metrics['accuracy']:.4f} | macro F1 "
        f"{metrics['macro_f1']:.4f} | ROC-AUC {metrics['roc_auc']:.4f}"
    )
    print(classification_report(truth, predictions, target_names=["Not Toxic", "Toxic"]))

    per_language_metrics = {}
    print(f"[eval] per language (support >= {MIN_LANG_SUPPORT // 3})")
    print(f"[eval]   {'lang':<6}{'n':>8}{'acc':>9}{'macro F1':>11}")
    for lang, group in sorted(frame.groupby("lang"), key=lambda kv: -len(kv[1])):
        if len(group) < MIN_LANG_SUPPORT // 3:
            continue
        cut = per_language.get(lang, global_cut) / 100
        preds = (group["prob"].values >= cut).astype(int)
        entry = {
            "n": int(len(group)),
            "accuracy": float(accuracy_score(group["is_toxic"].values, preds)),
            "macro_f1": float(
                f1_score(group["is_toxic"].values, preds, average="macro", zero_division=0)
            ),
        }
        per_language_metrics[lang] = entry
        print(
            f"[eval]   {lang:<6}{entry['n']:>8}{entry['accuracy']:>9.4f}"
            f"{entry['macro_f1']:>11.4f}"
        )
    return metrics, per_language_metrics


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preset", choices=["fast", "full"], default="full",
        help="fast = textdetox only (CI/low-memory), full = both corpora",
    )
    parser.add_argument(
        "--max-per-label", type=int, default=60000,
        help="cap of toxi-text-3M rows per language per label (0 = no cap)",
    )
    parser.add_argument("--word-features", type=int, default=400000)
    parser.add_argument("--char-features", type=int, default=600000)
    parser.add_argument("--test-size", type=float, default=0.08)
    parser.add_argument("--val-size", type=float, default=0.08)
    # >1 makes joblib memmap the sparse matrix read-only, which liblinear and
    # SGD refuse to work with ("WRITEBACKIFCOPY base is read-only").
    parser.add_argument("--n-jobs", type=int, default=1)
    parser.add_argument(
        "--skip-if-exists", action="store_true",
        help="exit successfully when a trained model is already present",
    )
    parser.add_argument(
        "--dump-csv", action="store_true",
        help="also write the merged corpus to models/multilingual_toxicity.csv "
             "(nothing reads it at runtime; it is for inspection only)",
    )
    parser.add_argument(
        "--no-extras", action="store_true",
        help="skip the Chinese and Korean language-specific corpora",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    os.makedirs(MODELS_DIR, exist_ok=True)

    if args.skip_if_exists and os.path.exists(MODEL_PATH) and os.path.exists(VECTORIZER_PATH):
        print("[train] model already present; nothing to do")
        return

    started = datetime.now(timezone.utc)
    df = build_dataset(args.preset, args.max_per_label or None, not args.no_extras)

    # Stratify on language *and* label so every language keeps a fair share of
    # both classes in validation and test.
    strata = df["lang"] + "_" + df["is_toxic"].astype(str)
    counts = strata.value_counts()
    strata = strata.where(strata.map(counts) >= 3, "rare")

    train_df, holdout_df = train_test_split(
        df,
        test_size=args.test_size + args.val_size,
        random_state=RANDOM_STATE,
        stratify=strata,
    )
    holdout_strata = holdout_df["lang"] + "_" + holdout_df["is_toxic"].astype(str)
    holdout_counts = holdout_strata.value_counts()
    holdout_strata = holdout_strata.where(holdout_strata.map(holdout_counts) >= 2, "rare")
    val_df, test_df = train_test_split(
        holdout_df,
        test_size=args.test_size / (args.test_size + args.val_size),
        random_state=RANDOM_STATE,
        stratify=holdout_strata,
    )
    print(
        f"[train] split: {len(train_df):,} train / {len(val_df):,} val / "
        f"{len(test_df):,} test"
    )

    vectorizer = build_vectorizer(args.word_features, args.char_features)
    print("[train] fitting TF-IDF (word 1-2 + char_wb 2-5) ...")
    x_train = vectorizer.fit_transform(train_df["normalized"])
    x_train.sort_indices()  # liblinear/SGD would otherwise sort in place
    print(f"[train]   feature matrix {x_train.shape[0]:,} x {x_train.shape[1]:,}")
    x_val = vectorizer.transform(val_df["normalized"])
    x_test = vectorizer.transform(test_df["normalized"])

    model = build_model(args.n_jobs)
    print("[train] fitting soft-voting ensemble (logreg + calibrated SVM + SGD) ...")
    model.fit(x_train, train_df["is_toxic"].values)

    val_scored = val_df.assign(prob=model.predict_proba(x_val)[:, 1])
    global_cut, per_language_cuts = tune_thresholds(val_scored)

    test_scored = test_df.assign(prob=model.predict_proba(x_test)[:, 1])
    metrics, per_language_metrics = evaluate(test_scored, global_cut, per_language_cuts)

    meta = {
        "backend": "linear",
        "datasets": (
            [TEXTDETOX_ID]
            + ([TOXI3M_ID] if args.preset == "full" else [])
            + ([COLD_ID, UNSMILE_ID] if not args.no_extras else [])
        ),
        "preset": args.preset,
        "languages": sorted(set(df["lang"].unique()) - {"und"}),
        "n_samples": int(len(df)),
        "n_train": int(len(train_df)),
        "n_test": int(len(test_df)),
        "global_threshold": global_cut,
        "thresholds": per_language_cuts,
        "per_language": per_language_metrics,
        "trained_at": started.isoformat(timespec="seconds"),
        "sklearn_version": __import__("sklearn").__version__,
        **metrics,
    }

    with open(VECTORIZER_PATH, "wb") as f:
        pickle.dump(vectorizer, f, protocol=pickle.HIGHEST_PROTOCOL)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f, protocol=pickle.HIGHEST_PROTOCOL)
    with open(META_PATH, "wb") as f:
        pickle.dump(meta, f, protocol=pickle.HIGHEST_PROTOCOL)

    test_df.head(HOLDOUT_ROWS)[["text", "is_toxic", "lang"]].to_csv(
        HOLDOUT_CSV, index=False
    )
    if args.dump_csv:
        df[["text", "is_toxic", "lang"]].to_csv(LEGACY_CSV, index=False)
        print(f"[train] saved {LEGACY_CSV}")

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    print(f"\n[train] saved {VECTORIZER_PATH}")
    print(f"[train] saved {MODEL_PATH}")
    print(f"[train] saved {META_PATH}")
    print(f"[train] saved {HOLDOUT_CSV}")
    print(f"[train] done in {elapsed / 60:.1f} min")


if __name__ == "__main__":
    sys.exit(main())
