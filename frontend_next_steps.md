# Front-end follow-up (temporary spec)

## Context
Backend is now running separately under `pitch-perfect-server`. It exposes the legacy `/analyze` and `/analyze-pdf` helpers plus a new evaluation workflow with:

1. `POST /api/evaluate/start` – accepts multipart form data (`target`, `context`, optional `metadata`, optional `transcript` text, plus `deck`/`media` file uploads) and immediately returns `{ jobId, statusUrl }` while kicking off Gemini/ElevenLabs agents in the background.
2. `GET /api/evaluate/status/{jobId}` – returns the persisted job payload alongside the evaluation report once completed (saved in `.data/results/{jobId}.json`). Result payload contains `agents`, `combine`, `audio_summary`, `deck`, `transcript`, etc.


## Front-end implementation tasks

1. **Job submission UI** – either reuse existing upload form or add a dedicated workflow form. When the user submits target/context/metadata/audio/deck:
   - Build `FormData` with those fields and POST to `/api/evaluate/start`.
   - Display the returned `jobId`/`statusUrl` immediately so the user knows the job is queued.

2. **Status polling/updates** – after submission, poll `/api/evaluate/status/{jobId}` (every few seconds or via WebSocket if you prefer) until a `result` object appears:
   - Show job status from `job.status` (`pending`, `running`, `completed`, `failed`) and any `error`.
   - Once `result` is available, display key pieces: combined summary (`result.combine`), timeline, recommendations, voice scripts (`result.combine.voiceScripts`), agent outputs (`result.agents`), transcript/audio decks etc.

3. **Structured feedback view** – map the nested fields (`agents`, `combine`, `deck`, `audio_summary`) into UI cards similar to the spec (highlights, risks, voice scripts with personas). Provide ability to download raw JSON if needed (per spec’s “raw JSON toggle” idea).

4. **Metadata awareness** – include a section that reflects metadata submitted alongside the job (it’s stored under `job.input.metadata` and surfaced under `job.meta` inside the status response).

5. **Error handling & UX** – handle CORS, file-type validation (backend already enforces allowed audio/PDF types), and display meaningful errors coming from `/api/evaluate/start` or `/api/evaluate/status/{jobId}`.

## Additional result details

The backend now attaches these fields in every `result` payload:

- `audioAnalysis`: summary text (`summary`), structured insights (`analysis`), and the raw Gemini response (`raw`), giving you the low-level audio cues to surface.
- `agentWarnings` and `combineWarnings`: explain malformed/missing agent fields, timeline/recommendation truncation, or action-count issues that may require UI flags.
- `summaryAdjustments`: captures penalties (which agents scored below 60, how many points were deducted, and the adjusted combine score).
- `meta.graphOrder`: the LangGraph execution order so you can map backend nodes (deck→text→audio→...) to your frontend loading states.

Use these to annotate the structured feedback view (e.g., highlight penalized summaries, show trimmed timelines, or warn when audio was text-only).


## Notes
- Backend still exposes `/analyze` and `/analyze-pdf` for immediate single-file summarization; keep those available or map them to “quick analyze” buttons if needed.
- Keep the front-end spec text in this file for later reference; once the front-end repo is ready, feed this file to Codex over there to apply the UI changes.
