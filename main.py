import requests
import time
import json
import random
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from datetime import datetime

BOT_TOKEN = "8919908599:AAGTBdy69N5NFXY5KTIMhTkO7q2VpOXwYa8"
CHAT_ID = "7898015877"
WEATHER_API_KEY = "84eaa833c8842565474aa84d53094962"
EXCHANGE_API_KEY = "b174a7c95ab92ab9e9a39a75"
GOLD_API_KEY = "goldapi-cc32e7d2de735906d4e7ac171ac3fb6e-io"

CITIES = ["Baguio", "La Trinidad", "Atok", "Bakun", "Bokod", "Buguias", "Itogon", "Kabayan", "Kapangan", "Kibungan", "Mankayan", "Sablan", "Tuba", "Tublay"]

NEWS_SOURCES = {
    "Rappler": "https://www.rappler.com/feed/",
    "Inquirer": "https://www.inquirer.net/fullfeed",
    "PhilStar": "https://www.philstar.com/rss/headlines"
}

CONNECTORS = ["Meanwhile, ", "In other news, ", "Elsewhere, ", "Also making headlines: "]

ACCENT_BLUE = (86, 180, 233, 255)
ACCENT_GREEN = (110, 210, 130, 255)
ACCENT_GOLD = (255, 195, 90, 255)
ACCENT_RED = (230, 100, 100, 255)
WHITE = (255, 255, 255, 255)
MARGIN = 55

def get_weather_data(city):
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city},PH&appid={WEATHER_API_KEY}&units=metric"
    return requests.get(url).json()

def get_weather_line(data, city):
    temp = data["main"]["temp"]
    condition = data["weather"][0]["description"]
    return f"{city}: {temp}C, {condition}"

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

def get_raw_headline(source_name, feed_url):
    try:
        response = requests.get(feed_url, timeout=10)
        root = ET.fromstring(response.content)
        title = root.find(".//item/title").text
        return title.strip()
    except Exception:
        return None

def build_news_narrative():
    headlines = []
    for name, url in NEWS_SOURCES.items():
        title = get_raw_headline(name, url)
        if title:
            headlines.append((name, title))

    if not headlines:
        return ["No headlines available right now."]

    lines = []
    first_name, first_title = headlines[0]
    lines.append(f"Today's top story: {first_title} ({first_name}).")

    for i, (name, title) in enumerate(headlines[1:], start=1):
        connector = CONNECTORS[i % len(CONNECTORS)]
        lines.append(f"{connector}{title} ({name}).")

    return lines

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

def build_weather_image():
    baguio_data = get_weather_data("Baguio")
    condition_main = baguio_data["weather"][0]["main"]
    prompt = weather_prompt_from_condition(condition_main)
    img = generate_background(prompt)

    overlay = Image.new("RGBA", img.size, (10, 15, 30, 90))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img, "RGBA")
    width, height = img.size

    badge_font = get_font(30)
    text_font = get_font(19)
    small_font = get_font(20)
    huge_title_font = get_font(55)

    draw_title(draw, huge_title_font, width, "BENGUET WEATHER")
    y = 170
    y = section_badge(draw, badge_font, MARGIN, y, "WEATHER", ACCENT_BLUE)
    y += 24

    weather_lines = [get_weather_line(get_weather_data(c), c) for c in CITIES]
    num_cols = 2
    GUTTER = 40
    col_width = (width - MARGIN * 2 - GUTTER * (num_cols - 1)) // num_cols
    row_height = 34
    for i, line in enumerate(weather_lines):
        col = i % num_cols
        row = i // num_cols
        x = MARGIN + col * (col_width + GUTTER)
        line_y = y + row * row_height
        draw.ellipse([(x, line_y + 7), (x + 8, line_y + 15)], fill=ACCENT_BLUE)
        draw.text((x + 15, line_y), line, font=text_font, fill=WHITE)

    today = datetime.now().strftime("%B %d, %Y")
    draw.rectangle([(0, height - 60), (width, height)], fill=(0, 0, 0, 180))
    draw.text((MARGIN, height - 45), today, font=small_font, fill=WHITE)

    buffer = BytesIO()
    img.save(buffer, format="JPEG")
    buffer.seek(0)
    return buffer

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

def build_news_image():
    prompt = "newspaper stack, coffee cup, morning light, editorial desk aesthetic, formal, minimalist"
    img = generate_background(prompt, height=1350)
    overlay = Image.new("RGBA", img.size, (10, 15, 30, 100))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img, "RGBA")
    width, height = img.size

    badge_font = get_font(30)
    text_font = get_font(22)
    small_font = get_font(20)
    huge_title_font = get_font(55)

    draw_title(draw, huge_title_font, width, "TODAY'S HEADLINES")
    y = 200
    y = section_badge(draw, badge_font, MARGIN, y, "NEWS ROUNDUP", ACCENT_RED)
    y += 35

    narrative_lines = build_news_narrative()
    max_text_width = width - (MARGIN * 2)

    for paragraph in narrative_lines:
        wrapped = wrap_text(draw, paragraph, text_font, max_text_width)
        for line in wrapped:
            draw.text((MARGIN, y), line, font=text_font, fill=WHITE)
            y += 32
        y += 18

    today = datetime.now().strftime("%B %d, %Y")
    draw.rectangle([(0, height - 60), (width, height)], fill=(0, 0, 0, 180))
    draw.text((MARGIN, height - 45), today, font=small_font, fill=WHITE)

    buffer = BytesIO()
    img.save(buffer, format="JPEG")
    buffer.seek(0)
    return buffer

def send_photo_for_approval(image_buffer, label):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    keyboard = {
        "inline_keyboard": [[
            {"text": "Approve", "callback_data": f"approve_{label}"},
            {"text": "Reject", "callback_data": f"reject_{label}"}
        ]]
    }
    files = {"photo": ("update.jpg", image_buffer, "image/jpeg")}
    data = {
        "chat_id": CHAT_ID,
        "reply_markup": json.dumps(keyboard)
    }
    response = requests.post(url, files=files, data=data)
    return response.json()

if __name__ == "__main__":
    weather_img = build_weather_image()
    send_photo_for_approval(weather_img, "weather")
    print("Sent weather post")
    time.sleep(2)

    currency_img = build_currency_gold_image()
    send_photo_for_approval(currency_img, "currency")
    print("Sent currency/gold post")
    time.sleep(2)

    news_img = build_news_image()
    send_photo_for_approval(news_img, "news")
    print("Sent news post")
