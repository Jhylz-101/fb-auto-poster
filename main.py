import requests

BOT_TOKEN = "8919908599:AAGTBdy69N5NFXY5KTIMhTkO7q2VpOXwYa8"
CHAT_ID = "7898015877"
WEATHER_API_KEY = "84eaa833c8842565474aa84d53094962"
EXCHANGE_API_KEY = "b174a7c95ab92ab9e9a39a75"
GOLD_API_KEY = "goldapi-cc32e7d2de735906d4e7ac171ac3fb6e-io"

CITIES = ["Baguio", "La Trinidad"]

def get_weather(city):
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city},PH&appid={WEATHER_API_KEY}&units=metric"
    response = requests.get(url)
    data = response.json()
    temp = data["main"]["temp"]
    feels_like = data["main"]["feels_like"]
    condition = data["weather"][0]["description"]
    return f"{city}: {temp}°C (feels like {feels_like}°C), {condition}"

def get_forex():
    url = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_API_KEY}/latest/USD"
    response = requests.get(url)
    data = response.json()
    rate = data["conversion_rates"]["PHP"]
    return f"USD to PHP: ₱{rate:.2f}"

def get_gold():
    url = "https://www.goldapi.io/api/XAU/PHP"
    headers = {"x-access-token": GOLD_API_KEY}
    response = requests.get(url, headers=headers)
    data = response.json()
    price_per_gram = data["price_gram_24k"]
    return f"World Gold Price: ₱{price_per_gram:,.2f} per gram (24k)"

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    response = requests.post(url, data=payload)
    return response.json()

if __name__ == "__main__":
    weather_lines = [get_weather(city) for city in CITIES]
    forex_line = get_forex()
    gold_line = get_gold()

    message = "Today's Update:\n\n"
    message += "Weather:\n" + "\n".join(weather_lines) + "\n\n"
    message += "Currency:\n" + forex_line + "\n\n"
    message += "Gold:\n" + gold_line

    result = send_telegram_message(message)
    print(result)
