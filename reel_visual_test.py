import requests
from main import build_reel_script, generate_reel_frame_image, send_text_message

BOT_TOKEN = "8919908599:AAGTBdy69N5NFXY5KTIMhTkO7q2VpOXwYa8"
CHAT_ID = "7898015877"

def send_photo(file_path, caption):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    with open(file_path, "rb") as f:
        files = {"photo": (file_path, f, "image/png")}
        data = {"chat_id": CHAT_ID, "caption": caption}
        response = requests.post(url, files=files, data=data)
    result = response.json()
    if not result.get("ok"):
        print(f"  [telegram ERROR] failed to send frame: {result}")
    else:
        print("  [telegram] frame sent OK")

def main():
    lines, headlines_used, headlines_available, est_seconds = build_reel_script()
    send_text_message(f"🖼️ Generating {len(lines)} visual frames for review — black/white/red/yellow style, real article photos where available...")

    for i, line_obj in enumerate(lines):
        text = line_obj["text"]
        image_url = line_obj.get("image_url")
        category = line_obj.get("category")
        source_note = "article photo" if image_url else "branded background"
        print(f"  [visual test] frame {i} ({source_note}, {category}): {text[:60]}")
        try:
            buffer = generate_reel_frame_image(text, image_url=image_url, category=category)
            frame_path = f"/tmp/reel_frame_{i}.png"
            with open(frame_path, "wb") as f:
                f.write(buffer.read())
            send_photo(frame_path, f"Frame {i+1}/{len(lines)} [{category}] ({source_note}): {text[:100]}")
        except Exception as e:
            print(f"  [visual test] frame {i} FAILED: {e}")
            send_text_message(f"⚠️ Frame {i+1} failed: {e}")

    send_text_message("✅ All frames sent. Reply with what you'd like changed (color treatment, text size/position, brand bar, etc.).")

if __name__ == "__main__":
    main()
