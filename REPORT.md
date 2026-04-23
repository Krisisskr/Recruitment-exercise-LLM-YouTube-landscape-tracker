# LLM YouTube Landscape Tracker - Project Report

## 1. Problem Statement
This project addresses the requirement to automatically monitor several influential YouTube channels in the LLM space, extract the actual spoken content (via transcripts), and present the information in a continuously updated public table. The system must run autonomously and remain accessible online.

## 2. Methodology

The solution is built as a serverless, fully automated pipeline using only free-tier services.

| Component | Technology | Role |
| :--- | :--- | :--- |
| Video discovery | YouTube Data API v3 | Fetches recent video metadata from specified channel handles. |
| Transcript extraction | Supadata API | Retrieves English transcripts (chosen for reliability within GitHub Actions environment). |
| AI summarization | OpenRouter API (free model routing) | Generates concise, LLM-focused summaries from transcripts. |
| Automation & scheduling | GitHub Actions | Runs the entire pipeline once per day, committing updated data back to the repository. |
| Data storage | JSON file (`data.json`) | Serves as the single source of truth for the frontend. |
| Web presentation | GitHub Pages | Hosts a static HTML page that dynamically renders the tracking table. |

The daily workflow fetches the most recent videos from each tracked channel, obtains their English transcripts, produces AI summaries, and updates the live website without any manual steps.

The daily workflow fetches the most recent videos from each tracked channel, obtains their English transcripts, produces AI summaries, and updates the live website without any manual steps. The system updates once daily and tracks a limited number of videos per channel due to the quota constraints of the free-tier APIs used throughout this project. Scaling to more frequent updates or additional channels would require paid API subscriptions.

The website: https://krisisskr.github.io/Recruitment-exercise-LLM-YouTube-landscape-tracker/

## 3. Tracked Channels

The following YouTube channels are monitored due to their consistent focus on LLMs and AI research:

- **Two Minute Papers** (`@TwoMinutePapers`)
- **AI Explained** (`@AIExplained`)
- **Yannic Kilcher** (`@YannicKilcher`)

The system captures the latest videos from these channels once per day.

## 4. Experimental Results

### 4.1 Automation & Reliability
The GitHub Actions workflow has been running on schedule with **no manual intervention required** since deployment. The pipeline successfully completes a full refresh every day.

### 4.2 Content Extraction & Summarization
For videos where English transcripts are available, the system consistently generates relevant AI summaries focused on the core LLM or AI topics discussed.

**Example output** (Two Minute Papers – *DeepMind's New AI: A Gift To Humanity*):
> *"Google DeepMind gave an amazing gift to humanity.  And it is full of surprises. Here’s why. Today,   we are living in the age of AI where these  smart assistants and agents can do things   we could only dream of 10 years ago. But.  Many of these solutions are proprietary"*

### 4.3 Public Dashboard
The live tracking table is accessible via GitHub Pages and displays:
- Channel name
- Video title (clickable link to YouTube)
- Publication date
- Transcript preview (first ~300 characters)
- AI-generated summary

## 5. Known Limitations

Some videos may show `[Summary generation failed]` or `[No transcript available]`. This occurs when:
- The video lacks English captions entirely (common for live streams or music content).
- The free-tier summarization API occasionally times out on the first attempt.

These occurrences do not affect the overall stability or automation of the system and are expected given the zero-cost infrastructure.

## 6. Conclusion

This project successfully delivers a **fully automated, daily-updating LLM YouTube tracker** that:
- Continuously monitors key channels,
- Extracts spoken content from video transcripts,
- Produces AI-powered summaries,
- And presents everything in a publicly accessible, zero-maintenance web dashboard.

The solution meets all core requirements of the recruitment exercise while operating entirely within free service tiers.
