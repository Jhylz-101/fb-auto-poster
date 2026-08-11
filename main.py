import requests
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

BOT_TOKEN = "8919908599:AAGTBdy69N5NFXY5KTIMhTkO7q2VpOXwYa8"
CHAT_ID = "7898015877"
WEATHER_API_KEY = "84eaa833c8842565474aa84d53094962"
EXCHANGE_API_KEY = "b174a7c95ab92ab9e9a39a75"
GOLD_API_KEY = "goldapi-cc32e7d2de735906d4e7ac171ac3fb6e-io"

CITIES = ["Baguio", "La Trinidad", "Atok", "Bakun", "Bokod", "Buguias", "Itogon", "Kabayan", "Kapangan", "Kibungan", "Mankayan", "Sablan", "Tuba", "Tublay"]

def get_weather(city):
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city},PH&appid={WEATHER_API_KEY}&units=metric"
    data = requests.get(url).json()
    temp = data["main"]["temp"]
    condition = data["weather"][0]["description"]
    return f"{city}: {temp}°C, {condition}"

def get_forex():
    url = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_API_KEY}/latest/USD"
    data = requests.get(url).json()
    rate = data["conversion_rates"]["PHP"]
    return f"USD to PHP: ₱{rate:.2f}"

def get_gold():
    url = "https://www.goldapi.io/api/XAU/PHP"
    headers = {"x-access-token": GOLD_API_KEY}
    data = requests.get(url, headers=headers).json()
    price_per_gram = data["price_gram_24k"]
    return f"Gold: ₱{price_per_gram:,.2f}/gram (24k)"

def get_font(size):
    font_url = "https://github.com/google/fonts/raw/main/apache/roboto/static/Roboto-Bold.ttf"
    font_data = requests.get(font_url).content
    return ImageFont.truetype(BytesIO(font_data), size)

def generate_background():
    prompt = "misty mountain highland landscape, golden hour, minimalist, soft colors"
    url = f"https://image.pollinations.ai/prompt/{prompt}?width=1080&height=1080"
    response = requests.get(url)
    img = Image.open(BytesIO(response.content)).convert("RGB")
    return img

def build_image():
    img = generate_background()
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 120))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(img)
    title_font = get_font(50)
    text_font = get_font(28)

    y = 40
    draw.text((40, y), "Benguet Daily Update", font=title_font, fill="white")
    y += 90

    weather_lines = [get_weather(c) for c in CITIES[:5]]
    for line in weather_lines:
        draw.text((40, y), line, font=text_font, fill="white")
        y += 40

    y += 20
    draw.text((40, y), get_forex(), font=text_font, fill="white")
    y += 40
    draw.text((40, y), get_gold(), font=text_font, fill="white")

    buffer = BytesIO()
    img.save(buffer, format="JPEG")
    buffer.seek(0)
    return buffer

def send_photo(image_buffer):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    files = {"photo": ("update.jpg", image_buffer, "image/jpeg")}
    data = {"chat_id": CHAT_ID}
    response = requests.post(url, files=files, data=data)
    return response.json()

if __name__ == "__main__":
    image_buffer = build_image()
    result = send_photo(image_buffer)
    print(result)
