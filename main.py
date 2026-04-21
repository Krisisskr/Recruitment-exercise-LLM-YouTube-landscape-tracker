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
HF_API_TOKEN = os.environ.get("HF_API_TOKEN")

# API endpoints
SUPADATA_TRANSCRIPT_URL = "https://api.supadata.ai/v1/youtube/transcript"
HF_SUMMARIZATION_MODEL = "facebook/bart-large-cnn"
HF_API_URL = f"https://api-inference.huggingface.co/models/{HF_SUMMARIZATION_MODEL}"

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

# How many recent videos to fetch per channel
MAX_VIDEOS_PER_CHANNEL = 5


def get_channel_id_from_handle(handle):
    """Convert a YouTube @handle to a channel ID."""
    try:
        request = youtube.channels().list(
            part="id",
            forHandle=handle
        )
        response = request.execute()
        items = response.get("items", [])
        if not items:
            print(f"    Warning: No channel found for handle @{handle}")
            return None
        return items[0]["id"]
    except Exception as e:
        print(f"    Error fetching channel ID for @{handle}: {e}")
        return None


def get_uploads_playlist_id(channel_id):
    """Retrieve the uploads playlist ID for a given YouTube channel."""
    try:
        request = youtube.channels().list(
            part="contentDetails",
            id=channel_id
        )
        response = request.execute()
        if not response.get("items"):
            print(f"    Warning: No channel details for ID {channel_id}")
            return None
        return response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    except Exception as e:
        print(f"    Error fetching playlist for channel {channel_id}: {e}")
        return None


def get_recent_videos(channel_id, max_results=MAX_VIDEOS_PER_CHANNEL):
    """Fetch the most recent videos from a channel's uploads playlist."""
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
        print(f"    Error fetching playlist items: {e}")
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
    """Retrieve English transcript using Supadata API."""
    if not SUPADATA_API_KEY:
        return "[Supadata API key missing]"

    headers = {
        "x-api-key": SUPADATA_API_KEY
    }
    params = {
        "videoId": video_id,
        "lang": "en"
    }

    try:
        response = requests.get(SUPADATA_TRANSCRIPT_URL, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if "content" in data:
            full_text = " ".join([item.get("text", "") for item in data["content"]])
            return full_text if full_text else "[Transcript empty]"
        else:
            return "[No transcript available]"
    except Exception as e:
        print(f"      Transcript fetch error: {e}")
        return "[Transcript unavailable]"


def generate_summary(text, max_retries=2):
    """
    Call Hugging Face Inference API with retry logic and proper text truncation.
    Bart model has a 1024 token limit (~4000 chars max input).
    """
    if not text or text.startswith("[") or text == "[Transcript empty]":
        return "[No transcript available]"

    # Truncate text to safe length for BART (approx 1024 tokens)
    truncated_text = text[:3800]

    headers = {
        "Authorization": f"Bearer {HF_API_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "inputs": truncated_text,
        "parameters": {
            "max_length": 150,
            "min_length": 30,
            "do_sample": False
        }
    }

    for attempt in range(max_retries + 1):
        try:
            response = requests.post(HF_API_URL, headers=headers, json=payload, timeout=45)
            response.raise_for_status()
            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                summary = result[0].get("summary_text", "")
                if summary:
                    return summary
            # If empty summary, retry
            if attempt < max_retries:
                time.sleep(3)
                continue
            return "[Empty summary returned]"
        except requests.exceptions.Timeout:
            if attempt < max_retries:
                print(f"      Timeout, retrying ({attempt+1}/{max_retries})...")
                time.sleep(5)
                continue
            return "[Summary timeout]"
        except Exception as e:
            if attempt < max_retries:
                print(f"      Error, retrying ({attempt+1}/{max_retries}): {e}")
                time.sleep(3)
                continue
            print(f"    Summarization error: {e}")
            return "[Summary generation failed]"
    
    return "[Summary generation failed]"


def main():
    all_videos = []

    for handle in CHANNEL_HANDLES:
        print(f"Processing handle: @{handle}")
        channel_id = get_channel_id_from_handle(handle)
        if not channel_id:
            print(f"  Skipping @{handle} (unable to resolve channel ID)")
            continue

        print(f"  Resolved channel ID: {channel_id}")
        videos = get_recent_videos(channel_id)
        if not videos:
            print(f"  No videos retrieved for @{handle}")
            continue

        for video in videos:
            print(f"    Fetching transcript: {video['title']}")
            transcript = get_transcript(video["video_id"])
            video["transcript_preview"] = transcript[:300] + "..." if len(transcript) > 300 else transcript

            print(f"    Generating summary...")
            summary = generate_summary(transcript)
            video["ai_summary"] = summary

            all_videos.append(video)
            # Small delay between requests to avoid rate limiting
            time.sleep(1)

    output_data = {
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "videos": all_videos
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"Successfully processed {len(all_videos)} videos across {len(CHANNEL_HANDLES)} channels.")


if __name__ == "__main__":
    main()
