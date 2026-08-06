<img src="./images/logo.png" width="50" height="50">

# X Toxicity Detection

Analyzes X (formerly Twitter) user posts for toxicity with a machine learning model that works in **56 languages**. **No Twitter/X API required** - posts come from X's public syndication endpoint.

Two frontends over one Python service:

- a **Next.js + React app** in [web/](web/) that mirrors X's real interface - three-column layout, Default / Dim / Lights out themes, timeline and profile patterns
- the original **Flask-rendered UI**, including a [Window GUI](#window-gui) version that runs without a browser

## Table of Contents

- [X Toxicity Detection](#x-toxicity-detection)
  - [Demo](#demo)
    - [Demo Video](#demo-video)
    - [Screenshots](#screenshots)
    - [Pie Chart](#pie-chart)
    - [Window GUI](#window-gui)
  - [Installation](#installation)
  - [Usage](#usage)
  - [Next.js Frontend](#nextjs-frontend)
  - [Features](#features)
  - [The Toxicity Model](#the-toxicity-model)
    - [Accuracy](#accuracy)
    - [Supported Languages](#supported-languages)
    - [Retraining](#retraining)
    - [Transformer Backend](#transformer-backend)
    - [Why Not 100%](#why-not-100)
  - [API](#api)
  - [How It Works](#how-it-works)
  - [Project Structure](#project-structure)
  - [Contributing](#contributing)
  - [Author](#author)

## Demo

### Demo Website

You can try the live demo of the app here: [https://x-toxicity-detection.onrender.com](https://x-toxicity-detection.onrender.com)

### Demo Video

<https://github.com/user-attachments/assets/7793ebed-c52b-44f0-b24f-63f0a958e833>

### Screenshots

| Light | Dark |
| :---: | :---: |
| ![App Screenshot](./assets/screenshots/screenshot-1-light.png) | ![App Screenshot](./assets/screenshots/screenshot-1-dark.png)
| ![App Screenshot](./assets/screenshots/screenshot-2-light.png) | ![App Screenshot](./assets/screenshots/screenshot-2-dark.png)

### Pie Chart

You can see a pie chart which portrays the percentage of tweets that are toxic and non-toxic. It can be viewed by clicking on the view Pie Chart button which is located below `following` and `followers` count.

<a align="left">
  <img src="./assets/screenshots/screenshot-3-chart.png" width="300">
</a>

### Window GUI

![App Screenshot](./assets/screenshots/screenshot-4-app.png)

## Installation

No API keys required! This app reads X's public syndication endpoint to fetch posts.

### Using Virtual Environment (Recommended)

```bash
git clone https://github.com/mantreshkhurana/x-toxicity-detection-flask.git
cd x-toxicity-detection-flask
python -m venv venv
source venv/bin/activate  # on windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

### Without Virtual Environment

```bash
git clone https://github.com/mantreshkhurana/x-toxicity-detection-flask.git
cd x-toxicity-detection-flask
pip install -r requirements.txt
python app.py
```

Navigate to [http://127.0.0.1:5000/](http://127.0.0.1:5000/) in your web browser to use the app.

## Usage

```bash
python app.py
```

Run the app in a window GUI:

```bash
python app.py --window
# or
python app.py -w
```

Use a custom port:

```bash
python app.py --port 8000
# or
python app.py -p 8000
```

## Next.js Frontend

A React frontend built to look and behave like X itself lives in [web/](web/). It renders what the Python service returns - the model never moves out of Python.

```bash
# terminal 1 - the analysis service
python app.py

# terminal 2 - the React frontend
cd web
npm install
cp .env.example .env.local     # TOXICITY_API_URL, defaults to http://127.0.0.1:5000
npm run dev                    # http://localhost:3000
```

| Route | What it does |
| :-- | :-- |
| `/` | Search a username and pick how many posts to analyze |
| `/u/[username]` | Profile header, scored timeline, Posts / Flagged / Safe tabs, toxicity donut, language mix |
| `/analyze` | Paste any text, one post per line, scored in any supported language |
| `/model` | Model card: pipeline, language list, measured accuracy |

It ships X's three themes (Default, Dim, Lights out), a three-column desktop layout with a bottom nav on phones, skeleton loading that matches the real layout, and badges that distinguish toxic from safe by icon and wording as well as colour. See [web/README.md](web/README.md) for details.

## Features

- [x] Search for a X user's recent tweets
- [x] Toxicity detection in 56 languages, with the detected language shown per post
- [x] Obfuscation-resistant scoring (`f*ck`, `sh1t`, `f u c k`, `looool`, Cyrillic look-alikes)
- [x] Per-language decision thresholds instead of one global cut-off
- [x] JSON API for scoring arbitrary text
- [x] Optional transformer backend for maximum accuracy
- [x] Dark/Light mode toggle
- [x] View a pie chart for profile's toxicity ratio
- [x] View user's profile picture, name, username, following and followers count
- [x] View images in tweets
- [x] View retweets and likes count for each tweet
- [x] View the date and time of each tweet
- [x] X-like feed layout
- [x] Simple bot protection
- [x] Native GUI window support
- [x] No API keys required (public syndication endpoint)
- [ ] Images/Videos toxicity detection

## The Toxicity Model

Everything that turns text into a score lives in [toxicity.py](toxicity.py); training lives in [train_multilingual.py](train_multilingual.py). Both share the same normalization function, so what the model sees at inference is exactly what it saw during training.

**Pipeline**

1. **Normalization** - Unicode NFKC, invisible/bidi character stripping, URL and mention removal, hashtag unwrapping, and de-obfuscation: repeated characters (`fuuuuck`), interior leetspeak (`sh1t`, `f4ggot`), censoring symbols (`f*ck`), spaced-out letters (`f u c k`), and Cyrillic/Greek homoglyphs smuggled into Latin words.
2. **Features** - a union of word 1-2 grams and character 2-5 grams (`char_wb`). The character half is what makes one model work across 50+ languages: it handles agglutinative morphology, unsegmented scripts like Chinese, Japanese and Thai, and misspellings that word tokens miss entirely.
3. **Classifier** - a soft-voting ensemble of three linear models with different loss functions: logistic regression (well calibrated), a calibrated linear SVM (wider margin), and modified-Huber SGD (tolerant of label noise). They fail on different examples, so the average beats every member.
4. **Per-language thresholds** - the decision cut-off is tuned separately for each language on a validation split. A single global threshold systematically over-flags the languages the model is least certain about.

**Training data** - 566,346 deduplicated posts merged from four public corpora:

| Corpus | Rows used | Languages | Notes |
| :-- | --: | --: | :-- |
| [textdetox/multilingual_toxicity_dataset](https://huggingface.co/datasets/textdetox/multilingual_toxicity_dataset) | 71,374 | 15 | balanced, human-annotated |
| [FredZhang7/toxi-text-3M](https://huggingface.co/datasets/FredZhang7/toxi-text-3M) | 472,664 | 55 | sampled per language so English (88% of the corpus) cannot dominate |
| [Fallen03/COLDataset](https://huggingface.co/datasets/Fallen03/COLDataset) | 32,157 | 1 | Chinese offensive language |
| [smilegate-ai/kor_unsmile](https://huggingface.co/datasets/smilegate-ai/kor_unsmile) | 15,005 | 1 | Korean hate speech |

The last two exist because Chinese and Korean were the weakest languages in the merged data - a few hundred rows each. Adding them took Chinese accuracy from **58.6% to 86.6%** and gave Korean its first real coverage at 82.3%.

Rows whose text appears twice with contradictory labels are dropped rather than left to a coin flip.

### Accuracy

Measured on a 45,308-post held-out split that the model never saw during training or threshold tuning:

| Metric | Score |
| :-- | --: |
| Accuracy | **84.98%** |
| Macro F1 | **84.65%** |
| ROC-AUC | **92.92%** |
| Toxic-class F1 | 82.2% |

For comparison, the previous English-centric model scored macro F1 0.81 on a balanced 15-language set and collapsed to **0.49 macro F1 / 0.56 ROC-AUC** on out-of-domain multilingual data - barely better than a coin flip. The current model scores 0.65 macro F1 / 0.77 ROC-AUC on that same out-of-domain set, which is the honest number for text that looks nothing like the training corpora.

Per language, largest test slices first:

| Language | Test posts | Accuracy | Macro F1 |
| :-- | --: | --: | --: |
| English | 9,962 | 88.8% | 0.888 |
| Arabic | 4,352 | 81.6% | 0.783 |
| Turkish | 3,947 | 87.7% | 0.778 |
| Chinese | 2,965 | 86.6% | 0.866 |
| Portuguese | 2,958 | 77.7% | 0.756 |
| Russian | 2,385 | 87.3% | 0.855 |
| Spanish | 2,220 | 76.1% | 0.755 |
| French | 2,173 | 84.4% | 0.829 |
| Italian | 1,880 | 84.5% | 0.815 |
| Indonesian | 1,390 | 87.1% | 0.870 |
| German | 1,308 | 84.2% | 0.826 |
| Korean | 1,203 | 82.3% | 0.728 |
| Hindi | 1,152 | 74.1% | 0.741 |
| Greek | 825 | 83.4% | 0.789 |
| Japanese | 441 | 76.2% | 0.760 |

The weak spots are real and worth knowing: Hindi, Japanese and Amharic sit in the low-to-mid 70s, and Marathi has so few toxic examples (0.7% of its rows) that the model never predicts toxic for it.

Reproduce it yourself:

```bash
python evaluate_model.py           # held-out test split, per-language breakdown
python evaluate_model.py --smoke   # hand-written multilingual sanity set
```

### Supported Languages

56 languages have training data and a tuned or inherited threshold:

```txt
af am ar bg bn ca cs cy da de el en es et fa fi fr gu he hi hr hu id it ja kn
ko lt lv mk ml mr ne nl no pa pl pt ro ru sk sl so sq sv sw ta te th tl tr tt
uk ur vi zh
```

17 of them earned a language-specific decision threshold; the rest use the global cut-off (41%). Language detection is separate from the model: Unicode blocks resolve non-Latin scripts, decisive letters split the shared ones (`ї` means Ukrainian, `ў` Belarusian, `ğ` Turkish), and `langdetect` plus a function-word heuristic handles Latin script.

Text in a language with no training data still gets scored - the character n-grams generalize across related languages - it just gets the global threshold instead of a tuned one.

### Retraining

```bash
python train_multilingual.py                   # full run, all corpora (~566k rows, ~9 min)
python train_multilingual.py --preset fast     # textdetox only, about a minute
python train_multilingual.py --max-per-label 20000   # smaller sample per language
python train_multilingual.py --no-extras       # skip the Chinese and Korean corpora
```

The full preset downloads a 1.4 GB corpus on first run and caches it. Training writes `models/vectorizer.pkl`, `models/toxicity_model.pkl`, `models/model_meta.pkl` (metrics + thresholds) and `models/holdout.csv` (the test split, for `evaluate_model.py`). The app loads those at startup; it never trains at boot.

### Transformer Backend

For a few more points of accuracy at the cost of RAM and a multi-gigabyte download, swap the linear model for a fine-tuned XLM-RoBERTa classifier:

```bash
pip install -r requirements-transformer.txt
TOXICITY_BACKEND=transformer python app.py
# any HF sequence-classification model works:
TOXICITY_MODEL_ID=textdetox/xlmr-large-toxicity-classifier python app.py
```

| Variable | Values | Meaning |
| :-- | :-- | :-- |
| `TOXICITY_BACKEND` | `auto`, `linear`, `transformer` | which model answers; `auto` uses the transformer only when its dependencies **and** `TOXICITY_MODEL_ID` are set |
| `TOXICITY_MODEL_ID` | any HF model id | checkpoint for the transformer backend |
| `TOXICITY_THRESHOLD` | `0`-`100` | override every threshold with one fixed cut-off |

### Why Not 100%

There is no 100% here, and any toxicity classifier claiming it is reporting its training error. Toxicity is a judgement call, not a fact: human annotators on these datasets disagree with each other a meaningful share of the time, sarcasm and reclaimed slurs invert the label depending on who is speaking, and the same sentence can be a joke between friends or harassment from a stranger. A model cannot be more consistent than the labels it learned from.

What is achievable, and what this model does: score every language it can, refuse to be fooled by the usual obfuscation tricks, calibrate its confidence per language, and publish the numbers above so you can decide whether they are good enough for your use. Treat the score as a ranking signal for human review, not a verdict.

## API

```bash
# what model is answering
curl http://127.0.0.1:5000/api/model

# score arbitrary text in any supported language
curl -X POST http://127.0.0.1:5000/api/analyze \
  -H 'Content-Type: application/json' \
  -d '{"texts": ["you are trash", "gracias por compartir", "ты тупой урод"]}'
```

```json
{
  "backend": "linear",
  "results": [
    {"text": "you are trash",         "score": 84.65, "is_toxic": true,  "language": "en", "threshold": 41.0},
    {"text": "gracias por compartir", "score": 1.99,  "is_toxic": false, "language": "es", "threshold": 34.0},
    {"text": "ты тупой урод",         "score": 100.0, "is_toxic": true,  "language": "ru", "threshold": 41.0}
  ]
}
```

A whole profile, scored, is one call — this is what the Next.js frontend renders:

```bash
curl "http://127.0.0.1:5000/api/profile/jack?posts=20"
```

It returns the user, a summary (totals, toxic ratio, average score, language mix), the model info, and every post with its own score, language and threshold.

## How It Works

1. Enter a Twitter/X username and the number of tweets to analyze
2. The app fetches those posts from X's public syndication endpoint - no API key, no login
3. Every post is scored in one batched pass: language detected, toxicity probability computed, threshold applied for that language
4. Tweets are displayed with color coding (green for non-toxic, red for toxic) and a language badge
5. An overall toxicity ratio is calculated and can be viewed as a pie chart

## Project Structure

```txt
x-toxicity-detection-flask/
├── app.py                 # flask app: scraping, JSON API, server-rendered UI
├── toxicity.py            # normalization, language detection, scoring backends
├── train_multilingual.py  # trains and persists the model
├── evaluate_model.py      # accuracy report + multilingual smoke test
├── models/
│   ├── vectorizer.pkl     # fitted word + char TF-IDF union
│   ├── toxicity_model.pkl # soft-voting linear ensemble
│   ├── model_meta.pkl     # metrics, languages, per-language thresholds
│   └── holdout.csv        # held-out test split
├── static/
│   ├── css/
│   │   ├── style.css      # main stylesheet (imports modules)
│   │   ├── base.css       # reset and typography
│   │   ├── header.css     # header and navigation
│   │   ├── search.css     # search bar and bot protection
│   │   ├── profile.css    # profile card styles
│   │   ├── tweet.css      # tweet card styles (X-like UI)
│   │   └── components.css # footer, modals, errors
│   ├── js/
│   │   └── script.js
│   └── images/
│       ├── favicon.ico
│       └── hate_speech.svg
├── templates/
│   ├── index.html
│   ├── results.html
│   └── error.html
├── web/                   # next.js + react frontend (see web/README.md)
│   ├── app/               # routes: /, /u/[username], /analyze, /model
│   ├── components/        # sidebar, timeline, tweet card, donut, badges
│   └── lib/               # api client, types, formatting
├── images/
│   └── logo.png
├── assets/
│   └── screenshots/
├── .gitignore
├── README.md
├── requirements.txt
└── requirements-transformer.txt   # optional transformer backend
```

## Contributing

Contributions are welcome! You can contribute to this project by forking it and making a pull request.

After forking:

```bash
git clone https://github.com/<your-username>/x-toxicity-detection-flask.git
cd x-toxicity-detection-flask
git checkout -b <your-branch-name>
# after adding your changes
git add .
git commit -m "your commit message"
git push origin <your-branch-name>
```

## Credits

- [Flask](https://www.fullstackpython.com/flask.html)
- [Sklearn](https://scikit-learn.org/stable/)
- [Python](https://www.python.org/)
- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/)
- [pywebview](https://pywebview.flowrl.com/)
- [textdetox/multilingual_toxicity_dataset](https://huggingface.co/datasets/textdetox/multilingual_toxicity_dataset)
- [FredZhang7/toxi-text-3M](https://huggingface.co/datasets/FredZhang7/toxi-text-3M)
- [langdetect](https://github.com/Mimino666/langdetect)

## Author

- [Mantresh Khurana](https://github.com/mantreshkhurana)
