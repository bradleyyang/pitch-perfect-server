from dotenv import load_dotenv
import os
from dotenv import load_dotenv
from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs
from io import BytesIO
import uuid
import speech_to_text
load_dotenv()

elevenlabs = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))


def createVoice(pathToAudio):
    voice = elevenlabs.voices.ivc.create(
        name="My Voice Clone",
        # Replace with the paths to your audio files.
        # The more files you add, the better the clone will be.
        files=[BytesIO(open(pathToAudio, "rb").read())]
    )
    speech = speech_to_text.speechToText(pathToAudio)
    text = speech['Transcription'] 
    return voice.voice_id


def TextToSpeech(text, voice_id="Mu5jxyqZOLIGltFpfalg"):
    # Calling the text_to_speech conversion API with detailed parameters
    response = elevenlabs.text_to_speech.convert( 
        voice_id=voice_id,
        output_format="mp3_22050_32",
        text=text,
        model_id="eleven_turbo_v2_5", # use the turbo model for low latency
        # Optional voice settings that allow you to customize the output
        voice_settings=VoiceSettings(
            stability=0.0,
            similarity_boost=1.0,
            style=0.0,
            use_speaker_boost=True,
            speed=1.0,
        ),
    )
    save_file_path = f"{uuid.uuid4()}.mp3"

    with open(save_file_path, "wb") as f:
        for chunk in response:
            if chunk:
                f.write(chunk)
    print(f"{save_file_path}: A new audio file was saved successfully!")

    return save_file_path