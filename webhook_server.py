import os
import subprocess
import glob
from flask import Flask, request, jsonify
from main import (
    BOT_TOKEN, answer_callback_query, send_text_message,
    get_telegram_file_bytes, post_to_facebook,
    send_photo_for_approval, build_custom_news_image
)


def ensure_playwright_browser_installed():
    """Railway's build-time RAILPACK_PYTHON_PLAYWRIGHT_INSTALL env var
    doesn't always reliably install the Chromium binary on every service
    (build caching, layer ordering, etc). Rather than depend on that build
    step working correctly, check for the actual browser binary at process
    startup and install it on the spot if it's missing. This runs once per
    deploy (a fresh container has nothing cached) and adds roughly 20-40
    seconds to the very first startup, but every request after that is
    normal speed."""
    cache_dir = os.path.expanduser("~/.cache/ms-playwright")
    chromium_dirs = glob.glob(os.path.join(cache_dir, "chromium*"))

    browser_found = False
    for d in chromium_dirs:
        matches = glob.glob(os.path.join(d, "**", "chrome*"), recursive=True)
        if matches:
            browser_found = True
            break

    if browser_found:
        print("  [playwright check] Chromium binary found, skipping install")
        return

    print("  [playwright check] Chromium binary not found — installing now, this may take a minute...")
    try:
        result = subprocess.run(
            ["playwright", "install", "chromium"],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0:
            print("  [playwright check] Chromium installed successfully")
        else:
            print(f"  [playwright check] install failed (exit {result.returncode}): {result.stderr[-1000:]}")
    except Exception as e:
        print(f"  [playwright check] install crashed: {e}")


ensure_playwright_browser_installed()

app = Flask(__name__)


def handle_callback(callback):
    data = callback.get("data", "")
    callback_id = callback["id"]

    try:
        if data.startswith("approve_"):
            label = data[len("approve_"):]
            message = callback.get("message", {})
            photos = message.get("photo", [])
            caption = message.get("caption", "")

            if not photos:
                print(f"  [webhook] approve for '{label}' but no photo on message")
                answer_callback_query(callback_id, "No photo found on this message")
                return

            largest_photo = photos[-1]
            image_bytes = get_telegram_file_bytes(largest_photo["file_id"])

            if not image_bytes:
                print(f"  [webhook] approve for '{label}' but could not download image")
                answer_callback_query(callback_id, "Could not download image — check logs")
                return

            print(f"  [webhook] approving '{label}' — posting to Facebook")
            result = post_to_facebook(image_bytes, caption)
            if result.get("id") or result.get("post_id"):
                print(f"  [webhook] '{label}' posted to Facebook successfully: {result}")
                answer_callback_query(callback_id, "Posted to Facebook!")
                send_text_message(f"✅ '{label}' approved and posted to Facebook.")
            else:
                print(f"  [webhook] '{label}' Facebook post FAILED: {result}")
                answer_callback_query(callback_id, "Facebook post failed — check logs")
                error_info = result.get("error", result)
                error_text = error_info.get("message", str(error_info)) if isinstance(error_info, dict) else str(error_info)
                send_text_message(f"⚠️ '{label}' approved but Facebook post failed: {error_text}")

        elif data.startswith("reject_"):
            label = data[len("reject_"):]
            print(f"  [webhook] '{label}' rejected, discarding")
            answer_callback_query(callback_id, "Rejected — discarded")
            send_text_message(f"🚫 '{label}' rejected — not posted to Facebook.")

    except Exception as e:
        print(f"  [webhook] error handling callback: {e}")


def handle_message(message):
    """Handles plain text messages sent to the bot (not button presses).
    Any non-command text of reasonable length is treated as a news
    narrative to turn into a themed post."""
    text = message.get("text", "")

    if not text or text.startswith("/"):
        return

    if len(text.strip()) < 20:
        send_text_message(
            "Send the full news text — headline on the first line, then the "
            "story below it — and I'll turn it into a post."
        )
        return

    send_text_message("📝 Got it — building the post now, one moment...")

    try:
        img_buffer, caption, label = build_custom_news_image(text)
        send_photo_for_approval(
            img_buffer, label, filename="update.png", mime="image/png", caption=caption
        )
        print(f"  [webhook] custom news post '{label}' sent for approval")
    except Exception as e:
        print(f"  [webhook] custom news post failed: {e}")
        send_text_message(f"⚠️ Couldn't build that post — {e}")


@app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook():
    update = request.get_json(force=True, silent=True) or {}

    callback = update.get("callback_query")
    if callback:
        handle_callback(callback)

    message = update.get("message")
    if message:
        handle_message(message)

    return jsonify({"ok": True})


@app.route("/", methods=["GET"])
def health():
    return "OK — webhook server is running"


@app.route("/debug-config", methods=["GET"])
def debug_config():
    """Shows a masked view of the currently-loaded FB credentials in this
    running process, to confirm they actually match what was pasted into
    Railway (since this is a long-running server, not a fresh script run,
    it's possible for it to be holding stale values in memory)."""
    from main import FB_PAGE_ACCESS_TOKEN, FB_PAGE_ID
    token = FB_PAGE_ACCESS_TOKEN or ""
    masked_token = f"{token[:12]}...{token[-8:]}" if len(token) > 20 else "(empty or too short)"
    return jsonify({
        "FB_PAGE_ID": FB_PAGE_ID,
        "FB_PAGE_ACCESS_TOKEN_masked": masked_token,
        "FB_PAGE_ACCESS_TOKEN_length": len(token)
    })


@app.route("/register-webhook", methods=["GET"])
def register_webhook():
    """Visit this URL once (in a browser) after deploying, to tell Telegram
    to start pushing button-taps here instantly instead of us polling."""
    import requests
    # Railway's generated domains are always HTTPS at the edge, even though
    # the app itself sees plain HTTP internally — force https explicitly
    # rather than trusting request.host_url's scheme.
    domain = request.host
    webhook_url = f"https://{domain}/telegram-webhook"
    response = requests.get(
        f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
        params={"url": webhook_url}
    ).json()
    return jsonify({"registered_url": webhook_url, "telegram_response": response})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
