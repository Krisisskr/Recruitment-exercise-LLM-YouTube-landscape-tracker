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
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

# GitHub Models Inference API (Free, no IP block)
GITHUB_MODEL = "gpt-4o-mini"
GITHUB_INFERENCE_URL = "https://models.inference.ai.azure.com/chat/completions"

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
    if not SUPADATA_API_KEY:
        return "[Supadata API key missing]"
    headers = {"x-api-key": SUPADATA_API_KEY}
    params = {"videoId": video_id, "lang": "en"}
    try:
        response = requests.get("https://api.supadata.ai/v1/youtube/transcript",
                                headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        if "content" in data:
            full_text = " ".join([item.get("text", "") for item in data["content"]])
            return full_text if full_text else "[Transcript empty]"
        else:
            return "[No transcript available]"
    except Exception as e:
        print(f"      Transcript error: {e}")
        return "[Transcript unavailable]"


def generate_summary_with_github_model(text):
    """Use GitHub Models (GPT-4o-mini) to summarize."""
    if not text or text.startswith("["):
        return "[No transcript available]"

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": GITHUB_MODEL,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that summarizes YouTube video transcripts in 2-3 concise English sentences. Focus on the main topic and key takeaways."},
            {"role": "user", "content": f"Summarize the following transcript:\n\n{text[:3000]}"}
        ],
        "max_tokens": 150,
        "temperature": 0.3
    }

    try:
        response = requests.post(GITHUB_INFERENCE_URL, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            result = response.json()
            summary = result["choices"][0]["message"]["content"].strip()
            return summary
        else:
            print(f"      GitHub Model error: {response.status_code} - {response.text}")
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
        for video in videos:
            print(f"  Fetching transcript: {video['title']}")
            transcript = get_transcript(video["video_id"])
            video["transcript_preview"] = transcript[:300] + "..." if len(transcript) > 300 else transcript

            print(f"  Generating summary via GitHub Models...")
            summary = generate_summary_with_github_model(transcript)
            video["ai_summary"] = summary

            all_videos.append(video)
            time.sleep(1)

    output_data = {
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "videos": all_videos
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"Done. Processed {len(all_videos)} videos.")


if __name__ == "__main__":
    main()
