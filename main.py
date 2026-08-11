import requests

BOT_TOKEN = "8919908599:AAGTBdy69N5NFXY5KTIMhTkO7q2VpOXwYa8"
CHAT_ID = "7898015877"
WEATHER_API_KEY = "84eaa833c8842565474aa84d53094962"

CITIES = ["Baguio", "La Trinidad"]

def get_weather(city):
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city},PH&appid={WEATHER_API_KEY}&units=metric"
    response = requests.get(url)
    data = response.json()
    temp = data["main"]["temp"]
    feels_like = data["main"]["feels_like"]
    condition = data["weather"][0]["description"]
    return f"{city}: {temp}°C (feels like {feels_like}°C), {condition}"

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    response = requests.post(url, data=payload)
    return response.json()

if __name__ == "__main__":
    weather_lines = [get_weather(city) for city in CITIES]
    message = "Today's Weather Update:\n\n" + "\n".join(weather_lines)
    result = send_telegram_message(message)
    print(result)
