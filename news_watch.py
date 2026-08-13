import json
import os
from main import (
    gather_news, is_local_article, build_news_html,
    render_html_to_png, send_photo_for_approval
)

SEEN_FILE = "/data/seen_news.json"
NATIONAL_STATE_FILE = "/data/national_top_story.json"


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


def load_national_state():
    if os.path.exists(NATIONAL_STATE_FILE):
        try:
            with open(NATIONAL_STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_national_state(state):
    os.makedirs(os.path.dirname(NATIONAL_STATE_FILE), exist_ok=True)
    with open(NATIONAL_STATE_FILE, "w") as f:
        json.dump(state, f)


def send_flash(label, top, articles, emoji):
    others = [a for a in articles if a.get("link") != top.get("link")][:4]
    display_articles = [top] + others

    html_out = build_news_html(display_articles)
    img_buffer = render_html_to_png(html_out)
    caption = f"{emoji} {top['title']}"
    if top.get("link"):
        caption += f"\n{top['link']}"

    send_photo_for_approval(
        img_buffer, label,
        filename="update.png", mime="image/png",
        caption=caption
    )


if __name__ == "__main__":
    seen = load_seen()
    print(f"Loaded {len(seen)} previously-seen local story links")

    articles = gather_news()

    # ---- Local Benguet news watch (unchanged) ----
    local_new = [
        a for a in articles
        if is_local_article(a) and a.get("link") and a["link"] not in seen
    ]

    if not local_new:
        print("No new Benguet-related story found this run.")
    else:
        top = local_new[0]
        print(f"New local story found: {top['title']} ({top['source']})")
        send_flash("news_flash", top, articles, "🚨")
        print("Sent local flash update for approval")
        seen.add(top["link"])

    save_seen(seen)

    # ---- National top-headline watch (new) ----
    national_state = load_national_state()
    previous_top_link = national_state.get("link", "")

    top_national = next((a for a in articles if not is_local_article(a) and a.get("link")), None)

    if top_national is None:
        print("No national headline available this run.")
    elif top_national["link"] == previous_top_link:
        print("Top national headline unchanged, no alert needed.")
    else:
        print(f"New top national headline: {top_national['title']} ({top_national['source']})")
        send_flash("national_flash", top_national, articles, "📰")
        print("Sent national flash update for approval")
        save_national_state({
            "link": top_national["link"],
            "title": top_national["title"],
            "source": top_national["source"]
        })
