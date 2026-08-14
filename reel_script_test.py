from main import build_reel_script, send_text_message

def main():
    script_text, headlines_used, headlines_available, est_seconds = build_reel_script()

    trimmed_note = ""
    if headlines_used < headlines_available:
        trimmed_note = f" ({headlines_available - headlines_used} more available but cut for time)"

    word_count = len(script_text.split())

    message = (
        f"🎬 Reel script draft\n"
        f"Headlines used: {headlines_used}{trimmed_note} | Words: {word_count} | Est. length: ~{est_seconds}s\n\n"
        f"{script_text}"
    )
    send_text_message(message)
    print(message)

if __name__ == "__main__":
    main()
