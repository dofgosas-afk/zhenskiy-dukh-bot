"""
YouTube → Telegram монитор — Женский Дух
GitHub Actions: запускается раз в 30 минут, постит если вышло новое видео
"""
import urllib.request
import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

TELEGRAM_TOKEN  = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT   = "@womennjldf"
YOUTUBE_CHANNEL = "UCzR5VXsj_6HcGsnKpvgwdiQ"
LAST_ID_FILE    = Path("last_video_id.txt")
MSK = timezone(timedelta(hours=3))


def get_latest_video():
    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={YOUTUBE_CHANNEL}"
    try:
        req = urllib.request.Request(rss_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            xml_data = r.read()
        ns = {
            'atom':  'http://www.w3.org/2005/Atom',
            'yt':    'http://www.youtube.com/xml/schemas/2015',
            'media': 'http://search.yahoo.com/mrss/'
        }
        root = ET.fromstring(xml_data)
        entries = root.findall('atom:entry', ns)
        if not entries:
            return None
        e = entries[0]
        video_id = e.find('yt:videoId', ns).text
        title    = e.find('atom:title', ns).text
        return {"id": video_id, "title": title, "url": f"https://youtu.be/{video_id}"}
    except Exception as ex:
        print(f"[yt] RSS ошибка: {ex}")
        return None


def load_last_id():
    if LAST_ID_FILE.exists():
        return LAST_ID_FILE.read_text(encoding="utf-8").strip()
    return None


def save_last_id(video_id):
    LAST_ID_FILE.write_text(video_id, encoding="utf-8")


def make_post(video):
    title = video["title"]
    url   = video["url"]
    title_lower = title.lower()
    if any(w in title_lower for w in ["тело", "психосоматик", "боль"]):
        emoji, hook = "🌿", "Твоё тело говорит с тобой. Умеешь ли ты его слышать?"
    elif any(w in title_lower for w in ["мужчин", "он ", "отношени", "притяжен", "забыть", "уходит"]):
        emoji, hook = "🌙", "То, о чём обычно не говорят вслух — но все чувствуют."
    elif any(w in title_lower for w in ["старен", "молодост", "возраст", "теломер"]):
        emoji, hook = "✨", "Наука открыла то, что женщины чувствовали всегда."
    elif any(w in title_lower for w in ["слов", "мысл", "говор"]):
        emoji, hook = "💫", "Слова, которые ты говоришь себе — меняют всё."
    elif any(w in title_lower for w in ["уровень", "жизн", "измени"]):
        emoji, hook = "🔥", "Механизм, который управляет твоей жизнью — внутри тебя."
    elif any(w in title_lower for w in ["скрывал", "знани", "тайн"]):
        emoji, hook = "🌑", "Это знали тысячи лет назад. Потом убрали из учебников."
    else:
        emoji, hook = "🌿", "Новый разбор — глубже, чем кажется."

    return (
        f"{emoji} Новое видео\n\n"
        f"{title}\n\n"
        f"{hook}\n\n"
        f"▶️ {url}\n\n"
        f"Если это отозвалось — в канале разбираю такие темы ещё глубже 🌿"
    )


def send_telegram(text):
    api_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({"chat_id": TELEGRAM_CHAT, "text": text}).encode("utf-8")
    req = urllib.request.Request(api_url, data=payload,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception as e:
        print(f"[yt] Telegram ошибка: {e}")
        return False


def main():
    if not TELEGRAM_TOKEN:
        print("[yt] TELEGRAM_TOKEN не задан!")
        return

    now = datetime.now(MSK)
    print(f"[yt] MSK: {now.strftime('%d.%m.%Y %H:%M')}")

    video = get_latest_video()
    if not video:
        print("[yt] Не удалось получить RSS")
        return

    print(f"[yt] Последнее видео: {video['title']}")
    last_id = load_last_id()

    if last_id is None:
        save_last_id(video["id"])
        print(f"[yt] Первый запуск — запомнил ID {video['id']}")
        return

    if video["id"] == last_id:
        print("[yt] Новых видео нет")
        return

    print(f"[yt] НОВОЕ ВИДЕО! Постю...")
    if send_telegram(make_post(video)):
        save_last_id(video["id"])
        print(f"[yt] ✓ Пост отправлен")


if __name__ == "__main__":
    main()
