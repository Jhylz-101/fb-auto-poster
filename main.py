import requests
import time
import json
import random
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from datetime import datetime, timedelta

BOT_TOKEN = "8919908599:AAGTBdy69N5NFXY5KTIMhTkO7q2VpOXwYa8"
CHAT_ID = "7898015877"
WEATHER_API_KEY = "84eaa833c8842565474aa84d53094962"
EXCHANGE_API_KEY = "b174a7c95ab92ab9e9a39a75"
GOLD_API_KEY = "goldapi-cc32e7d2de735906d4e7ac171ac3fb6e-io"
SUPABASE_URL = "https://xsjhgocorinncafcpbmv.supabase.co"
SUPABASE_KEY = "sb_secret_5fl8wEbkxKPLju6VLJr2eA_UJljgjER"

CITIES = ["Baguio", "La Trinidad", "Atok", "Bakun", "Bokod", "Buguias", "Itogon", "Kabayan", "Kapangan", "Kibungan", "Mankayan", "Sablan", "Tuba", "Tublay"]

BACKGROUND_PROMPTS = [
    "misty mountain highland landscape, golden hour, minimalist, soft colors",
    "pine forest hills at sunrise, soft fog, minimalist landscape",
    "golden rice terraces at dawn, soft light, minimalist",
    "highland valley with clouds below, warm sunset tones, minimalist",
    "mountain ridge silhouette, pastel sky, minimalist landscape"
]

def get_weather(city):
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city},PH&appid={WEATHER_API_KEY}&units=metric"
    data = requests.get(url).json()
    temp = data["main"]["temp"]
    condition = data["weather"][0]["description"]
    return f"{city}: {temp}C, {condition}"

def get_forex_value():
    url = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_API_KEY}/latest/USD"
    data = requests.get(url).json()
    return data["conversion_rates"]["PHP"]

def get_gold_value():
    url = "https://www.goldapi.io/api/XAU/PHP"
    headers = {"x-access-token": GOLD_API_KEY}
    data = requests.get(url, headers=headers).json()
    return data["price_gram_24k"]

def save_today_prices(usd_php, gold_php):
    url = f"{SUPABASE_URL}/rest/v1/daily_prices"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    today = datetime.now().strftime("%Y-%m-%d")
    payload = {"date": today, "usd_php": usd_php, "gold_php": gold_php}
    requests.post(url, headers=headers, json=payload)

def get_yesterday_prices():
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    url = f"{SUPABASE_URL}/rest/v1/daily_prices?date=eq.{yesterday}&select=usd_php,gold_php"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    response = requests.get(url, headers=headers).json()
    if response and len(response) > 0:
        return response[0]["usd_php"], response[0]["gold_php"]
    return None, None

def get_font(size):
    return ImageFont.load_default(size=size)

def generate_background():
    prompt = random.choice(BACKGROUND_PROMPTS)
    url = f"https://image.pollinations.ai/prompt/{prompt}?width=1080&height=1080"
    response = requests.get(url)
    img = Image.open(BytesIO(response.content)).convert("RGB")
    return img

def build_image():
    today_usd = get_forex_value()
    today_gold = get_gold_value()
    yesterday_usd, yesterday_gold = get_yesterday_prices()
    save_today_prices(today_usd, today_gold)

    img = generate_background()
    overlay = Image.new("RGBA", img.size, (10, 15, 30, 90))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(img, "RGBA")
    width, height = img.size

    badge_font = get_font(30)
    text_font = get_font(19)
    small_font = get_font(20)

    ACCENT_BLUE = (86, 180, 233, 255)
    ACCENT_GREEN = (110, 210, 130, 255)
    ACCENT_GOLD = (255, 195, 90, 255)
    WHITE = (255, 255, 255, 255)
    GRAY = (200, 200, 200, 255)

    MARGIN = 55
    GUTTER = 40

    def section_badge(x, y, text, color):
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

    title_text = "BENGUET DAILY UPDATE"
    temp_font = get_font(100)
    temp_img = Image.new("RGBA", (1400, 180), (0, 0, 0, 0))
    temp_draw = ImageDraw.Draw(temp_img)
    temp_draw.text((10, 10), title_text, font=temp_font, fill=WHITE)
    bbox = temp_draw.textbbox((10, 10), title_text, font=temp_font)
    cropped = temp_img.crop((bbox[0] - 5, bbox[1] - 5, bbox[2] + 5, bbox[3] + 5))

    target_height = 85
    scale = target_height / cropped.height
    new_width = int(cropped.width * scale)
    resized_title = cropped.resize((new_width, target_height), Image.LANCZOS)

    draw.rectangle([(0, 0), (width, 160)], fill=(0, 0, 0, 150))
    title_x = (width - new_width) // 2
    img.paste(resized_title, (title_x, 40), resized_title)

    y = 190

    y = section_badge(MARGIN, y, "WEATHER", ACCENT_BLUE)
    y += 24

    weather_lines = [get_weather(c) for c in CITIES]
    num_cols = 2
    col_width = (width - MARGIN * 2 - GUTTER * (num_cols - 1)) // num_cols
    row_height = 34
    for i, line in enumerate(weather_lines):
        col = i % num_cols
        row = i // num_cols
        x = MARGIN + col * (col_width + GUTTER)
        line_y = y + row * row_height
        draw.ellipse([(x, line_y + 7), (x + 8, line_y + 15)], fill=ACCENT_BLUE)
        draw.text((x + 15, line_y), line, font=text_font, fill=WHITE)

    num_rows = (len(weather_lines) + num_cols - 1) // num_cols
    y += num_rows * row_height + 30

    y = section_badge(MARGIN, y, "CURRENCY", ACCENT_GREEN)
    y += 24
    draw.ellipse([(MARGIN, y + 8), (MARGIN + 9, y + 17)], fill=ACCENT_GREEN)
    draw.text((MARGIN + 18, y), f"1 USD = PHP {today_usd:.2f}", font=text_font, fill=WHITE)
    y += 32
    if yesterday_usd:
        draw.text((MARGIN + 18, y), f"Yesterday: PHP {yesterday_usd:.2f}", font=small_font, fill=GRAY)
        y += 32
    y += 20

    y = section_badge(MARGIN, y, "GOLD", ACCENT_GOLD)
    y += 24
    draw.ellipse([(MARGIN, y + 8), (MARGIN + 9, y + 17)], fill=ACCENT_GOLD)
    draw.text((MARGIN + 18, y), f"PHP {today_gold:,.2f}/gram (24k)", font=text_font, fill=WHITE)
    y += 32
    if yesterday_gold:
        draw.text((MARGIN + 18, y), f"Yesterday: PHP {yesterday_gold:,.2f}", font=small_font, fill=GRAY)
        y += 32
    y += 30

    today = datetime.now().strftime("%B %d, %Y")
    draw.rectangle([(0, height - 60), (width, height)], fill=(0, 0, 0, 150))
    draw.text((MARGIN, height - 45), today, font=small_font, fill=WHITE)

    buffer = BytesIO()
    img.save(buffer, format="JPEG")
    buffer.seek(0)
    return buffer

def send_photo_for_approval(image_buffer):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    keyboard = {
        "inline_keyboard": [[
            {"text": "Approve", "callback_data": "approve"},
            {"text": "Reject", "callback_data": "reject"}
        ]]
    }
    files = {"photo": ("update.jpg", image_buffer, "image/jpeg")}
    data = {
        "chat_id": CHAT_ID,
        "reply_markup": json.dumps(keyboard)
    }
    response = requests.post(url, files=files, data=data)
    return response.json()

def listen_for_response(timeout_seconds=300):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    last_update_id = None
    start_time = time.time()

    while time.time() - start_time < timeout_seconds:
        params = {"timeout": 10}
        if last_update_id:
            params["offset"] = last_update_id + 1

        response = requests.get(url, params=params).json()

        for update in response.get("result", []):
            last_update_id = update["update_id"]
            if "callback_query" in update:
                data = update["callback_query"]["data"]
                requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    data={"chat_id": CHAT_ID, "text": f"You selected: {data}"}
                )
                return data

        time.sleep(2)

    return "timeout"

if __name__ == "__main__":
    image_buffer = build_image()
    time.sleep(2)
    result = send_photo_for_approval(image_buffer)
    print("SEND RESULT:", result)
    decision = listen_for_response()
    print(f"Final decision: {decision}")
