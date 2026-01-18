# Project Brief

## Overview
PitchCoach (branded as Pitch Perfect inside `code/`) is a Next.js App Router experience that collects slide decks plus speech recordings and surfaces Gemini/ElevenLabs feedback. The frontend currently calls legacy `/analyze` and `/analyze-pdf` endpoints, but the next milestone is migrating to `pitch-perfect-server`’s evaluation workflow (`POST /api/evaluate/start` + `GET /api/evaluate/status/{jobId}`), showing structured summaries, agent outputs, deck feedback, metadata, and voice scripts while retaining quick-analyze helpers.

## Goals
- Implement the new evaluation workflow so users can submit target/context/metadata with deck/media files and immediately see a `jobId`/`statusUrl` while background agents run.
- Poll `/api/evaluate/status/{jobId}` until `result` appears, surface job status / errors / metadata, and render the combined summary, transcript, timeline, agent outputs, deck insights, and persona voice scripts.
- Keep the current `/analyze` helpers available as quick actions for the existing Speech/PDF experience.

## Constraints
- Frontend changes live inside `code/`; backend API lives in `pitch-perfect-server` (`backend/` folder in this repo will host coordination docs for that codex).
- All submissions must handle file validations (audio/video types, PDF size) and present user-friendly errors (CORS, network, validation).
- Results must gracefully handle partial data (missing audio, absent metadata, etc.) and offer raw JSON download for debugging.

## Owner
Product team + backend Codex workflow owners (see `backend/frontend-schema.md` once created) for aligned release.
