"""Post new horizontal YouTube videos to Telegram without duplicates."""

import html as html_lib
import json
import os
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT = "@womennjldf"
YOUTUBE_CHANNEL = "UCzR5VXsj_6HcGsnKpvgwdiQ"
VIDEO_STATE_FILE = Path("last_video_id.txt")

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}


def request_text(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "ru-RU,ru;q=0.9"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8", "replace")


def videos_from_rss():
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={YOUTUBE_CHANNEL}"
    root = ET.fromstring(request_text(url))
    videos = []
    for entry in root.findall("atom:entry", NS):
        video_id = entry.find("yt:videoId", NS).text
        title = entry.find("atom:title", NS).text
        videos.append({"id": video_id, "title": title})
    return videos


def videos_from_channel_page():
    """Fallback used when YouTube's RSS endpoint is temporarily unavailable."""
    page = request_text(f"https://www.youtube.com/channel/{YOUTUBE_CHANNEL}/videos")
    ids = list(dict.fromkeys(re.findall(r'"videoId":"([A-Za-z0-9_-]{11})"', page)))
    return [{"id": video_id, "title": None} for video_id in ids[:30]]


def get_recent_videos():
    try:
        videos = videos_from_rss()
        if videos:
            print("[yt] Source: RSS")
            return videos
    except Exception as error:
        print(f"[yt] RSS unavailable, using channel page: {error}")

    videos = videos_from_channel_page()
    print("[yt] Source: channel /videos page")
    return videos


def get_video_metadata(video):
    page = request_text(f"https://www.youtube.com/watch?v={video['id']}")

    short_match = re.search(r'"isShortsEligible":(true|false)', page)
    status_match = re.search(r'"playabilityStatus":\{"status":"([^"]+)"', page)
    title_match = re.search(r"<title>(.*?)</title>", page, re.DOTALL)

    if not short_match or not status_match:
        raise RuntimeError("YouTube did not return complete video metadata")

    title = video.get("title")
    if not title and title_match:
        title = html_lib.unescape(title_match.group(1)).removesuffix(" - YouTube").strip()

    return {
        **video,
        "title": title or "Новое видео",
        "is_short": short_match.group(1) == "true",
        "is_playable": status_match.group(1) == "OK",
    }


def get_horizontal_ids():
    """IDs listed on /videos; YouTube keeps Shorts on a separate tab."""
    return {video["id"] for video in videos_from_channel_page()}


def load_processed_ids():
    if not VIDEO_STATE_FILE.exists():
        return set()
    return {
        value.strip()
        for value in VIDEO_STATE_FILE.read_text(encoding="utf-8").splitlines()
        if value.strip()
    }


def save_processed_ids(processed_ids):
    # Keep enough history to survive RSS reorderings and switching to fallback mode.
    values = sorted(processed_ids)[-250:]
    VIDEO_STATE_FILE.write_text("\n".join(values) + "\n", encoding="utf-8")


def make_post(video):
    return (
        f"🌿 Новое видео\n\n"
        f"{video['title']}\n\n"
        "Иногда тело понимает происходящее раньше, чем мы успеваем это назвать. "
        "В новом видео разбираемся, что стоит за этим сигналом и как вернуть себе опору.\n\n"
        f"▶️ Смотреть: https://youtu.be/{video['id']}\n\n"
        "@womennjldf"
    )


def send_telegram(text):
    payload = json.dumps({"chat_id": TELEGRAM_CHAT, "text": text}).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.loads(response.read()).get("ok", False)


def main():
    if not TELEGRAM_TOKEN:
        print("[yt] TELEGRAM_TOKEN secret is missing")
        return

    try:
        videos = get_recent_videos()
    except Exception as error:
        # YouTube failure must never prevent scheduled-post state from being saved.
        print(f"[yt] Cannot load channel: {error}")
        return

    if not videos:
        print("[yt] No videos found")
        return

    processed = load_processed_ids()
    visible_ids = {video["id"] for video in videos}
    try:
        horizontal_ids = get_horizontal_ids()
    except Exception as error:
        horizontal_ids = set()
        print(f"[yt] Cannot load /videos filter: {error}")

    if not processed:
        processed.update(visible_ids)
        save_processed_ids(processed)
        print("[yt] First run: synchronized without posting old videos")
        return

    if len(processed) == 1:
        # Migrate the legacy single-ID state without publishing the accumulated
        # backlog.  Only the newest current video remains eligible for posting.
        processed.update(video["id"] for video in videos[1:])
        save_processed_ids(processed)
        print("[yt] Migrated legacy state; old video backlog was skipped")

    if not (processed & visible_ids):
        # State may contain only a Short while fallback /videos contains long videos.
        # Mark the old history and leave only the newest video for normal processing.
        processed.update(video["id"] for video in videos[1:])
        save_processed_ids(processed)
        print("[yt] Migrated video history; newest video will be checked")

    for video in reversed(videos):
        if video["id"] in processed:
            continue

        if video["id"] in horizontal_ids:
            # RSS contains only published entries, and /videos excludes Shorts.
            metadata = {
                **video,
                "title": video.get("title") or "Новое видео",
                "is_short": False,
                "is_playable": True,
            }
        else:
            try:
                metadata = get_video_metadata(video)
            except Exception as error:
                # If the watch page is reduced on a cloud runner and the ID is
                # absent from /videos, treat it as a Short and never publish it.
                processed.add(video["id"])
                save_processed_ids(processed)
                print(f"[yt] Not listed under /videos; skipped: {video['id']} ({error})")
                continue

        if metadata["is_short"]:
            processed.add(video["id"])
            save_processed_ids(processed)
            print(f"[yt] Short skipped: {video['id']}")
            continue

        if not metadata["is_playable"]:
            print(f"[yt] Video is not public yet: {video['id']}")
            return

        try:
            sent = send_telegram(make_post(metadata))
        except Exception as error:
            print(f"[yt] Telegram error for {video['id']}; will retry: {error}")
            return

        if not sent:
            print(f"[yt] Telegram rejected {video['id']}; will retry")
            return

        processed.add(video["id"])
        save_processed_ids(processed)
        print(f"[yt] Posted horizontal video: {video['id']}")


if __name__ == "__main__":
    main()
