import os, json, requests, datetime
from youtube_transcript_api import YouTubeTranscriptApi
from openai import OpenAI
from config import YT_API_KEY, GROQ_API_KEY, CHANNELS

# Initialize Groq client (OpenAI-compatible)
client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")

def fetch_recent_videos():
    """Fetch the latest 3 videos per channel from the past 7 days."""
    videos = []
    since_date = (datetime.datetime.utcnow() - datetime.timedelta(days=7)).isoformat() + "Z"

    for ch_id in CHANNELS:
        url = f"https://www.googleapis.com/youtube/v3/search?key={YT_API_KEY}&channelId={ch_id}&part=snippet&order=date&maxResults=3&type=video&publishedAfter={since_date}"
        res = requests.get(url).json()

        for item in res.get("items", []):
            videos.append({
                "id": item["id"]["videoId"],
                "title": item["snippet"]["title"],
                "channel": item["snippet"]["channelTitle"],
                "url": f"https://youtu.be/{item['id']['videoId']}",
                "date": item["snippet"]["publishedAt"][:10]
            })
    return videos

def get_transcript(video_id):
    """Extract English subtitles. Truncates to 2500 chars to save tokens."""
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=["en"])
        full_text = " ".join([entry["text"] for entry in transcript_list])
        return full_text[:2500]
    except Exception:
        return None

def analyze_with_llm(text, title):
    """Use LLM to extract structured insights from the transcript."""
    if not text:
        return {"topics": [], "summary": "No subtitles available", "llm_angle": "N/A", "relation": "N/A"}

    prompt = f"""Video Title: {title}
Transcript Excerpt: {text}

Please return a valid JSON object with this exact structure:
{{
  "topics": ["Topic1", "Topic2"],
  "summary": "One-sentence core takeaway",
  "llm_angle": "How this video relates to LLM technology/trends",
  "relation": "Does this overlap or conflict with other tracked channels? Briefly explain, or state 'Independent view'."
}}
Return ONLY valid JSON. No markdown, no extra text."""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception:
        return {"topics": [], "summary": "Parsing failed", "llm_angle": "N/A", "relation": "N/A"}

def generate_html_table(data):
    """Render parsed data into a clean, responsive HTML table."""
    rows = ""
    for item in data:
        topics_str = ", ".join(item.get("topics", []))
        rows += f"""<tr>
          <td><a href='{item["url"]}' target='_blank'>{item["title"]}</a></td>
          <td>{item["channel"]}</td>
          <td>{topics_str}</td>
          <td>{item.get("llm_angle", "")}</td>
          <td>{item.get("relation", "")}</td>
          <td>{item["date"]}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>LLM YouTube Landscape Tracker</title>
  <style>
    body {{ font-family: system-ui, -apple-system, sans-serif; max-width: 1100px; margin: 40px auto; padding: 20px; background: #fafafa; color: #333; }}
    h2 {{ border-bottom: 2px solid #0066cc; padding-bottom: 10px; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
    th, td {{ border: 1px solid #ddd; padding: 12px 15px; text-align: left; vertical-align: top; }}
    th {{ background: #0066cc; color: #fff; font-weight: 600; }}
    tr:nth-child(even) {{ background: #f9f9f9; }}
    tr:hover {{ background: #eef6ff; }}
    a {{ color: #0066cc; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .timestamp {{ color: #666; font-size: 0.9em; margin-top: -10px; margin-bottom: 20px; }}
  </style>
</head>
<body>
  <h2>📊 LLM YouTube Landscape Tracker</h2>
  <p class="timestamp">Last updated: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
  <table>
    <tr><th>Video</th><th>Channel</th><th>LLM Topics</th><th>Core Insight</th><th>Cross-Channel Relation</th><th>Date</th></tr>
    {rows}
  </table>
</body>
</html>"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    print("🔄 Starting LLM YouTube Tracker...")
    videos = fetch_recent_videos()
    print(f"📥 Found {len(videos)} recent videos.")

    results = []
    for v in videos:
        print(f"🔍 Processing: {v['title']}")
        transcript = get_transcript(v["id"])
        analysis = analyze_with_llm(transcript, v["title"])
        v.update(analysis)
        results.append(v)

    generate_html_table(results)
    print(f"✅ Successfully updated {len(results)} entries. index.html generated.")
