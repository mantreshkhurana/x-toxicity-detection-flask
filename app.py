import os
import re
import json
import html as html_lib
from flask import Flask, jsonify, render_template, request, send_from_directory
import requests
from dotenv import load_dotenv
from email.utils import parsedate_to_datetime
import argparse
from datetime import datetime

from toxicity import get_classifier

load_dotenv()

debug = os.getenv('DEBUG_MODE')

# argument parser setup — only parse when executed directly so WSGI servers
# (gunicorn, uwsgi) that import `app:app` are not confused by their own argv.
def _parse_cli_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-w", "--window", action="store_true", help="show the application in a window gui")
    parser.add_argument("-p", "--port", type=int, default=int(os.getenv("PORT", 5000)), help="specify the port number, default is 5000")
    return parser.parse_args()

SYNDICATION_URL = "https://syndication.twitter.com/srv/timeline-profile/screen-name/{username}"


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
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        response = requests.get(
            SYNDICATION_URL.format(username=username), headers=headers, timeout=15
        )
    except requests.RequestException as e:
        raise Exception(f"Network error: {e}")

    if response.status_code == 429:
        raise Exception(
            "X is rate-limiting this IP right now. Wait a few minutes and try again."
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

classifier = get_classifier()
_info = classifier.info
print(
    f"Toxicity model ready: {_info['backend']} backend, "
    f"{len(_info['languages'])} languages, "
    f"{(_info['n_samples'] or 0):,} training samples, "
    f"macro F1 {(_info['macro_f1'] or 0):.3f}"
)

app = Flask(__name__)

def format_number(num):
    if num < 1000:
        return str(num)
    elif num >= 1000 and num < 1000000:
        return '{:.1f}K'.format(num / 1000)
    elif num >= 1000000 and num < 1000000000:
        return '{:.1f}M'.format(num / 1000000)
    else:
        return '{:.1f}B'.format(num / 1000000000)


def is_toxic(text):
    """Whether text crosses the toxicity threshold for its language"""
    return classifier.is_toxic(text)


def get_toxicity_score(text):
    """Toxicity probability for text, as a percentage"""
    return classifier.score(text)


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/images/<path:filename>')
def serve_images(filename):
    return send_from_directory('images', filename)

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

    try:
        tweets, user_info = scrape_nitter_tweets(username, posts)
    except Exception as e:
        return jsonify({'error': str(e)}), 502

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

@app.route('/results', methods=['GET', 'POST'])
def results():
    if request.method == 'GET':
        return render_template('index.html')

    username = request.form['username']
    posts = int(request.form['posts'])

    try:
        tweets, user_info = scrape_nitter_tweets(username, posts)
    except Exception as e:
        return render_template('error.html', error=str(e))

    if not tweets:
        return render_template('error.html', error=f"No tweets found for user @{username}")

    # one batched pass over every post; the template then reads the cached
    # result off each tweet instead of re-running the model per render
    analyses = classifier.analyze_batch([tweet.full_text for tweet in tweets])
    for tweet, analysis in zip(tweets, analyses):
        tweet.toxicity_score = analysis.score
        tweet.is_toxic = analysis.is_toxic
        tweet.language = analysis.language

    num_hateful = sum(1 for a in analyses if a.is_toxic)
    num_total = len(tweets)
    hate_speech_ratio = num_hateful / num_total * 100

    toxicity = sum(a.score for a in analyses) / num_total
    languages = sorted({a.language for a in analyses if a.language != 'und'})

    user = tweets[0].user
    name = user.name
    followers_count = format_number(user.followers_count)
    following_count = format_number(user.friends_count)
    tweet_url = tweets[0].tweet_url if tweets else ''

    return render_template('results.html',
        username=username,
        posts=posts,
        num_total=num_total,
        num_hateful=num_hateful,
        hate_speech_ratio=round(hate_speech_ratio, 1),
        tweets=tweets,
        format_number=format_number,
        is_toxic=is_toxic,
        get_toxicity_score=get_toxicity_score,
        toxicity=round(toxicity, 1),
        followers_count=followers_count,
        following_count=following_count,
        name=name,
        tweet_url=tweet_url,
        languages=languages,
        model_info=classifier.info,
    )

if __name__ == '__main__':
    args = _parse_cli_args()
    if args.window:
        import webview
        app.config["TEMPLATES_AUTO_RELOAD"] = True
        webview.create_window(
            "Twitter Toxicity Detection",
            app,
            width=850,
            height=700,
            min_size=(600, 700),
        )
        webview.start()
    else:
        app.run(host='0.0.0.0', debug=debug, port=args.port)
