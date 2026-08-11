import requests
import time
import json
import random
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from datetime import datetime

BOT_TOKEN = "8919908599:AAGTBdy69N5NFXY5KTIMhTkO7q2VpOXwYa8"
CHAT_ID = "7898015877"
WEATHER_API_KEY = "84eaa833c8842565474aa84d53094962"
EXCHANGE_API_KEY = "b174a7c95ab92ab9e9a39a75"
GOLD_API_KEY = "goldapi-cc32e7d2de735906d4e7ac171ac3fb6e-io"

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
    return f"Gold: {price_per_gram:,.2f}/gram (24k)"

def get_font(size):
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except:
        return ImageFont.load_default()

def generate_background():
    prompt = random.choice(BACKGROUND_PROMPTS)
    url = f"https://image.pollinations.ai/prompt/{prompt}?width=1080&height=1080"
    response = requests.get(url)
    img = Image.open(BytesIO(response.content)).convert("RGB")
    return img

def build_image():
    img = generate_background()
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 100))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(img, "RGBA")
    width, height = img.size

    title_font = get_font(48)
    header_font = get_font(30)
