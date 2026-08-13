import json
import os
from main import (
    gather_news, is_local_article, build_news_html,
    render_html_to_png, send_photo_for_approval
)

SEEN_FILE = "/data/seen_news.json"


def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_seen(seen_links):
    os.makedirs(os.path.dirname(SEEN_FILE), exist_ok=True)
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen_links), f)


if __name__ == "__main__":
    seen = load_seen()
    print(f"Loaded {len(seen)} previously-seen story links")

    articles = gather_news()
    local_new = [
        a for a in articles
        if is_local_article(a) and a.get("link") and a["link"] not in seen
    ]

    if not local_new:
        print("No new Benguet-related story found this run.")
    else:
        top = local_new[0]
        print(f"New local story found: {top['title']} ({top['source']})")

        # Fill out the post with a few more headlines from the same scan
        # instead of showing just one story with lots of empty space below.
        others = [a for a in articles if a.get("link") != top.get("link")][:4]
        display_articles = [top] + others

        html_out = build_news_html(display_articles)
        img_buffer = render_html_to_png(html_out)
        caption = f"🚨 {top['title']}"
        if top.get("link"):
            caption += f"\n{top['link']}"

        send_photo_for_approval(
            img_buffer, "news_flash",
            filename="update.png", mime="image/png",
            caption=caption
        )
        print("Sent flash update for approval")
        seen.add(top["link"])

    save_seen(seen)
