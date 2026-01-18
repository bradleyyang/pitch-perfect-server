
import json

from google import genai
from google.genai import types

# Initialize OpenAI client
client = OpenAI()

# Sample JSON representing your audio file analysis
audio_data = {
    "file_name": "pitch_audio_01.wav",
    "duration": 120,  # in seconds
    "transcript": "Hello everyone, today I'm presenting our product...",
    "speech_features": [
        {"timestamp": 0, "clarity": 4, "pace": 3, "fillers": 1, "structure": 4},
        {"timestamp": 30, "clarity": 5, "pace": 4, "fillers": 0, "structure": 3},
        # Add more segments
    ]
}

# Prepare prompt for Gemini summarization
prompt = f"""
You are an expert presentation coach. Summarize the following pitch audio performance and provide:
1. Overall summary focusing on speech clarity, pacing, fillers, structure.
2. Detailed actionable feedback per segment with timestamps.
3. Strengths and weaknesses.
4. Ratings (1-5 scale) for each aspect.
5. Optional voice-narrated coaching tips.

Audio Data:
{json.dumps(audio_data, indent=2)}
"""

# Send request to Gemini model (free tier)
response = client.chat.completions.create(
    model="gpt-5.1-mini",  # Free Gemini model
    messages=[{"role": "user", "content": prompt}],
    temperature=0.7
)
