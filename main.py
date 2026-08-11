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
    bbo
