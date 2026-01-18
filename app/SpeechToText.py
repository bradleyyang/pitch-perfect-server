from dotenv import load_dotenv
import os
import requests
from elevenlabs.client import ElevenLabs
import syllables  
import librosa
import numpy as np

load_dotenv()

elevenlabs = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))

def track_loudness_deviation(audioPath, frame_length=512, hop_length=256):
    # Load audio
    y, sr = librosa.load(audioPath, sr=None)

    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
    rms_db = librosa.amplitude_to_db(rms, ref=np.max) # Convert to dB for better visualization

    # Get time axis for plotting
    times = librosa.times_like(rms_db, sr=sr, hop_length=hop_length)

    result = []
    for time,db in zip(times,rms_db):
        result.append([float(time),float(db)])


    return result

def get_most_frequent_speed(analysisWords):
    speed_counts = {}
    
    for word_data in analysisWords:
        speed = word_data[1]
        speed_counts[speed] = speed_counts.get(speed, 0) + 1
    
    if not speed_counts:
        return None
    
    most_frequent_speed = max(speed_counts, key=speed_counts.get)
    return most_frequent_speed

def speechToText(audioSource):
    with open(audioSource, "rb") as audioData:
        transcription = elevenlabs.speech_to_text.convert(
            file=audioData,
            model_id="scribe_v2",
        )

    
    
    # The transcription object contains both text and word-level timestamps
    result = {
        "text": transcription.text,
        "words": []
    }
    
    if hasattr(transcription, 'words') and transcription.words:
        for word in transcription.words:
            result["words"].append({
                "word": word.text,
                "start": word.start,
                "end": word.end
            })
    
    analysisWords = []
    timeStamps = []
    
    for word in result["words"]:
        time = word["end"] - word["start"]
        timeWord = word['end']


        
        if time <= 0 or word["word"] == ' ':
            continue
        
        # Count syllables in the word
        syllable_count = syllables.estimate(word["word"])
        if syllable_count == 0:
            syllable_count = 1  # Default to 1 if estimation fails
        
        # Calculate syllables per second
        syllables_per_second = syllable_count / time
        
        # Convert to syllables per minute for easier interpretation
        syllables_per_minute = syllables_per_second * 60

        if syllables_per_minute<130:
            syllables_per_minute = 300
        
        timeStamps.append([timeWord, syllables_per_minute])
    
        if syllables_per_minute < 130:
            speed = "Too Slow"
        elif 130 <= syllables_per_minute <= 300:
            speed = "Ideal"
        elif 300 < syllables_per_minute <= 400:
            speed = "Fast"
        else:  # > 300
            speed = "Too Fast"

        analysis = [word["word"],speed]
        
        analysisWords.append(analysis)
    
    dbGraph = track_loudness_deviation()
    return {"Transcription": transcription.text,
            "Word Analysis": analysisWords,
            "Timestamps": timeStamps,
            "Loudness": dbGraph
            }




