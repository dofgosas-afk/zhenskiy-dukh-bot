"""Post new horizontal YouTube videos to Telegram; Shorts are skipped."""
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT = "@womennjldf"
YOUTUBE_CHANNEL = "UCzR5VXsj_6HcGsnKpvgwdiQ"
LAST_VIDEO_FILE = Path("last_video_id.txt")

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


def get_recent_videos():
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={YOUTUBE_CHANNEL}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        root = ET.fromstring(response.read())

    videos = []
    for entry in root.findall("atom:entry", NS):
        video_id = entry.find("yt:videoId", NS).text
        title = entry.find("atom:title", NS).text
        videos.append({"id": video_id, "title": title, "url": f"https://youtu.be/{video_id}"})
    return videos


def is_short(video_id):
    """YouTube marks vertical Shorts explicitly in the watch-page metadata."""
    request = urllib.request.Request(
        f"https://www.youtube.com/watch?v={video_id}",
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        page = response.read().decode("utf-8", "replace")
    match = re.search(r'"isShortsEligible":(true|false)', page)
    if not match:
        raise RuntimeError("YouTube did not return the video type")
    return match.group(1) == "true"


def load_last_id():
    return LAST_VIDEO_FILE.read_text(encoding="utf-8").strip() if LAST_VIDEO_FILE.exists() else None


def save_last_id(video_id):
    LAST_VIDEO_FILE.write_text(video_id + "\n", encoding="utf-8")


def make_post(video):
    return f"?? ????? ?????\n\n{video['title']}\n\n?? ????????: {video['url']}\n\n@womennjldf"


def send_telegram(text):
    payload = json.dumps({"chat_id": TELEGRAM_CHAT, "text": text}).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read()).get("ok", False)


def main():
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN secret is not configured")

    videos = get_recent_videos()  # newest first
    if not videos:
        print("[yt] RSS is empty")
        return

    last_id = load_last_id()
    if last_id is None:
        save_last_id(videos[0]["id"])
        print("[yt] First run: saved the current video without posting it")
        return

    ids = [video["id"] for video in videos]
    if last_id not in ids:
        # The feed keeps only a limited history.  Do not risk reposting old videos.
        save_last_id(videos[0]["id"])
        print("[yt] Previous ID is outside RSS history; synchronized without posting")
        return

    unseen = videos[:ids.index(last_id)]
    for video in reversed(unseen):  # publish in chronological order
        try:
            if is_short(video["id"]):
                print(f"[yt] Short skipped: {video['id']}")
                save_last_id(video["id"])
                continue
        except Exception as error:
            print(f"[yt] Cannot verify {video['id']}; will retry: {error}")
            return

        if not send_telegram(make_post(video)):
            print(f"[yt] Telegram rejected {video['id']}; will retry")
            return
        save_last_id(video["id"])
        print(f"[yt] Posted horizontal video: {video['id']}")


if __name__ == "__main__":
    main()
