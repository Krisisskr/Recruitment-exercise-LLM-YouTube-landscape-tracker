import os
import json
import requests
from datetime import datetime
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi

# -------------------------------
# Configuration
# -------------------------------
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
HF_API_TOKEN = os.environ.get("HF_API_TOKEN")

# Hugging Face Inference API settings
# Using a free summarization model: facebook/bart-large-cnn
HF_SUMMARIZATION_MODEL = "facebook/bart-large-cnn"
HF_API_URL = f"https://api-inference.huggingface.co/models/{HF_SUMMARIZATION_MODEL}"

# YouTube API service
youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

# List of YouTube channel IDs to track
# Replace these with the actual channel IDs you want to monitor
CHANNEL_IDS = [
    "UCbfYPyITQ-7l4upoX8nvctg",   # Two Minute Papers
    "UCwkk7FQb5eBd5qJdM1bYxZg",   # Matt Wolfe (corrected ID)
    "UCNJ1Ymd5yFuUPW21JxO2u3g",   # AI Explained
]

# How many recent videos to fetch per channel
MAX_VIDEOS_PER_CHANNEL = 5


def get_uploads_playlist_id(channel_id):
    """
    Retrieve the uploads playlist ID for a given YouTube channel.
    Returns None if the channel is not found or quota is exceeded.
    """
    try:
        request = youtube.channels().list(
            part="contentDetails",
            id=channel_id
        )
        response = request.execute()
        if not response.get("items"):
            print(f"    Warning: No channel found for ID {channel_id}. Skipping.")
            return None
        return response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    except Exception as e:
        print(f"    Error fetching channel {channel_id}: {e}")
        return None

def get_recent_videos(channel_id, max_results=MAX_VIDEOS_PER_CHANNEL):
    """
    Fetch the most recent videos from a channel's uploads playlist.
    Returns a list of video metadata dictionaries.
    """
    playlist_id = get_uploads_playlist_id(channel_id)
    request = youtube.playlistItems().list(
        part="snippet",
        playlistId=playlist_id,
        maxResults=max_results
    )
    response = request.execute()

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
    """
    Retrieve the English transcript of a YouTube video.
    Returns the full transcript text or a fallback message if unavailable.
    """
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
        full_text = " ".join([item['text'] for item in transcript_list])
        # Limit to ~4000 characters to avoid overwhelming the summarization API
        return full_text[:4000]
    except Exception:
        return "[Transcript unavailable]"


def generate_summary(text):
    """
    Call Hugging Face Inference API to generate a concise summary.
    Returns the summary string or a fallback message on error.
    """
    if not text or text == "[Transcript unavailable]":
        return "[No transcript available for summary]"

    headers = {
        "Authorization": f"Bearer {HF_API_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "inputs": text,
        "parameters": {
            "max_length": 150,
            "min_length": 30,
            "do_sample": False
        }
    }

    try:
        response = requests.post(HF_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        # The API returns a list with one dictionary
        if isinstance(result, list) and len(result) > 0:
            return result[0].get("summary_text", "[Summary generation failed]")
        else:
            return "[Summary generation failed]"
    except Exception as e:
        print(f"Summarization error: {e}")
        return "[Summary generation failed]"

def main():
    all_videos = []

    for channel_id in CHANNEL_IDS:
        print(f"Processing channel: {channel_id}")
        videos = get_recent_videos(channel_id)   # this function already checks for None playlist
        if not videos:
            print(f"  Skipping channel {channel_id} due to errors.")
            continue

        for video in videos:
            # ... 原有的处理逻辑保持不变 ...
            print(f"  Fetching transcript for: {video['title']}")
            transcript = get_transcript(video["video_id"])
            video["transcript_preview"] = transcript[:300] + "..." if len(transcript) > 300 else transcript

            print(f"  Generating summary...")
            summary = generate_summary(transcript)
            video["ai_summary"] = summary

            all_videos.append(video)

    # Build final data structure
    output_data = {
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "videos": all_videos
    }

    # Write to data.json (will be used by the frontend)
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"Successfully processed {len(all_videos)} videos.")


if __name__ == "__main__":
    main()
