from main import build_reel_script, send_text_message

def main():
    script_text, headline_count, is_heavy_day = build_reel_script()

    day_label = "HEAVY DAY (8-headline stretch)" if is_heavy_day else "normal day"
    word_count = len(script_text.split())
    est_seconds = round(word_count / 2.5)

    message = (
        f"🎬 Reel script draft — {day_label}\n"
        f"Headlines used: {headline_count} | Words: {word_count} | Est. length: ~{est_seconds}s\n\n"
        f"{script_text}"
    )
    send_text_message(message)
    print(message)

if __name__ == "__main__":
    main()
