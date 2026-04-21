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

# OpenRouter API settings
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "openrouter/free"

# YouTube API service
youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

# List of YouTube channel handles
CHANNEL_HANDLES = [
    "TwoMinutePapers",
    "AIExplained",
    "sentdex",
    "lexfridman",
    "YannicKilcher",
]

MAX_VIDEOS_PER_CHANNEL = 5
TRANSCRIPT_RETRIES = 2  # Number of retries for transcript fetching


def get_channel_id_from_handle(handle):
    try:
        request = youtube.channels().list(part="id", forHandle=handle)
        response = request.execute()
        items = response.get("items", [])
        if not items:
            print(f"    Warning: No channel found for @{handle}")
            return None
        return items[0]["id"]
    except Exception as e:
        print(f"    Error: {e}")
        return None


def get_uploads_playlist_id(channel_id):
    try:
        request = youtube.channels().list(part="contentDetails", id=channel_id)
        response = request.execute()
        if not response.get("items"):
            return None
        return response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    except Exception as e:
        print(f"    Error: {e}")
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
        print(f"    Error: {e}")
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
    """Fetch transcript with retries."""
    if not SUPADATA_API_KEY:
        return "[Supadata API key missing]"

    headers = {"x-api-key": SUPADATA_API_KEY}
    params = {"videoId": video_id, "lang": "en"}

    for attempt in range(TRANSCRIPT_RETRIES + 1):
        try:
            response = requests.get(
                "https://api.supadata.ai/v1/youtube/transcript",
                headers=headers,
                params=params,
                timeout=45
            )
            if response.status_code == 200:
                data = response.json()
                if "content" in data:
                    full_text = " ".join([item.get("text", "") for item in data["content"]])
                    return full_text if full_text else "[Transcript empty]"
                else:
                    return "[No transcript available]"
            else:
                print(f"      Transcript API status {response.status_code}, retry {attempt+1}/{TRANSCRIPT_RETRIES}")
                if attempt < TRANSCRIPT_RETRIES:
                    time.sleep(3)
        except Exception as e:
            print(f"      Transcript error (attempt {attempt+1}): {e}")
            if attempt < TRANSCRIPT_RETRIES:
                time.sleep(3)

    return "[Transcript unavailable]"


def generate_summary_with_openrouter(text):
    """Use OpenRouter's free model router to summarize."""
    if not text or text.startswith("["):
        return "[No transcript available]"
    if not OPENROUTER_API_KEY:
        return "[OpenRouter API key missing]"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/YOUR_USERNAME/llm-youtube-tracker",  # Replace with your repo
        "X-Title": "LLM YouTube Tracker"
    }

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that summarizes YouTube video transcripts in 2-3 concise English sentences. Focus on the main topic and key takeaways."},
            {"role": "user", "content": f"Summarize the following transcript:\n\n{text[:3000]}"}
        ],
        "max_tokens": 150,
        "temperature": 0.3
    }

    try:
        response = requests.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=60)
        if response.status_code == 200:
            result = response.json()
            summary = result["choices"][0]["message"]["content"].strip()
            return summary
        else:
            print(f"      OpenRouter error: {response.status_code} - {response.text}")
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
            print(f"  Fetching transcript: {video['title'][:50]}...")
            transcript = get_transcript(video["video_id"])
            video["transcript_preview"] = transcript[:300] + "..." if len(transcript) > 300 else transcript

            if transcript.startswith("["):
                video["ai_summary"] = "[No transcript available]"
            else:
                print(f"  Generating summary via OpenRouter...")
                summary = generate_summary_with_openrouter(transcript)
                video["ai_summary"] = summary

            all_videos.append(video)
            time.sleep(1)  # Be polite

    output_data = {
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "videos": all_videos
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"Done. Processed {len(all_videos)} videos.")


if __name__ == "__main__":
    main()
