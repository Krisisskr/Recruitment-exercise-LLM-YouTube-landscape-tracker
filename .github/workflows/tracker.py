import feedparser
import subprocess
import json
import os
import requests
from datetime import datetime

# ====== Add YouTube Channel IDs you want to track ======
CHANNEL_IDS = [
    "UCsBjURrPoezykLs9EqgamOA",  # Fireship
    "UCvKRFNawVcuz4b9ihUTApCg",  # AI Explained
]
# ========================================================

DATA_FILE = "docs/data.json"
HTML_FILE = "docs/index.html"

# Cloudflare Workers AI settings
ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN")
API_URL = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/@cf/meta/llama-3-8b-instruct"

def get_latest_videos():
    """Fetch latest 2 videos from each channel via RSS feed."""
    videos = []
    for cid in CHANNEL_IDS:
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
        feed = feedparser.parse(url)
        for entry in feed.entries[:2]:
            videos.append({
                "id": entry.id,
                "title": entry.title,
                "url": entry.link,
                "published": entry.published,
                "channel": feed.feed.title
            })
    return videos

def get_transcript(url):
    """Download English subtitles (auto-generated if manual not available)."""
    try:
        cmd = [
            "yt-dlp", "--write-auto-sub", "--sub-lang", "en",
            "--sub-format", "vtt", "--skip-download",
            "--print", "after_move:requested_subtitles.en.url",
            url
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        sub_url = result.stdout.strip()
        if sub_url:
            import urllib.request
            content = urllib.request.urlopen(sub_url).read().decode('utf-8')
            # Basic VTT cleanup
            lines = []
            for line in content.split('\n'):
                if '-->' not in line and line.strip() and not line.startswith('WEBVTT'):
                    lines.append(line.strip())
            return " ".join(lines)[:4000]  # Limit for AI input
    except Exception as e:
        print(f"Subtitle fetch failed: {e}")
    return None

def analyze_with_cloudflare(title, transcript):
    """Use Cloudflare Workers AI (free) to summarize the video."""
    if not ACCOUNT_ID or not API_TOKEN:
        print("Missing Cloudflare credentials")
        return {"speaker": "Unknown", "topics": ["Error"], "llm_point": "Missing API keys"}
    
    prompt = f"""Based on the video transcript excerpt, return a JSON summary.
Video Title: {title}
Transcript excerpt: {transcript}

Output only JSON in this format (no extra text):
{{"speaker":"Channel or main speaker","topics":["Topic1","Topic2"],"llm_point":"One sentence about the LLM-related main point."}}
"""
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 300
    }
    
    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            result = response.json()
            text = result.get("result", {}).get("response", "")
            # Extract JSON from response
            start = text.find('{')
            end = text.rfind('}') + 1
            if start != -1 and end != 0:
                return json.loads(text[start:end])
    except Exception as e:
        print(f"Cloudflare AI failed: {e}")
    
    return {"speaker": "Unknown", "topics": ["Uncategorized"], "llm_point": "Analysis failed"}

def load_existing_data():
    """Load previously saved data."""
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_data(data):
    """Save data to JSON file."""
    os.makedirs("docs", exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def generate_html(data):
    """Generate a simple HTML table."""
    html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>LLM YouTube Tracker</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
        th { background-color: #4CAF50; color: white; }
        tr:nth-child(even) { background-color: #f2f2f2; }
        a { color: #1a73e8; }
        .topic { background: #e0e0e0; padding: 4px 8px; margin: 2px; border-radius: 12px; display: inline-block; font-size: 0.9em; }
    </style>
</head>
<body>
    <h1>🤖 LLM YouTube Channel Tracker</h1>
    <p>Last updated: """ + datetime.now().strftime("%Y-%m-%d %H:%M") + """</p>
    <table>
        <tr><th>Channel</th><th>Video Title</th><th>Speaker</th><th>Topics</th><th>LLM Core Point</th></tr>
"""
    for item in data:
        topics_html = " ".join([f'<span class="topic">{t}</span>' for t in item.get("topics", [])])
        html += f"""
        <tr>
            <td>{item.get('channel', '')}</td>
            <td><a href="{item.get('url', '#')}" target="_blank">{item.get('title', '')}</a></td>
            <td>{item.get('speaker', '')}</td>
            <td>{topics_html}</td>
            <td>{item.get('llm_point', '')}</td>
        </tr>"""
    
    html += """
    </table>
</body>
</html>"""
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)

def main():
    print("Fetching latest videos...")
    new_videos = get_latest_videos()
    
    print("Loading existing data...")
    existing = load_existing_data()
    existing_ids = {v["id"] for v in existing}
    
    for v in new_videos:
        if v["id"] in existing_ids:
            print(f"Skipping already processed: {v['title']}")
            continue
        
        print(f"Processing: {v['title']}")
        transcript = get_transcript(v["url"])
        if transcript:
            analysis = analyze_with_cloudflare(v["title"], transcript)
            v.update(analysis)
        else:
            v["speaker"] = v["channel"]
            v["topics"] = ["No subtitles"]
            v["llm_point"] = "Transcript unavailable"
        
        existing.append(v)
        existing_ids.add(v["id"])
    
    print("Saving data...")
    save_data(existing)
    print("Generating website...")
    generate_html(existing)
    print("Done!")

if __name__ == "__main__":
    main()
