import os
import json
import subprocess
import tempfile
import glob
import requests
import time
from datetime import datetime
from googleapiclient.discovery import build

# -------------------------------
# Configuration
# -------------------------------
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "openrouter/free"

youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

# Handles of channels that reliably have English captions
CHANNEL_HANDLES = [
    "TwoMinutePapers",   # Always has manual English captions
    "YannicKilcher",     # Paper explanation videos usually have captions
]

MAX_VIDEOS_PER_CHANNEL = 3   # Keep it small to stay within free API limits


def get_channel_id_from_handle(handle):
    try:
        request = youtube.channels().list(part="id", forHandle=handle)
        response = request.execute()
        items = response.get("items", [])
        return items[0]["id"] if items else None
    except Exception:
        return None


def get_uploads_playlist_id(channel_id):
    try:
        request = youtube.channels().list(part="contentDetails", id=channel_id)
        response = request.execute()
        return response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    except Exception:
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
    except Exception:
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


def get_transcript_ytdlp(video_id):
    """
    Use yt-dlp to download English subtitles. Returns transcript text or None.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    with tempfile.TemporaryDirectory() as tmpdir:
        cmd = [
            "yt-dlp",
            "--skip-download",
            "--write-subs",
            "--write-auto-subs",
            "--sub-lang", "en",
            "--sub-format", "vtt",
            "--output", f"{tmpdir}/subs",
            "--no-warnings",
            url
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=60)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            return None

        vtt_files = glob.glob(os.path.join(tmpdir, "*.vtt"))
        if not vtt_files:
            return None

        try:
            with open(vtt_files[0], "r", encoding="utf-8") as f:
                content = f.read()
            # Simple VTT parsing
            lines = content.splitlines()
            text_lines = []
            for line in lines:
                line = line.strip()
                if not line or line == "WEBVTT" or "-->" in line or line.isdigit():
                    continue
                text_lines.append(line)
            transcript = " ".join(text_lines)
            return transcript[:4000] if transcript else None
        except Exception:
            return None


def generate_summary_openrouter(text):
    if not text:
        return "[No transcript available]"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/YOUR_USERNAME/llm-youtube-tracker",
        "X-Title": "LLM YouTube Tracker"
    }
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": "Summarize in 2-3 English sentences, focusing on LLM/AI topics."},
            {"role": "user", "content": f"Summarize:\n{text[:3000]}"}
        ],
        "max_tokens": 150,
        "temperature": 0.3
    }

    try:
        resp = requests.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=60)
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
            print(f"  Transcript for: {video['title'][:50]}...")
            transcript = get_transcript_ytdlp(video["video_id"])
            if transcript:
                video["transcript_preview"] = transcript[:300] + "..."
                summary = generate_summary_openrouter(transcript)
                video["ai_summary"] = summary
            else:
                video["transcript_preview"] = "[Transcript unavailable]"
                video["ai_summary"] = "[No transcript available]"
            all_videos.append(video)
            time.sleep(2)   # Avoid rate limits

    output_data = {
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "videos": all_videos
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"Done. Processed {len(all_videos)} videos.")


if __name__ == "__main__":
    main()
