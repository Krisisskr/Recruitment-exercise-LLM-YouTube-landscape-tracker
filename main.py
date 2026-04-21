import os
import json
import requests
import subprocess
import tempfile
import glob
from datetime import datetime
from googleapiclient.discovery import build

# -------------------------------
# Configuration
# -------------------------------
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
HF_API_TOKEN = os.environ.get("HF_API_TOKEN")

# Hugging Face Inference API settings
HF_SUMMARIZATION_MODEL = "facebook/bart-large-cnn"
HF_API_URL = f"https://api-inference.huggingface.co/models/{HF_SUMMARIZATION_MODEL}"

# YouTube API service
youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

# List of YouTube channel handles (the part after '@' in the URL)
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
    """
    Convert a YouTube @handle to a channel ID.
    Returns None if the handle cannot be found.
    """
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
    """
    Retrieve the uploads playlist ID for a given YouTube channel.
    """
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
    """
    Fetch the most recent videos from a channel's uploads playlist.
    """
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


def get_transcript_with_ytdlp(video_id):
    """
    Use yt-dlp to download subtitles (English) for a YouTube video.
    Returns the transcript text or None if unavailable.
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
            url
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=60)
        except subprocess.TimeoutExpired:
            print("      yt-dlp timed out")
            return None
        except subprocess.CalledProcessError:
            return None

        vtt_files = glob.glob(os.path.join(tmpdir, "*.vtt"))
        if not vtt_files:
            return None

        try:
            with open(vtt_files[0], "r", encoding="utf-8") as f:
                content = f.read()
            lines = content.splitlines()
            text_lines = []
            for line in lines:
                line = line.strip()
                if not line or line == "WEBVTT" or "-->" in line:
                    continue
                if line.isdigit():
                    continue
                text_lines.append(line)
            transcript = " ".join(text_lines)
            if transcript.strip():
                return transcript[:4000]
        except Exception as e:
            print(f"      Error parsing VTT: {e}")
            return None
    return None


def get_transcript(video_id):
    """
    Retrieve English transcript using yt-dlp.
    """
    transcript = get_transcript_with_ytdlp(video_id)
    if transcript:
        return transcript
    return "[Transcript unavailable]"


def generate_summary(text):
    """
    Call Hugging Face Inference API to generate a concise summary.
    """
    if not text or text == "[Transcript unavailable]":
        return "[No transcript available]"

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
        if isinstance(result, list) and len(result) > 0:
            return result[0].get("summary_text", "[Summary generation failed]")
        else:
            return "[Summary generation failed]"
    except Exception as e:
        print(f"    Summarization error: {e}")
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

    output_data = {
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "videos": all_videos
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"Successfully processed {len(all_videos)} videos across {len(CHANNEL_HANDLES)} channels.")


if __name__ == "__main__":
    main()
