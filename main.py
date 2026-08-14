import requests
import time
import json
import random
import re
import os
import base64
import html as html_lib
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw, ImageFont, ImageOps
from io import BytesIO
from datetime import datetime, timedelta
from collections import Counter
from playwright.sync_api import sync_playwright

BOT_TOKEN = "8919908599:AAGTBdy69N5NFXY5KTIMhTkO7q2VpOXwYa8"
CHAT_ID = "7898015877"
WEATHER_API_KEY = "84eaa833c8842565474aa84d53094962"
EXCHANGE_API_KEY = "b174a7c95ab92ab9e9a39a75"
GOLD_API_KEY = "goldapi-cc32e7d2de735906d4e7ac171ac3fb6e-io"

CITIES = ["Baguio", "La Trinidad", "Atok", "Bakun", "Bokod", "Buguias", "Itogon", "Kabayan", "Kapangan", "Kibungan", "Mankayan", "Sablan", "Tuba", "Tublay"]

NEWS_SOURCES = {
    "Rappler": "https://www.rappler.com/feed/",
    "Inquirer": "https://newsinfo.inquirer.net/feed",
    "PhilStar": "https://www.philstar.com/rss/nation",
    "PNA": "https://syndication.pna.gov.ph/rss",
    "NorDis": "https://nordis.net/feed/",
    "GMA News": "https://data.gmanews.tv/gno/rss/news/feed.xml",
    "BaguioCityGuide": "https://baguiocityguide.com/feed/"
}

CONNECTORS = [
    "Meanwhile, ", "In other news, ", "Elsewhere, ", "Also making headlines, ",
    "On another note, ", "Moving on, "
]

ACCENT_BLUE = (86, 180, 233, 255)
ACCENT_GREEN = (110, 210, 130, 255)
ACCENT_GOLD = (255, 195, 90, 255)
ACCENT_RED = (230, 100, 100, 255)
WHITE = (255, 255, 255, 255)
MARGIN = 55

# ---------- Weather data ----------

def get_weather_data(city):
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city},PH&appid={WEATHER_API_KEY}&units=metric"
    return requests.get(url).json()

def get_weather_line(data, city):
    temp = data["main"]["temp"]
    condition = data["weather"][0]["description"]
    return f"{city}: {temp}C, {condition}"

# ---------- Forex / Gold ----------

def get_forex_rate():
    url = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_API_KEY}/latest/USD"
    response = requests.get(url)
    data = response.json()
    if "conversion_rates" not in data:
        print(f"  [forex error] unexpected response: {data}")
        raise RuntimeError(f"ExchangeRate-API did not return conversion_rates: {data}")
    return data["conversion_rates"]["PHP"]

def get_gold_price(usd_to_php_rate):
    """Uses gold-api.com (free, no key, no rate limit) instead of GoldAPI.io,
    since that one's free tier kept hitting its monthly quota. gold-api.com
    doesn't support PHP directly, so we pull the USD/troy-oz spot price and
    convert to PHP/gram ourselves using the forex rate we already have."""
    url = "https://api.gold-api.com/price/XAU"
    response = requests.get(url, timeout=15)
    data = response.json()
    if "price" not in data:
        print(f"  [gold error] unexpected response (status {response.status_code}): {data}")
        raise RuntimeError(f"gold-api.com did not return a price: {data}")

    usd_per_troy_oz = data["price"]
    TROY_OZ_TO_GRAMS = 31.1034768
    usd_per_gram = usd_per_troy_oz / TROY_OZ_TO_GRAMS
    php_per_gram_24k = usd_per_gram * usd_to_php_rate
    return php_per_gram_24k

PRICE_HISTORY_FILE = "/data/price_history.json"

def load_previous_prices():
    if os.path.exists(PRICE_HISTORY_FILE):
        try:
            with open(PRICE_HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_current_prices(usd_rate, gold_price):
    try:
        os.makedirs(os.path.dirname(PRICE_HISTORY_FILE), exist_ok=True)
        with open(PRICE_HISTORY_FILE, "w") as f:
            json.dump({
                "usd_rate": usd_rate,
                "gold_price": gold_price,
                "date": datetime.now().strftime("%Y-%m-%d")
            }, f)
    except Exception as e:
        print(f"  [price history] could not save: {e}")

def compute_trend(current, previous, flat_threshold_pct=0.05):
    if previous is None:
        return {"direction": "flat", "color": "#9a9a9a", "arrow": "•", "pct": None, "label": "No previous data"}
    if previous == 0:
        return {"direction": "flat", "color": "#9a9a9a", "arrow": "•", "pct": None, "label": "No previous data"}

    pct_change = ((current - previous) / previous) * 100

    if pct_change > flat_threshold_pct:
        return {"direction": "up", "color": "#4caf50", "arrow": "▲", "pct": pct_change, "label": "Up from yesterday"}
    elif pct_change < -flat_threshold_pct:
        return {"direction": "down", "color": "#e05252", "arrow": "▼", "pct": pct_change, "label": "Down from yesterday"}
    else:
        return {"direction": "flat", "color": "#e0c14c", "arrow": "→", "pct": pct_change, "label": "Steady vs yesterday"}

# ---------- News ----------

LOCAL_KEYWORDS = [
    "benguet", "baguio", "la trinidad", "cordillera", "car region",
    "itogon", "atok", "buguias", "kabayan", "kapangan", "kibungan",
    "mankayan", "sablan", "tuba", "tublay", "bokod", "bakun",
    "pagasa", "car-car"
]

FEED_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*"
}

def get_articles_from_feed(feed_url, limit=6):
    try:
        response = requests.get(feed_url, headers=FEED_HEADERS, timeout=10)
        response.raise_for_status()
        raw_content = response.content

        content_type = response.headers.get("Content-Type", "unknown")
        if b"<rss" not in raw_content[:2000] and b"<feed" not in raw_content[:2000] and b"<?xml" not in raw_content[:200]:
            snippet = raw_content[:400].decode("utf-8", errors="replace")
            print(f"  [feed diagnostic] {feed_url} -> Content-Type: {content_type}, doesn't look like XML. First 400 bytes: {snippet!r}")

        try:
            import feedparser
            parsed = feedparser.parse(raw_content)
            if parsed.entries:
                articles = []
                for position, entry in enumerate(parsed.entries[:limit]):
                    title = entry.get("title", "").strip()
                    desc_raw = entry.get("summary", "") or entry.get("description", "")
                    desc = re.sub(r"<[^>]+>", "", desc_raw)
                    desc = html_lib.unescape(desc).strip()
                    link = entry.get("link", "").strip()
                    published_dt = None
                    published_struct = entry.get("published_parsed") or entry.get("updated_parsed")
                    if published_struct:
                        try:
                            published_dt = datetime.fromtimestamp(time.mktime(published_struct))
                        except Exception:
                            published_dt = None

                    image_url = None
                    media_thumb = entry.get("media_thumbnail")
                    if media_thumb and isinstance(media_thumb, list) and media_thumb[0].get("url"):
                        image_url = media_thumb[0]["url"]
                    if not image_url:
                        media_content = entry.get("media_content")
                        if media_content and isinstance(media_content, list) and media_content[0].get("url"):
                            image_url = media_content[0]["url"]
                    if not image_url:
                        for link_obj in entry.get("links", []):
                            if link_obj.get("rel") == "enclosure" and str(link_obj.get("type", "")).startswith("image"):
                                image_url = link_obj.get("href")
                                break
                    if not image_url and desc_raw:
                        img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', desc_raw)
                        if img_match:
                            image_url = img_match.group(1)

                    if title:
                        articles.append({"title": title, "description": desc, "link": link, "position": position, "published": published_dt, "image_url": image_url})
                if articles:
                    return articles
        except ImportError:
            print("  [feed] feedparser not installed, falling back to manual XML parsing")
        except Exception as e:
            print(f"  [feed] feedparser failed ({type(e).__name__}: {e}), falling back to manual XML parsing")

        text = raw_content.decode("utf-8", errors="replace")
        text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", text)
        text = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)", "&amp;", text)

        root = ET.fromstring(text)
        items = root.findall(".//item")[:limit]
        articles = []
        for position, item in enumerate(items):
            title_el = item.find("title")
            desc_el = item.find("description")
            link_el = item.find("link")
            pubdate_el = item.find("pubDate")
            title = title_el.text.strip() if title_el is not None and title_el.text else None
            desc_raw = desc_el.text.strip() if desc_el is not None and desc_el.text else ""
            desc = re.sub(r"<[^>]+>", "", desc_raw)
            desc = html_lib.unescape(desc).strip()
            link = link_el.text.strip() if link_el is not None and link_el.text else ""
            published_dt = None
            if pubdate_el is not None and pubdate_el.text:
                try:
                    import email.utils
                    published_dt = email.utils.parsedate_to_datetime(pubdate_el.text.strip())
                    if published_dt.tzinfo is not None:
                        published_dt = published_dt.replace(tzinfo=None)
                except Exception:
                    published_dt = None

            image_url = None
            enclosure_el = item.find("enclosure")
            if enclosure_el is not None and str(enclosure_el.get("type", "")).startswith("image"):
                image_url = enclosure_el.get("url")
            if not image_url:
                media_thumb_el = item.find("{http://search.yahoo.com/mrss/}thumbnail")
                if media_thumb_el is not None:
                    image_url = media_thumb_el.get("url")
            if not image_url and desc_raw:
                img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', desc_raw)
                if img_match:
                    image_url = img_match.group(1)

            if title:
                articles.append({"title": title.strip(), "description": desc, "link": link, "position": position, "published": published_dt, "image_url": image_url})
        return articles
    except Exception as e:
        print(f"  [feed error] {feed_url} -> {type(e).__name__}: {e}")
        position = getattr(e, "position", None)
        try:
            if position:
                offset = position[1]
                start = max(0, offset - 80)
                end = min(len(text), offset + 80)
                print(f"  [feed diagnostic] content around parse error position: {text[start:end]!r}")
        except Exception:
            pass
        return []

def is_local_article(article):
    text = (article["title"] + " " + article["description"]).lower()
    return any(keyword in text for keyword in LOCAL_KEYWORDS)

EXCLUDE_UNLESS_LOCAL = [
    "walang pasok", "class suspension", "suspension of classes",
    "no classes", "classes suspended"
]

ENTERTAINMENT_KEYWORDS = [
    "kpop", "k-pop", "bts", "blackpink", "showbiz", "celebrity", "actress",
    "actor ", "album", "music video", "concert", "artista", "teleserye",
    "movie premiere", "red carpet", "boy group", "girl group", "idol group",
    "gma network star", "abs-cbn star", "kapamilya", "kapuso star",
    "wedding", "engaged", "engagement", "dating rumors", "breakup",
    "love team", "romance rumors", "taylor swift", "hollywood"
]

def is_entertainment_article(article):
    text = (article["title"] + " " + article["description"]).lower()
    return any(keyword in text for keyword in ENTERTAINMENT_KEYWORDS)

def is_excluded_article(article):
    text = (article["title"] + " " + article["description"]).lower()
    matches_exclude = any(keyword in text for keyword in EXCLUDE_UNLESS_LOCAL)
    matches_entertainment = is_entertainment_article(article)
    return (matches_exclude or matches_entertainment) and not is_local_article(article)

SOURCE_PRIORITY = ["BaguioCityGuide", "Inquirer", "PhilStar", "GMA News", "NorDis", "PNA", "Rappler"]

def source_rank(name):
    try:
        return SOURCE_PRIORITY.index(name)
    except ValueError:
        return len(SOURCE_PRIORITY)

def gather_news():
    all_articles = []
    for name, url in NEWS_SOURCES.items():
        articles = get_articles_from_feed(url, limit=6)
        print(f"  [news source] {name}: {len(articles)} articles fetched")
        for article in articles:
            all_articles.append({"source": name, **article})

    all_articles = [a for a in all_articles if not is_excluded_article(a)]

    all_articles.sort(key=lambda a: (
        0 if is_local_article(a) else 1,
        source_rank(a["source"]),
        a["position"]
    ))

    return all_articles

# ---------- Shared image helpers (Pillow, used by currency/gold + news) ----------

def wrap_text(draw, text, font, max_width):
    words = text.split(" ")
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines

def get_font(size):
    return ImageFont.load_default(size=size)

def weather_prompt_from_condition(condition_main):
    mapping = {
        "Clear": "clear blue sky over misty mountains, bright sunny day, minimalist landscape",
        "Clouds": "overcast cloudy mountain landscape, soft grey sky, minimalist",
        "Rain": "rainy misty mountain highland, rain streaks, moody grey atmosphere, minimalist",
        "Thunderstorm": "dramatic storm clouds over mountains, dark sky, lightning glow, minimalist",
        "Drizzle": "light drizzle over foggy pine forest hills, soft grey tones, minimalist",
        "Mist": "thick fog over highland valley, misty mysterious atmosphere, minimalist",
        "Fog": "dense fog rolling over mountain ridges, muted tones, minimalist"
    }
    return mapping.get(condition_main, "misty mountain highland landscape, soft colors, minimalist")

def generate_background(prompt, height=1080, seed=None):
    if seed is None:
        seed = random.randint(1, 999999)
    url = f"https://image.pollinations.ai/prompt/{prompt}?width=1080&height={height}&seed={seed}"
    response = requests.get(url)
    img = Image.open(BytesIO(response.content)).convert("RGB")
    return img

def image_to_data_uri(img, quality=85):
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64_str}"

def section_badge(draw, badge_font, x, y, text, color):
    bbox = draw.textbbox((0, 0), text, font=badge_font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    pad_x, pad_y = 24, 14
    capsule_h = text_h + pad_y * 2
    draw.rounded_rectangle(
        [(x, y), (x + text_w + pad_x * 2, y + capsule_h)],
        radius=capsule_h / 2, fill=color
    )
    text_y = y + pad_y - bbox[1]
    draw.text((x + pad_x, text_y), text, font=badge_font, fill=(15, 15, 15, 255))
    return y + capsule_h

def draw_title(draw, huge_title_font, width, title_text):
    bbox = draw.textbbox((0, 0), title_text, font=huge_title_font)
    title_w = bbox[2] - bbox[0]
    title_x = (width - title_w) / 2
    draw.rectangle([(0, 0), (width, 140)], fill=(0, 0, 0, 150))
    draw.text((title_x, 40), title_text, font=huge_title_font, fill=WHITE)

# ---------- HTML rendering (used by weather post) ----------

def render_html_to_png(html, width=1080, height=1350):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.set_content(html, wait_until="networkidle")
        page.wait_for_timeout(300)
        screenshot_bytes = page.screenshot()
        browser.close()
    buffer = BytesIO(screenshot_bytes)
    buffer.seek(0)
    return buffer

def render_html_to_png_dynamic(html, width=1080, min_height=900, max_height=2400):
    """Like render_html_to_png, but lets the image grow taller to fit
    however much content there is, instead of cramming/shrinking it into
    a fixed frame. Use for posts with a variable number of items (e.g.
    road status with an unpredictable number of affected roads)."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": min_height})
        page.set_content(html, wait_until="networkidle")
        page.wait_for_timeout(300)
        content_height = page.evaluate("document.body.scrollHeight")
        final_height = max(min_height, min(content_height, max_height))
        page.set_viewport_size({"width": width, "height": final_height})
        page.wait_for_timeout(150)
        screenshot_bytes = page.screenshot(full_page=True)
        browser.close()
    buffer = BytesIO(screenshot_bytes)
    buffer.seek(0)
    return buffer

def generate_weather_narrative(weather_list):
    temps = [w["temp"] for w in weather_list]
    min_temp = round(min(temps))
    max_temp = round(max(temps))
    conditions = Counter(w["main"] for w in weather_list)
    dominant = conditions.most_common(1)[0][0].lower()

    rainy = any(w["main"] in ("Rain", "Thunderstorm", "Drizzle") for w in weather_list)

    para1 = (
        f"Temperatures across Benguet today are ranging from {min_temp}\u00b0C to {max_temp}\u00b0C, "
        f"with mostly {dominant} conditions expected across the province's 14 municipalities."
    )

    if rainy:
        para2 = "Some areas are experiencing rain — bring an umbrella and drive carefully on mountain roads."
    else:
        para2 = "No rain is currently reported in any municipality, but conditions can shift quickly in the highlands."

    return para1, para2, rainy

def build_weather_html():
    weather_list = []
    for city in CITIES:
        data = get_weather_data(city)
        temp = data["main"]["temp"]
        condition_main = data["weather"][0]["main"]
        condition_desc = data["weather"][0]["description"].title()
        weather_list.append({
            "city": city,
            "temp": temp,
            "main": condition_main,
            "desc": condition_desc
        })

    para1, para2, rainy = generate_weather_narrative(weather_list)
    today = datetime.now().strftime("%B %d, %Y")

    alertbar_html = ""
    if rainy:
        alertbar_html = """
    <div class="alertbar">
      <div class="dot"></div>
      <div class="txt">Rain reported in parts of Benguet today — travel with caution</div>
    </div>"""

    towns_html = ""
    for w in weather_list:
        towns_html += f'      <div class="town">{w["city"]} — {round(w["temp"])}\u00b0C, {w["desc"]}</div>\n'

    title_text = "Weather &amp;<br>Rain Advisory" if rainy else "Benguet<br>Weather Update"

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Archivo+Black&family=Archivo:wght@400;500;600;700&display=swap');
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:1080px; min-height:900px; font-family:'Archivo',sans-serif; position:relative; background:#1c2b33; }}

  .sky {{
    position:absolute; inset:0;
    background:
      radial-gradient(ellipse at 70% 0%, rgba(91,155,213,0.25), transparent 60%),
      linear-gradient(180deg, #16232b 0%, #223744 45%, #2c4756 100%);
  }}
  .rain {{
    position:absolute; inset:0; opacity:0.35;
    background-image: repeating-linear-gradient(100deg, transparent 0 18px, rgba(200,225,245,0.5) 18px 19px, transparent 19px 46px);
  }}

  .content {{ position:relative; z-index:2; padding:60px 76px 54px; }}

  .eyebrow {{ color:#a8d0ea; font-size:24px; letter-spacing:6px; font-weight:600; text-transform:uppercase; }}
  .title {{ font-family:'Archivo Black',sans-serif; color:#fdfdfb; font-size:64px; line-height:1.05; margin-top:14px; text-transform:uppercase; }}
  .date {{ color:#d8e8f2; font-size:26px; margin-top:16px; font-weight:500; }}

  .alertbar {{
    margin-top:36px; background:#e8a33d; color:#241a05; border-radius:14px;
    padding:22px 30px; display:flex; align-items:center; gap:18px;
  }}
  .alertbar .dot {{ width:16px; height:16px; border-radius:50%; background:#241a05; flex-shrink:0; }}
  .alertbar .txt {{ font-size:27px; font-weight:700; line-height:1.3; }}

  .body {{ margin-top:32px; background:rgba(12,22,28,0.55); border:1px solid rgba(255,255,255,0.12); border-radius:18px; padding:38px 42px; backdrop-filter: blur(2px); }}
  .body p {{ color:#f2f7fa; font-size:28px; line-height:1.55; font-weight:400; }}
  .body p + p {{ margin-top:20px; }}
  .body b {{ color:#ffd98a; font-weight:700; }}

  .towns {{ margin-top:32px; display:grid; grid-template-columns:1fr 1fr; gap:20px 32px; }}
  .town {{ color:#f2f7fa; font-size:31px; font-weight:600; display:flex; align-items:center; gap:12px; }}
  .town::before {{ content:''; width:11px; height:11px; border-radius:50%; background:#6fb3e8; flex-shrink:0; }}

  .footer {{ margin-top:40px; display:flex; justify-content:space-between; align-items:flex-end; padding-top:30px; }}
  .brand {{ color:#a8c8dc; font-size:24px; font-weight:700; letter-spacing:2px; }}
  .advice {{ color:#ffd98a; font-size:22px; font-weight:600; text-align:right; max-width:480px; line-height:1.45; }}
</style>
</head>
<body>
  <div class="sky"></div>
  <div class="rain"></div>
  <div class="content">
    <div class="eyebrow">Benguet Daily Update</div>
    <div class="title">{title_text}</div>
    <div class="date">{today}</div>
{alertbar_html}
    <div class="body">
      <p>{para1}</p>
      <p>{para2}</p>
    </div>

    <div class="towns">
{towns_html}    </div>

    <div class="footer">
      <div class="brand">BENGUET DAILY UPDATE</div>
      <div class="advice">Stay safe and check with your barangay for local advisories.</div>
    </div>
  </div>
</body>
</html>"""
    return html, para1, para2, rainy

def build_weather_caption(para1, para2):
    return f"{para1}\n\n{para2}"

def build_weather_image():
    html, para1, para2, rainy = build_weather_html()
    buffer = render_html_to_png_dynamic(html)
    caption = build_weather_caption(para1, para2)
    return buffer, caption

# ---------- Currency & Gold (HTML/Playwright card design) ----------

def build_currency_gold_html():
    usd_rate = get_forex_rate()
    gold_price = get_gold_price(usd_rate)
    today = datetime.now().strftime("%B %d, %Y")

    previous = load_previous_prices()
    usd_trend = compute_trend(usd_rate, previous.get("usd_rate"))
    gold_trend = compute_trend(gold_price, previous.get("gold_price"))

    def trend_badge(trend):
        if trend["pct"] is None:
            label = "NO PREVIOUS DATA"
        elif trend["direction"] == "up":
            label = f"UP {abs(trend['pct']):.2f}% VS YESTERDAY"
        elif trend["direction"] == "down":
            label = f"DOWN {abs(trend['pct']):.2f}% VS YESTERDAY"
        else:
            label = "STEADY VS YESTERDAY"
        return f'''<div class="trendbadge" style="background:{trend["color"]}22; color:{trend["color"]}; border:1px solid {trend["color"]}66;">
            <span class="arrow">{trend["arrow"]}</span> {label}
          </div>'''

    html_out = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Fraunces:wght@600;700;900&family=Archivo:wght@400;500;600;700&display=swap');
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:1080px; min-height:900px; font-family:'Archivo',sans-serif; background:#122019; position:relative; }}

  .bg {{
    position:absolute; inset:0;
    background:
      radial-gradient(circle at 85% 8%, rgba(212,175,55,0.20), transparent 45%),
      radial-gradient(circle at 5% 95%, rgba(212,175,55,0.10), transparent 40%),
      linear-gradient(160deg, #0e1b15 0%, #16281f 60%, #1c3226 100%);
  }}
  .ring {{ position:absolute; border-radius:50%; border:1px solid rgba(212,175,55,0.18); }}
  .r1 {{ width:900px; height:900px; top:-260px; right:-320px; }}
  .r2 {{ width:600px; height:600px; bottom:-200px; left:-200px; }}

  .content {{ position:relative; z-index:2; padding:76px; }}

  .eyebrow {{ color:#dcc06a; font-size:24px; letter-spacing:6px; font-weight:600; text-transform:uppercase; }}
  .title {{ font-family:'Fraunces',serif; font-weight:900; color:#f7f2e3; font-size:70px; line-height:1.05; margin-top:16px; }}
  .date {{ color:#c2ddd0; font-size:27px; margin-top:16px; font-weight:500; }}

  .cards {{ margin-top:56px; display:flex; flex-direction:column; gap:30px; }}
  .card {{
    background:rgba(247,242,227,0.05); border:1px solid rgba(212,175,55,0.4);
    border-radius:22px; padding:44px 46px; display:flex; justify-content:space-between; align-items:center;
  }}
  .card .label {{ color:#e2f5ea; font-size:29px; font-weight:600; letter-spacing:1px; }}
  .card .sub {{ color:#a8c9b8; font-size:21px; margin-top:10px; }}
  .card .valuewrap {{ text-align:right; }}
  .card .value {{ font-family:'Fraunces',serif; font-weight:700; color:#f0cd6e; font-size:58px; }}
  .trendbadge {{
    display:inline-flex; align-items:center; gap:9px; margin-top:16px;
    padding:10px 18px; border-radius:20px; font-size:18px; font-weight:800; letter-spacing:0.5px;
  }}
  .trendbadge .arrow {{ font-size:20px; }}

  .note {{ margin-top:44px; color:#c2ddd0; font-size:24px; line-height:1.55; }}
  .note b {{ color:#f0cd6e; }}

  .footer {{ margin-top:56px; display:flex; justify-content:space-between; align-items:flex-end; }}
  .brand {{ color:#a8c2b5; font-size:24px; font-weight:700; letter-spacing:2px; }}
  .tag {{ color:#f0cd6e; font-size:22px; font-weight:600; }}
</style>
</head>
<body>
  <div class="bg"></div>
  <div class="ring r1"></div>
  <div class="ring r2"></div>
  <div class="content">
    <div class="eyebrow">Benguet Daily Update</div>
    <div class="title">Money &amp; Markets</div>
    <div class="date">{today}</div>

    <div class="cards">
      <div class="card">
        <div>
          <div class="label">US Dollar → Peso</div>
          <div class="sub">Mid-market reference rate</div>
        </div>
        <div class="valuewrap">
          <div class="value">₱{usd_rate:.2f}</div>
          {trend_badge(usd_trend)}
        </div>
      </div>

      <div class="card">
        <div>
          <div class="label">Gold, 24K</div>
          <div class="sub">Price per gram, world spot rate in PHP</div>
        </div>
        <div class="valuewrap">
          <div class="value">₱{gold_price:,.0f}</div>
          {trend_badge(gold_trend)}
        </div>
      </div>
    </div>

    <div class="note">Rates move throughout the day — treat these as a <b>daily snapshot</b>, not a live quote, before making any big purchase or exchange.</div>

    <div class="footer">
      <div class="brand">BENGUET DAILY UPDATE</div>
      <div class="tag">Currency &amp; Gold</div>
    </div>
  </div>
</body>
</html>"""
    return html_out, usd_rate, gold_price, usd_trend, gold_trend

def build_currency_gold_caption(usd_rate, gold_price, usd_trend, gold_trend):
    lines = [
        f"💰 USD/PHP: ₱{usd_rate:.2f} ({usd_trend['label']})",
        f"🪙 Gold 24K: ₱{gold_price:,.0f}/gram ({gold_trend['label']})",
        "",
        "Daily snapshot — rates shift through the day, double check before any big transaction."
    ]
    return "\n".join(lines)

def build_currency_gold_image():
    html_out, usd_rate, gold_price, usd_trend, gold_trend = build_currency_gold_html()
    buffer = render_html_to_png_dynamic(html_out)
    caption = build_currency_gold_caption(usd_rate, gold_price, usd_trend, gold_trend)
    save_current_prices(usd_rate, gold_price)
    return buffer, caption

# ---------- Fuel Price Watch (specific per-liter estimates from DOE weekly advisory coverage) ----------

FUEL_UP_WORDS = ["increase", "increases", "hike", "hikes", "rise", "rises", "up by", "climb", "climbs", "higher", "surge"]
FUEL_DOWN_WORDS = ["decrease", "decreases", "rollback", "rollbacks", "cut", "cuts", "down by", "drop", "drops", "decline", "lower", "reduction"]
FUEL_MIXED_WORDS = ["either", "may rise or fall", "may go up or down", "may increase or decrease"]

def is_fuel_article(article):
    text = (article["title"] + " " + article["description"]).lower()

    has_fuel_topic = (
        "fuel price" in text or "oil price" in text or "pump price" in text
        or "per liter" in text or "/liter" in text
        or "price tracker: oil" in text or "oil monitor" in text
        or "price watch" in text
        or ("gasoline" in text and "price" in text)
        or ("diesel" in text and "price" in text)
        or ("kerosene" in text and "price" in text)
        or ("doe" in text and any(w in text for w in ["fuel", "oil", "diesel", "gasoline", "kerosene"]))
    )

    is_corporate_story = any(w in text for w in [
        "profit", "earnings", "revenue", "net income", "quarter", " q1 ", " q2 ",
        " q3 ", " q4 ", "airline", "eps", "stock", "shares", "ipo",
        "merger", "acquisition", " ceo ", " cfo "
    ])

    return has_fuel_topic and not is_corporate_story

def is_fuel_article_strong(article):
    """Stricter check for articles likely to contain actual per-liter pump
    price figures, as opposed to vague crude-market commentary like
    'oil prices inch up amid Hormuz talks' which mentions 'oil price' but
    has no consumer-facing numbers at all."""
    text = (article["title"] + " " + article["description"]).lower()

    has_strong_signal = (
        "per liter" in text or "/liter" in text or "pump price" in text
        or "price tracker: oil" in text or "oil monitor" in text or "price watch" in text
    )

    is_corporate_story = any(w in text for w in [
        "profit", "earnings", "revenue", "net income", "quarter", " q1 ", " q2 ",
        " q3 ", " q4 ", "airline", "eps", "stock", "shares", "ipo",
        "merger", "acquisition", " ceo ", " cfo "
    ])

    return has_strong_signal and not is_corporate_story

def classify_fuel_direction(article):
    text = (article["title"] + " " + article["description"]).lower()

    if any(phrase in text for phrase in FUEL_MIXED_WORDS):
        return "mixed"

    has_up = any(word in text for word in FUEL_UP_WORDS)
    has_down = any(word in text for word in FUEL_DOWN_WORDS)

    if has_up and has_down:
        return "mixed"
    elif has_up:
        return "up"
    elif has_down:
        return "down"
    else:
        return "unknown"

FUEL_SOURCES = {
    "GMA Economy": "https://data.gmanetwork.com/gno/rss/money/economy/feed.xml",
    "PhilNews": "https://philnews.ph/feed",
    "Rappler": "https://www.rappler.com/feed/",
    "Inquirer": "https://www.inquirer.net/fullfeed",
    "PhilStar": "https://www.philstar.com/rss/headlines",
    "GMA News": "https://data.gmanews.tv/gno/rss/news/feed.xml",
    "BaguioCityGuide": "https://baguiocityguide.com/feed/"
}

def find_fuel_article():
    candidates = []
    near_misses = []
    for name, url in FUEL_SOURCES.items():
        articles = get_articles_from_feed(url, limit=20)
        print(f"  [fuel scan] {name}: {len(articles)} articles fetched")
        for article in articles:
            article["source"] = name
            text = (article["title"] + " " + article["description"]).lower()
            if is_fuel_article(article):
                candidates.append(article)
            elif any(w in text for w in ["fuel", "diesel", "gasoline", "pump price", "oil price"]):
                near_misses.append(f"{name}: {article['title']}")

    print(f"  [fuel scan] {len(candidates)} matching fuel articles found")
    if not candidates and near_misses:
        print(f"  [fuel scan] near-miss headlines (mentioned fuel-ish terms but didn't match): {near_misses[:5]}")

    return candidates[0] if candidates else None

def fetch_full_article_text(url):
    try:
        response = requests.get(url, headers=FEED_HEADERS, timeout=10)
        response.raise_for_status()
        text = response.text
        text = re.sub(r"<script.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html_lib.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text
    except Exception as e:
        print(f"  [fuel article fetch error] {url} -> {e}")
        return ""

FUEL_RANGE_PATTERN = re.compile(
    r"(Diesel|Gasoline|Kerosene)\s*[-–:]\s*may\s*(?:either\s*)?go\s*up\s*by\s*[₱P]?([\d.]+)\s*(?:per\s*liter\s*)?or\s*go\s*down\s*by\s*[₱P]?([\d.]+)\s*per\s*liter",
    re.IGNORECASE
)

FUEL_SINGLE_PATTERN = re.compile(
    r"(Diesel|Gasoline|Kerosene)\w*\s*(?:prices?\s*)?(?:,\s*[^,]*,\s*)?(?:may\s+|will\s+|are\s+|is\s+)?(?:be\s+)?"
    r"(?:set to\s+|expected to\s+)?(rise|increase|climb|surge|hike|jump|spike|drop|decrease|roll ?back|fall|decline|cut|slash|reduce|lower|trim)\w*\s*"
    r"(?:by\s+)?(?:up to\s+|more than\s+|about\s+)?[₱P]?([\d.]+)\s*(?:/|per\s*)liter",
    re.IGNORECASE
)

FUEL_UP_VERBS = {"rise", "increase", "climb", "surge", "hike", "jump", "spike"}
FUEL_DOWN_VERBS = {"drop", "decrease", "rollback", "fall", "decline", "cut", "slash", "reduce", "lower", "trim"}

def parse_specific_fuel_estimates(text):
    results = {}

    for match in FUEL_RANGE_PATTERN.finditer(text):
        fuel = match.group(1).capitalize()
        results[fuel] = {
            "up": float(match.group(2)),
            "down": float(match.group(3)),
            "single": False
        }

    for match in FUEL_SINGLE_PATTERN.finditer(text):
        fuel = match.group(1).capitalize()
        if fuel in results:
            continue
        verb = match.group(2).lower().replace(" ", "")
        amount = float(match.group(3))
        if verb in FUEL_UP_VERBS:
            results[fuel] = {"up": amount, "down": 0.0, "single": True, "direction": "up"}
        elif verb in FUEL_DOWN_VERBS:
            results[fuel] = {"up": 0.0, "down": amount, "single": True, "direction": "down"}

    return results

FUEL_STATE_FILE = "/data/fuel_state.json"

def load_fuel_state():
    exists = os.path.exists(FUEL_STATE_FILE)
    print(f"  [fuel state] checking {FUEL_STATE_FILE} — exists: {exists}")
    if exists:
        try:
            with open(FUEL_STATE_FILE, "r") as f:
                loaded = json.load(f)
                print(f"  [fuel state] loaded keys: {list(loaded.keys())}")
                return loaded
        except Exception as e:
            print(f"  [fuel state] failed to parse existing file: {e}")
            return {}
    return {}

def save_fuel_state(state):
    try:
        os.makedirs(os.path.dirname(FUEL_STATE_FILE), exist_ok=True)
        with open(FUEL_STATE_FILE, "w") as f:
            json.dump(state, f)
        print(f"  [fuel state] saved successfully to {FUEL_STATE_FILE}")
    except Exception as e:
        print(f"  [fuel state] could not save: {e}")

def get_fuel_estimates():
    combined = {}
    source_used = None
    link_used = ""
    full_fetch_count = 0
    MAX_FULL_FETCHES = 4

    for name, url in FUEL_SOURCES.items():
        articles = get_articles_from_feed(url, limit=20)
        strong_matches = [a for a in articles if is_fuel_article_strong(a)]
        print(f"  [fuel scan] {name}: {len(articles)} articles fetched, {len(strong_matches)} passed strong filter")
        for a in strong_matches:
            print(f"    [fuel scan candidate] {name}: {a['title'][:80]}")

        if not strong_matches and articles:
            print(f"    [fuel scan {name} titles seen]: {[a['title'][:60] for a in articles[:8]]}")

        for article in articles:
            if not is_fuel_article_strong(article):
                continue

            estimates = parse_specific_fuel_estimates(article["description"])

            if not estimates and article.get("link") and full_fetch_count < MAX_FULL_FETCHES:
                full_fetch_count += 1
                fetched = fetch_full_article_text(article["link"])
                if fetched:
                    estimates = parse_specific_fuel_estimates(fetched)

            if estimates:
                print(f"  [fuel scan] {name}: found specific figures for {list(estimates.keys())}")
                for fuel, val in estimates.items():
                    if fuel not in combined:
                        combined[fuel] = val
                        if source_used is None:
                            source_used = name
                            link_used = article.get("link", "")

            if len(combined) == 3:
                break
        if len(combined) == 3:
            break

    if combined:
        print(f"  [fuel scan] final combined estimates: {combined} (primary source: {source_used})")
        article_info = {"source": source_used or "Multiple sources", "link": link_used}
        return combined, article_info

    print("  [fuel scan] no specific per-liter estimates found from any source this run — not falling back to vague commentary")
    return {}, None

def get_fuel_status(report_is_new=False):
    state = load_fuel_state()
    fresh_estimates, fresh_article = get_fuel_estimates()
    fresh_link = fresh_article.get("link", "") if fresh_article else ""

    stored_current = state.get("current")
    is_new = bool(fresh_link) and fresh_link != (stored_current or {}).get("link")

    if fresh_estimates and is_new:
        print("  [fuel state] new specific data found, updating current status")
        if stored_current:
            state["previous"] = stored_current
        state["current"] = {
            "mode": "specific",
            "estimates": fresh_estimates,
            "source": fresh_article.get("source", ""),
            "link": fresh_link,
            "found_date": datetime.now().strftime("%B %d, %Y")
        }
        save_fuel_state(state)
        return (state["current"], True) if report_is_new else state["current"]

    if not fresh_estimates and fresh_article and is_new:
        direction = classify_fuel_direction(fresh_article)
        print(f"  [fuel state] new general article found (no specific numbers), direction={direction}")
        if stored_current:
            state["previous"] = stored_current
        state["current"] = {
            "mode": "general",
            "direction": direction,
            "headline": fresh_article["title"],
            "source": fresh_article.get("source", ""),
            "link": fresh_link,
            "found_date": datetime.now().strftime("%B %d, %Y")
        }
        save_fuel_state(state)
        return (state["current"], True) if report_is_new else state["current"]

    if stored_current:
        print(f"  [fuel state] no new update this run, reusing status from {stored_current.get('found_date', 'earlier')}")
        return (stored_current, False) if report_is_new else stored_current

    print("  [fuel state] no data found this run and nothing stored previously")
    return (None, False) if report_is_new else None

FUEL_COLORS = {
    "Diesel": "#4caf50",
    "Gasoline": "#e05252",
    "Kerosene": "#e0c14c"
}

FUEL_STYLE = {
    "up": {
        "color": "#e05252", "arrow": "▲", "badge": "PRICES RISING",
        "advice": "This week's DOE advisory points to higher pump prices at the next adjustment. Fill up before Tuesday to lock in today's rate."
    },
    "down": {
        "color": "#4caf50", "arrow": "▼", "badge": "ROLLBACK IN EFFECT",
        "advice": "This week's DOE advisory points to a rollback at the next adjustment. If you can wait, filling up after the drop saves you money."
    },
    "mixed": {
        "color": "#e0c14c", "arrow": "→", "badge": "MIXED SIGNALS",
        "advice": "Fuel types are pointing in different directions this week — check which one applies to your vehicle before deciding when to fill up."
    },
    "unknown": {
        "color": "#9a9a9a", "arrow": "•", "badge": "NO UPDATE YET",
        "advice": "No DOE advisory found yet — this updates automatically once fresh coverage is published, usually Monday evening."
    }
}

def build_fuel_html(status=None):
    if status is None:
        status = get_fuel_status()
    today = datetime.now().strftime("%B %d, %Y")

    if status is None:
        estimates = {}
        mode = "unknown"
        source_label, link, found_date, headline = "", "", "", "No fuel price advisory found yet"
    elif status.get("mode") == "specific":
        estimates = status["estimates"]
        mode = "specific"
        source_label = status.get("source", "")
        link = status.get("link", "")
        found_date = status.get("found_date", "")
        headline = ""
    else:
        estimates = {}
        mode = status.get("direction", "unknown")
        source_label = status.get("source", "")
        link = status.get("link", "")
        found_date = status.get("found_date", "")
        headline = status.get("headline", "")

    if estimates:
        rows_html = ""
        for fuel_name in ["Diesel", "Gasoline", "Kerosene"]:
            if fuel_name not in estimates:
                continue
            data = estimates[fuel_name]
            up_amt = data["up"]
            down_amt = data["down"]
            color = FUEL_COLORS[fuel_name]
            is_single = data.get("single", False)

            if is_single:
                if data["direction"] == "up":
                    values_html = f'<div class="rangeline"><span class="up">▲ up by ₱{up_amt:.2f}</span></div>'
                    arrow = "▲"
                else:
                    values_html = f'<div class="rangeline"><span class="down">▼ down by ₱{down_amt:.2f}</span></div>'
                    arrow = "▼"
            else:
                values_html = (
                    f'<div class="rangeline"><span class="up">▲ up to ₱{up_amt:.2f}</span></div>'
                    f'<div class="rangeline"><span class="down">▼ down to ₱{down_amt:.2f}</span></div>'
                )
                arrow = "▲" if up_amt >= down_amt else "▼"

            rows_html += f"""
      <div class="row">
        <div class="rowlabel" style="background:{color};">{fuel_name}</div>
        <div class="rowvalues">
          {values_html}
        </div>
        <div class="rowarrow" style="color:{color};">{arrow}</div>
      </div>"""

        subhead = f"As of {found_date}" if found_date else "This week's fuel prices per liter"
        html_out = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Archivo+Black&family=Archivo:wght@400;500;600;700;800&display=swap');
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:1080px; min-height:900px; font-family:'Archivo',sans-serif; background:#171310; position:relative; }}

  .bg {{
    position:absolute; inset:0;
    background: linear-gradient(160deg, #14100d 0%, #1e1712 60%, #241b14 100%);
  }}

  .content {{ position:relative; z-index:2; padding:64px 70px 58px; }}

  .eyebrow {{ color:#dcb670; font-size:24px; letter-spacing:6px; font-weight:600; text-transform:uppercase; }}
  .title {{ font-family:'Archivo Black',sans-serif; color:#f7f2e3; font-size:56px; line-height:1.05; margin-top:16px; }}
  .date {{ color:#c2bab2; font-size:26px; margin-top:16px; font-weight:500; }}
  .subhead {{ color:#e8e2d6; font-size:26px; margin-top:26px; }}

  .rows {{ margin-top:38px; display:flex; flex-direction:column; gap:26px; }}
  .row {{
    display:flex; align-items:center; gap:22px; background:rgba(247,242,227,0.05);
    border:1px solid rgba(247,242,227,0.16); border-radius:18px; padding:32px 34px;
  }}
  .rowlabel {{
    color:#171310; font-weight:800; font-size:27px; padding:16px 24px; border-radius:10px;
    min-width:190px; text-align:center;
  }}
  .rowvalues {{ flex:1; display:flex; flex-direction:column; gap:8px; }}
  .rangeline {{ font-size:28px; font-weight:700; }}
  .up {{ color:#ea6767; }}
  .down {{ color:#5fc46b; }}
  .rowarrow {{ font-size:48px; font-weight:800; }}

  .note {{ margin-top:38px; color:#c2bab2; font-size:22px; line-height:1.55; }}

  .footer {{ margin-top:44px; padding-top:34px; display:flex; justify-content:space-between; align-items:flex-end; }}
  .brand {{ color:#a8a098; font-size:24px; font-weight:700; letter-spacing:2px; }}
  .tag {{ color:#dcb670; font-size:21px; font-weight:600; }}
</style>
</head>
<body>
  <div class="bg"></div>
  <div class="content">
    <div class="eyebrow">Benguet Daily Update</div>
    <div class="title">Fuel Price Update</div>
    <div class="date">{today}</div>
    <div class="subhead">{subhead}</div>

    <div class="rows">{rows_html}
    </div>

    <div class="note">Reflects the latest DOE-reported adjustment for this week — actual pump prices may vary by station and region.</div>

    <div class="footer">
      <div class="brand">BENGUET DAILY UPDATE</div>
      <div class="tag">Source: {source_label if source_label else "—"}</div>
    </div>
  </div>
</body>
</html>"""
        return html_out, "specific", estimates, link, source_label

    direction = mode
    if not headline:
        headline = "No fuel price advisory found this week"
    if found_date:
        headline = f"{headline} (as of {found_date})"

    style = FUEL_STYLE[direction]

    html_out = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Archivo+Black&family=Archivo:wght@400;500;600;700;800&display=swap');
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:1080px; min-height:900px; font-family:'Archivo',sans-serif; background:#171310; position:relative; }}

  .bg {{
    position:absolute; inset:0;
    background:
      radial-gradient(circle at 85% 10%, {style["color"]}22, transparent 45%),
      linear-gradient(160deg, #14100d 0%, #1e1712 60%, #241b14 100%);
  }}

  .content {{ position:relative; z-index:2; padding:76px; }}

  .eyebrow {{ color:#dcb670; font-size:24px; letter-spacing:6px; font-weight:600; text-transform:uppercase; }}
  .title {{ font-family:'Archivo Black',sans-serif; color:#f7f2e3; font-size:62px; line-height:1.05; margin-top:16px; }}
  .date {{ color:#c2bab2; font-size:27px; margin-top:16px; font-weight:500; }}

  .badge {{
    margin-top:48px; align-self:flex-start;
    background:{style["color"]}; color:#171310; font-weight:800; font-size:27px; letter-spacing:2px;
    padding:16px 30px; border-radius:8px; display:inline-flex; align-items:center; gap:14px;
  }}
  .badge .arrow {{ font-size:29px; }}

  .headline {{ margin-top:44px; color:#f5f1ea; font-size:36px; line-height:1.45; font-weight:600; }}

  .advice {{
    margin-top:40px; background:rgba(247,242,227,0.06); border:1px solid {style["color"]}55;
    border-radius:18px; padding:38px 42px; color:#e2dcd0; font-size:27px; line-height:1.6;
  }}
  .advice b {{ color:{style["color"]}; }}

  .footer {{ margin-top:56px; display:flex; justify-content:space-between; align-items:flex-end; }}
  .brand {{ color:#a8a098; font-size:24px; font-weight:700; letter-spacing:2px; }}
  .tag {{ color:{style["color"]}; font-size:22px; font-weight:600; }}
</style>
</head>
<body>
  <div class="bg"></div>
  <div class="content">
    <div class="eyebrow">Benguet Daily Update</div>
    <div class="title">Fuel Price Watch</div>
    <div class="date">{today}</div>

    <div class="badge"><span class="arrow">{style["arrow"]}</span> {style["badge"]}</div>

    <div class="headline">{headline}</div>

    <div class="advice">{style["advice"]}</div>

    <div class="footer">
      <div class="brand">BENGUET DAILY UPDATE</div>
      <div class="tag">Source: {source_label if source_label else "—"}</div>
    </div>
  </div>
</body>
</html>"""
    return html_out, direction, headline, link, source_label

def build_fuel_specific_caption(estimates, link, source_label):
    lines = ["⛽ This week's fuel prices (per liter):"]
    for fuel_name in ["Diesel", "Gasoline", "Kerosene"]:
        if fuel_name in estimates:
            data = estimates[fuel_name]
            if data.get("single", False):
                if data["direction"] == "up":
                    lines.append(f"{fuel_name}: up by ▲₱{data['up']:.2f}")
                else:
                    lines.append(f"{fuel_name}: down by ▼₱{data['down']:.2f}")
            else:
                lines.append(f"{fuel_name}: up to ▲₱{data['up']:.2f} or down to ▼₱{data['down']:.2f}")
    if source_label:
        lines.append(f"Source: {source_label}")
    if link:
        lines.append(link)
    return "\n".join(lines)

def build_fuel_caption_fallback(direction, headline, link, source_label):
    style = FUEL_STYLE[direction]
    lines = [f"⛽ {style['badge']}: {headline}"]
    if source_label:
        lines[0] += f" ({source_label})"
    if link:
        lines.append(link)
    lines.append("")
    lines.append(style["advice"])
    return "\n".join(lines)

def build_fuel_image():
    html_out, mode, data, link, source_label = build_fuel_html()
    buffer = render_html_to_png_dynamic(html_out)
    if mode == "specific":
        caption = build_fuel_specific_caption(data, link, source_label)
    else:
        caption = build_fuel_caption_fallback(mode, data, link, source_label)
    return buffer, caption

# ---------- News (HTML/Playwright narrative-style) ----------

def truncate_text(text, max_len=340):
    text = " ".join(text.split())
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "…"

def compute_news_layout(articles):
    count = max(len(articles), 1)
    return {
        "title_size": 54,
        "date_size": 24,
        "brand_size": 24,
        "num_size": 30,
        "headline_size": 40,
        "snippet_size": 26,
        "source_size": 20,
        "footer_size": 20,
        "card_pad": 40,
        "card_gap": 28,
        "snippet_max_len": round(220 * (1.0 if count <= 1 else max(0.75, 1.0 - (count - 1) * 0.1))),
    }

def build_news_html(articles):
    today = datetime.now().strftime("%B %d, %Y")

    top3 = articles[:3] if articles else []
    if not top3:
        top3 = [{"source": "", "title": "No headlines available today", "description": "", "link": ""}]

    layout = compute_news_layout(top3)

    cards_html = ""
    for i, a in enumerate(top3, start=1):
        snippet = truncate_text(a.get("description", ""), max_len=layout["snippet_max_len"]) if a.get("description") else ""
        source_label = a.get("source") or "Wire"
        tag_label = "LOCAL" if a.get("link") and is_local_article(a) else source_label.upper()
        snippet_html = f'<div class="snippet">{snippet}</div>' if snippet else ""

        cards_html += f"""
    <div class="card">
      <div class="cardtop">
        <div class="num">{i}</div>
        <div class="tag">{tag_label}</div>
      </div>
      <div class="headline">{a["title"]}</div>
      {snippet_html}
      <div class="source">{source_label}</div>
    </div>"""

    html_out = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Archivo+Black&family=Archivo:wght@400;500;600;700;800&display=swap');
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:1080px; min-height:900px; font-family:'Archivo',sans-serif; background:#141414; position:relative; }}

  .bg {{ position:absolute; inset:0; background: linear-gradient(180deg, #0d0d0d 0%, #1a1414 55%, #241412 100%); }}
  .texture {{ position:absolute; inset:0; opacity:0.06; background-image: repeating-linear-gradient(0deg, #fff 0 1px, transparent 1px 3px); }}

  .content {{ position:relative; z-index:2; padding:56px 60px 50px; }}

  .topbar {{ display:flex; justify-content:space-between; align-items:center; }}
  .brand {{ color:#c9453c; font-size:{layout["brand_size"]}px; font-weight:800; letter-spacing:3px; }}
  .date {{ color:#b0b0b0; font-size:{layout["date_size"]}px; font-weight:500; }}

  .title {{
    font-family:'Archivo Black',sans-serif; color:#f7f4ee; font-size:{layout["title_size"]}px;
    margin-top:24px; text-transform:uppercase; letter-spacing:1px;
  }}

  .cards {{ display:flex; flex-direction:column; gap:{layout["card_gap"]}px; margin-top:32px; }}

  .card {{
    background:rgba(247,242,227,0.05); border:1px solid #3a3a3a; border-radius:18px;
    padding:{layout["card_pad"]}px;
  }}
  .cardtop {{ display:flex; align-items:center; gap:16px; }}
  .num {{
    background:#c9453c; color:#fff; font-weight:800; font-size:{layout["num_size"]}px;
    width:{round(layout["num_size"]*1.7)}px; height:{round(layout["num_size"]*1.7)}px; border-radius:50%;
    display:flex; align-items:center; justify-content:center; flex-shrink:0;
  }}
  .tag {{ color:#f0a97a; font-size:{layout["source_size"]}px; font-weight:700; letter-spacing:2px; }}
  .headline {{
    color:#f7f4ee; font-size:{layout["headline_size"]}px; font-weight:700; line-height:1.28;
    margin-top:18px;
  }}
  .snippet {{ color:#d5cfc4; font-size:{layout["snippet_size"]}px; line-height:1.55; margin-top:16px; }}
  .source {{ color:#9a9a9a; font-size:{layout["source_size"]}px; margin-top:18px; font-weight:600; }}

  .footer {{ margin-top:32px; display:flex; justify-content:space-between; align-items:center; padding-top:26px; border-top:1px solid #3a3a3a; }}
  .footerbrand {{ color:#a8a098; font-size:{layout["footer_size"]}px; font-weight:700; letter-spacing:2px; }}
  .footertag {{ color:#f0a97a; font-size:{layout["footer_size"]}px; font-weight:700; }}
</style>
</head>
<body>
  <div class="bg"></div>
  <div class="texture"></div>
  <div class="content">
    <div class="topbar">
      <div class="brand">BENGUET DAILY UPDATE</div>
      <div class="date">{today}</div>
    </div>

    <div class="title">Today's Top Stories</div>

    <div class="cards">{cards_html}
    </div>

    <div class="footer">
      <div class="footerbrand">BENGUET DAILY UPDATE</div>
      <div class="footertag">Full stories via sources above →</div>
    </div>
  </div>
</body>
</html>"""
    return html_out

def build_flash_news_html(article, badge_label="BREAKING"):
    today = datetime.now().strftime("%B %d, %Y")

    title = article["title"]
    description = article.get("description", "")
    source_label = article.get("source") or "Wire"

    snippet = truncate_text(description, max_len=320) if description else "Full details available from the source below."

    html_out = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Archivo+Black&family=Archivo:wght@400;500;600;700;800&display=swap');
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:1080px; min-height:900px; font-family:'Archivo',sans-serif; background:#141414; position:relative; }}

  .bg {{ position:absolute; inset:0; background: linear-gradient(180deg, #0d0d0d 0%, #1a1414 55%, #241412 100%); }}
  .texture {{ position:absolute; inset:0; opacity:0.06; background-image: repeating-linear-gradient(0deg, #fff 0 1px, transparent 1px 3px); }}

  .content {{ position:relative; z-index:2; padding:80px 70px; padding-bottom:60px; }}

  .topbar {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:44px; }}
  .brand {{ color:#a8a098; font-size:22px; font-weight:700; letter-spacing:2px; }}
  .date {{ color:#b0b0b0; font-size:21px; }}

  .badge {{
    align-self:flex-start; background:#b02e26; color:#fff; font-weight:800; font-size:27px;
    letter-spacing:3px; padding:16px 34px; text-transform:uppercase; margin-bottom:42px; display:inline-block;
  }}

  .headline {{
    font-family:'Archivo Black',sans-serif; color:#f7f4ee; font-size:58px; line-height:1.18;
  }}

  .rule {{ height:2px; background:#3a3a3a; margin:46px 0; }}

  .snippet {{ color:#e3ded3; font-size:32px; line-height:1.6; }}

  .footer {{ margin-top:56px; display:flex; justify-content:space-between; align-items:center; padding-top:40px; border-top:1px solid #3a3a3a; }}
  .source {{ color:#a8a098; font-size:22px; }}
  .cta {{ color:#f0a97a; font-size:22px; font-weight:700; }}
</style>
</head>
<body>
  <div class="bg"></div>
  <div class="texture"></div>
  <div class="content">
    <div class="topbar">
      <div class="brand">BENGUET DAILY UPDATE</div>
      <div class="date">{today}</div>
    </div>

    <div class="badge">{badge_label}</div>

    <div class="headline">{title}</div>

    <div class="rule"></div>

    <div class="snippet">{snippet}</div>

    <div class="footer">
      <div class="source">Source: {source_label}</div>
      <div class="cta">Full story via {source_label} →</div>
    </div>
  </div>
</body>
</html>"""
    return html_out

def build_diversified_top3(articles):
    if not articles:
        return []

    local_articles = [a for a in articles if is_local_article(a)]
    national_articles = [a for a in articles if not is_local_article(a)]

    top3 = []
    if local_articles:
        top3.append(local_articles[0])
    if national_articles:
        top3.append(national_articles[0])

    remaining_pool = [a for a in articles if a not in top3]
    while len(top3) < 3 and remaining_pool:
        top3.append(remaining_pool.pop(0))

    return top3[:3]

def build_news_caption(articles):
    if not articles:
        return "No headlines available today."

    top3 = build_diversified_top3(articles)
    lines = ["📰 Today's top stories:"]
    for i, a in enumerate(top3, start=1):
        lines.append(f"{i}. {a['title']}")
        if a.get("link"):
            lines.append(a["link"])

    caption = "\n".join(lines)
    return caption[:1024]

def build_news_image():
    articles = gather_news()
    top3 = build_diversified_top3(articles)
    html_out = build_news_html(top3)
    buffer = render_html_to_png_dynamic(html_out)
    caption = build_news_caption(articles)
    return buffer, caption

# ---------- Custom News (dynamic-theme template for externally sourced news) ----------

CUSTOM_NEWS_THEMES = {
    "disaster": {
        "badge": "ALERT",
        "color": "#c9453c",
        "bg_prompt": "misty mountain highway, dramatic dark storm clouds, rain, moody atmosphere, minimalist"
    },
    "crime": {
        "badge": "SAFETY ALERT",
        "color": "#8a2e2e",
        "bg_prompt": "dark misty highland at night, moody shadows, minimalist"
    },
    "government": {
        "badge": "OFFICIAL",
        "color": "#4a7ba6",
        "bg_prompt": "blue-toned misty mountain highland, formal calm atmosphere, minimalist"
    },
    "community": {
        "badge": "COMMUNITY",
        "color": "#d4a94a",
        "bg_prompt": "warm golden mountain valley at sunset, community atmosphere, minimalist"
    },
    "weather": {
        "badge": "WEATHER WATCH",
        "color": "#5b8fa8",
        "bg_prompt": "dramatic storm clouds over misty mountains, dark grey sky, minimalist"
    },
    "general": {
        "badge": "BREAKING",
        "color": "#b02e26",
        "bg_prompt": "misty mountain highland landscape, moody overcast light, minimalist"
    }
}

CUSTOM_NEWS_KEYWORDS = {
    "disaster": ["landslide", "flood", "fire", "explosion", "accident", "crash", "collapse",
                 "earthquake", "killed", "dead", "injured", "victims", "emergency", "rescue",
                 "mudflow", "rockslide"],
    "crime": ["arrest", "arrested", "robbery", "shooting", "stabbing", "murder", "police",
              "raid", "illegal drugs", "scam", "fraud", "suspect", "wanted"],
    "government": ["mayor", "governor", "dpwh", "dswd", "doh ", "ordinance", "budget",
                   "barangay", "municipal", "provincial", "senate", "congress", "president",
                   "election", "doe ", "dilg", "executive order", "resolution"],
    "community": ["festival", "fiesta", "celebration", "tourism", "farmers", "harvest",
                  "award", "scholarship", "donation", "charity", "anniversary", "fair"],
    "weather": ["typhoon", "rainfall", "storm", "habagat", "signal no", "pagasa",
                "weather advisory", "flood warning", "amihan"]
}

def classify_custom_news_category(text):
    text_lower = text.lower()
    for category, keywords in CUSTOM_NEWS_KEYWORDS.items():
        if any(keyword in text_lower for keyword in keywords):
            return category
    return "general"

def render_custom_news_body_html(body):
    """Splits the pasted body into blocks: consecutive bullet lines
    (starting with • or -) become a multi-column grid so short items
    (like municipality names) don't waste horizontal space stacked one
    per line; everything else renders as a normal paragraph."""
    lines = body.split("\n")
    blocks = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith("•") or line.startswith("-"):
            items = []
            while i < n and (lines[i].strip().startswith("•") or lines[i].strip().startswith("-")):
                item_text = lines[i].strip().lstrip("•").lstrip("-").strip()
                if item_text:
                    items.append(item_text)
                i += 1
            items_html = "".join(f'<div class="bulletitem">{item}</div>' for item in items)
            blocks.append(f'<div class="bulletgrid">{items_html}</div>')
        else:
            blocks.append(f"<p>{line}</p>")
            i += 1
    return "".join(blocks)

def build_custom_news_html(headline, body, category):
    theme = CUSTOM_NEWS_THEMES.get(category, CUSTOM_NEWS_THEMES["general"])
    today = datetime.now().strftime("%B %d, %Y")
    body_html = render_custom_news_body_html(body)

    try:
        bg_img = generate_background(theme["bg_prompt"], height=1350)
        bg_data_uri = image_to_data_uri(bg_img)
        bg_style = f"background-image:url('{bg_data_uri}'); background-size:cover; background-position:center;"
    except Exception as e:
        print(f"  [custom news bg] could not generate background, using flat fallback: {e}")
        bg_style = ""

    html_out = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Archivo+Black&family=Archivo:wght@400;500;600;700;800&display=swap');
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:1080px; min-height:900px; font-family:'Archivo',sans-serif; background:#14181c; position:relative; }}

  .bg {{ position:absolute; inset:0; {bg_style} background-color:#14181c; background-repeat:no-repeat; }}
  .overlay {{ position:absolute; inset:0; background: linear-gradient(160deg, rgba(14,16,20,0.80) 0%, rgba(20,24,28,0.82) 55%, rgba(24,28,34,0.88) 100%); }}

  .content {{ position:relative; z-index:2; padding:76px; padding-bottom:60px; }}

  .topbar {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:40px; }}
  .brand {{ color:#a8a098; font-size:22px; font-weight:700; letter-spacing:2px; }}
  .date {{ color:#b0b0b0; font-size:21px; }}

  .badge {{
    align-self:flex-start; background:{theme["color"]}; color:#fff; font-weight:800; font-size:26px;
    letter-spacing:3px; padding:15px 32px; text-transform:uppercase; margin-bottom:40px; display:inline-block;
    border-radius:6px;
  }}

  .headline {{
    font-family:'Archivo Black',sans-serif; color:#f7f4ee; font-size:52px; line-height:1.18;
  }}

  .rule {{ height:2px; background:{theme["color"]}66; margin:42px 0; }}

  .body {{ color:#e3ded3; font-size:29px; line-height:1.65; }}
  .body p {{ margin-bottom:22px; }}
  .body p:last-child {{ margin-bottom:0; }}

  .bulletgrid {{
    display:grid; grid-template-columns:repeat(auto-fill, minmax(230px, 1fr));
    gap:14px 30px; margin:6px 0 30px 0;
  }}
  .bulletitem {{
    color:#f0ece2; font-size:27px; font-weight:600; position:relative; padding-left:30px;
  }}
  .bulletitem::before {{
    content:'•'; position:absolute; left:0; color:{theme["color"]}; font-weight:800; font-size:28px;
  }}

  .footer {{ margin-top:52px; display:flex; justify-content:space-between; align-items:center; padding-top:36px; border-top:1px solid rgba(247,242,227,0.16); }}
  .footerbrand {{ color:#a8a098; font-size:22px; font-weight:700; letter-spacing:2px; }}
  .tag {{ color:{theme["color"]}; font-size:20px; font-weight:700; letter-spacing:1px; }}
</style>
</head>
<body>
  <div class="bg"></div>
  <div class="overlay"></div>
  <div class="content">
    <div class="topbar">
      <div class="brand">BENGUET DAILY UPDATE</div>
      <div class="date">{today}</div>
    </div>

    <div class="badge">{theme["badge"]}</div>

    <div class="headline">{headline}</div>

    <div class="rule"></div>

    <div class="body">{body_html}</div>

    <div class="footer">
      <div class="footerbrand">BENGUET DAILY UPDATE</div>
      <div class="tag">{theme["badge"]}</div>
    </div>
  </div>
</body>
</html>"""
    return html_out

def parse_custom_news_input(raw_text):
    """Joel writes/humanizes the story himself in a separate chat before
    pasting it here — no AI rewriting happens in this pipeline. This just
    splits the paste into headline (line 1) and body (everything after),
    preserving blank lines between paragraphs exactly as typed, so the
    card renders proper paragraph breaks."""
    text = raw_text.strip("\n")
    lines = text.split("\n")
    headline = lines[0].strip()
    body = "\n".join(lines[1:]).strip()
    if not body:
        body = headline
    return headline, body

def build_custom_news_image(raw_text):
    """Takes Joel's pasted, already-humanized news text and turns it into
    a themed, ready-to-approve post. No AI rewriting happens here."""
    headline, body = parse_custom_news_input(raw_text)

    category = classify_custom_news_category(headline + " " + body)
    html_out = build_custom_news_html(headline, body, category)
    buffer = render_html_to_png_dynamic(html_out)

    caption = body if len(body) <= 1000 else body[:1000] + "…"
    label = f"customnews_{category}"
    return buffer, caption, label

# ---------- Telegram ----------

def send_photo_for_approval(image_buffer, label, filename="update.jpg", mime="image/jpeg", caption=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    keyboard = {
        "inline_keyboard": [[
            {"text": "Approve", "callback_data": f"approve_{label}"},
            {"text": "Reject", "callback_data": f"reject_{label}"}
        ]]
    }
    files = {"photo": (filename, image_buffer, mime)}
    data = {
        "chat_id": CHAT_ID,
        "reply_markup": json.dumps(keyboard)
    }
    if caption:
        data["caption"] = caption
        print(f"  [telegram] caption length for '{label}': {len(caption)} chars")
    response = requests.post(url, files=files, data=data)
    result = response.json()
    if not result.get("ok"):
        print(f"  [telegram ERROR] '{label}' failed: {result}")
    else:
        print(f"  [telegram] '{label}' delivered OK")
    return result

# ---------- Facebook posting (fetches the approved image directly from
# Telegram, so it works regardless of which service/volume handles the
# approval check — no shared local storage needed) ----------

FB_PAGE_ACCESS_TOKEN = os.environ.get("FB_PAGE_ACCESS_TOKEN", "")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID", "")

def get_telegram_file_bytes(file_id):
    try:
        file_info = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getFile",
            params={"file_id": file_id}, timeout=15
        ).json()
        if not file_info.get("ok"):
            print(f"  [telegram file] getFile failed: {file_info}")
            return None
        file_path = file_info["result"]["file_path"]
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        response = requests.get(file_url, timeout=30)
        return response.content
    except Exception as e:
        print(f"  [telegram file] could not download: {e}")
        return None

def post_to_facebook(image_bytes, caption):
    if not FB_PAGE_ACCESS_TOKEN or not FB_PAGE_ID:
        return {"error": "FB_PAGE_ACCESS_TOKEN or FB_PAGE_ID not configured"}

    url = f"https://graph.facebook.com/{FB_PAGE_ID}/photos"
    files = {"source": ("post.png", image_bytes, "image/png")}
    data = {
        "caption": caption or "",
        "access_token": FB_PAGE_ACCESS_TOKEN
    }
    response = requests.post(url, files=files, data=data)
    return response.json()

TELEGRAM_OFFSET_FILE = "/data/telegram_offset.json"

def load_telegram_offset():
    if os.path.exists(TELEGRAM_OFFSET_FILE):
        try:
            with open(TELEGRAM_OFFSET_FILE, "r") as f:
                return json.load(f).get("offset")
        except Exception:
            return None
    return None

def save_telegram_offset(offset):
    try:
        os.makedirs(os.path.dirname(TELEGRAM_OFFSET_FILE), exist_ok=True)
        with open(TELEGRAM_OFFSET_FILE, "w") as f:
            json.dump({"offset": offset}, f)
    except Exception as e:
        print(f"  [telegram offset] could not save: {e}")

def answer_callback_query(callback_query_id, text=""):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery"
    requests.post(url, data={"callback_query_id": callback_query_id, "text": text})

def send_text_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text})

def process_telegram_approvals():
    try:
        webhook_info = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo", timeout=10).json()
        webhook_url = webhook_info.get("result", {}).get("url", "")
        if webhook_url:
            print(f"  [approvals] a webhook is set ({webhook_url}) — this blocks polling, deleting it")
            requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook", timeout=10)
        else:
            print("  [approvals] no webhook set, polling should work normally")
    except Exception as e:
        print(f"  [approvals] could not check webhook status: {e}")

    offset = load_telegram_offset()
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"timeout": 5}
    if offset:
        params["offset"] = offset + 1

    try:
        response = requests.get(url, params=params, timeout=15).json()
    except Exception as e:
        print(f"  [approvals] could not fetch updates: {e}")
        return

    if not response.get("ok"):
        print(f"  [approvals] getUpdates failed: {response}")
        return

    updates = response.get("result", [])
    print(f"  [approvals] getUpdates returned {len(updates)} update(s) total, offset was: {offset}")
    if not updates:
        print("  [approvals] no new button presses")
        return

    latest_update_id = offset
    for update in updates:
        latest_update_id = update["update_id"]
        callback = update.get("callback_query")
        other_keys = [k for k in update.keys() if k != "update_id"]
        print(f"  [approvals] update_id={update['update_id']}, contains: {other_keys}")
        if not callback:
            continue

        data = callback.get("data", "")
        callback_id = callback["id"]

        try:
            if data.startswith("approve_"):
                label = data[len("approve_"):]
                message = callback.get("message", {})
                photos = message.get("photo", [])
                caption = message.get("caption", "")

                if not photos:
                    print(f"  [approvals] approve for '{label}' but the original message has no photo attached")
                    answer_callback_query(callback_id, "No photo found on this message")
                    continue

                largest_photo = photos[-1]
                image_bytes = get_telegram_file_bytes(largest_photo["file_id"])

                if not image_bytes:
                    print(f"  [approvals] approve for '{label}' but could not download the image from Telegram")
                    answer_callback_query(callback_id, "Could not download image — check logs")
                    continue

                print(f"  [approvals] approving '{label}' — posting to Facebook")
                result = post_to_facebook(image_bytes, caption)
                if result.get("id") or result.get("post_id"):
                    print(f"  [approvals] '{label}' posted to Facebook successfully: {result}")
                    answer_callback_query(callback_id, "Posted to Facebook!")
                    send_text_message(f"✅ '{label}' approved and posted to Facebook.")
                else:
                    print(f"  [approvals] '{label}' Facebook post FAILED: {result}")
                    answer_callback_query(callback_id, "Facebook post failed — check logs")
                    error_info = result.get("error", result)
                    if isinstance(error_info, dict):
                        error_text = error_info.get("message", str(error_info))
                    else:
                        error_text = str(error_info)
                    send_text_message(f"⚠️ '{label}' approved but Facebook post failed: {error_text}")

            elif data.startswith("reject_"):
                label = data[len("reject_"):]
                print(f"  [approvals] '{label}' rejected, discarding")
                answer_callback_query(callback_id, "Rejected — discarded")
                send_text_message(f"🚫 '{label}' rejected — not posted to Facebook.")
        except Exception as e:
            print(f"  [approvals] error handling update {update['update_id']}: {e}")

    if latest_update_id:
        save_telegram_offset(latest_update_id)

def seed_fuel_state_if_empty():
    if os.path.exists(FUEL_STATE_FILE):
        print("  [fuel seed] state file already exists, skipping seed")
        return

    print("  [fuel seed] no state file found, seeding with known real data")
    seed_state = {
        "current": {
            "mode": "specific",
            "estimates": {
                "Diesel": {"up": 0.0, "down": 4.30, "single": True, "direction": "down"},
                "Gasoline": {"up": 0.0, "down": 4.70, "single": True, "direction": "down"},
                "Kerosene": {"up": 0.0, "down": 4.88, "single": True, "direction": "down"}
            },
            "source": "GMA News",
            "link": "https://www.gmanetwork.com/news/money/economy/997957/fuel-prices-down-by-over-p4-per-liter-starting-august-11/story/",
            "found_date": "August 10, 2026"
        }
    }
    save_fuel_state(seed_state)

# ---------- Road Status Watch (Kennon/Halsema/Marcos, via BaguioCityGuide) ----------

ROAD_SOURCES = {
    "BaguioCityGuide": "https://baguiocityguide.com/feed/"
}

TRACKED_ROADS = [
    "Kennon Road", "Halsema Highway", "Marcos Highway",
    "Benguet-Nueva Vizcaya Road", "Baguio-Bontoc Road", "Naguilian Road",
    "Gov Bado Dangwa National Road", "Baguio-Itogon Road",
    "Tawang-Ambiong Road", "Abatan-Mankayan-Cervantes Road",
    "Pico-Lamtang Road", "Itogon-Dalupirip Road"
]

ROAD_TOPIC_KEYWORDS = [
    "road condition", "road advisory", "passable", "not passable", "impassable",
    "one lane", "one-lane", "road closure", "landslide", "rockslide", "road slip",
    "mudflow", "dpwh", "slope collapse", "rocknet"
]

def is_road_article(article):
    text = (article["title"] + " " + article["description"]).lower()
    return any(keyword in text for keyword in ROAD_TOPIC_KEYWORDS)

ROAD_STATUS_STYLES = {
    "closed": {"label": "CLOSED / NOT PASSABLE", "color": "#e05252"},
    "one_lane": {"label": "ONE LANE PASSABLE", "color": "#e0c14c"},
    "passable": {"label": "PASSABLE", "color": "#4caf50"},
}

REASON_KEYWORDS = [
    "road slip", "landslide", "rockslide", "mudflow", "heavy rainfall",
    "heavy rain", "flooding", "erosion", "debris", "continuous heavy rainfall",
    "slope collapse", "soil collapse", "rock collapse", "damaged abutment",
    "scoured", "cracks on the girder"
]

def classify_road_status_text(window_text):
    t = window_text.lower()
    if any(k in t for k in ["not passable", "impassable", "closed", "no entry"]):
        return "closed"
    if any(k in t for k in ["one lane", "one-lane", "single lane"]):
        return "one_lane"
    if any(k in t for k in ["passable", "open", "cleared"]):
        return "passable"
    return None

def extract_reason(window_text):
    t = window_text.lower()
    for keyword in REASON_KEYWORDS:
        if keyword in t:
            return keyword
    return None

LOCATION_PATTERN = re.compile(
    r"at\s+([A-Z][a-zA-Z\u00f1\u00d1'.\- ]{2,30}?)\s+in\s+([A-Z][a-zA-Z\u00f1\u00d1'.\- ]{2,30}?)[,\.]",
)

def extract_location(window_text):
    match = LOCATION_PATTERN.search(window_text)
    if match:
        place = match.group(1).strip()
        town = match.group(2).strip()
        return f"{place}, {town}"
    return None

def split_sentences(text):
    return re.split(r"(?<=[.!?])\s+", text)

def extract_road_statuses(text):
    text = text.replace("Gov.", "Gov")

    results = {}
    sentences = split_sentences(text)

    for sentence in sentences:
        sentence_lower = sentence.lower()
        for road in TRACKED_ROADS:
            if road in results:
                continue
            if road.lower() in sentence_lower:
                status = classify_road_status_text(sentence)
                if status:
                    results[road] = {
                        "status": status,
                        "reason": extract_reason(sentence),
                        "location": extract_location(sentence)
                    }
    return results

REASON_PHRASES = {
    "road slip": "a road slip",
    "landslide": "a landslide",
    "rockslide": "a rockslide",
    "mudflow": "a mudflow",
    "heavy rainfall": "heavy rainfall",
    "heavy rain": "heavy rain",
    "flooding": "flooding",
    "erosion": "erosion",
    "debris": "debris on the road",
    "continuous heavy rainfall": "continuous heavy rainfall",
    "slope collapse": "a slope collapse",
    "soil collapse": "a soil collapse",
    "rock collapse": "a rock collapse",
    "damaged abutment": "a damaged bridge abutment",
    "scoured": "a scoured bridge foundation",
    "cracks on the girder": "cracked bridge girders"
}

STATUS_PHRASES = {
    "closed": "currently closed to travel",
    "one_lane": "open but limited to one-lane traffic",
    "passable": "fully passable"
}

def normalize_road_info(info):
    if isinstance(info, dict):
        return info
    return {"status": info, "reason": None}

def build_road_narrative(statuses):
    if not statuses:
        return ""

    bullets = []
    for road, raw_info in statuses.items():
        info = normalize_road_info(raw_info)
        status_phrase = STATUS_PHRASES.get(info["status"], "affected by current conditions")
        reason = info.get("reason")
        location = info.get("location")

        location_phrase = f" near {location}" if location else ""
        reason_phrase = f", due to {REASON_PHRASES.get(reason, reason)}" if reason else ""

        bullets.append(f"• {road} is {status_phrase}{location_phrase}{reason_phrase}.")

    return "\n".join(bullets)

def find_road_article():
    for name, url in ROAD_SOURCES.items():
        articles = get_articles_from_feed(url, limit=20)
        print(f"  [road scan] {name}: {len(articles)} articles fetched")
        for i, article in enumerate(articles):
            matched = is_road_article(article)
            print(f"    [road scan #{i}] {'MATCH' if matched else 'skip '} — {article['title'][:80]}")
            if matched:
                article["source"] = name
                return article
    return None

def find_road_articles(max_articles=5):
    matched = []
    for name, url in ROAD_SOURCES.items():
        articles = get_articles_from_feed(url, limit=20)
        print(f"  [road scan] {name}: {len(articles)} articles fetched")
        for i, article in enumerate(articles):
            is_match = is_road_article(article)
            print(f"    [road scan #{i}] {'MATCH' if is_match else 'skip '} — {article['title'][:80]}")
            if is_match:
                article["source"] = name
                matched.append(article)
                if len(matched) >= max_articles:
                    return matched
    return matched

ROAD_STATE_FILE = "/data/road_state.json"

def load_road_state():
    if os.path.exists(ROAD_STATE_FILE):
        try:
            with open(ROAD_STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_road_state(state):
    try:
        os.makedirs(os.path.dirname(ROAD_STATE_FILE), exist_ok=True)
        with open(ROAD_STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        print(f"  [road state] could not save: {e}")

def get_road_status(report_is_new=False):
    state = load_road_state()
    stored_current = state.get("current")
    stored_statuses = (stored_current or {}).get("statuses", {})

    articles = find_road_articles(max_articles=5)
    if not articles:
        print("  [road scan] no road advisory article found this run")
        return (stored_current, False) if report_is_new else stored_current

    newest_article = articles[0]

    merged_statuses = dict(stored_statuses)
    for article in articles:
        full_text = article["description"]
        if article.get("link"):
            fetched = fetch_full_article_text(article["link"])
            if fetched:
                full_text = fetched
        statuses = extract_road_statuses(full_text)
        if statuses:
            print(f"  [road scan] '{article['title'][:60]}' -> {list(statuses.keys())}")
            merged_statuses.update(statuses)

    if not merged_statuses:
        print("  [road scan] articles found but no per-road status could be extracted from any of them")
        return (stored_current, False) if report_is_new else stored_current

    same_link = newest_article.get("link") and newest_article["link"] == (stored_current or {}).get("link")
    same_statuses = merged_statuses == stored_statuses

    if same_link and same_statuses:
        print("  [road state] same newest article, same merged statuses — no update needed")
        return (stored_current, False) if report_is_new else stored_current

    if same_statuses:
        print("  [road state] newest article changed but merged statuses are unchanged — no update needed")
        return (stored_current, False) if report_is_new else stored_current

    print(f"  [road scan] merged statuses across {len(articles)} recent articles -> {merged_statuses}")

    new_current = {
        "statuses": merged_statuses,
        "source": newest_article.get("source", "BaguioCityGuide"),
        "link": newest_article.get("link", ""),
        "found_date": datetime.now().strftime("%B %d, %Y")
    }
    if stored_current:
        state["previous"] = stored_current
    state["current"] = new_current
    save_road_state(state)
    return (new_current, True) if report_is_new else new_current

def road_background_prompt(status):
    statuses = (status or {}).get("statuses", {})
    has_closed = any(
        normalize_road_info(v)["status"] == "closed" for v in statuses.values()
    ) if statuses else False

    if has_closed:
        return "rainy misty mountain highway, landslide warning, wet asphalt cliffside road, moody grey clouds, dramatic atmosphere, minimalist"
    return "scenic misty mountain highway, pine forest cliffside road, soft overcast light, minimalist"

def build_road_html(status=None):
    if status is None:
        status = get_road_status()
    today = datetime.now().strftime("%B %d, %Y")

    try:
        bg_prompt = road_background_prompt(status)
        bg_img = generate_background(bg_prompt, height=1350)
        bg_data_uri = image_to_data_uri(bg_img)
        bg_style = f"background-image:url('{bg_data_uri}'); background-size:cover; background-position:center;"
    except Exception as e:
        print(f"  [road bg] could not generate background image, using fallback: {e}")
        bg_style = ""

    if not status or not status.get("statuses"):
        rows_html = ""
        narrative = "No road advisory available yet — this updates automatically once fresh coverage is published."
        subhead = "No road advisory available yet"
    else:
        all_statuses = status["statuses"]

        severity_order = {"closed": 0, "one_lane": 1, "passable": 2}
        sorted_roads = dict(sorted(
            all_statuses.items(),
            key=lambda item: severity_order.get(normalize_road_info(item[1])["status"], 3)
        ))

        rows_html = ""
        for road, raw_info in sorted_roads.items():
            info = normalize_road_info(raw_info)
            style = ROAD_STATUS_STYLES.get(info["status"], ROAD_STATUS_STYLES["passable"])
            rows_html += f"""
      <div class="row">
        <div class="roadname">{road}</div>
        <div class="statuspill" style="background:{style['color']}22; color:{style['color']}; border:1px solid {style['color']}66;">{style['label']}</div>
      </div>"""

        narrative = build_road_narrative(all_statuses)
        found_date = status.get("found_date", "")
        subhead = f"As of {found_date}" if found_date else "Latest road advisory"

    html_out = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Archivo+Black&family=Archivo:wght@400;500;600;700;800&display=swap');
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:1080px; min-height:900px; font-family:'Archivo',sans-serif; background:#14181c; position:relative; }}

  .bg {{ position:absolute; inset:0; {bg_style} background-color:#14181c; background-repeat:no-repeat; }}
  .overlay {{ position:absolute; inset:0; background: linear-gradient(160deg, rgba(16,20,26,0.72) 0%, rgba(22,28,34,0.78) 60%, rgba(28,37,48,0.85) 100%); }}

  .content {{ position:relative; z-index:2; padding:76px; padding-bottom:60px; }}

  .eyebrow {{ color:#6fa8c9; font-size:22px; letter-spacing:6px; font-weight:600; text-transform:uppercase; }}
  .title {{ font-family:'Archivo Black',sans-serif; color:#f7f2e3; font-size:54px; line-height:1.05; margin-top:14px; }}
  .subhead {{ color:#e2e8ec; font-size:26px; margin-top:20px; font-weight:600; }}

  .rows {{ margin-top:36px; display:flex; flex-direction:column; gap:22px; }}
  .row {{
    display:flex; align-items:center; justify-content:space-between; gap:20px;
    background:rgba(247,242,227,0.06); border:1px solid rgba(247,242,227,0.16);
    border-radius:16px; padding:32px 34px;
  }}
  .roadname {{ color:#f7fafc; font-size:29px; font-weight:700; }}
  .statuspill {{ font-size:20px; font-weight:800; letter-spacing:1px; padding:12px 24px; border-radius:20px; white-space:nowrap; }}

  .note {{ margin-top:30px; color:#c3ccd2; font-size:19px; line-height:1.5; }}

  .footer {{ margin-top:auto; padding-top:32px; display:flex; justify-content:space-between; align-items:flex-end; }}
  .brand {{ color:#a8b2ba; font-size:22px; font-weight:700; letter-spacing:2px; }}
  .tag {{ color:#6fa8c9; font-size:18px; font-weight:600; }}
</style>
</head>
<body>
  <div class="bg"></div>
  <div class="overlay"></div>
  <div class="content">
    <div class="eyebrow">Benguet Daily Update</div>
    <div class="title">Road Status Watch</div>
    <div class="subhead">{subhead}</div>

    <div class="rows">{rows_html}
    </div>

    <div class="note">Reflects the latest DPWH-CAR advisory — conditions may change with weather.</div>

    <div class="footer">
      <div class="brand">BENGUET DAILY UPDATE</div>
      <div class="tag">Road Status Watch</div>
    </div>
  </div>
</body>
</html>"""
    return html_out, status

def build_road_caption(status):
    if not status or not status.get("statuses"):
        return "🛣️ No road advisory available yet — check back later."

    lines = ["🛣️ Road status update:", build_road_narrative(status["statuses"])]
    caption = "\n".join(lines)
    return caption[:1024]

def build_road_image():
    html_out, status = build_road_html()
    buffer = render_html_to_png_dynamic(html_out)
    caption = build_road_caption(status)
    return buffer, caption

# ---------- Reel Script Generation (headlines -> spoken narration draft) ----------
# Builds the daily reel narration script from real, already-working data
# sources (NEWS_SOURCES, weather, currency, fuel) -- no new APIs, no AI
# rewrite cost. This only produces the DRAFT TEXT and sends it to Telegram
# for Joel to read/approve. Voice synthesis and video assembly are later,
# separate steps.

SPORTS_KEYWORDS = [
    "basketball", "volleyball", "chess", "athletics", "marathon", "pba",
    "uaap", "ncaa", "palarong pambansa", "sportsfest", "boxing", "football",
    "sepak takraw", "coach", "athlete", "tournament", "championship",
    "batang pinoy", "car games", "cordillera games", "milo marathon",
    "track and field", "cheerdance", "sports meet"
]

def is_sports_article(article):
    text = (article["title"] + " " + article["description"]).lower()
    return any(keyword in text for keyword in SPORTS_KEYWORDS)

def gather_reel_article_pool():
    """Fetches from the same NEWS_SOURCES feeds already used for the daily
    news post, deduplicated by title, with excluded articles filtered out
    the same way gather_news() does."""
    all_articles = []
    for name, url in NEWS_SOURCES.items():
        articles = get_articles_from_feed(url, limit=10)
        for article in articles:
            all_articles.append({"source": name, **article})

    all_articles = [a for a in all_articles if not is_excluded_article(a)]

    seen_titles = set()
    deduped = []
    for a in all_articles:
        key = a["title"].strip().lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        deduped.append(a)

    def is_recent(article, hours):
        published = article.get("published")
        if not published:
            return False
        age_hours = (datetime.now() - published).total_seconds() / 3600
        return 0 <= age_hours <= hours

    fresh = [a for a in deduped if is_recent(a, 36)]
    print(f"  [reel pool] {len(fresh)}/{len(deduped)} articles within 36h freshness window")

    if len(fresh) < 3:
        fresh = [a for a in deduped if is_recent(a, 60)]
        print(f"  [reel pool] too few within 36h, relaxed to 60h -> {len(fresh)} articles")

    return fresh

TITLE_STOPWORDS = {
    "the", "a", "an", "in", "on", "at", "to", "of", "for", "and", "with",
    "as", "is", "are", "by", "from", "this", "that", "its", "after",
    "before", "due", "amid", "new", "over", "into", "than", "not"
}

def title_significant_words(title):
    words = re.findall(r"[a-zA-Z']+", title.lower())
    return set(w for w in words if w not in TITLE_STOPWORDS and len(w) > 3)

def is_too_similar_to_selected(article, selected):
    """Catches multiple articles covering the same underlying story from
    different angles (e.g. four separate headlines all about the same
    Habagat rain event) -- these have different titles so exact-match
    dedup misses them, but share enough significant words to read as
    repetitive back-to-back in a spoken script."""
    words = title_significant_words(article["title"])
    for s in selected:
        s_words = title_significant_words(s["title"])
        if len(words & s_words) >= 2:
            return True
    return False

def build_reel_headline_pool(max_items=8, sports_slots=1):
    """Selects up to max_items headlines: Benguet/Cordillera general news
    first, national general news fills remaining slots, and a reserved
    number of sports_slots go to sports coverage (local sports preferred,
    national sports as fallback) -- this ratio is an assumption pending
    Joel's confirmation, not a spec he gave explicitly."""
    articles = gather_reel_article_pool()

    # Road advisories are excluded here entirely -- they're often reported
    # across several near-duplicate articles (same closure, different
    # posts), which used to eat multiple headline slots with repetitive
    # content. Road Status Watch already merges these properly; the reel
    # gets ONE consolidated road line via build_reel_road_narration_line()
    # instead (see build_reel_script).
    articles = [a for a in articles if not is_road_article(a)]

    local_general = [a for a in articles if is_local_article(a) and not is_sports_article(a)]
    national_general = [a for a in articles if not is_local_article(a) and not is_sports_article(a)]
    local_sports = [a for a in articles if is_local_article(a) and is_sports_article(a)]
    national_sports = [a for a in articles if not is_local_article(a) and is_sports_article(a)]

    selected = []
    selected_titles = set()

    def add(article):
        key = article["title"].strip().lower()
        if key in selected_titles or len(selected) >= max_items:
            return
        if is_too_similar_to_selected(article, selected):
            return
        selected.append(article)
        selected_titles.add(key)

    general_slots = max_items - sports_slots

    for a in local_general:
        if len([s for s in selected if not is_sports_article(s)]) >= general_slots:
            break
        add(a)
    for a in national_general:
        if len([s for s in selected if not is_sports_article(s)]) >= general_slots:
            break
        add(a)

    sports_pool = local_sports if local_sports else national_sports
    for a in sports_pool[:sports_slots]:
        add(a)

    # If sports coverage wasn't available at all, let general news fill
    # those leftover slots instead of coming up short.
    if len(selected) < max_items:
        for a in national_general:
            add(a)

    return selected

def is_monday():
    return datetime.now().weekday() == 0

def get_weather_narration_line():
    """Lightweight reuse of the same weather data/narrative logic used
    for the weather post, condensed to one filler line for slow news
    days."""
    try:
        weather_list = []
        for city in CITIES:
            data = get_weather_data(city)
            weather_list.append({
                "city": city,
                "temp": data["main"]["temp"],
                "main": data["weather"][0]["main"],
                "desc": data["weather"][0]["description"]
            })
        para1, para2, rainy = generate_weather_narrative(weather_list)
        return para1
    except Exception as e:
        print(f"  [reel filler] weather line failed: {e}")
        return None

def get_currency_narration_line():
    try:
        usd_rate = get_forex_rate()
        gold_price = get_gold_price(usd_rate)
        return f"The US dollar is trading at {usd_rate:.2f} pesos today, and 24-karat gold is at {gold_price:,.0f} pesos per gram."
    except Exception as e:
        print(f"  [reel filler] currency line failed: {e}")
        return None

def get_fuel_narration_line():
    """Monday-only fuel update line, reusing the existing fuel state
    without re-scanning feeds if a status was already found this run."""
    try:
        status = get_fuel_status()
        if not status:
            return None
        if status.get("mode") == "specific":
            estimates = status["estimates"]
            parts = []
            for fuel_name in ["Diesel", "Gasoline", "Kerosene"]:
                if fuel_name not in estimates:
                    continue
                data = estimates[fuel_name]
                if data.get("single", False):
                    direction_word = "down" if data["direction"] == "down" else "up"
                    amount = data["down"] if data["direction"] == "down" else data["up"]
                    parts.append(f"{fuel_name} {direction_word} by {amount:.2f} pesos")
                else:
                    parts.append(f"{fuel_name} up to {data['up']:.2f} or down to {data['down']:.2f} pesos")
            if not parts:
                return None
            return "This week's fuel price watch: " + ", ".join(parts) + " per liter."
        else:
            direction = status.get("direction", "unknown")
            style = FUEL_STYLE.get(direction, FUEL_STYLE["unknown"])
            return f"Fuel price watch: {style['badge'].lower()} this week, according to the latest DOE advisory."
    except Exception as e:
        print(f"  [reel filler] fuel line failed: {e}")
        return None

def headline_to_sentence(article):
    title = article["title"].strip()
    if not title.endswith((".", "!", "?")):
        title += "."
    return title

def build_reel_road_narration_line():
    """One consolidated, spoken-friendly road-status line, reusing the
    same merged data your Road Status Watch post already produces --
    instead of the reel treating each raw road article as its own
    headline (which caused near-duplicate lines pulled from separate
    articles about the same closure)."""
    try:
        status = get_road_status()
        if not status or not status.get("statuses"):
            return None

        statuses = status["statuses"]
        closed_roads = [r for r, info in statuses.items() if normalize_road_info(info)["status"] == "closed"]
        one_lane_roads = [r for r, info in statuses.items() if normalize_road_info(info)["status"] == "one_lane"]

        if closed_roads:
            named = closed_roads[:2]
            names = " and ".join(named) if len(named) <= 2 else ", ".join(named)
            remainder = len(closed_roads) - len(named)
            extra = f", plus {remainder} other road{'s' if remainder != 1 else ''}" if remainder > 0 else ""
            verb = "remain" if len(named) > 1 or remainder > 0 else "remains"
            return f"Road watch: {names}{extra} {verb} closed or not passable due to continued rains."
        elif one_lane_roads:
            named = one_lane_roads[:2]
            names = " and ".join(named) if len(named) <= 2 else ", ".join(named)
            verb = "are" if len(named) > 1 else "is"
            return f"Road watch: {names} {verb} open but limited to one-lane traffic."
        else:
            return "Road watch: all tracked roads across Benguet remain passable today."
    except Exception as e:
        print(f"  [reel filler] road line failed: {e}")
        return None

REEL_INTRO_LINE = "Here's what's happening today."
REEL_OUTRO_LINE = "That's your update for today. Stay safe, and till next time."

REEL_WORDS_PER_SECOND = 2.5
REEL_TARGET_MAX_SECONDS = 85  # buffer under Facebook's 90s Reels hard cap
REEL_WORD_BUDGET = round(REEL_TARGET_MAX_SECONDS * REEL_WORDS_PER_SECOND)  # ~212 words

def build_reel_script(max_items=8):
    """Builds the full narration script draft: intro, road watch line,
    Monday fuel line if applicable, headlines with rotating connector
    phrases for natural pacing (with weather/currency filler on slow
    days), outro. Headline count is driven by a ~85s time budget, not a
    fixed count -- on a heavy news day, extra headlines simply don't
    make the cut rather than forcing everything into 90 seconds.
    Returns (lines, headlines_used, headlines_available, est_seconds)
    where lines is an ordered list of {"text": str, "image_url": str_or_None}
    dicts -- image_url is the source article's photo for headline lines
    (used for the black/white/red visual treatment), and None for
    structural lines (intro, road watch, fuel, weather, currency, outro),
    which fall back to a styled branded background. Does NOT send to
    Telegram or run voice/video."""
    candidates = build_reel_headline_pool(max_items=max_items, sports_slots=1)

    fixed_lines = [{"text": REEL_INTRO_LINE, "image_url": None, "category": "intro"}]

    road_line = build_reel_road_narration_line()
    if road_line:
        fixed_lines.append({"text": road_line, "image_url": None, "category": "road"})

    if is_monday():
        fuel_line = get_fuel_narration_line()
        if fuel_line:
            fixed_lines.append({"text": fuel_line, "image_url": None, "category": "fuel"})

    # Slow day: pad with weather + currency so the reel isn't thin,
    # per Joel's instruction to fill with local weather/currency/gold
    # when there aren't enough genuine headlines.
    if len(candidates) < 3:
        weather_line = get_weather_narration_line()
        if weather_line:
            fixed_lines.append({"text": weather_line, "image_url": None, "category": "weather"})
        currency_line = get_currency_narration_line()
        if currency_line:
            fixed_lines.append({"text": currency_line, "image_url": None, "category": "currency"})

    def word_count(line_dicts):
        return sum(len(d["text"].split()) for d in line_dicts)

    outro_words = len(REEL_OUTRO_LINE.split())
    headline_lines = []
    connector_i = 0

    for i, article in enumerate(candidates):
        sentence = headline_to_sentence(article)
        if i == 0:
            text = sentence
        else:
            text = CONNECTORS[connector_i % len(CONNECTORS)] + sentence
            connector_i += 1

        projected = word_count(fixed_lines) + word_count(headline_lines) + len(text.split()) + outro_words
        if projected > REEL_WORD_BUDGET and len(headline_lines) > 0:
            # Budget reached -- stop here rather than cramming the rest in.
            break
        category = "sports" if is_sports_article(article) else "news"
        image_url = article.get("image_url")
        if not image_url and article.get("link"):
            image_url = fetch_og_image(article["link"])
        headline_lines.append({"text": text, "image_url": image_url, "category": category})

    all_lines = fixed_lines + headline_lines + [{"text": REEL_OUTRO_LINE, "image_url": None, "category": "outro"}]
    script_text = " ".join(d["text"] for d in all_lines)
    est_seconds = round(len(script_text.split()) / REEL_WORDS_PER_SECOND)

    return all_lines, len(headline_lines), len(candidates), est_seconds

def build_reel_script_text(max_items=8):
    """Convenience wrapper for callers that just want the joined script
    text (e.g. the Telegram review message) without the per-line list."""
    all_lines, headlines_used, headlines_available, est_seconds = build_reel_script(max_items=max_items)
    script_text = " ".join(d["text"] for d in all_lines)
    return script_text, headlines_used, headlines_available, est_seconds

# ---------- Reel Visual Frames (place-aware backgrounds + burned-in captions) ----------

REEL_WIDTH = 1080
REEL_HEIGHT = 1920

REEL_BRANDED_BG_PROMPT = "misty Benguet mountain highland landscape at golden hour, cinematic aerial view, minimalist"

def detect_place_in_reel_line(line):
    """Checks a script line against known municipality and tracked-road
    names so the background can be tied to the actual place mentioned,
    instead of always using the generic branded background."""
    text = line.lower()
    for city in CITIES:
        if city.lower() in text:
            return city
    for road in TRACKED_ROADS:
        if road.lower() in text:
            return road
    return None

def reel_background_prompt_for_line(line):
    place = detect_place_in_reel_line(line)
    if place:
        return f"aerial cinematic view of {place}, Benguet Philippines, misty mountains, golden hour lighting, minimalist"
    return REEL_BRANDED_BG_PROMPT

REEL_DUOTONE_BLACK = "#0a0a0a"
REEL_DUOTONE_WHITE = "#f5f0e8"
REEL_DUOTONE_RED = "#c9302c"
REEL_ACCENT_YELLOW = "#e8b923"

def fetch_og_image(article_url):
    """Fallback for when the RSS feed itself doesn't include a photo:
    fetches the actual article page and pulls its og:image meta tag,
    which is the same image most sites show when the link is shared."""
    if not article_url:
        return None
    try:
        response = requests.get(article_url, headers=FEED_HEADERS, timeout=10)
        response.raise_for_status()
        html_text = response.text
        match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html_text, re.IGNORECASE)
        if not match:
            match = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html_text, re.IGNORECASE)
        if match:
            return match.group(1)
    except Exception as e:
        print(f"  [reel frame] og:image fetch failed for {article_url}: {e}")
    return None

def fetch_image_from_url(url):
    try:
        response = requests.get(url, headers=FEED_HEADERS, timeout=15)
        response.raise_for_status()
        img = Image.open(BytesIO(response.content)).convert("RGB")
        return img
    except Exception as e:
        print(f"  [reel frame] could not fetch article image {url}: {e}")
        return None

def apply_bw_treatment(img, target_width=None, target_height=None):
    """True black-and-white treatment: cover-fit crop to the frame size,
    then grayscale -- no color tint, so caption text (yellow) is what
    carries the accent color instead of the photo itself."""
    target_width = target_width or REEL_WIDTH
    target_height = target_height or REEL_HEIGHT

    img_ratio = img.width / img.height
    target_ratio = target_width / target_height
    if img_ratio > target_ratio:
        new_height = target_height
        new_width = max(target_width, int(img_ratio * new_height))
    else:
        new_width = target_width
        new_height = max(target_height, int(new_width / img_ratio))
    img_resized = img.resize((new_width, new_height))

    left = (new_width - target_width) // 2
    top = (new_height - target_height) // 2
    img_cropped = img_resized.crop((left, top, left + target_width, top + target_height))

    grayscale = img_cropped.convert("L")
    return grayscale.convert("RGB")

REEL_CATEGORY_TAGS = {
    "road": ("ROAD WATCH", REEL_DUOTONE_RED),
    "news": ("BREAKING", REEL_DUOTONE_RED),
    "fuel": ("FUEL WATCH", REEL_ACCENT_YELLOW),
    "weather": ("WEATHER", REEL_ACCENT_YELLOW),
    "currency": ("MARKET WATCH", REEL_ACCENT_YELLOW),
    "sports": ("SPORTS", REEL_ACCENT_YELLOW),
}

def build_reel_frame_html(line_text, bg_data_uri, tag_label=None, tag_color=None):
    """Vertical (1080x1920) frame: background image, dark gradient for
    caption readability, burned-in caption text lower-third, and an
    optional category tag pill (red = urgent, yellow = advisory)."""
    tag_html = ""
    if tag_label:
        tag_html = f'<div class="tag" style="background:{tag_color};">{tag_label}</div>'

    html_out = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Archivo+Black&family=Archivo:wght@400;600;700;800&display=swap');
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:{REEL_WIDTH}px; height:{REEL_HEIGHT}px; position:relative; font-family:'Archivo',sans-serif; background:#0a0a0a; }}

  .bg {{
    position:absolute; inset:0;
    background-image:url('{bg_data_uri}'); background-size:cover; background-position:center;
  }}
  .overlay {{
    position:absolute; inset:0;
    background: linear-gradient(180deg, rgba(10,10,10,0.20) 0%, rgba(10,10,10,0.25) 50%, rgba(10,10,10,0.88) 100%);
  }}

  .brandbar {{
    position:absolute; top:70px; left:60px; color:{REEL_DUOTONE_RED}; font-size:26px;
    font-weight:800; letter-spacing:3px; text-shadow: 0 2px 10px rgba(0,0,0,0.6);
  }}

  .tag {{
    position:absolute; top:64px; right:60px; color:#0a0a0a; font-weight:800; font-size:22px;
    letter-spacing:2px; padding:12px 22px; border-radius:6px;
  }}

  .caption {{
    position:absolute; left:60px; right:60px; bottom:180px;
    color:{REEL_ACCENT_YELLOW}; font-family:'Archivo Black',sans-serif; font-size:58px; line-height:1.28;
    text-shadow: 0 4px 24px rgba(0,0,0,0.8);
  }}
</style>
</head>
<body>
  <div class="bg"></div>
  <div class="overlay"></div>
  <div class="brandbar">BENGUET DAILY UPDATE</div>
  {tag_html}
  <div class="caption">{line_text}</div>
</body>
</html>"""
    return html_out

def generate_reel_frame_image(line_text, image_url=None, category=None):
    """Generates one vertical frame (PNG bytes buffer) for a single
    script line. If image_url is given (the source article's own photo),
    fetches and applies a true black-and-white treatment. Otherwise
    falls back to a place-aware or branded AI-generated background, with
    the same black-and-white treatment applied for visual consistency
    across the whole reel. category (if provided) adds a red/yellow tag
    pill -- red for urgent content (road, breaking news), yellow for
    advisory content (fuel, weather, market, sports). Caption text is
    yellow, which is where the accent color now lives."""
    bw_img = None

    if image_url:
        fetched = fetch_image_from_url(image_url)
        if fetched:
            bw_img = apply_bw_treatment(fetched)

    if bw_img is None:
        prompt = reel_background_prompt_for_line(line_text)
        try:
            bg_img = generate_background(prompt, height=REEL_HEIGHT)
            bw_img = apply_bw_treatment(bg_img)
        except Exception as e:
            print(f"  [reel frame] background generation failed for '{line_text[:40]}': {e}")
            bw_img = None

    bg_data_uri = image_to_data_uri(bw_img) if bw_img is not None else ""

    tag_label, tag_color = REEL_CATEGORY_TAGS.get(category, (None, None))
    html_out = build_reel_frame_html(line_text, bg_data_uri, tag_label=tag_label, tag_color=tag_color)
    buffer = render_html_to_png(html_out, width=REEL_WIDTH, height=REEL_HEIGHT)
    return buffer

if __name__ == "__main__":
    seed_fuel_state_if_empty()

    try:
        weather_img, weather_caption = build_weather_image()
        send_photo_for_approval(weather_img, "weather", filename="update.png", mime="image/png", caption=weather_caption)
        print("Sent weather post")
    except Exception as e:
        print(f"  [ERROR] weather post failed, skipping: {e}")
    time.sleep(2)

    try:
        currency_img, currency_caption = build_currency_gold_image()
        send_photo_for_approval(currency_img, "currency", filename="update.png", mime="image/png", caption=currency_caption)
        print("Sent currency/gold post")
    except Exception as e:
        print(f"  [ERROR] currency/gold post failed, skipping: {e}")
    time.sleep(2)

    try:
        news_img, news_caption = build_news_image()
        send_photo_for_approval(news_img, "news", filename="update.png", mime="image/png", caption=news_caption)
        print("Sent news post")
    except Exception as e:
        print(f"  [ERROR] news post failed, skipping: {e}")
    time.sleep(2)

    try:
        fuel_img, fuel_caption = build_fuel_image()
        send_photo_for_approval(fuel_img, "fuel", filename="update.png", mime="image/png", caption=fuel_caption)
        print("Sent fuel price watch post")
    except Exception as e:
        print(f"  [ERROR] fuel post failed, skipping: {e}")
    time.sleep(2)

    try:
        road_img, road_caption = build_road_image()
        send_photo_for_approval(road_img, "road", filename="update.png", mime="image/png", caption=road_caption)
        print("Sent road status post")
    except Exception as e:
        print(f"  [ERROR] road post failed, skipping: {e}")
