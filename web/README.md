# X Toxicity Detection — web frontend

Next.js (App Router) + React + Tailwind frontend that mirrors X's real interface:
three-column layout, X's Default / Dim / Lights out themes, and its timeline,
profile and tab-bar patterns.

The model stays in Python. This app renders what the API at `TOXICITY_API_URL`
returns and never talks to X directly.

## Run it

Normally you do not run this directly — `python app.py` in the repo root starts
this frontend *and* the API, installs dependencies on first run, and stops
everything on exit:

```bash
cd ..
python app.py            # whole app on http://localhost:3000
python app.py --port 8000  # or wherever you like
```

This app owns the public port. `/api/*` is forwarded to the Python service by
`app/api/[...path]/route.ts`, which is why a single port serves everything and
the browser never needs CORS.

To work on the frontend alone, against an API you started separately:

```bash
python ../app.py --no-web &   # API on :3000, or gunicorn, or a deployed API
npm install
cp .env.example .env.local    # TOXICITY_API_URL
npm run dev
```

| Variable | Meaning |
| :-- | :-- |
| `TOXICITY_API_URL` | full URL of the Python API, e.g. `http://127.0.0.1:5000` |
| `TOXICITY_API_HOST` | bare hostname instead, for hosts that inject one; a domain becomes `https://<host>`, a private-network name becomes `http://<host>:<TOXICITY_API_PORT or 10000>` |
| `TOXICITY_API_PORT` | port for `TOXICITY_API_HOST`, when it is not the default |

## Routes

| Route | What it does |
| :-- | :-- |
| `/` | Search a username, pick how many posts, plus a short explainer |
| `/u/[username]?posts=20` | Profile header, scored timeline, filter tabs, toxicity donut and language mix |
| `/analyze` | Paste any text, one post per line, score it in any supported language |
| `/model` | Model card: pipeline, language list, measured accuracy |
| `/api/*` | Catch-all proxy to the Python API, resolved per request so the API can move without a rebuild |

## Layout

```txt
web/
├── app/
│   ├── layout.tsx              # fonts, theme bootstrap, three-column frame
│   ├── page.tsx                # home
│   ├── u/[username]/page.tsx   # profile results (server component)
│   ├── u/[username]/loading.tsx# skeleton matching the real layout
│   ├── analyze/page.tsx        # text playground
│   ├── model/page.tsx          # model card
│   └── api/[...path]/route.ts  # forwards /api/* to the Python API
├── components/                 # sidebar, timeline, tweet card, donut, badges…
└── lib/                        # API client, types, formatting
```

## Design notes

- **Themes** — X's three themes are semantic CSS variables in `globals.css`.
  Components only ever reference tokens (`bg-canvas`, `text-muted`,
  `border-line`), so all three stay in sync. The `data-theme` attribute on
  `<html>` is the single source of truth, written before paint so there is no
  flash and read by React through `useSyncExternalStore`.
- **Colour is never the only signal** — toxic and safe differ by colour, by
  icon shape and by the word in the badge.
- **Touch targets** are 44px or larger, with 8px+ spacing; the mobile bottom
  nav respects the safe-area inset.
- **Motion** is 200-300ms, transform/opacity only, staggered 30ms per row, and
  fully disabled under `prefers-reduced-motion`.
- **Loading** uses a skeleton whose boxes match the real layout's dimensions so
  nothing shifts when data arrives.
- **Fonts** — X's Chirp is proprietary; Inter is the closest freely licensable
  match and covers Latin, Cyrillic and Greek.

## Build

```bash
npm run build && npm start
```

Or let the Python side do it: `python app.py --prod`.
