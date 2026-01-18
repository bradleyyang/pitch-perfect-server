# Pitch Perfect — Backend & Agent Architecture Spec

## 1. Overview
This document captures the backend responsibilities, AI agent pipeline, evaluation schema, and prompt guidance powering the Pitch Perfect product. It can be reused when re-implementing the system in a new repository while preserving the Multimodal evaluation logic built around Gemini and ElevenLabs.

### Goals

* Persist evaluation jobs, allow uploads, and manage async processing via a Next.js API or standalone backend.
* Coordinate Gemini + ElevenLabs agents (deck critique, delivery, speech content, audio, voice, transcription, voice narration).
* Surface metrics, highlights, structured recommendations, and coach narration scripts for TTS playback.

## 2. Backend Components

### 2.1 Job persistence (`job-store`)

* Stores jobs, results, and uploads inside a `.data` directory (or database when scaling).
* Exposes:
  * `createJob({id, target, input, media})` -> writes job JSON file (`jobs/{id}.json`).
  * `updateJob(id, data)` -> merges updates.
  * `saveResult(id, result)` -> writes `results/{id}.json`.
  * `getJob`, `getResult`.
  * `persistUpload(...)` -> saves uploaded files (`uploads/{id}-{name}`).
  * `updateJobStatus(id, status, error?)`.

### 2.2 Evaluation REST endpoints

* `POST /api/evaluate/start`:
  * Accepts multipart data: `target`, `context`, `deck`, `metadata`, `transcript`, `media`.
  * Extracts deck text (via PDF parser) when provided.
  * Persists uploads via `persistUpload`.
  * Creates job record and launches `runAgentWorkflow`.
  * Returns `{ jobId, statusUrl }`.

* `GET /api/evaluate/status/:jobId`:
  * Returns job metadata plus `result` once available (after `runAgentWorkflow` completes).

* Any new backend (Express/FastAPI) should honor this contract and reuse the `job-store` and workflow logic to avoid duplication.

### 2.3 Agent orchestrator (`agent-workflow`)

* Core responsibilities:
  * Prepares audio via `prepareAudioForAgent` (finds `audioPath`, metadata, MIME type).
  * Determines transcript: user input > ElevenLabs STT > Gemini transcription. Stores `transcriptInfo`.
  * Calls Gemini audio analysis; stores summaries & file handles (to avoid re-uploading).
  * Runs LangGraph state graph with agents: deck, text (delivery), speech content, transcription, audio, voice, combine.
  * Combines outputs; logs warnings; persists `EvaluationReport`.

## 3. Agent Definitions & Prompts

Each agent is backed by a `prompts/*.txt` file describing the schema and rules. All prompts expect strict JSON responses and rely on Gemini/ElevenLabs.

### 3.1 Deck Agent (`prompts/deck-agent.txt`)

* Input: deck text + context.
* Schema: `overallScore`, five category scores (narrative, structure, visuals, clarity, persuasiveness), strengths, gaps, slideNotes.
* Rules: cite slide text, identify missing fundamentals (problem/solution/traction/market), provide actionable slide notes (8+), avoid markdown.

### 3.2 Delivery (text) Agent (`prompts/text-agent.txt`)

* Input: transcript + context.
* Schema: `overallScore`, `clarity`, `pacing`, `confidence`, `engagement`, `vocalDelivery`, `bodyLanguage`.
* Rules: default scores mid-60s; penalize fillers/weak close; include improvement suggestion in each rationale; cite transcript quotes/timestamps.

### 3.3 Speech Content Agent (`prompts/speech-content-agent.txt`)

* Input: transcript (or audio summary if transcript missing) + context.
* Schema: `overallScore`, `storyArc`, `valueProp`, `differentiation`, `ask`.
* Rules: scores 40-75 unless outstanding; cite transcript snippets; provide per-category rationale (observation, impact, fix); include two evidences.

### 3.4 Audio Agent (`prompts/audio-agent.txt`)

* Input: transcript (if available), audio metadata, Gemini audio summary.
* Schema: `overallScore`, array of `issues` (timestamp/type/description/severity), `metrics` (pace, filler words, silence ratio, avg volume).
* Rules: default mid-60s, avoid 90+ without strong evidence; produce 6-10 issues (incl. strengths); link metrics to timestamps; penalize filler/lack of energy.

### 3.5 Voice Agent (`prompts/voice-agent.txt`)

* Input: transcript, audio metadata, audio summary.
* Schema: Category scores for tone, cadence, confidence, clarity, articulation, vocabulary, conviction + `overallSummary`.
* Rules: evidence-backed, mention metadata metrics, integrate timestamps, keep wording ASCII.

### 3.6 Transcription Agent (`prompts/transcription-agent.txt`)

* Input: transcript + audio summary.
* Schema: `overallScore`, `clarity`, `relevance`, `structure`, `highlights`, `risks`, `recommendations`.
* Rules: default mid-60s, cite transcript quotes/timestamps, highlight risks/gaps, provide copy revisions, note whether tone matches audio.

### 3.7 Combine Agent (`prompts/combine-agent.txt`)

* Input: JSON strings from deck/text/speech/audio/voice/transcription agents.
* Schema:
  ```
  {
    summary: {...},
    timeline: [...],
    recommendations: [...],
    voiceScripts: [{ persona, tone, script }]
  }
  ```
* Rules:
  * Heavily weight poorest modality; drop overall score 5-15pts if any <60/high severity.
  * Provide 6-8 recommendations (3-5 action items each), 6-10 timeline events, balanced highlights/risks.
  * Voice scripts: two personas (`encouraging`, `harsh`), 2-4 sentences, include concrete action. Scripts should not repeat summary verbatim.

## 4. Evaluation Report Schema

Key fields:

* `summary`: overallScore/headline/highlights/risks.
* `pitchDeck`, `delivery`, `speechContent`, `audio`, `voice`, `transcription`: agent outputs.
* `timline`, `recommendations`.
* `voiceNarrations`: array of persona scripts for ElevenLabs TTS.
* `transcript`: info about transcript source (user/elevenlabs/gemini).
* `meta`: model/timestamp/target.

## 5. Gemini & ElevenLabs Integration

### 5.1 Gemini

* `agent-llm` abstracts `callGeminiJson`.
* `audio-analysis` handles file uploads, ensures active file, transcribes and analyzes audio via `gemini-2.0-flash-lite`.
* Use `withGeminiRetry` to gracefully back off on quota errors.
* Combiner uses `voiceScripts` and `voiceNarrations` for TTS sequences.

### 5.2 ElevenLabs

* `transcription.ts` calls ElevenLabs Scribe v2 (fallback when Gemini transcription fails) and returns text/segments.
* `ANG workflow` ensures voice TTS scripts target encouraging/harsh voices (IDs stored in env).
* UI plan: display script text w/ persona tags, route to ElevenLabs for audio output.

## 6. Frontend Presentation (For Reference)

* Summary panel shows overall score, headline, highlights/risks, top recommendations, warnings.
* Speech content -> deck -> delivery/audio -> voice -> transcription cards.
* Voice card also surfaces coach narration scripts.
* Raw JSON toggled via button.

## 7. Environment Variables

* `GEMINI_API_KEY`, `GEMINI_AUDIO_MODEL`.
* `ELEVENLABS_API_KEY`, `ELEVENLABS_STT_ENDPOINT`, `ELEVENLABS_STT_MODEL`.
* Optional envs for voice persona IDs when 11Labs TTS implemented.

## 8. Next Steps for New Repo

1. Implement job persistence + REST endpoints (matching contracts above). Use shared logic if possible.
2. Port agent workflow, LLM abstractions, prompts, and evaluation schema.
3. Build `audio-analysis`, `transcription`, `agent-llm` helpers for Gemini/11Labs.
4. Add UI or CLI to inspect EvaluationReport, tests for prompts, and integration with ElevenLabs TTS for coach narration.

Use this spec as context when adding features to the new repo so the multi-agent evaluation/integration logic remains consistent with the existing behavior. 
