## Frontend Integration Plan (Step 2)

This repo only has the backend, so here’s the client contract and ready-to-drop code for the separate Next.js app (Turbopack, Next 16). No Git pushes required.

### API shape
- `POST http://127.0.0.1:8000/api/evaluate/start` (multipart)
  - Fields: optional `deck` (PDF), optional `transcript` (text), optional `media` (audio/video). At least one required.
  - Returns: `{ jobId, status: "pending" }`.
- `GET http://127.0.0.1:8000/api/evaluate/status/:jobId`
  - Returns: `{ id, status: "pending" | "running" | "completed" | "failed", result?, warnings?, logs?, error? }`.
  - `result` conforms to the EvaluationReport: `{ version, summary, deck?, transcript?, delivery?, speechContent?, audio?, recommendations?, voiceNarrations?, warnings?, meta }`.

### TypeScript types (drop into `src/types/evaluation.ts`)
```ts
export type JobStatus = "pending" | "running" | "completed" | "failed";

export interface EvaluationReport {
  version: string;
  summary: any;
  deck?: any;
  transcript?: any;
  delivery?: any;
  speechContent?: any;
  audio?: any;
  recommendations?: any[];
  voiceNarrations?: { persona: string; tone: string; script: string }[];
  warnings?: string[];
  meta?: { generatedAt: number; model: string; target: string };
}

export interface EvaluationJob {
  id: string;
  status: JobStatus;
  result?: EvaluationReport;
  warnings?: string[];
  logs?: string[];
  error?: string;
}
```

### API client (drop into `src/app/services/api.ts`)
```ts
const BASE_URL = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export async function startEvaluation(params: {
  deck?: File | null;
  media?: File | null;
  transcript?: string | null;
}): Promise<{ jobId: string }> {
  const form = new FormData();
  if (params.deck) form.append("deck", params.deck);
  if (params.media) form.append("media", params.media);
  if (params.transcript) form.append("transcript", params.transcript);
  if (!form.has("deck") && !form.has("media") && !form.has("transcript")) {
    throw new Error("Provide at least one of deck, transcript, or media.");
  }
  const res = await fetch(`${BASE_URL}/api/evaluate/start`, { method: "POST", body: form });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || "Failed to start evaluation");
  }
  return res.json();
}

export async function getJobStatus(jobId: string): Promise<EvaluationJob> {
  const res = await fetch(`${BASE_URL}/api/evaluate/status/${jobId}`);
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || "Failed to fetch status");
  }
  return res.json();
}
```

### React hook (drop into `src/app/hooks/useEvaluation.ts`)
```ts
import { useEffect, useState } from "react";
import { startEvaluation, getJobStatus } from "../services/api";
import type { EvaluationJob } from "../../types/evaluation";

const POLL_MS = 2000;

export function useEvaluation() {
  const [job, setJob] = useState<EvaluationJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function kickOff(args: Parameters<typeof startEvaluation>[0]) {
    setIsLoading(true);
    setError(null);
    try {
      const { jobId } = await startEvaluation(args);
      setJob({ id: jobId, status: "pending" });
    } catch (err: any) {
      setError(err?.message || "Failed to start evaluation");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    if (!job?.id || job.status === "completed" || job.status === "failed") return;
    const handle = setInterval(async () => {
      try {
        const next = await getJobStatus(job.id);
        setJob(next);
      } catch (err: any) {
        setError(err?.message || "Polling failed");
      }
    }, POLL_MS);
    return () => clearInterval(handle);
  }, [job?.id, job?.status]);

  return { job, error, isLoading, start: kickOff };
}
```

### UI rendering notes
- Show upload controls for PDF/transcript/media; start job with `start({ deck, media, transcript })`.
- Polling hook returns `job.result` once ready; render modality cards from `deck`, `transcript`, `delivery`, `speechContent`, `audio`, `recommendations`, `voiceNarrations`.
- Surface `job.warnings` and `job.logs` in a debug panel for this session (per your request, no persistence).
- Guard against missing modalities in components to avoid null access (e.g., `data.summary` on `null`). Example:
  ```tsx
  // ModalityCard defensively handles null/undefined
  const ModalityCard: React.FC<{ label: string; data: ModalityResult | null | undefined }> = ({ label, data }) => {
    if (!data) return null;
    return (
      <Card title={label}>
        {data.summary && <p>{data.summary}</p>}
        {data.details && <p>{data.details}</p>}
        {renderList(data.strengths)}
        {renderList(data.issues)}
      </Card>
    );
  };

  // Only render cards when that modality exists
  {report.deck && <ModalityCard label="Deck" data={report.deck} />}
  {report.transcript && <ModalityCard label="Transcript Quality" data={report.transcript} />}
  {report.delivery && <ModalityCard label="Delivery" data={report.delivery} />}
  {report.speechContent && <ModalityCard label="Speech Content" data={report.speechContent} />}
  {report.audio && <ModalityCard label="Audio" data={report.audio} />}
  ```

### Env config
- Add `NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000` to your frontend `.env.local` (or point to your deployed backend URL).
