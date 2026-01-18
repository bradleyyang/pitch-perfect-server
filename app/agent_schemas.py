from __future__ import annotations

from typing import Any, Dict, List, Tuple, Type

from pydantic import BaseModel, Field, ValidationError, conint

ScoreInt = conint(ge=1, le=100)


class SlideNote(BaseModel):
    slideNumber: int = Field(default=0)
    observation: str = Field(default="")
    suggestion: str = Field(default="")


class DeckAgent(BaseModel):
    overallScore: ScoreInt = Field(default=65)
    narrativeScore: ScoreInt = Field(default=65)
    structureScore: ScoreInt = Field(default=65)
    visualsScore: ScoreInt = Field(default=65)
    clarityScore: ScoreInt = Field(default=65)
    persuasivenessScore: ScoreInt = Field(default=65)
    strengths: List[str] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
    slideNotes: List[SlideNote] = Field(default_factory=list)


class ScoreDetail(BaseModel):
    score: ScoreInt = Field(default=65)
    rationale: str = Field(default="")


class TextAgent(BaseModel):
    overallScore: ScoreInt = Field(default=65)
    clarity: ScoreDetail = Field(default_factory=ScoreDetail)
    pacing: ScoreDetail = Field(default_factory=ScoreDetail)
    confidence: ScoreDetail = Field(default_factory=ScoreDetail)
    engagement: ScoreDetail = Field(default_factory=ScoreDetail)
    vocalDelivery: str = Field(default="")
    bodyLanguage: str = Field(default="")
    recommendations: List[str] = Field(default_factory=list)


class SpeechContentAgent(BaseModel):
    overallScore: ScoreInt = Field(default=65)
    storyArc: ScoreDetail = Field(default_factory=ScoreDetail)
    valueProp: ScoreDetail = Field(default_factory=ScoreDetail)
    differentiation: ScoreDetail = Field(default_factory=ScoreDetail)
    ask: ScoreDetail = Field(default_factory=ScoreDetail)
    evidences: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


class AudioIssue(BaseModel):
    timestamp: str = Field(default="")
    type: str = Field(default="")
    description: str = Field(default="")
    severity: str = Field(default="low")


class AudioMetrics(BaseModel):
    pace: str = Field(default="")
    fillerWords: str = Field(default="")
    silenceRatio: str = Field(default="")
    averageVolume: str = Field(default="")


class AudioAgent(BaseModel):
    overallScore: ScoreInt = Field(default=65)
    issues: List[AudioIssue] = Field(default_factory=list)
    metrics: AudioMetrics = Field(default_factory=AudioMetrics)


class VoiceAgent(BaseModel):
    overallSummary: str = Field(default="")
    tone: ScoreDetail = Field(default_factory=ScoreDetail)
    cadence: ScoreDetail = Field(default_factory=ScoreDetail)
    confidence: ScoreDetail = Field(default_factory=ScoreDetail)
    clarity: ScoreDetail = Field(default_factory=ScoreDetail)
    articulation: ScoreDetail = Field(default_factory=ScoreDetail)
    vocabulary: ScoreDetail = Field(default_factory=ScoreDetail)
    conviction: ScoreDetail = Field(default_factory=ScoreDetail)


class TranscriptAgent(BaseModel):
    overallScore: ScoreInt = Field(default=65)
    clarity: ScoreDetail = Field(default_factory=ScoreDetail)
    relevance: ScoreDetail = Field(default_factory=ScoreDetail)
    structure: ScoreDetail = Field(default_factory=ScoreDetail)
    highlights: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


class TimelineItem(BaseModel):
    timestamp: str = Field(default="")
    description: str = Field(default="")
    impact: str = Field(default="")


class RecommendationItem(BaseModel):
    title: str = Field(default="")
    actions: List[str] = Field(default_factory=list)


class VoiceScript(BaseModel):
    persona: str = Field(default="")
    tone: str = Field(default="")
    script: str = Field(default="")


class CombineSummary(BaseModel):
    overallScore: ScoreInt = Field(default=65)
    headline: str = Field(default="")
    highlights: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)


class CombineAgent(BaseModel):
    summary: CombineSummary = Field(default_factory=CombineSummary)
    timeline: List[TimelineItem] = Field(default_factory=list)
    recommendations: List[RecommendationItem] = Field(default_factory=list)
    voiceScripts: List[VoiceScript] = Field(default_factory=list)


AGENT_MODELS: Dict[str, Type[BaseModel]] = {
    "deck": DeckAgent,
    "text": TextAgent,
    "speech_content": SpeechContentAgent,
    "audio": AudioAgent,
    "voice": VoiceAgent,
    "transcription": TranscriptAgent,
    "combine": CombineAgent,
}


def validate_agent_output(agent_name: str, data: Any) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    model_cls = AGENT_MODELS.get(agent_name)
    if not model_cls:
        return data if isinstance(data, dict) else {"raw": data}, warnings

    try:
        parsed = model_cls.model_validate(data)
    except ValidationError as exc:
        warnings.append(str(exc))
        parsed = model_cls.model_validate({})

    return parsed.model_dump(), warnings
