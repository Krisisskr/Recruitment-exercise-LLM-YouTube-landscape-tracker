import os
import json
import requests
import time
from datetime import datetime
from googleapiclient.discovery import build

# -------------------------------
# Configuration
# -------------------------------
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
SUPADATA_API_KEY = os.environ.get("SUPADATA_API_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

SUPADATA_URL = "https://api.supadata.ai/v1/youtube/transcript"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "openrouter/free"

youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

# Core LLM channels only, keep small to conserve Supadata quota
CHANNEL_HANDLES = [
    "TwoMinutePapers",   # Concise AI paper summaries
    "AIExplained",       # In-depth AI news & analysis
    "YannicKilcher",     # AI paper walkthroughs
]

MAX_VIDEOS_PER_CHANNEL = 2  # Only 2 latest videos per channel


def get_channel_id_from_handle(handle):
    try:
        request = youtube.channels().list(part="id", forHandle=handle)
        response = request.execute()
        items = response.get("items", [])
        return items[0]["id"] if items else None
    except Exception as e:
        print(f"    Error getting channel ID: {e}")
        return None


def get_uploads_playlist_id(channel_id):
    try:
        request = youtube.channels().list(part="contentDetails", id=channel_id)
        response = request.execute()
        return response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    except Exception as e:
        print(f"    Error getting playlist: {e}")
        return None


def get_recent_videos(channel_id, max_results=MAX_VIDEOS_PER_CHANNEL):
    playlist_id = get_uploads_playlist_id(channel_id)
    if not playlist_id:
        return []
    try:
        request = youtube.playlistItems().list(
            part="snippet",
            playlistId=playlist_id,
            maxResults=max_results
        )
        response = request.execute()
    except Exception as e:
        print(f"    Error getting videos: {e}")
        return []

    videos = []
    for item in response.get("items", []):
        snippet = item["snippet"]
        video_id = snippet["resourceId"]["videoId"]
        videos.append({
            "video_id": video_id,
            "title": snippet["title"],
            "channel_name": snippet["channelTitle"],
            "published_at": snippet["publishedAt"],
            "url": f"https://www.youtube.com/watch?v={video_id}"
        })
    return videos


def get_transcript(video_id):
    """Fetch transcript from Supadata (only reliable method in GitHub Actions)."""
    if not SUPADATA_API_KEY:
        return "[Supadata API key missing]"

    headers = {"x-api-key": SUPADATA_API_KEY}
    params = {"videoId": video_id, "lang": "en"}

    try:
        resp = requests.get(SUPADATA_URL, headers=headers, params=params, timeout=45)
        if resp.status_code == 200:
            data = resp.json()
            if "content" in data:
                text = " ".join([item.get("text", "") for item in data["content"]])
                return text if text else "[Transcript empty]"
            else:
                return "[No transcript available]"
        elif resp.status_code == 429:
            print("      ⚠️ Supadata quota exceeded!")
            return "[Supadata quota exceeded]"
        else:
            print(f"      Supadata error {resp.status_code}")
            return "[Transcript unavailable]"
    except Exception as e:
        print(f"      Supadata exception: {e}")
        return "[Transcript unavailable]"


def generate_summary(text):
    if not text or text.startswith("["):
        return "[No transcript available]"
    if not OPENROUTER_API_KEY:
        return "[OpenRouter key missing]"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/YOUR_USERNAME/llm-youtube-tracker",  # Replace with your repo
        "X-Title": "LLM YouTube Tracker"
    }
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": "Summarize in 2-3 English sentences, focusing on AI/LLM topics."},
            {"role": "user", "content": f"Summarize:\n{text[:3000]}"}
        ],
        "max_tokens": 150,
        "temperature": 0.3
    }

    try:
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
        else:
            print(f"      OpenRouter error {resp.status_code}")
            return "[Summary API error]"
    except Exception as e:
        print(f"      Summary exception: {e}")
        return "[Summary generation failed]"


def main():
    all_videos = []

    for handle in CHANNEL_HANDLES:
        print(f"Processing @{handle}")
        channel_id = get_channel_id_from_handle(handle)
        if not channel_id:
            continue
        videos = get_recent_videos(channel_id)
        print(f"  Found {len(videos)} videos")
        for video in videos:
            print(f"  Transcript: {video['title'][:50]}...")
            transcript = get_transcript(video["video_id"])
            video["transcript_preview"] = transcript[:300] + "..." if len(transcript) > 300 else transcript

            if transcript.startswith("["):
                video["ai_summary"] = "[No transcript available]"
            else:
                print("  Summarizing...")
                video["ai_summary"] = generate_summary(transcript)

            all_videos.append(video)
            time.sleep(1.5)  # Slightly longer delay for safety

    output_data = {
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "videos": all_videos
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"Done. Processed {len(all_videos)} videos.")


if __name__ == "__main__":
    main()
