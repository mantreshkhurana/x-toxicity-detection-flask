"""JSON API for the toxicity detector.

The interface lives in `web/` (Next.js). `python app.py` runs both: the
interface takes the public port you choose, this API sits behind it on a
private one, and the interface forwards `/api/*` through to it — so the whole
app answers on a single URL.
"""

import os
import re
import json
import html as html_lib
import socket
import subprocess
import sys
import time
from flask import Flask, jsonify, redirect, request
import requests
from dotenv import load_dotenv
from email.utils import parsedate_to_datetime
import argparse
from datetime import datetime

from toxicity import get_classifier

load_dotenv()

# "DEBUG_MODE=False" is a string, and every non-empty string is truthy — this
# used to turn the debugger *on* whenever the variable was set at all.
debug = os.getenv('DEBUG_MODE', 'False').strip().lower() in {'1', 'true', 'yes', 'on'}

# argument parser setup — only parse when executed directly so WSGI servers
# (gunicorn, uwsgi) that import `app:app` are not confused by their own argv.
def _parse_cli_args():
    parser = argparse.ArgumentParser(
        description="Run the toxicity detector: interface and API on one port.",
    )
    parser.add_argument(
        "-p", "--port", type=int, default=int(os.getenv("PORT", 3000)),
        help="the port you open — serves the interface and /api/*, default 3000",
    )
    parser.add_argument(
        "--api-port", type=int, default=int(os.getenv("API_PORT", 5000)),
        help="private port for the API behind the interface, default 5000; "
             "moves to the next free port if that one is taken",
    )
    parser.add_argument(
        "--no-web", action="store_true",
        help="serve the API alone on --port, without the interface",
    )
    parser.add_argument(
        "--prod", action="store_true",
        help="run the interface as a production build instead of dev mode",
    )
    parser.add_argument(
        "-w", "--window", action="store_true",
        help="open the interface in a desktop window instead of a browser",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="report whether everything needed to run is present, then exit",
    )
    return parser.parse_args()


def _check_environment(args):
    """`--check`: say what is and isn't ready, instead of failing at startup."""
    import platform
    import shutil

    print("\nEnvironment")
    print(f"  python           {platform.python_version()} ({platform.machine()})")
    print(f"  model            {len(classifier.info['languages'])} languages, "
          f"{classifier.backend.name} backend")

    ok = True

    npm = shutil.which("npm")
    node = shutil.which("node")
    if npm and node:
        version = subprocess.run(
            [node, "--version"], capture_output=True, text=True
        ).stdout.strip()
        print(f"  node             {version} ({node})")
        major = int(version.lstrip("v").split(".")[0]) if version else 0
        if major and major < 20:
            print("                   ! Next.js needs Node 20 or newer")
            ok = False
    else:
        print("  node             NOT FOUND — install Node.js 20+ "
              "(or run with --no-web)")
        ok = False

    web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')
    deps = os.path.isdir(os.path.join(web_dir, 'node_modules'))
    print(f"  web/node_modules {'present' if deps else 'missing (installed on first run)'}")

    print("\nPorts")
    for label, port in (('interface', args.port), ('api', args.api_port)):
        free = _port_is_free(port)
        resolved = '' if free else f" -> will use {_resolve_port(port, label)}"
        print(f"  {label:<16} {port} {'free' if free else 'in use'}{resolved}")

    print("\n" + ("Ready. Run: python app.py" if ok else
                  "Not ready — see the notes above.") + "\n")
    return 0 if ok else 1


def _port_is_free(port, host="127.0.0.1"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
            return True
        except OSError:
            return False


def _resolve_port(preferred, label, host="127.0.0.1"):
    """First free port at or after `preferred`, so a busy port never crashes us."""
    for candidate in range(preferred, preferred + 50):
        if _port_is_free(candidate, host):
            if candidate != preferred:
                print(f"[{label}] port {preferred} is in use, using {candidate}")
            return candidate
    raise SystemExit(
        f"[{label}] no free port between {preferred} and {preferred + 49}."
    )

SYNDICATION_URL = "https://syndication.twitter.com/srv/timeline-profile/screen-name/{username}"

# X rate-limits by IP, and a shared datacenter address (any PaaS free tier) burns
# through the allowance far faster than a home connection — a single 429 there is
# routine rather than a sign of abuse. Three things make it survivable: retrying
# past the short-lived limits, not re-fetching a timeline we already hold, and an
# escape hatch for an outbound address that isn't rate-limited.
SCRAPE_ATTEMPTS = 3
SCRAPE_BACKOFF_SECONDS = 1.5
CACHE_TTL_SECONDS = int(os.getenv('TOXICITY_CACHE_TTL', '600'))
CACHE_MAX_ENTRIES = 256

# Same Chrome build, three platforms. The endpoint serves embedded-timeline
# widgets, so a browser UA is what it expects; varying it costs nothing.
USER_AGENTS = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
)


def _outbound_proxies():
    """An optional proxy for the X request only.

    Nothing in code can talk an IP block out of existing, so this is the one
    real fix when the host's own address is limited: point it at an address
    that isn't. Unset by default — the direct request is tried as before.
    """
    proxy = os.getenv('TOXICITY_HTTP_PROXY', '').strip()
    return {'http': proxy, 'https': proxy} if proxy else None


# username -> (fetched_at, tweets, user_info). A timeline is the slow, rate-limited
# half of a request; the scoring underneath is cheap and re-runs on every call.
_timeline_cache = {}


def _cache_get(key, count, allow_stale=False):
    """A cached timeline, or None.

    Expired entries are kept rather than dropped: once X starts refusing us, the
    last good timeline is the only thing standing between the user and an error
    page, and `allow_stale` is how the failure path reaches it.
    """
    entry = _timeline_cache.get(key)
    if not entry:
        return None
    fetched_at, tweets, user_info = entry
    fresh = (datetime.now() - fetched_at).total_seconds() <= CACHE_TTL_SECONDS
    if not fresh and not allow_stale:
        return None
    # A cached fetch of 20 posts answers a request for 5, but not one for 50.
    if len(tweets) < count:
        return None
    return tweets[:count], user_info


def _cache_put(key, tweets, user_info):
    if len(_timeline_cache) >= CACHE_MAX_ENTRIES:
        oldest = min(_timeline_cache, key=lambda k: _timeline_cache[k][0])
        _timeline_cache.pop(oldest, None)
    _timeline_cache[key] = (datetime.now(), tweets, user_info)


def _parse_created_at(value):
    if not value:
        return datetime.now()
    try:
        return parsedate_to_datetime(value).replace(tzinfo=None)
    except (TypeError, ValueError):
        return datetime.now()


def scrape_nitter_tweets(username, count=10):
    """Fetch tweets via Twitter's public syndication endpoint.

    Nitter is effectively dead (JS bot-challenges, 403/503, rate limits). The
    syndication endpoint is what Twitter's own embedded-timeline widgets use —
    public, unauthenticated, returns a full tweet schema inside __NEXT_DATA__.
    """
    url = SYNDICATION_URL.format(username=username)
    proxies = _outbound_proxies()
    response = None
    network_error = None

    # X's limits here are short — a second or two apart is often enough for the
    # retry to land, so one 429 is not worth surfacing as a failed analysis.
    for attempt in range(SCRAPE_ATTEMPTS):
        if attempt:
            time.sleep(SCRAPE_BACKOFF_SECONDS * (2 ** (attempt - 1)))

        headers = {
            'User-Agent': USER_AGENTS[attempt % len(USER_AGENTS)],
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://platform.twitter.com/',
        }

        try:
            response = requests.get(url, headers=headers, timeout=15, proxies=proxies)
        except requests.RequestException as e:
            network_error = e
            continue

        network_error = None
        # 404 is a settled answer; retrying it only makes the user wait.
        if response.status_code not in (429, 503):
            break

    if response is None:
        raise Exception(f"Network error: {network_error}")

    if response.status_code in (429, 503):
        raise Exception(
            "X is rate-limiting this server's IP. Wait a few minutes and try "
            "again — or set TOXICITY_HTTP_PROXY to route the request elsewhere."
        )

    if response.status_code == 404:
        raise Exception(f"User @{username} not found")

    if response.status_code != 200:
        raise Exception(f"Failed to fetch tweets: HTTP {response.status_code}")

    match = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', response.text, re.DOTALL
    )
    if not match:
        raise Exception("Unexpected response from Twitter syndication endpoint")

    try:
        payload = json.loads(html_lib.unescape(match.group(1)))
    except json.JSONDecodeError as e:
        raise Exception(f"Failed to parse tweet data: {e}")

    page_props = payload.get('props', {}).get('pageProps', {}) or {}
    timeline = page_props.get('timeline') or {}
    entries = timeline.get('entries', []) if isinstance(timeline, dict) else []

    tweet_entries = [e for e in entries if e.get('type') == 'tweet']
    if not tweet_entries:
        # empty timeline + no header means the user doesn't exist; with a
        # header it's a real (but empty/private) account
        if not page_props.get('headerProps'):
            raise Exception(f"User @{username} not found")
        return [], {
            'name': username,
            'screen_name': username,
            'profile_image_url_https': f'https://unavatar.io/twitter/{username}',
            'followers_count': 0,
            'friends_count': 0,
        }

    tweets = []
    user_info = None
    for entry in tweet_entries[:count]:
        t = (entry.get('content') or {}).get('tweet') or {}
        u = t.get('user') or {}

        if user_info is None:
            user_info = {
                'name': u.get('name') or username,
                'screen_name': u.get('screen_name') or username,
                'profile_image_url_https': u.get('profile_image_url_https')
                    or f'https://unavatar.io/twitter/{username}',
                'followers_count': int(u.get('followers_count') or 0),
                'friends_count': int(u.get('friends_count') or 0),
            }

        media = []
        for m in (t.get('extended_entities') or t.get('entities') or {}).get('media', []) or []:
            url = m.get('media_url_https') or m.get('media_url') or ''
            if url:
                media.append({'type': m.get('type', 'photo'), 'media_url_https': url})

        tweet_id = t.get('id_str') or ''
        screen = user_info['screen_name']
        tweet_url = t.get('permalink')
        if tweet_url and tweet_url.startswith('/'):
            tweet_url = f"https://twitter.com{tweet_url}"
        if not tweet_url and tweet_id:
            tweet_url = f"https://twitter.com/{screen}/status/{tweet_id}"

        tweets.append(TweetWrapper(
            full_text=t.get('full_text') or t.get('text') or '',
            id_str=tweet_id,
            created_at=_parse_created_at(t.get('created_at')),
            favorite_count=int(t.get('favorite_count') or 0),
            retweet_count=int(t.get('retweet_count') or 0),
            tweet_url=tweet_url or '',
            user=user_info,
            media=media,
        ))

    if user_info is None:
        user_info = {
            'name': username,
            'screen_name': username,
            'profile_image_url_https': f'https://unavatar.io/twitter/{username}',
            'followers_count': 0,
            'friends_count': 0,
        }

    return tweets, user_info


# wrapper class to mimic tweepy tweet object structure
class TweetWrapper:
    def __init__(self, full_text, id_str, created_at, favorite_count, retweet_count, tweet_url, user, media=None):
        self.full_text = full_text
        self.id_str = id_str
        self.created_at = created_at
        self.favorite_count = favorite_count
        self.retweet_count = retweet_count
        self.tweet_url = tweet_url
        self.entities = EntityWrapper(media or [])
        self.user = UserWrapper(user)


class UserWrapper:
    def __init__(self, user_data):
        self.name = user_data.get('name', '')
        self.screen_name = user_data.get('screen_name', '')
        self.profile_image_url_https = user_data.get('profile_image_url_https', '')
        self.followers_count = user_data.get('followers_count', 0)
        self.friends_count = user_data.get('friends_count', 0)


class EntityWrapper:
    def __init__(self, media_list):
        self.media = []
        for m in media_list:
            self.media.append(MediaWrapper(m))


class MediaWrapper:
    def __init__(self, media_data):
        self.type = media_data.get('type', 'photo')
        self.media_url_https = media_data.get('media_url_https', '')
        self.video_info = None

def _load_classifier():
    """Load the model, turning the two common failures into plain English."""
    try:
        return get_classifier()
    except FileNotFoundError as exc:
        raise SystemExit(
            f"\n  {exc}\n\n"
            "  Fix: python train_multilingual.py --preset fast\n"
        )
    except ImportError as exc:
        message = str(exc)
        if "incompatible architecture" in message:
            raise SystemExit(
                "\n  Your installed packages were built for a different CPU "
                "architecture than\n  the Python running them (a Rosetta / "
                "Apple Silicon mismatch).\n\n"
                "  Fix: rm -rf venv && python3 -m venv venv && "
                "source venv/bin/activate\n"
                "       pip install -r requirements.txt\n"
            )
        raise SystemExit(
            f"\n  A dependency failed to import: {message}\n\n"
            "  Fix: pip install -r requirements.txt\n"
        )


classifier = _load_classifier()
_info = classifier.info
print(
    f"Toxicity model ready: {_info['backend']} backend, "
    f"{len(_info['languages'])} languages, "
    f"{(_info['n_samples'] or 0):,} training samples, "
    f"macro F1 {(_info['macro_f1'] or 0):.3f}"
)

# No templates, no static files: this process is an API, and `static_folder=None`
# keeps Flask from advertising a /static route that serves nothing.
app = Flask(__name__, static_folder=None)


@app.route('/')
def index():
    """Endpoint listing — the human-facing app is the Next.js frontend.

    Opening this port in a browser is a natural mistake, so send people to the
    interface instead of showing them raw JSON.
    """
    # Only a client that names text/html gets redirected. Werkzeug's
    # negotiation treats curl's `Accept: */*` as HTML-willing, which would
    # break API clients, so the header is matched literally.
    web_url = os.getenv('WEB_URL')
    if web_url and 'text/html' in request.headers.get('Accept', ''):
        return redirect(web_url, code=302)

    return jsonify({
        'service': 'x-toxicity-detection API',
        'frontend': os.getenv('WEB_URL', 'http://127.0.0.1:3000'),
        'endpoints': {
            'GET /api/model': 'model backend, languages and measured accuracy',
            'POST /api/analyze': 'score arbitrary text: {"texts": ["..."]}',
            'GET /api/profile/<username>?posts=20': 'fetch and score a public profile',
        },
    })

@app.route('/api/model')
def api_model():
    """Which model is answering, in how many languages, and how well."""
    return jsonify(classifier.info)

@app.route('/api/analyze', methods=['POST'])
def api_analyze():
    """Score arbitrary text — handy for checking the model in your own language.

    POST {"text": "..."} or {"texts": ["...", "..."]}
    """
    payload = request.get_json(silent=True) or {}
    texts = payload.get('texts')
    if texts is None:
        texts = [payload.get('text', '')]
    if not isinstance(texts, list):
        return jsonify({'error': '"texts" must be a list of strings'}), 400
    texts = [str(t) for t in texts][:200]
    if not any(t.strip() for t in texts):
        return jsonify({'error': 'no text provided'}), 400

    results = classifier.analyze_batch(texts)
    return jsonify({
        'backend': classifier.backend.name,
        'results': [r.as_dict() for r in results],
    })

@app.route('/api/profile/<username>')
def api_profile(username):
    """Profile + scored posts as JSON — what the Next.js frontend renders.

    GET /api/profile/<username>?posts=20
    """
    try:
        posts = min(max(int(request.args.get('posts', 20)), 1), 100)
    except (TypeError, ValueError):
        posts = 20

    key = username.lower()
    cached = _cache_get(key, posts)
    if cached:
        tweets, user_info = cached
    else:
        try:
            tweets, user_info = scrape_nitter_tweets(username, posts)
        except Exception as e:
            # A stale timeline beats an error page when X is refusing us: the
            # cache only holds what it already served, so nothing is invented.
            stale = _cache_get(key, posts, allow_stale=True)
            if not stale:
                return jsonify({'error': str(e)}), 502
            tweets, user_info = stale
        else:
            _cache_put(key, tweets, user_info)

    if not tweets:
        return jsonify({'error': f"No posts found for @{username}"}), 404

    analyses = classifier.analyze_batch([tweet.full_text for tweet in tweets])
    scored = []
    for tweet, analysis in zip(tweets, analyses):
        scored.append({
            'id': tweet.id_str,
            'text': tweet.full_text,
            'created_at': tweet.created_at.isoformat(),
            'favorite_count': tweet.favorite_count,
            'retweet_count': tweet.retweet_count,
            'url': tweet.tweet_url,
            'media': [
                {'type': m.type, 'url': m.media_url_https}
                for m in tweet.entities.media
            ],
            'toxicity': {
                'score': analysis.score,
                'is_toxic': analysis.is_toxic,
                'language': analysis.language,
                'threshold': analysis.threshold,
            },
        })

    toxic_count = sum(1 for a in analyses if a.is_toxic)
    languages = {}
    for analysis in analyses:
        languages[analysis.language] = languages.get(analysis.language, 0) + 1

    return jsonify({
        'user': {
            'name': user_info['name'],
            'screen_name': user_info['screen_name'],
            'avatar': user_info['profile_image_url_https'],
            'followers_count': user_info['followers_count'],
            'following_count': user_info['friends_count'],
        },
        'summary': {
            'total': len(scored),
            'toxic': toxic_count,
            'safe': len(scored) - toxic_count,
            'toxic_ratio': round(toxic_count / len(scored) * 100, 1),
            'average_score': round(sum(a.score for a in analyses) / len(analyses), 1),
            'languages': dict(sorted(languages.items(), key=lambda kv: -kv[1])),
        },
        'model': classifier.info,
        'posts': scored,
    })

def _start_frontend(public_port, api_port, production):
    """Bring up the interface, or explain why it could not start."""
    import frontend

    try:
        url = frontend.start(
            api_port=api_port,
            web_port=public_port,
            production=production,
        )
    except frontend.FrontendError as exc:
        print(f"[web] {exc}")
        return None

    frontend.install_signal_handlers()
    os.environ['WEB_URL'] = url
    return url


def _print_banner(web_url, api_port):
    """The URL to open, hard to miss — ports move when they are taken."""
    if web_url:
        lines = [
            f"Open  {web_url}",
            f"API   http://127.0.0.1:{api_port}  (behind the interface)",
        ]
    else:
        lines = [f"API   http://127.0.0.1:{api_port}  (no interface running)"]

    width = max(len(line) for line in lines) + 4
    print("\n  ┌" + "─" * width + "┐")
    for line in lines:
        print(f"  │  {line.ljust(width - 4)}  │")
    print("  └" + "─" * width + "┘\n")


def _run_window(url):
    """Desktop window pointed at the frontend. Blocks until it is closed."""
    import webview
    import frontend

    if not frontend.wait_until_ready(url):
        print("[web] frontend did not come up in time; not opening the window")
        return
    webview.create_window(
        "X Toxicity Detection",
        url,
        width=1100,
        height=820,
        min_size=(600, 700),
    )
    webview.start()


if __name__ == '__main__':
    args = _parse_cli_args()

    if args.check:
        sys.exit(_check_environment(args))

    if args.no_web:
        # The API is the public service here: it takes --port and listens
        # outward, and there is no interface in front of it.
        api_port, api_host, web_url = args.port, '0.0.0.0', None
    else:
        # The interface is the public service; the API sits behind it on
        # localhost, reachable only through the interface's /api/* proxy.
        api_port = _resolve_port(args.api_port, 'api')
        api_host = '127.0.0.1'
        public_port = _resolve_port(args.port, 'web', host='0.0.0.0')

        # Flask's reloader runs this module twice; only the child should own
        # the frontend, otherwise two copies fight over the same port.
        is_reloader_parent = debug and os.environ.get('WERKZEUG_RUN_MAIN') != 'true'
        if is_reloader_parent:
            web_url = None
        else:
            web_url = _start_frontend(public_port, api_port, args.prod)
            if web_url is None:
                print(f"[web] continuing with the API alone on "
                      f"http://127.0.0.1:{api_port}")

    window = args.window and web_url is not None
    if window:
        try:
            import webview  # noqa: F401
        except ImportError:
            print("[window] pywebview is not installed. Run `pip install pywebview`, "
                  f"or open {web_url} in a browser.")
            window = False

    if window:
        # webview owns the main thread, so Flask serves from a background one
        import threading

        threading.Thread(
            target=lambda: app.run(host=api_host, port=api_port, debug=False),
            daemon=True,
        ).start()
        _run_window(web_url)
    else:
        _print_banner(web_url, api_port)
        app.run(host=api_host, debug=debug, port=api_port)
