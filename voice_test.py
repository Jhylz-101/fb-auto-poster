import asyncio
import requests
import edge_tts

BOT_TOKEN = "8919908599:AAGTBdy69N5NFXY5KTIMhTkO7q2VpOXwYa8"
CHAT_ID = "7898015877"

SAMPLE_TEXT = (
    "Good morning, Benguet. Here's what's happening today. "
    "Classes are suspended in Atok, Kabayan, Kibungan, Tublay, Kapangan, and Bakun. "
    "Meanwhile, the Halsema Highway remains passable, though DPWH-CAR is monitoring a slope "
    "near the Gov. Bado Dangwa National Road in Buguias. Over in La Trinidad and Itogon, "
    "local officials continue rescue operations following the Habagat rains."
)

VOICE_ID = "en-US-GuyNeural"
VOICE_LABEL = "US English — Male (Guy)"

async def generate_sample(voice_id, output_path):
    communicate = edge_tts.Communicate(SAMPLE_TEXT, voice_id)
    await communicate.save(output_path)

def send_voice_note(file_path, caption):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendAudio"
    with open(file_path, "rb") as f:
        files = {"audio": (file_path, f, "audio/mpeg")}
        data = {"chat_id": CHAT_ID, "caption": caption}
        response = requests.post(url, files=files, data=data)
    result = response.json()
    if not result.get("ok"):
        print(f"  [telegram ERROR] failed to send {file_path}: {result}")
    else:
        print(f"  [telegram] sent {file_path} OK")

def send_text_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text})

async def main():
    send_text_message(f"🎙️ Testing {VOICE_LABEL} on real Benguet place names — listen for how it handles Kabayan, Kibungan, Kapangan, Halsema, and Gov. Bado Dangwa.")
    output_path = f"/tmp/{VOICE_ID}_places.mp3"
    try:
        await generate_sample(VOICE_ID, output_path)
        send_voice_note(output_path, VOICE_LABEL)
        send_text_message("✅ Sample sent. Reply 'good' to lock this voice in, or tell me what sounded off.")
    except Exception as e:
        print(f"  [voice test] FAILED: {e}")
        send_text_message(f"⚠️ Could not generate sample: {e}")

if __name__ == "__main__":
    asyncio.run(main())
