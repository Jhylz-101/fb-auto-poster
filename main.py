import requests
import time
import json

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
    feels_like = data["main"]["feels_like"]
    condition = data["weather"][0]["description"]
    return f"{city}: {temp}°C (feels like {feels_like}°C), {condition}"

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
    return f"World Gold Price: ₱{price_per_gram:,.2f} per gram (24k)"

def build_message():
    weather_lines = [get_weather(city) for city in CITIES]
    forex_line = get_forex()
    gold_line = get_gold()
    message = "Today's Update:\n\n"
    message += "Weather:\n" + "\n".join(weather_lines) + "\n\n"
    message += "Currency:\n" + forex_line + "\n\n"
    message += "Gold:\n" + gold_line
    return message

def send_for_approval(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Approve", "callback_data": "approve"},
            {"text": "❌ Reject", "callback_data": "reject"}
        ]]
    }
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "reply_markup": json.dumps(keyboard)
    }
    response = requests.post(url, data=payload)
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
    message = build_message()
    send_for_approval(message)
    decision = listen_for_response()
    print(f"Final decision: {decision}")
