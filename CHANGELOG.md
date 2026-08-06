## 1.1.0

- Multilingual toxicity model covering 55+ languages, trained on ~520k posts from textdetox and toxi-text-3M.
- Word + character n-gram features and a soft-voting ensemble (logistic regression, calibrated linear SVM, modified-Huber SGD).
- Decision threshold tuned per language instead of one global cut-off.
- Obfuscation-resistant normalization: leetspeak, censoring symbols, repeated and spaced-out letters, homoglyphs, invisible characters.
- Language detection per post, shown as a badge in the feed.
- `/api/analyze` and `/api/model` JSON endpoints.
- Optional transformer backend via `TOXICITY_BACKEND=transformer`.
- `evaluate_model.py` for per-language accuracy reports and a multilingual smoke test.
- Posts are scored in one batched pass instead of re-running the model per template render.

## 1.0.0

- Search for a Twitter user's recent tweets.
- Dark/Light mode.
- View a pie chart for profile's toxicity.
- View user's profile picture, name, username, bio, location, website, following, followers, and tweet count*.
- View images/videos in tweets.
- View retweets and likes count for each tweet.
- View the date and time of each tweet.
- View the source of each tweet.
- Twitter like feed.
- Simple bot protection.
- GUI Window Added.
