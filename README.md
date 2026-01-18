Create virtual env (it will be in a directory called `.venv`)

On mac,

```bash
python3 -m venv .venv
source .venv/bin/activate
```

on windows,

```bash
python -m venv .venv
venv\Scripts\Activate.ps1
```

Install deps,

```bash
pip install -r requirements.txt
```
> `uvloop` cannot be built on Windows, so it was removed from requirements.txt; install it manually on Linux after the base install if you need it.


To update the deps,

```bash
pip freeze > requirements.txt
```

Running the server, do

```bash
make run
```

Server is running at `http://127.0.0.1:8000`

## Evaluation Workflow

- POST `/api/evaluate/start`: submits a multipart job (`target`, `context`, optional `metadata`, `transcript`, `deck`, `media`). `target` is optional (defaults to `general`), but you still need at least one of `deck`, `media`, or `transcript`. Jobs are persisted under `.data/jobs`/`.data/uploads`, agent results land in `.data/results`, and the workflow runs Gemini + ElevenLabs agents in the background.
- GET `/api/evaluate/status/{jobId}`: returns the stored job payload plus the multi-agent report once processing completes.
   - The saved report now includes `audioAnalysis`, `agentWarnings`, `combineWarnings`, `summaryAdjustments`, and `meta.graphOrder` so clients can surface execution warnings, LangGraph order, and audio-specific insights.
   - Each transcript record identifies its source (`user`, `elevenlabs`, or `gemini`) in `result.transcript.source`.
   - The combine summary enforces weighting heuristics via `summaryAdjustments`, so low modality scores automatically nudge the final score downward rather than relying on unchecked Gemini output.

### Environment configuration

- Copy `.env.example` to `.env` and populate the placeholders before starting the server.
- Required: `GEMINI_API_KEY` and `ELEVENLABS_API_KEY`. The example also exposes `GEMINI_AUDIO_MODEL`, `ELEVENLABS_STT_MODEL`, and `ELEVENLABS_STT_ENDPOINT` to make it easy to tune models.
- Optional: `GEMINI_STT_ENDPOINT` (defaults to the Gemini speech-to-text API) to configure the fallback transcription endpoint if ElevenLabs fails.
- Optional: `ELEVENLABS_VOICE_ID_ENCOURAGING` and `ELEVENLABS_VOICE_ID_HARSH` when you extend the workflow with coach narration TTS links.

Metadata payloads (sent as JSON in the `metadata` form field) are persisted with each job and appear alongside the stored report for downstream UIs, so structure them according to your evaluation needs.

