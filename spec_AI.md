
# Pitch Perfect Simplified Pipeline Spec

## 1. Background
We are pivoting away from the LangGraph-heavy architecture to a straightforward backend that:

1. Accepts at least one of (deck PDF, transcript text, audio file) as input.
2. Calls Gemini (and ElevenLabs for STT when applicable) via plain API functions.
3. Produces granular feedback for each modality plus a combined summary.

Future implementation should follow this spec so the simplified experience mirrors the key insights of the old system while being easier to maintain.

## 2. High-Level Flow

1. **Input ingestion API** (`POST /api/evaluate/start`):
   * Accepts multipart/form-data: optional `deck` (PDF), optional `transcript` (text), optional `media` (audio/video). Require at least one asset.
   * Persist files to disk/storage.
   * Trigger async evaluation job (record job state, run worker/handler).
2. **Evaluation worker**:
   * Extract deck text (if PDF).
   * Resolve transcript: user-provided text > ElevenLabs STT > Gemini transcription.
   * Always run Gemini deck critique if deck text exists.
   * Always run Gemini transcript analysis if transcript exists.
   * Always run Gemini native audio evaluation (and transcription fallback if necessary) when audio file is available.
   * Combine outputs into final JSON (`EvaluationReport`).
3. **Status endpoint** (`GET /api/evaluate/status/:jobId`) returns job + results.
4. **Frontend** reads the report and renders per-modality cards plus a combined summary. Raw JSON display optional.

## 3. Prompts & GEMINI Tasks

### 3.1 Deck prompt

* Purpose: critique deck narrative, structure, visuals, clarity, persuasiveness.
* Schema: { overallScore, narrative {...}, structure {...}, visuals {...}, clarity {...}, persuasiveness {...}, strengths[], gaps[], slideNotes[] }.
* Guidance: cite deck text, call out missing fundamentals (problem, solution, traction), keep rewrite suggestions actionable.
* Prompt used: same as `prompts/deck-agent.txt`.

### 3.2 Transcript (text) prompt

* Purpose: evaluate delivery (clarity/pacing/confidence/engagement/vocalDelivery) from transcript.
* Schema: { overallScore, clarity {...}, pacing {...}, confidence {...}, engagement {...}, vocalDelivery {...}, bodyLanguage {...}}.
* Guidance: default mid-60s, cite transcript quotes, call out filler words and hedging, provide concrete improvements.
* Prompt: `prompts/text-agent.txt`.

### 3.3 Speech content prompt

* Purpose: judge story arc, value prop, differentiation, ask strength.
* Schema: { overallScore, storyArc {...}, valueProp {...}, differentiation {...}, ask {...}}.
* Guidance: keep scores between 40-75 unless extraordinary, always suggest improvements, rely on transcript sections or Gemini audio summary when transcript absent.
* Prompt: `prompts/speech-content-agent.txt`.

### 3.4 Audio prompt

* Purpose: native audio understanding (tone/pacing/filler/etc.) plus metrics/issues.
* Schema: { overallScore, issues[], metrics {paceWpm, fillerWordsPerMin, silenceRatio, avgVolumeDb}}.
* Guidance: reference timestamps, penalize missing energy/filler, include strengths and weaknesses.
* Prompt: `prompts/audio-agent.txt`.

### 3.5 Transcription prompt

* Purpose: analyze transcript language quality.
* Schema: { overallScore, clarity {...}, relevance {...}, structure {...}, highlights[], risks[], recommendations[] }.
* Guidance: require quotes, call out risks, provide actionable recommendations (copy/pacing adjustments).
* Prompt: `prompts/transcription-agent.txt`.

### 3.6 Combine prompt

* Purpose: aggregate modality outputs into final summary, timeline, recommendations, and voice scripts.
* Schema: {
  summary, timeline[], recommendations[], voiceScripts[]
 }.
* Guidance: weight weakest modality, drop overall score if any modality <60, produce coach scripts (encouraging/harsh) without repeating summary, include action items.
* Prompt: `prompts/combine-agent.txt`.

## 4. Gemini + ElevenLabs Integration

### 4.1 Audio helpers

* Implement helper to upload audio to Gemini, poll until processed, and request multimodal evaluation/transcription via `gemini-2.0-flash-lite`.
* Retry on rate-limit/quota errors with exponential backoff.

### 4.2 ElevenLabs STT

* Use when transcript input absent but audio exists.
* Endpoint: ElevenLabs Scribe v2; return text + segments.
* On failure, fall back to Gemini transcription via audio file upload.

## 5. Evaluation Report Format

```
{
  version: "1.0",
  summary: { overallScore, headline, highlights[], risks[] },
  deck?: {...agent schema...},
  transcript?: {...transcription schema...},
  delivery?: {...text schema...},
  speechContent?: {...speech schema...},
  audio?: {...audio schema...},
  voice?: {...voice schema...},
  voiceNarrations?: [{ persona, tone, script }],
  recommendations: [...],
  warnings?: [...],
  meta: { model, generatedAt, target }
}
```

The `voiceNarrations` field holds the encouraging/harsh scripts for ElevenLabs TTS.

## 6. Operational Notes

* Mandatory: at least one input is required (deck/transcript/audio) before starting evaluation.
* Processing order: deck > transcript > audio. Combine stage runs once data available.
* Errors (missing inputs, Gemini failures) should be surfaced via `warnings` and not block the entire job.

## 7. Call-to-action for new repo

1. Build simplified backend endpoints and job persistence.
2. Implement helper functions to run Gemini prompts listed above.
3. Add ElevenLabs STT as described.
4. Ensure final `EvaluationReport` follows the schema so the frontend can render summary + modality cards + voice scripts.

Use this spec when porting to the new repository to preserve the core capabilities while simplifying the infrastructure. Focus on the prompts and evaluation schema to keep feedback consistent. 
