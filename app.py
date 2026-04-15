import os
import pickle
import re
import json
import html as html_lib
import pandas as pd
from flask import Flask, render_template, request, send_from_directory
from sklearn.model_selection import train_test_split
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from email.utils import parsedate_to_datetime
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion
import argparse
from datetime import datetime
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

# text preprocessing for better toxicity detection
def preprocess_text(text):
    """Clean and normalize text for better model performance"""
    if pd.isna(text):
        return ''
    text = str(text).lower()
    # remove URLs
    text = re.sub(r'http\S+|www\S+|https\S+', '', text)
    # remove mentions
    text = re.sub(r'@\w+', '', text)
    # remove hashtags but keep the word
    text = re.sub(r'#(\w+)', r'\1', text)
    # remove extra whitespace
    text = ' '.join(text.split())
    return text

VECTORIZER_PATH = 'models/vectorizer.pkl'
MODEL_PATH = 'models/toxicity_model.pkl'
META_PATH = 'models/model_meta.pkl'
MULTILINGUAL_CSV = 'models/multilingual_toxicity.csv'
LEGACY_CSV = 'models/hate_speech_model.csv'

toxicity = 0


def _train_from_csv(csv_path):
    """Fallback: train a simple TF-IDF + LogReg model from a labeled CSV."""
    frame = pd.read_csv(csv_path)
    x = frame['text'].apply(preprocess_text)
    y = frame['is_toxic'].map({'Toxic': 1, 'Not Toxic': 0})
    vec = TfidfVectorizer(
        max_features=5000,
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.95,
        sublinear_tf=True,
    )
    x_vec = vec.fit_transform(x)
    x_train, _, y_train, _ = train_test_split(
        x_vec, y, test_size=0.2, random_state=42
    )
    clf = LogisticRegression(
        max_iter=1000, C=1.0, class_weight='balanced', solver='lbfgs'
    )
    clf.fit(x_train, y_train)
    return vec, clf


if os.path.exists(VECTORIZER_PATH) and os.path.exists(MODEL_PATH):
    with open(VECTORIZER_PATH, 'rb') as f:
        vectorizer = pickle.load(f)
    with open(MODEL_PATH, 'rb') as f:
        model = pickle.load(f)
    if os.path.exists(META_PATH):
        with open(META_PATH, 'rb') as f:
            meta = pickle.load(f)
        print(
            f"Loaded multilingual model: {meta.get('n_samples')} samples, "
            f"{len(meta.get('languages', []))} languages, "
            f"macro F1 {meta.get('macro_f1', 0):.3f}"
        )
    else:
        print("Loaded persisted toxicity model.")
else:
    csv_path = MULTILINGUAL_CSV if os.path.exists(MULTILINGUAL_CSV) else LEGACY_CSV
    print(
        f"No persisted model found; training fallback from {csv_path}. "
        "Run `python train_multilingual.py` for the full multilingual model."
    )
    vectorizer, model = _train_from_csv(csv_path)

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
    """Check if text is toxic using the trained model"""
    processed = preprocess_text(text)
    vec = vectorizer.transform([processed])
    percentage = round((model.predict_proba(vec)[0][1] * 100), 2)

    # threshold of 50% for balanced classification
    if percentage >= 50.00:
        return True
    else:
        return False


def get_toxicity_score(text):
    """Get the toxicity probability score for text"""
    processed = preprocess_text(text)
    vec = vectorizer.transform([processed])
    return round((model.predict_proba(vec)[0][1] * 100), 2)


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/images/<path:filename>')
def serve_images(filename):
    return send_from_directory('images', filename)

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

    labels = [is_toxic(tweet.full_text) for tweet in tweets]

    num_hateful = sum(labels)
    num_total = len(tweets)
    hate_speech_ratio = num_hateful / num_total * 100

    toxicity = sum([get_toxicity_score(tweet.full_text) for tweet in tweets]) / num_total

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
