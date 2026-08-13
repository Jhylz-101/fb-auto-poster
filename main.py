import requests
import time
import json
import random
import re
import os
import html as html_lib
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw, ImageFont
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
    "Inquirer": "https://www.inquirer.net/fullfeed",
    "PhilStar": "https://www.philstar.com/rss/headlines",
    "PNA": "https://syndication.pna.gov.ph/rss",
    "NorDis": "https://nordis.net/feed/",
    "GMA News": "https://data.gmanews.tv/gno/rss/news/feed.xml"
}

CONNECTORS = ["Meanwhile, ", "In other news, ", "Elsewhere, ", "Also making headlines: "]

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
    data = requests.get(url).json()
    return data["conversion_rates"]["PHP"]

def get_gold_price():
    url = "https://www.goldapi.io/api/XAU/PHP"
    headers = {"x-access-token": GOLD_API_KEY}
    data = requests.get(url, headers=headers).json()
    return data["price_gram_24k"]

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
        root = ET.fromstring(response.content)
        items = root.findall(".//item")[:limit]
        articles = []
        for position, item in enumerate(items):
            title_el = item.find("title")
            desc_el = item.find("description")
            link_el = item.find("link")
            title = title_el.text.strip() if title_el is not None and title_el.text else None
            desc_raw = desc_el.text.strip() if desc_el is not None and desc_el.text else ""
            desc = re.sub(r"<[^>]+>", "", desc_raw)
            desc = html_lib.unescape(desc).strip()
            link = link_el.text.strip() if link_el is not None and link_el.text else ""
            if title:
                articles.append({"title": title.strip(), "description": desc, "link": link, "position": position})
        return articles
    except Exception as e:
        print(f"  [feed error] {feed_url} -> {type(e).__name__}: {e}")
        return []

def is_local_article(article):
    text = (article["title"] + " " + article["description"]).lower()
    return any(keyword in text for keyword in LOCAL_KEYWORDS)

EXCLUDE_UNLESS_LOCAL = [
    "walang pasok", "class suspension", "suspension of classes",
    "no classes", "classes suspended"
]

def is_excluded_article(article):
    text = (article["title"] + " " + article["description"]).lower()
    matches_exclude = any(keyword in text for keyword in EXCLUDE_UNLESS_LOCAL)
    return matches_exclude and not is_local_article(article)

SOURCE_PRIORITY = ["Inquirer", "PhilStar", "GMA News", "NorDis", "PNA", "Rappler"]

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

def generate_background(prompt, height=1080):
    url = f"https://image.pollinations.ai/prompt/{prompt}?width=1080&height={height}"
    response = requests.get(url)
    img = Image.open(BytesIO(response.content)).convert("RGB")
    return img

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
  body {{ width:1080px; height:1350px; font-family:'Archivo',sans-serif; position:relative; overflow:hidden; background:#1c2b33; }}

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

  .content {{ position:relative; z-index:2; padding:56px 76px 46px; height:100%; display:flex; flex-direction:column; }}

  .eyebrow {{ color:#8fb8d4; font-size:20px; letter-spacing:6px; font-weight:600; text-transform:uppercase; }}
  .title {{ font-family:'Archivo Black',sans-serif; color:#fdfdfb; font-size:60px; line-height:1.02; margin-top:12px; text-transform:uppercase; }}
  .date {{ color:#c9dcea; font-size:22px; margin-top:14px; font-weight:500; }}

  .alertbar {{
    margin-top:32px; background:#e8a33d; color:#241a05; border-radius:14px;
    padding:18px 28px; display:flex; align-items:center; gap:16px;
  }}
  .alertbar .dot {{ width:14px; height:14px; border-radius:50%; background:#241a05; flex-shrink:0; }}
  .alertbar .txt {{ font-size:23px; font-weight:700; line-height:1.25; }}

  .body {{ margin-top:28px; background:rgba(12,22,28,0.55); border:1px solid rgba(255,255,255,0.12); border-radius:18px; padding:34px 38px; backdrop-filter: blur(2px); }}
  .body p {{ color:#eef4f8; font-size:24px; line-height:1.48; font-weight:400; }}
  .body p + p {{ margin-top:18px; }}
  .body b {{ color:#ffd98a; font-weight:700; }}

  .towns {{ margin-top:28px; display:grid; grid-template-columns:1fr 1fr; gap:16px 30px; }}
  .town {{ color:#eef4f8; font-size:27px; font-weight:600; display:flex; align-items:center; gap:10px; }}
  .town::before {{ content:''; width:9px; height:9px; border-radius:50%; background:#5b9bd5; flex-shrink:0; }}

  .footer {{ margin-top:auto; display:flex; justify-content:space-between; align-items:flex-end; padding-top:26px; }}
  .brand {{ color:#7fa6bd; font-size:20px; font-weight:700; letter-spacing:2px; }}
  .advice {{ color:#ffd98a; font-size:19px; font-weight:600; text-align:right; max-width:460px; line-height:1.4; }}
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
    buffer = render_html_to_png(html)
    caption = build_weather_caption(para1, para2)
    return buffer, caption

# ---------- Currency & Gold (HTML/Playwright card design) ----------

def build_currency_gold_html():
    usd_rate = get_forex_rate()
    gold_price = get_gold_price()
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
  body {{ width:1080px; height:1350px; font-family:'Archivo',sans-serif; background:#122019; position:relative; overflow:hidden; }}

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

  .content {{ position:relative; z-index:2; padding:76px; height:100%; display:flex; flex-direction:column; justify-content:center; }}

  .eyebrow {{ color:#c9a94f; font-size:22px; letter-spacing:6px; font-weight:600; text-transform:uppercase; }}
  .title {{ font-family:'Fraunces',serif; font-weight:900; color:#f7f2e3; font-size:66px; line-height:1.05; margin-top:14px; }}
  .date {{ color:#a9c2b3; font-size:24px; margin-top:14px; font-weight:500; }}

  .cards {{ margin-top:56px; display:flex; flex-direction:column; gap:28px; }}
  .card {{
    background:rgba(247,242,227,0.04); border:1px solid rgba(212,175,55,0.35);
    border-radius:22px; padding:40px 42px; display:flex; justify-content:space-between; align-items:center;
  }}
  .card .label {{ color:#cfead9; font-size:26px; font-weight:600; letter-spacing:1px; }}
  .card .sub {{ color:#8fae9d; font-size:19px; margin-top:8px; }}
  .card .valuewrap {{ text-align:right; }}
  .card .value {{ font-family:'Fraunces',serif; font-weight:700; color:#e9c25f; font-size:52px; }}
  .trendbadge {{
    display:inline-flex; align-items:center; gap:8px; margin-top:14px;
    padding:8px 16px; border-radius:20px; font-size:16px; font-weight:800; letter-spacing:0.5px;
  }}
  .trendbadge .arrow {{ font-size:18px; }}

  .note {{ margin-top:40px; color:#a9c2b3; font-size:22px; line-height:1.5; }}
  .note b {{ color:#e9c25f; }}

  .footer {{ margin-top:60px; display:flex; justify-content:space-between; align-items:flex-end; }}
  .brand {{ color:#7d9689; font-size:22px; font-weight:700; letter-spacing:2px; }}
  .tag {{ color:#e9c25f; font-size:20px; font-weight:600; }}
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
    buffer = render_html_to_png(html_out)
    caption = build_currency_gold_caption(usd_rate, gold_price, usd_trend, gold_trend)
    save_current_prices(usd_rate, gold_price)
    return buffer, caption

# ---------- Fuel Price Watch (specific per-liter estimates from DOE weekly advisory coverage) ----------

FUEL_UP_WORDS = ["increase", "increases", "hike", "hikes", "rise", "rises", "up by", "climb", "climbs", "higher", "surge"]
FUEL_DOWN_WORDS = ["decrease", "decreases", "rollback", "rollbacks", "cut", "cuts", "down by", "drop", "drops", "decline", "lower", "reduction"]
FUEL_MIXED_WORDS = ["either", "may rise or fall", "may go up or down", "may increase or decrease"]

def is_fuel_article(article):
    text = (article["title"] + " " + article["description"]).lower()

    # Catch general fuel-price coverage (Inquirer, GMA, Rappler, PhilStar), not
    # just formal DOE advisory wording — DOE itself isn't always named.
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
    "GMA News": "https://data.gmanews.tv/gno/rss/news/feed.xml"
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

# Matches recurring "range" format, e.g.:
# "Diesel - may either go up by P0.84 or go down by P1.16 per liter"
FUEL_RANGE_PATTERN = re.compile(
    r"(Diesel|Gasoline|Kerosene)\s*[-–:]\s*may\s*(?:either\s*)?go\s*up\s*by\s*[₱P]?([\d.]+)\s*(?:per\s*liter\s*)?or\s*go\s*down\s*by\s*[₱P]?([\d.]+)\s*per\s*liter",
    re.IGNORECASE
)

# Matches single-direction phrasing used by other outlets, e.g.:
# "Diesel prices are set to rise by more than P2 per liter this week"
# "gasoline prices may either increase or roll back by up to P1 per liter"
# "gasoline prices will be slashed by ₱4.70 per liter"
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
    """Scan all fuel-related sources this week and merge whatever specific
    per-liter figures we can find. Tries the fast RSS snippet first; only
    fetches the full article page (slower) as a last resort, and only up
    to a small number of times so this can't run away and hang."""
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

        for article in articles:
            if not is_fuel_article_strong(article):
                continue

            # Try the fast RSS description first — no extra network call
            estimates = parse_specific_fuel_estimates(article["description"])

            # Only fetch the full page if the snippet didn't have enough,
            # and only up to our fetch budget for this run
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

def get_fuel_status():
    """Combines fresh scanning with persisted state: if this run finds a
    genuinely new article (different link than what's stored), it becomes
    the new current status and the old one is kept as previous. If nothing
    new is found, we keep showing the last known status instead of an
    empty 'no forecast yet' card."""
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
        return state["current"]

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
        return state["current"]

    if stored_current:
        print(f"  [fuel state] no new update this run, reusing status from {stored_current.get('found_date', 'earlier')}")
        return stored_current

    print("  [fuel state] no data found this run and nothing stored previously")
    return None

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

def build_fuel_html():
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
  body {{ width:1080px; height:1350px; font-family:'Archivo',sans-serif; background:#171310; position:relative; overflow:hidden; }}

  .bg {{
    position:absolute; inset:0;
    background: linear-gradient(160deg, #14100d 0%, #1e1712 60%, #241b14 100%);
  }}

  .content {{ position:relative; z-index:2; padding:70px; height:100%; display:flex; flex-direction:column; justify-content:center; }}

  .eyebrow {{ color:#c9a15a; font-size:20px; letter-spacing:6px; font-weight:600; text-transform:uppercase; }}
  .title {{ font-family:'Archivo Black',sans-serif; color:#f7f2e3; font-size:52px; line-height:1.05; margin-top:14px; }}
  .date {{ color:#a9a09c; font-size:22px; margin-top:14px; font-weight:500; }}
  .subhead {{ color:#d8d2c6; font-size:22px; margin-top:24px; }}

  .rows {{ margin-top:36px; display:flex; flex-direction:column; gap:22px; }}
  .row {{
    display:flex; align-items:center; gap:20px; background:rgba(247,242,227,0.04);
    border:1px solid rgba(247,242,227,0.14); border-radius:18px; padding:26px 30px;
  }}
  .rowlabel {{
    color:#171310; font-weight:800; font-size:24px; padding:14px 22px; border-radius:10px;
    min-width:170px; text-align:center;
  }}
  .rowvalues {{ flex:1; display:flex; flex-direction:column; gap:6px; }}
  .rangeline {{ font-size:24px; font-weight:700; }}
  .up {{ color:#e05252; }}
  .down {{ color:#4caf50; }}
  .rowarrow {{ font-size:44px; font-weight:800; }}

  .note {{ margin-top:34px; color:#a9a09c; font-size:19px; line-height:1.5; }}

  .footer {{ margin-top:auto; padding-top:40px; display:flex; justify-content:space-between; align-items:flex-end; }}
  .brand {{ color:#8a8078; font-size:20px; font-weight:700; letter-spacing:2px; }}
  .tag {{ color:#c9a15a; font-size:18px; font-weight:600; }}
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

    # Qualitative fallback (no specific numbers available for this status)
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
  body {{ width:1080px; height:1350px; font-family:'Archivo',sans-serif; background:#171310; position:relative; overflow:hidden; }}

  .bg {{
    position:absolute; inset:0;
    background:
      radial-gradient(circle at 85% 10%, {style["color"]}22, transparent 45%),
      linear-gradient(160deg, #14100d 0%, #1e1712 60%, #241b14 100%);
  }}

  .content {{ position:relative; z-index:2; padding:76px; height:100%; display:flex; flex-direction:column; justify-content:center; }}

  .eyebrow {{ color:#c9a15a; font-size:22px; letter-spacing:6px; font-weight:600; text-transform:uppercase; }}
  .title {{ font-family:'Archivo Black',sans-serif; color:#f7f2e3; font-size:58px; line-height:1.05; margin-top:14px; }}
  .date {{ color:#a9a09c; font-size:24px; margin-top:14px; font-weight:500; }}

  .badge {{
    margin-top:44px; align-self:flex-start;
    background:{style["color"]}; color:#171310; font-weight:800; font-size:24px; letter-spacing:2px;
    padding:14px 28px; border-radius:8px; display:flex; align-items:center; gap:12px;
  }}
  .badge .arrow {{ font-size:26px; }}

  .headline {{ margin-top:40px; color:#f0ece5; font-size:32px; line-height:1.4; font-weight:600; }}

  .advice {{
    margin-top:36px; background:rgba(247,242,227,0.05); border:1px solid {style["color"]}55;
    border-radius:18px; padding:34px 38px; color:#d8d2c6; font-size:24px; line-height:1.55;
  }}
  .advice b {{ color:{style["color"]}; }}

  .footer {{ margin-top:60px; display:flex; justify-content:space-between; align-items:flex-end; }}
  .brand {{ color:#8a8078; font-size:22px; font-weight:700; letter-spacing:2px; }}
  .tag {{ color:{style["color"]}; font-size:20px; font-weight:600; }}
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
    buffer = render_html_to_png(html_out)
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

def compute_news_layout(title, description_len, rest_count):
    """Scale down font sizes/spacing as content grows, so everything fits
    the fixed 1080x1350 canvas without overflowing."""
    scale = 1.0

    title_len = len(title)
    if title_len > 100:
        scale -= 0.14
    elif title_len > 70:
        scale -= 0.07

    if description_len > 320:
        scale -= 0.12
    elif description_len > 220:
        scale -= 0.06

    if rest_count >= 4:
        scale -= 0.10
    elif rest_count == 3:
        scale -= 0.05
    elif rest_count == 2:
        scale -= 0.02

    scale = max(0.70, min(1.0, scale))

    return {
        "scale": scale,
        "headline_size": round(52 * scale),
        "lede_size": round(25 * scale),
        "lede_max_len": round(340 * (1.0 if rest_count == 0 else max(0.55, 1.0 - rest_count * 0.12))),
        "item_text_size": round(19 * scale),
        "item_src_size": round(15 * scale),
        "also_label_size": round(16 * scale),
        "badge_size": round(22 * scale),
        "date_size": round(20 * scale),
        "brand_size": round(22 * scale),
        "footer_size": round(18 * scale),
        "topbar_pad": round(44 * scale),
        "badge_margin": round(32 * scale),
        "headline_pad": round(24 * scale),
        "rule_margin": round(32 * scale),
        "lede_pad": round(30 * scale),
        "also_margin": round(36 * scale),
        "also_pad": round(28 * scale),
        "item_gap": round(14 * scale),
        "footer_pad": round(32 * scale),
    }

def build_news_html(articles):
    today = datetime.now().strftime("%B %d, %Y")

    if not articles:
        top = {"source": "", "title": "No headlines available today", "description": "", "link": ""}
        rest = []
    else:
        top = articles[0]
        rest = articles[1:5]

    layout = compute_news_layout(top["title"], len(top["description"]), len(rest))
    lede_text = truncate_text(top["description"], max_len=layout["lede_max_len"]) if top["description"] else "Full details available from the source below."

    rest_html = ""
    for a in rest:
        rest_html += f'      <div class="item"><span class="dot"></span><span class="itext">{a["title"]}</span><span class="src">{a["source"]}</span></div>\n'

    rest_section = ""
    if rest_html:
        rest_section = f"""
    <div class="also">
      <div class="also-label">Also in the news</div>
{rest_html}    </div>"""

    source_label = top["source"] if top["source"] else "Wire"
    badge_label = "Local News" if top.get("link") and is_local_article(top) else "Top Story"

    html_out = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Archivo+Black&family=Archivo:wght@400;500;600;700;800&display=swap');
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:1080px; height:1350px; font-family:'Archivo',sans-serif; background:#141414; position:relative; overflow:hidden; }}

  .bg {{ position:absolute; inset:0; background: linear-gradient(180deg, #0d0d0d 0%, #1a1414 55%, #241412 100%); }}
  .texture {{ position:absolute; inset:0; opacity:0.06; background-image: repeating-linear-gradient(0deg, #fff 0 1px, transparent 1px 3px); }}

  .content {{ position:relative; z-index:2; height:100%; display:flex; flex-direction:column; }}

  .topbar {{ display:flex; justify-content:space-between; align-items:center; padding:{layout["topbar_pad"]}px 70px 0; }}
  .brand {{ color:#b02e26; font-size:{layout["brand_size"]}px; font-weight:800; letter-spacing:3px; }}
  .date {{ color:#9a9a9a; font-size:{layout["date_size"]}px; font-weight:500; }}

  .badge {{
    margin:{layout["badge_margin"]}px 70px 0; align-self:flex-start;
    background:#b02e26; color:#fff; font-weight:800; font-size:{layout["badge_size"]}px; letter-spacing:3px;
    padding:11px 24px; text-transform:uppercase;
  }}

  .headline {{
    font-family:'Archivo Black',sans-serif; color:#f7f4ee; font-size:{layout["headline_size"]}px; line-height:1.1;
    padding:{layout["headline_pad"]}px 70px 0; text-transform:none;
  }}

  .rule {{ height:2px; background:#3a3a3a; margin:{layout["rule_margin"]}px 70px 0; }}

  .lede {{ color:#e3ded3; font-size:{layout["lede_size"]}px; line-height:1.5; padding:{layout["lede_pad"]}px 70px 0; font-weight:400; }}

  .also {{ margin:{layout["also_margin"]}px 70px 0; border-top:1px solid #3a3a3a; padding-top:{layout["also_pad"]}px; }}
  .also-label {{ color:#8a8a8a; font-size:{layout["also_label_size"]}px; font-weight:700; letter-spacing:2px; text-transform:uppercase; margin-bottom:16px; }}
  .item {{ display:flex; align-items:flex-start; gap:12px; margin-top:{layout["item_gap"]}px; }}
  .item .dot {{ width:7px; height:7px; border-radius:50%; background:#b02e26; flex-shrink:0; margin-top:9px; }}
  .item .itext {{ color:#d8d2c6; font-size:{layout["item_text_size"]}px; line-height:1.4; flex:1; }}
  .item .src {{ color:#8a8a8a; font-size:{layout["item_src_size"]}px; white-space:nowrap; margin-top:2px; }}

  .footer {{ margin-top:auto; display:flex; justify-content:space-between; align-items:center; padding:{layout["footer_pad"]}px 70px 42px; border-top:1px solid #3a3a3a; }}
  .source {{ color:#8a8a8a; font-size:{layout["footer_size"]}px; }}
  .cta {{ color:#f0a97a; font-size:{layout["footer_size"]}px; font-weight:700; }}
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

    <div class="headline">{top["title"]}</div>

    <div class="rule"></div>

    <div class="lede">{lede_text}</div>
{rest_section}

    <div class="footer">
      <div class="source">Source: {source_label}</div>
      <div class="cta">Full story via {source_label} →</div>
    </div>
  </div>
</body>
</html>"""
    return html_out

def build_news_caption(articles):
    if not articles:
        return "No headlines available today."

    top = articles[0]
    rest = articles[1:5]

    lines = [f"📰 {top['title']}"]
    if top.get("link"):
        lines.append(top["link"])

    if rest:
        lines.append("")
        lines.append("Also:")
        for a in rest:
            lines.append(f"• {a['title']}")
            if a.get("link"):
                lines.append(a["link"])

    caption = "\n".join(lines)
    return caption[:1024]

def build_news_image():
    articles = gather_news()
    html_out = build_news_html(articles)
    buffer = render_html_to_png(html_out)
    caption = build_news_caption(articles)
    return buffer, caption

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

def seed_fuel_state_if_empty():
    """One-time bootstrap: if no fuel state exists yet, seed it with real,
    manually-verified numbers so the system has something to compare
    against instead of starting from zero. Safe to leave in permanently —
    it only writes if the file doesn't already exist."""
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

if __name__ == "__main__":
    seed_fuel_state_if_empty()

    weather_img, weather_caption = build_weather_image()
    send_photo_for_approval(weather_img, "weather", filename="update.png", mime="image/png", caption=weather_caption)
    print("Sent weather post")
    time.sleep(2)

    currency_img, currency_caption = build_currency_gold_image()
    send_photo_for_approval(currency_img, "currency", filename="update.png", mime="image/png", caption=currency_caption)
    print("Sent currency/gold post")
    time.sleep(2)

    news_img, news_caption = build_news_image()
    send_photo_for_approval(news_img, "news", filename="update.png", mime="image/png", caption=news_caption)
    print("Sent news post")
    time.sleep(2)

    fuel_img, fuel_caption = build_fuel_image()
    send_photo_for_approval(fuel_img, "fuel", filename="update.png", mime="image/png", caption=fuel_caption)
    print("Sent fuel price watch post")
