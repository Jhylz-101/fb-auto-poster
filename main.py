def build_image():
    today_usd = get_forex_value()
    today_gold = get_gold_value()
    yesterday_usd, yesterday_gold = get_yesterday_prices()
    save_today_prices(today_usd, today_gold)

    img = generate_background()
    overlay = Image.new("RGBA", img.size, (10, 15, 30, 90))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(img, "RGBA")
    width, height = img.size

    badge_font = get_font(30)
    text_font = get_font(19)
    small_font = get_font(20)

    ACCENT_BLUE = (86, 180, 233, 255)
    ACCENT_GREEN = (110, 210, 130, 255)
    ACCENT_GOLD = (255, 195, 90, 255)
    WHITE = (255, 255, 255, 255)
    GRAY = (200, 200, 200, 255)

    MARGIN = 55
    GUTTER = 40

    def section_badge(x, y, text, color):
        bbox = draw.textbbox((0, 0), text, font=badge_font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        pad_x, pad_y = 24, 14
        capsule_h = text_h + pad_y * 2
        draw.rounded_rectangle(
            [(x, y), (x + text_w + pad_x * 2, y + capsule_h)],
            radius=capsule_h / 2, fill=color
        )
        text_y = y + pad_y - bbox[1]
        draw.text((x + pad_x, text_y), text, font=badge_font, fill=(15, 15, 15, 255))
        return y + capsule_h

    # Bulletproof title: render huge, crop, force-resize to exact height
    title_text = "BENGUET DAILY UPDATE"
    temp_font = get_font(100)
    temp_img = Image.new("RGBA", (1400, 180), (0, 0, 0, 0))
    temp_draw = ImageDraw.Draw(temp_img)
    temp_draw.text((10, 10), title_text, font=temp_font, fill=WHITE)
    bbox = temp_draw.textbbox((10, 10), title_text, font=temp_font)
    cropped = temp_img.crop((bbox[0] - 5, bbox[1] - 5, bbox[2] + 5, bbox[3] + 5))

    target_height = 85
    scale = target_height / cropped.height
    new_width = int(cropped.width * scale)
    resized_title = cropped.resize((new_width, target_height), Image.LANCZOS)

    draw.rectangle([(0, 0), (width, 160)], fill=(0, 0, 0, 150))
    title_x = (width - new_width) // 2
    img.paste(resized_title, (title_x, 40), resized_title)

    y = 190

    y = section_badge(MARGIN, y, "WEATHER", ACCENT_BLUE)
    y += 24

    weather_lines = [get_weather(c) for c in CITIES]
    num_cols = 2
    col_width = (width - MARGIN * 2 - GUTTER * (num_cols - 1)) // num_cols
    row_height = 34
    for i, line in enumerate(weather_lines):
        col = i % num_cols
        row = i // num_cols
        x = MARGIN + col * (col_width + GUTTER)
        line_y = y + row * row_height
        draw.ellipse([(x, line_y + 7), (x + 8, line_y + 15)], fill=ACCENT_BLUE)
        draw.text((x + 15, line_y), line, font=text_font, fill=WHITE)

    num_rows = (len(weather_lines) + num_cols - 1) // num_cols
    y += num_rows * row_height + 30

    y = section_badge(MARGIN, y, "CURRENCY", ACCENT_GREEN)
    y += 24
    draw.ellipse([(MARGIN, y + 8), (MARGIN + 9, y + 17)], fill=ACCENT_GREEN)
    draw.text((MARGIN + 18, y), f"1 USD = PHP {today_usd:.2f}", font=text_font, fill=WHITE)
    y += 32
    if yesterday_usd:
        draw.text((MARGIN + 18, y), f"Yesterday: PHP {yesterday_usd:.2f}", font=small_font, fill=GRAY)
        y += 32
    y += 20

    y = section_badge(MARGIN, y, "GOLD", ACCENT_GOLD)
    y += 24
    draw.ellipse([(MARGIN, y + 8), (MARGIN + 9, y + 17)], fill=ACCENT_GOLD)
    draw.text((MARGIN + 18, y), f"PHP {today_gold:,.2f}/gram (24k)", font=text_font, fill=WHITE)
    y += 32
    if yesterday_gold:
        draw.text((MARGIN + 18, y), f"Yesterday: PHP {yesterday_gold:,.2f}", font=small_font, fill=GRAY)
        y += 32
    y += 30

    today = datetime.now().strftime("%B %d, %Y")
    draw.rectangle([(0, height - 60), (width, height)], fill=(0, 0, 0, 150))
    draw.text((MARGIN, height - 45), today, font=small_font, fill=WHITE)

    buffer = BytesIO()
    img.save(buffer, format="JPEG")
    buffer.seek(0)
    return buffer
