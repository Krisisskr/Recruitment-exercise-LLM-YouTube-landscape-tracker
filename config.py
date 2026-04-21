import os

# API keys are securely loaded from GitHub Secrets
YT_API_KEY = os.getenv("YT_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# YouTube Channel IDs to track
CHANNELS = [
    "UCbfYPyITQ-7l4upoX8nvctg",  # Two Minute Papers
    "UCtYLUTtgS3k1Fg4y5tAhLbw",  # Yannic Kilcher
    "UCZ9qFEC82qM6Pk-54Q4TVWA"   # Matt Wolfe
]
