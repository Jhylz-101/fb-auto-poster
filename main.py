import requests
import time
import json
import random
import re
import html as html_lib
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from datetime import datetime
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

def get_forex():
    url = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_API_KEY}/latest/USD"
    data = requests.get(url).json()
    rate = data["conversion_rates"]["PHP"]
    return f"USD to PHP: {rate:.2f}"

def get_gold():
    url = "https://www.goldapi.io/api/XAU/PHP"
    headers = {"x-access-token": GOLD_API_KEY}
    data = requests.get(url, headers=headers).json()
    price_per_gram = data["price_gram_24k"]
    return f"PHP {price_per_gram:,.2f}/gram (24k pure gold)"

# ---------- News ----------

LOCAL_KEYWORDS = [
    "benguet", "baguio", "la trinidad", "cordillera", "car region",
    "itogon", "atok", "buguias", "kabayan", "kapangan", "kibungan",
    "mankayan", "sablan", "tuba", "tublay", "bokod", "bakun",
    "pagasa", "car-car"
]

def get_articles_from_feed(feed_url, limit=6):
    try:
        response = requests.get(feed_url, timeout=10)
        root = ET.fromstring(response.content)
        items = root.findall(".//item")[:limit]
        articles = []
        for item in items:
            title_el = item.find("title")
            desc_el = item.find("description")
            link_el = item.find("link")
            title = title_el.text.strip() if title_el is not None and title_el.text else None
            desc_raw = desc_el.text.strip() if desc_el is not None and desc_el.text else ""
            desc = re.sub(r"<[^>]+>", "", desc_raw)
            desc = html_lib.unescape(desc).strip()
            link = link_el.text.strip() if link_el is not None and link_el.text else ""
            if title:
                articles.append({"title": title.strip(), "description": desc, "link": link})
        return articles
    except Exception:
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

def gather_news():
    all_articles = []
    for name, url in NEWS_SOURCES.items():
        for article in get_articles_from_feed(url, limit=6):
            all_articles.append({"source": name, **article})

    all_articles = [a for a in all_articles if not is_excluded_article(a)]

    local_articles = [a for a in all_articles if is_local_article(a)]
    other_articles = [a for a in all_articles if not is_local_article(a)]

    return local_articles + other_articles

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
    return html

def build_weather_image():
    html = build_weather_html()
    return render_html_to_png(html)

# ---------- Currency & Gold (Pillow, unchanged) ----------

def build_currency_gold_image():
    prompt = "elegant financial district skyline, gold bars and coins, professional business aesthetic, formal, minimalist"
    img = generate_background(prompt)
    overlay = Image.new("RGBA", img.size, (10, 15, 30, 90))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img, "RGBA")
    width, height = img.size

    badge_font = get_font(30)
    text_font = get_font(24)
    small_font = get_font(20)
    huge_title_font = get_font(55)

    draw_title(draw, huge_title_font, width, "CURRENCY & GOLD")
    y = 200

    y = section_badge(draw, badge_font, MARGIN, y, "CURRENCY", ACCENT_GREEN)
    y += 30
    draw.ellipse([(MARGIN, y + 8), (MARGIN + 9, y + 17)], fill=ACCENT_GREEN)
    draw.text((MARGIN + 18, y), get_forex(), font=text_font, fill=WHITE)
    y += 70

    y = section_badge(draw, badge_font, MARGIN, y, "GOLD", ACCENT_GOLD)
    y += 30
    draw.ellipse([(MARGIN, y + 8), (MARGIN + 9, y + 17)], fill=ACCENT_GOLD)
    draw.text((MARGIN + 18, y), get_gold(), font=text_font, fill=WHITE)

    today = datetime.now().strftime("%B %d, %Y")
    draw.rectangle([(0, height - 60), (width, height)], fill=(0, 0, 0, 180))
    draw.text((MARGIN, height - 45), today, font=small_font, fill=WHITE)

    buffer = BytesIO()
    img.save(buffer, format="JPEG")
    buffer.seek(0)
    return buffer

# ---------- News (HTML/Playwright narrative-style) ----------

def truncate_text(text, max_len=340):
    text = " ".join(text.split())
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "…"

def build_news_html(articles):
    today = datetime.now().strftime("%B %d, %Y")

    if not articles:
        top = {"source": "", "title": "No headlines available today", "description": "", "link": ""}
        rest = []
    else:
        top = articles[0]
        rest = articles[1:5]

    lede_text = truncate_text(top["description"]) if top["description"] else "Full details available from the source below."

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

  .topbar {{ display:flex; justify-content:space-between; align-items:center; padding:44px 70px 0; }}
  .brand {{ color:#b02e26; font-size:22px; font-weight:800; letter-spacing:3px; }}
  .date {{ color:#9a9a9a; font-size:20px; font-weight:500; }}

  .badge {{
    margin:32px 70px 0; align-self:flex-start;
    background:#b02e26; color:#fff; font-weight:800; font-size:22px; letter-spacing:3px;
    padding:11px 24px; text-transform:uppercase;
  }}

  .headline {{
    font-family:'Archivo Black',sans-serif; color:#f7f4ee; font-size:52px; line-height:1.1;
    padding:24px 70px 0; text-transform:none;
  }}

  .rule {{ height:2px; background:#3a3a3a; margin:32px 70px 0; }}

  .lede {{ color:#e3ded3; font-size:25px; line-height:1.55; padding:30px 70px 0; font-weight:400; }}

  .also {{ margin:36px 70px 0; border-top:1px solid #3a3a3a; padding-top:28px; }}
  .also-label {{ color:#8a8a8a; font-size:16px; font-weight:700; letter-spacing:2px; text-transform:uppercase; margin-bottom:16px; }}
  .item {{ display:flex; align-items:flex-start; gap:12px; margin-top:14px; }}
  .item .dot {{ width:7px; height:7px; border-radius:50%; background:#b02e26; flex-shrink:0; margin-top:9px; }}
  .item .itext {{ color:#d8d2c6; font-size:19px; line-height:1.4; flex:1; }}
  .item .src {{ color:#8a8a8a; font-size:15px; white-space:nowrap; margin-top:2px; }}

  .footer {{ margin-top:auto; display:flex; justify-content:space-between; align-items:center; padding:32px 70px 42px; border-top:1px solid #3a3a3a; }}
  .source {{ color:#8a8a8a; font-size:18px; }}
  .cta {{ color:#f0a97a; font-size:18px; font-weight:700; }}
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
    response = requests.post(url, files=files, data=data)
    return response.json()

if __name__ == "__main__":
    weather_img = build_weather_image()
    send_photo_for_approval(weather_img, "weather", filename="update.png", mime="image/png")
    print("Sent weather post")
    time.sleep(2)

    currency_img = build_currency_gold_image()
    send_photo_for_approval(currency_img, "currency")
    print("Sent currency/gold post")
    time.sleep(2)

    news_img, news_caption = build_news_image()
    send_photo_for_approval(news_img, "news", filename="update.png", mime="image/png", caption=news_caption)
    print("Sent news post")
