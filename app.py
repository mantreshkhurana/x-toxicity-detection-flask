import os
import pickle
import re
import pandas as pd
from flask import Flask, render_template, request, send_from_directory
from sklearn.model_selection import train_test_split
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
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

# nitter instances to try
NITTER_INSTANCES = [
    "https://xcancel.com",
    "https://nitter.poast.org",
    "https://nitter.privacyredirect.com",
    "https://lightbrd.com",
]


def get_working_nitter():
    """find a working nitter instance"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    for instance in NITTER_INSTANCES:
        try:
            response = requests.get(f"{instance}/", headers=headers, timeout=5)
            if response.status_code == 200:
                return instance
        except:
            continue
    return None


def scrape_nitter_tweets(username, count=10):
    """scrape tweets from a nitter instance"""
    nitter_base = get_working_nitter()
    if not nitter_base:
        raise Exception("No working Nitter instance found. Please try again later.")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    tweets = []
    url = f"{nitter_base}/{username}"

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 404:
            raise Exception(f"User @{username} not found")
        if response.status_code != 200:
            raise Exception(f"Failed to fetch tweets: HTTP {response.status_code}")

        soup = BeautifulSoup(response.text, 'html.parser')

        # get user info - use unavatar.io as reliable profile pic source
        user_info = {
            'name': username,
            'screen_name': username,
            'profile_image_url_https': f'https://unavatar.io/twitter/{username}',
            'followers_count': 0,
            'friends_count': 0
        }

        # try different selectors for profile card
        profile_card = soup.find('div', class_='profile-card')
        if not profile_card:
            profile_card = soup.find('div', class_='profile-card-info')

        if profile_card:
            # try different selectors for name
            name_elem = profile_card.find('a', class_='profile-card-fullname')
            if not name_elem:
                name_elem = profile_card.find('div', class_='profile-card-fullname')
            if not name_elem:
                name_elem = profile_card.find(class_='fullname')
            if name_elem:
                user_info['name'] = name_elem.get_text(strip=True)

            # try different selectors for stats - check multiple structures
            stats = profile_card.find_all('li', class_='profile-stat')
            if not stats:
                stats = profile_card.find_all('span', class_='profile-stat')
            if not stats:
                stats = soup.select('.profile-statlist li')
            if not stats:
                stats = soup.select('ul.profile-statlist li')

            for stat in stats:
                stat_type = stat.find('span', class_='profile-stat-header')
                stat_value = stat.find('span', class_='profile-stat-num')

                if not stat_type:
                    stat_type = stat.find(class_='profile-stat-header')
                if not stat_value:
                    stat_value = stat.find(class_='profile-stat-num')

                if stat_type and stat_value:
                    stat_type_text = stat_type.get_text(strip=True).lower()
                    value_text = stat_value.get_text(strip=True).replace(',', '').replace('.', '')

                    # handle K/M/B suffixes
                    multiplier = 1
                    if value_text.endswith('K') or value_text.endswith('k'):
                        multiplier = 1000
                        value_text = value_text[:-1]
                    elif value_text.endswith('M') or value_text.endswith('m'):
                        multiplier = 1000000
                        value_text = value_text[:-1]
                    elif value_text.endswith('B') or value_text.endswith('b'):
                        multiplier = 1000000000
                        value_text = value_text[:-1]

                    try:
                        value = int(float(value_text) * multiplier)
                    except:
                        value = 0

                    if 'following' in stat_type_text:
                        user_info['friends_count'] = value
                    elif 'follower' in stat_type_text:
                        user_info['followers_count'] = value

        # also check for stats in tab links (alternative structure)
        if user_info['followers_count'] == 0 and user_info['friends_count'] == 0:
            tab_links = soup.select('.profile-tab-item')
            for tab in tab_links:
                tab_text = tab.get_text(strip=True).lower()
                # extract numbers from tab text
                numbers = re.findall(r'[\d,]+[KkMmBb]?', tab_text)
                if numbers:
                    num_text = numbers[0].replace(',', '')
                    multiplier = 1
                    if num_text.endswith(('K', 'k')):
                        multiplier = 1000
                        num_text = num_text[:-1]
                    elif num_text.endswith(('M', 'm')):
                        multiplier = 1000000
                        num_text = num_text[:-1]
                    elif num_text.endswith(('B', 'b')):
                        multiplier = 1000000000
                        num_text = num_text[:-1]
                    try:
                        value = int(float(num_text) * multiplier)
                        if 'following' in tab_text:
                            user_info['friends_count'] = value
                        elif 'follower' in tab_text:
                            user_info['followers_count'] = value
                    except:
                        pass

        # get tweets
        tweet_items = soup.find_all('div', class_='timeline-item')

        for item in tweet_items[:count]:
            tweet_content = item.find('div', class_='tweet-content')
            if not tweet_content:
                continue

            tweet_text = tweet_content.get_text(strip=True)

            # get tweet link and id
            tweet_link = item.find('a', class_='tweet-link')
            tweet_id = ''
            tweet_url = ''
            if tweet_link:
                href = tweet_link.get('href', '')
                tweet_id = href.split('/')[-1].replace('#m', '') if href else ''
                tweet_url = f"https://twitter.com/{username}/status/{tweet_id}"

            # get stats
            stats = item.find('div', class_='tweet-stats')
            likes = 0
            retweets = 0
            if stats:
                like_elem = stats.find('span', class_='icon-heart')
                if like_elem and like_elem.parent:
                    like_text = like_elem.parent.get_text(strip=True).replace(',', '')
                    try:
                        likes = int(like_text) if like_text else 0
                    except:
                        likes = 0

                rt_elem = stats.find('span', class_='icon-retweet')
                if rt_elem and rt_elem.parent:
                    rt_text = rt_elem.parent.get_text(strip=True).replace(',', '')
                    try:
                        retweets = int(rt_text) if rt_text else 0
                    except:
                        retweets = 0

            # get date
            date_elem = item.find('span', class_='tweet-date')
            created_at = datetime.now()
            if date_elem:
                date_link = date_elem.find('a')
                if date_link:
                    date_str = date_link.get('title', '')
                    try:
                        created_at = datetime.strptime(date_str, '%b %d, %Y · %I:%M %p %Z')
                    except:
                        pass

            # get media
            media = []
            attachments = item.find('div', class_='attachments')
            if attachments:
                images = attachments.find_all('img')
                for img in images:
                    src = img.get('src', '')
                    if src:
                        if src.startswith('/'):
                            src = f"{nitter_base}{src}"
                        media.append({'type': 'photo', 'media_url_https': src})

            tweet = TweetWrapper(
                full_text=tweet_text,
                id_str=tweet_id,
                created_at=created_at,
                favorite_count=likes,
                retweet_count=retweets,
                tweet_url=tweet_url,
                user=user_info,
                media=media
            )
            tweets.append(tweet)

    except requests.RequestException as e:
        raise Exception(f"Network error: {str(e)}")

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
