"""Train a multilingual toxicity classifier.

Downloads textdetox/multilingual_toxicity_dataset (16 languages, ~77k rows),
trains a TF-IDF (word + char n-gram) + LogisticRegression model, and persists
the fitted vectorizer and classifier to models/ so app.py can load them at
startup instead of retraining from CSV.
"""

import os
import pickle
import re

import pandas as pd
from datasets import load_dataset
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import FeatureUnion

DATASET_ID = "textdetox/multilingual_toxicity_dataset"
MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
CSV_PATH = os.path.join(MODELS_DIR, "multilingual_toxicity.csv")
VECTORIZER_PATH = os.path.join(MODELS_DIR, "vectorizer.pkl")
MODEL_PATH = os.path.join(MODELS_DIR, "toxicity_model.pkl")
META_PATH = os.path.join(MODELS_DIR, "model_meta.pkl")


def preprocess_text(text: str) -> str:
    if text is None:
        return ""
    text = str(text).lower()
    text = re.sub(r"http\S+|www\S+|https\S+", "", text)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"#(\w+)", r"\1", text)
    return " ".join(text.split())


def load_multilingual_dataframe() -> pd.DataFrame:
    print(f"Downloading {DATASET_ID} ...")
    ds = load_dataset(DATASET_ID)
    frames = []
    for lang, split in ds.items():
        df = split.to_pandas()
        df["lang"] = lang
        frames.append(df)
        print(f"  {lang}: {len(df)} rows")
    full = pd.concat(frames, ignore_index=True)
    full = full.dropna(subset=["text", "toxic"])
    full["text"] = full["text"].astype(str)
    full["toxic"] = full["toxic"].astype(int)
    print(f"Total: {len(full)} rows across {full['lang'].nunique()} languages")
    return full


def save_legacy_csv(df: pd.DataFrame) -> None:
    legacy = pd.DataFrame(
        {
            "text": df["text"],
            "is_toxic": df["toxic"].map({1: "Toxic", 0: "Not Toxic"}),
        }
    )
    legacy.to_csv(CSV_PATH, index=False)
    print(f"Wrote merged CSV: {CSV_PATH}")


def build_vectorizer() -> FeatureUnion:
    word_vec = TfidfVectorizer(
        analyzer="word",
        ngram_range=(1, 2),
        max_features=60000,
        min_df=2,
        max_df=0.95,
        sublinear_tf=True,
    )
    char_vec = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(3, 5),
        max_features=60000,
        min_df=2,
        max_df=0.95,
        sublinear_tf=True,
    )
    return FeatureUnion([("word", word_vec), ("char", char_vec)])


def main() -> None:
    os.makedirs(MODELS_DIR, exist_ok=True)

    df = load_multilingual_dataframe()
    save_legacy_csv(df)

    x_raw = df["text"].map(preprocess_text)
    y = df["toxic"].values

    x_train_raw, x_test_raw, y_train, y_test = train_test_split(
        x_raw, y, test_size=0.1, random_state=42, stratify=y
    )

    vectorizer = build_vectorizer()
    print("Fitting TF-IDF (word + char n-grams) ...")
    x_train = vectorizer.fit_transform(x_train_raw)
    x_test = vectorizer.transform(x_test_raw)
    print(f"Feature matrix: {x_train.shape}")

    model = LogisticRegression(
        max_iter=2000,
        C=4.0,
        class_weight="balanced",
        solver="liblinear",
    )
    print("Training LogisticRegression ...")
    model.fit(x_train, y_train)

    preds = model.predict(x_test)
    macro_f1 = f1_score(y_test, preds, average="macro")
    print(f"\nHold-out macro F1: {macro_f1:.4f}")
    print(classification_report(y_test, preds, target_names=["Not Toxic", "Toxic"]))

    with open(VECTORIZER_PATH, "wb") as f:
        pickle.dump(vectorizer, f)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)
    with open(META_PATH, "wb") as f:
        pickle.dump(
            {
                "dataset": DATASET_ID,
                "languages": sorted(df["lang"].unique().tolist()),
                "n_samples": int(len(df)),
                "macro_f1": float(macro_f1),
            },
            f,
        )
    print(f"\nSaved: {VECTORIZER_PATH}")
    print(f"Saved: {MODEL_PATH}")
    print(f"Saved: {META_PATH}")


if __name__ == "__main__":
    main()
