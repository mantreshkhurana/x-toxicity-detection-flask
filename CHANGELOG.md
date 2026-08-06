## 1.3.0

- **One port serves the whole app.** The interface takes the port you choose and forwards `/api/*` to the Python service behind it, so there is a single URL to open, share and deploy.
- **Breaking:** `--port` now means the port you open (default 3000), not the API port. The API moved to `--api-port` (default 5000) and binds localhost only. `--web-port` is gone; `--no-web` still puts the API on `--port`.
- A busy port no longer crashes the app: the next free one is used and printed.
- `/api/*` is proxied by a catch-all route handler that resolves the API location per request, so one build works wherever the API lives.
- Frontend dependencies install with `npm ci` when a lockfile is present, falling back to `npm install`.
- Added a `Dockerfile` that builds both halves into a single image, matching the single-port behaviour.

## 1.2.0

- The interface is now a Next.js + React app in `web/` that mirrors X's real UI: three-column layout, Default / Dim / Lights out themes, timeline, profile header, filter tabs, bottom nav on phones.
- Removed the server-rendered frontend: `templates/` and `static/` are gone, and `app.py` is a JSON API.
- `python app.py` starts both processes — it installs the frontend's dependencies on first run, prefixes its logs with `[web]`, and stops it on exit. `--no-web`, `--web-port` and `--prod` control that.
- `--window` opens the React interface in a desktop window instead of the old server-rendered pages.
- `render.yaml` now declares two services: the Python API and the Node frontend wired to it.
- Fixed `DEBUG_MODE=False` turning the debugger on (every non-empty string was truthy).

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
