import requests
import time
import json
import random
import re
import os
import base64
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
    "Inquirer": "https://newsinfo.inquirer.net/feed",
    "PhilStar": "https://www.philstar.com/rss/nation",
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
    response = requests.get(url)
    data = response.json()
    if "conversion_rates" not in data:
        print(f"  [forex error] unexpected response: {data}")
        raise RuntimeError(f"ExchangeRate-API did not return conversion_rates: {data}")
    return data["conversion_rates"]["PHP"]

def get_gold_price():
    url = "https://www.goldapi.io/api/XAU/PHP"
    headers = {"x-access-token": GOLD_API_KEY}
    response = requests.get(url, headers=headers)
    data = response.json()
    if "price_gram_24k" not in data:
        print(f"  [gold error] unexpected response (status {response.status_code}): {data}")
        raise RuntimeError(f"GoldAPI did not return price_gram_24k: {data}")
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

ENTERTAINMENT_KEYWORDS = [
    "kpop", "k-pop", "bts", "blackpink", "showbiz", "celebrity", "actress",
    "actor ", "album", "music video", "concert", "artista", "teleserye",
    "movie premiere", "red carpet", "boy group", "girl group", "idol group",
    "gma network star", "abs-cbn star", "kapamilya", "kapuso star"
]

def is_entertainment_article(article):
    text = (article["title"] + " " + article["description"]).lower()
    return any(keyword in text for keyword in ENTERTAINMENT_KEYWORDS)

def is_excluded_article(article):
    text = (article["title"] + " " + article["description"]).lower()
    matches_exclude = any(keyword in text for keyword in EXCLUDE_UNLESS_LOCAL)
    matches_entertainment = is_entertainment_article(article)
    return (matches_exclude or matches_entertainment) and not is_local_article(article)

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

def compute_news_layout(articles):
    """Sizes tuned for showing up to 3 equally-weighted headlines that
    fill the full 1080x1350 canvas with readable text throughout."""
    count = max(len(articles), 1)
    total_len = sum(len(a["title"]) + len(a.get("description", "")) for a in articles) if articles else 0
    avg_len = total_len / count

    scale = 1.0
    if avg_len > 220:
        scale -= 0.10
    elif avg_len > 150:
        scale -= 0.05

    scale = max(0.78, min(1.0, scale))

    return {
        "scale": scale,
        "title_size": round(44 * scale),
        "date_size": round(20 * scale),
        "brand_size": round(20 * scale),
        "num_size": round(24 * scale),
        "headline_size": round(33 * scale),
        "snippet_size": round(21 * scale),
        "source_size": round(16 * scale),
        "footer_size": round(17 * scale),
        "card_pad": round(34 * scale),
        "card_gap": round(24 * scale),
        "snippet_max_len": round(170 * (1.0 if count <= 1 else max(0.65, 1.0 - (count - 1) * 0.12))),
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
  body {{ width:1080px; height:1350px; font-family:'Archivo',sans-serif; background:#141414; position:relative; overflow:hidden; }}

  .bg {{ position:absolute; inset:0; background: linear-gradient(180deg, #0d0d0d 0%, #1a1414 55%, #241412 100%); }}
  .texture {{ position:absolute; inset:0; opacity:0.06; background-image: repeating-linear-gradient(0deg, #fff 0 1px, transparent 1px 3px); }}

  .content {{ position:relative; z-index:2; height:100%; display:flex; flex-direction:column; padding:44px 60px 42px; }}

  .topbar {{ display:flex; justify-content:space-between; align-items:center; }}
  .brand {{ color:#b02e26; font-size:{layout["brand_size"]}px; font-weight:800; letter-spacing:3px; }}
  .date {{ color:#9a9a9a; font-size:{layout["date_size"]}px; font-weight:500; }}

  .title {{
    font-family:'Archivo Black',sans-serif; color:#f7f4ee; font-size:{layout["title_size"]}px;
    margin-top:20px; text-transform:uppercase; letter-spacing:1px;
  }}

  .cards {{ flex:1; display:flex; flex-direction:column; justify-content:space-between; gap:{layout["card_gap"]}px; margin-top:28px; }}

  .card {{
    background:rgba(247,242,227,0.04); border:1px solid #3a3a3a; border-radius:16px;
    padding:{layout["card_pad"]}px; flex:1; display:flex; flex-direction:column; justify-content:center;
  }}
  .cardtop {{ display:flex; align-items:center; gap:14px; }}
  .num {{
    background:#b02e26; color:#fff; font-weight:800; font-size:{layout["num_size"]}px;
    width:{round(layout["num_size"]*1.7)}px; height:{round(layout["num_size"]*1.7)}px; border-radius:50%;
    display:flex; align-items:center; justify-content:center; flex-shrink:0;
  }}
  .tag {{ color:#f0a97a; font-size:{layout["source_size"]}px; font-weight:700; letter-spacing:2px; }}
  .headline {{
    color:#f7f4ee; font-size:{layout["headline_size"]}px; font-weight:700; line-height:1.25;
    margin-top:14px;
  }}
  .snippet {{ color:#c9c3ba; font-size:{layout["snippet_size"]}px; line-height:1.45; margin-top:12px; }}
  .source {{ color:#7a7a7a; font-size:{layout["source_size"]}px; margin-top:14px; font-weight:600; }}

  .footer {{ margin-top:24px; display:flex; justify-content:space-between; align-items:center; padding-top:20px; border-top:1px solid #3a3a3a; }}
  .footerbrand {{ color:#8a8078; font-size:{layout["footer_size"]}px; font-weight:700; letter-spacing:2px; }}
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
    """Single-headline layout for the 15-min flash watcher — distinct from
    the 3-card daily digest, and posts immediately with no padding/filler."""
    today = datetime.now().strftime("%B %d, %Y")

    title = article["title"]
    description = article.get("description", "")
    source_label = article.get("source") or "Wire"

    snippet = truncate_text(description, max_len=280) if description else "Full details available from the source below."

    title_len = len(title)
    scale = 1.0
    if title_len > 100:
        scale = 0.82
    elif title_len > 70:
        scale = 0.90

    headline_size = round(46 * scale)
    snippet_size = round(26 * scale)

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

  .content {{ position:relative; z-index:2; height:100%; display:flex; flex-direction:column; justify-content:center; padding:80px 70px; }}

  .topbar {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:40px; }}
  .brand {{ color:#8a8078; font-size:20px; font-weight:700; letter-spacing:2px; }}
  .date {{ color:#9a9a9a; font-size:19px; }}

  .badge {{
    align-self:flex-start; background:#b02e26; color:#fff; font-weight:800; font-size:24px;
    letter-spacing:3px; padding:14px 30px; text-transform:uppercase; margin-bottom:36px;
  }}

  .headline {{
    font-family:'Archivo Black',sans-serif; color:#f7f4ee; font-size:{headline_size}px; line-height:1.15;
  }}

  .rule {{ height:2px; background:#3a3a3a; margin:40px 0; }}

  .snippet {{ color:#d8d2c6; font-size:{snippet_size}px; line-height:1.55; }}

  .footer {{ margin-top:auto; display:flex; justify-content:space-between; align-items:center; padding-top:40px; border-top:1px solid #3a3a3a; }}
  .source {{ color:#8a8a8a; font-size:19px; }}
  .cta {{ color:#f0a97a; font-size:19px; font-weight:700; }}
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

def build_news_caption(articles):
    if not articles:
        return "No headlines available today."

    top3 = articles[:3]
    lines = ["📰 Today's top stories:"]
    for i, a in enumerate(top3, start=1):
        lines.append(f"{i}. {a['title']}")
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

# ---------- Road Status Watch (Kennon/Halsema/Marcos, via BaguioCityGuide) ----------

ROAD_SOURCES = {
    "BaguioCityGuide": "https://baguiocityguide.com/feed/"
}

TRACKED_ROADS = [
    "Kennon Road", "Halsema Highway", "Marcos Highway",
    "Benguet-Nueva Vizcaya Road", "Baguio-Bontoc Road", "Naguilian Road",
    "Gov. Bado Dangwa National Road", "Baguio-Itogon Road",
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

def extract_road_statuses(text):
    results = {}
    text_lower = text.lower()
    positions = []
    for road in TRACKED_ROADS:
        idx = text_lower.find(road.lower())
        if idx != -1:
            positions.append((idx, road))
    positions.sort()

    for i, (idx, road) in enumerate(positions):
        next_idx = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        end = min(idx + 260, next_idx, len(text))
        window = text[idx:end]
        status = classify_road_status_text(window)
        if status:
            results[road] = {
                "status": status,
                "reason": extract_reason(window),
                "location": extract_location(window)
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
    """Handles both the old format (plain status string) and the new
    format (dict with status+reason), so cached data saved before this
    change doesn't break."""
    if isinstance(info, dict):
        return info
    return {"status": info, "reason": None}

def build_road_narrative(statuses):
    """Builds narrative sentences from extracted facts (road, status, reason,
    location) in our own wording — not copied from the source article."""
    if not statuses:
        return ""

    sentences = []
    for road, raw_info in statuses.items():
        info = normalize_road_info(raw_info)
        status_phrase = STATUS_PHRASES.get(info["status"], "affected by current conditions")
        reason = info.get("reason")
        location = info.get("location")

        location_phrase = f" near {location}" if location else ""
        reason_phrase = f", due to {REASON_PHRASES.get(reason, reason)}" if reason else ""

        sentences.append(f"{road} is {status_phrase}{location_phrase}{reason_phrase}.")

    return " ".join(sentences)

def find_road_article():
    for name, url in ROAD_SOURCES.items():
        articles = get_articles_from_feed(url, limit=20)
        print(f"  [road scan] {name}: {len(articles)} articles fetched")
        for article in articles:
            if is_road_article(article):
                article["source"] = name
                return article
    return None

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

    article = find_road_article()
    if article is None:
        print("  [road scan] no road advisory article found this run")
        return (stored_current, False) if report_is_new else stored_current

    if article.get("link") and article["link"] == (stored_current or {}).get("link"):
        print("  [road state] same article as before, reusing status")
        return (stored_current, False) if report_is_new else stored_current

    full_text = article["description"]
    if article.get("link"):
        fetched = fetch_full_article_text(article["link"])
        if fetched:
            full_text = fetched

    statuses = extract_road_statuses(full_text)
    if not statuses:
        print("  [road scan] article found but no per-road status could be extracted")
        return (stored_current, False) if report_is_new else stored_current

    print(f"  [road scan] extracted statuses: {statuses}")
    new_current = {
        "statuses": statuses,
        "source": article.get("source", "BaguioCityGuide"),
        "link": article.get("link", ""),
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
        rows_html = ""
        for road, raw_info in status["statuses"].items():
            info = normalize_road_info(raw_info)
            style = ROAD_STATUS_STYLES.get(info["status"], ROAD_STATUS_STYLES["passable"])
            rows_html += f"""
      <div class="row">
        <div class="roadname">{road}</div>
        <div class="statuspill" style="background:{style['color']}22; color:{style['color']}; border:1px solid {style['color']}66;">{style['label']}</div>
      </div>"""
        narrative = build_road_narrative(status["statuses"])
        found_date = status.get("found_date", "")
        subhead = f"As of {found_date}" if found_date else "Latest road advisory"

    html_out = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Archivo+Black&family=Archivo:wght@400;500;600;700;800&display=swap');
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:1080px; height:1350px; font-family:'Archivo',sans-serif; background:#14181c; position:relative; overflow:hidden; }}

  .bg {{ position:absolute; inset:0; {bg_style} background-color:#14181c; }}
  .overlay {{ position:absolute; inset:0; background: linear-gradient(160deg, rgba(16,20,26,0.72) 0%, rgba(22,28,34,0.78) 60%, rgba(28,37,48,0.85) 100%); }}

  .content {{ position:relative; z-index:2; padding:76px; height:100%; display:flex; flex-direction:column; justify-content:center; }}

  .eyebrow {{ color:#6fa8c9; font-size:22px; letter-spacing:6px; font-weight:600; text-transform:uppercase; }}
  .title {{ font-family:'Archivo Black',sans-serif; color:#f7f2e3; font-size:54px; line-height:1.05; margin-top:14px; }}
  .date {{ color:#c9d2d9; font-size:25px; margin-top:14px; font-weight:500; }}
  .subhead {{ color:#e2e8ec; font-size:26px; margin-top:20px; font-weight:600; }}

  .narrative {{
    margin-top:30px; background:rgba(247,242,227,0.06); border:1px solid rgba(247,242,227,0.16);
    border-radius:16px; padding:32px 34px; color:#eef2f5; font-size:26px; line-height:1.6;
  }}

  .rows {{ margin-top:30px; display:flex; flex-direction:column; gap:18px; }}
  .row {{
    display:flex; align-items:center; justify-content:space-between; gap:20px;
    background:rgba(247,242,227,0.06); border:1px solid rgba(247,242,227,0.16);
    border-radius:16px; padding:28px 32px;
  }}
  .roadname {{ color:#f7fafc; font-size:28px; font-weight:700; }}
  .statuspill {{ font-size:20px; font-weight:800; letter-spacing:1px; padding:11px 22px; border-radius:20px; white-space:nowrap; }}

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
    <div class="date">{today}</div>
    <div class="subhead">{subhead}</div>

    <div class="narrative">{narrative}</div>

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
    return "\n".join(lines)

def build_road_image():
    html_out, status = build_road_html()
    buffer = render_html_to_png(html_out)
    caption = build_road_caption(status)
    return buffer, caption

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
