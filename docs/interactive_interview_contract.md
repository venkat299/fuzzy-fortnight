# Interactive Interview Session Contract

## Overview
The existing batch-style interview playback will be replaced with an interactive loop where the client and server exchange questions and answers turn by turn. The backend orchestrates stateful interview progress while the UI renders the latest conversation, scoring, and stage metadata.

Goals:
- Single source of truth for interview state (`InterviewSessionState`) maintained server-side.
- Deterministic request/response contract so the UI can drive the conversation without guessing.
- Incremental delivery of events and scoring updates after every turn.

## Session Lifecycle
1. **Session start**
   - Client requests `/api/interview-sessions/start` with `interviewId`, `candidateId`, optional persona overrides.
   - Server loads rubrics, persona, candidate profile, initializes `InterviewSessionState`, persists it, and responds with `sessionId`, warmup context, first interviewer message (if any), and initial score snapshot.
   - Timer for checkpoints and stage logic remains in backend state.
2. **Interactive turns**
   - Client submits candidate reply via `/api/interview-sessions/turn`.
   - Server retrieves session, injects answer, runs one LangGraph step (question → evaluation), updates state, appends new events, recalculates scores, and returns payload needed for UI refresh.
   - Response also includes the next interviewer prompt (unless the session moved to wrap-up or complete).
3. **Completion**
   - Once wrap-up answer processed and state enters `complete`, backend flags session as finished. Further `/turn` calls return `409` with `code="session_complete"`.
4. **Expiry / cleanup**
   - Sessions expire after configurable idle period (default 30 minutes). Expired sessions respond with `410` and `code="session_expired"`; clients must call `/start` again.

## REST Endpoints

### `POST /api/interview-sessions/start`
Request body:
```json
{
  "interviewId": "string",
  "candidateId": "string",
  "persona": {
    "name": "string?",
    "probingStyle": "string?",
    "hintStyle": "string?",
    "encouragement": "string?"
  }
}
```

Response body (`200 OK`):
```json
{
  "sessionId": "uuid",
  "stage": "warmup",
  "persona": { ...PersonaConfig },
  "profile": { ...CandidateProfile },
  "question": {
    "content": "string",
    "metadata": {
      "competency": null,
      "stage": "warmup",
      "reasoning": "string",
      "escalation": "broad|why|how|challenge|hint|edge",
      "followUpPrompt": "string"
    }
  },
  "events": [ ...InterviewEvent ],
  "competencies": [ ...CompetencySummary ],
  "overallScore": 0.0,
  "elapsedMs": 0
}
```
Notes:
- If the warmup stage does not emit an immediate question, `question` can be `null`; UI should wait for first `/turn` response.
- `events` contains any bootstrap messages (warmup stage entered, resume summary, etc.) so the UI can render them immediately.

Errors:
- `404 candidate_not_found` / `404 interview_not_found`
- `502 llm_failure`
- `500 session_start_failed`

### `POST /api/interview-sessions/turn`
Request body:
```json
{
  "sessionId": "uuid",
  "answer": "string",
  "autoSend": true,
  "autoGenerate": true
}
```
`autoSend` and `autoGenerate` mirror UI toggles; they allow the backend to adapt questioning strategy. They are optional booleans.

Response body (`200 OK`):
```json
{
  "stage": "warmup|competency|wrapup|complete",
  "question": {
    "content": "string|null",
    "metadata": {
      "competency": "string|null",
      "stage": "warmup|competency|wrapup",
      "reasoning": "string",
      "escalation": "broad|why|how|challenge|hint|edge",
      "followUpPrompt": "string"
    }
  },
  "evaluation": {
    "summary": "string",
    "totalScore": 0.0,
    "rubricFilled": false,
    "criterionScores": [
      {
        "criterion": "string",
        "score": 0.0,
        "weight": 0.0,
        "rationale": "string"
      }
    ],
    "hints": ["string"],
    "followUpNeeded": false
  },
  "events": [ ...InterviewEvent ],
  "competencies": [ ...CompetencySummary ],
  "overallScore": 0.0,
  "questionsAsked": 0,
  "elapsedMs": 12345,
  "completed": false
}
```
Fields:
- `question` is `null` when the session is complete.
- `events` includes only the newly generated events since the previous response. The UI should append them to its running log.
- `competencies` is the full latest snapshot so the UI can overwrite existing tables.
- `overallScore` is the recomputed average each turn.
- `questionsAsked` counts interviewer prompts emitted so far (useful for telemetry displays).
- `completed` becomes `true` when the stage transitions to `complete`.

Errors:
- `400 invalid_payload` (e.g., empty answer when required).
- `401 session_unknown` when `sessionId` is not found.
- `409 session_complete` when additional answers arrive after completion.
- `410 session_expired` when idle timeout reached.
- `502 llm_failure` when question generation or evaluation fails mid-turn (UI should surface and allow retry).

## Data Contracts
- **InterviewEvent**: `{ "eventId": int, "createdAt": ISO8601, "stage": StageLiteral, "competency": "string|null", "eventType": "...", "payload": {...} }`
- **CompetencySummary**: `{ "competency": "string", "totalScore": 0.0, "rubricFilled": false, "criteria": [...] }`
- **CriterionScore payload** mirrors evaluator output; include `weight` for UI table without additional lookups.
- **PersonaConfig / CandidateProfile** reuse existing Pydantic models.

## State Persistence & Timeouts
- Session manager should store `InterviewSessionState` plus a `lastTouched` timestamp.
- Configuration options:
  - `session_timeout_minutes` (default 30)
  - `checkpoint_interval_minutes` (carry over from existing config)
  - `max_questions_per_competency`
- Cleanup job (lazy eviction): when sessions are fetched, expire any that are past timeout.

## UI Responsibilities
- Cache `sessionId` after `start`. Clear state when `/turn` responds with `completed=true` or any terminal error.
- Append `events` sequentially; no deduping necessary if backend guarantees monotonic `eventId`.
- Update score tables by replacing current arrays with the latest `competencies`.
- Disable send button while awaiting `/turn` response to avoid concurrent answers.
- Handle `410 session_expired` by prompting the user to restart; handle `502` with retry option.

## Open Questions
- Should warmup auto-send first question without waiting for user input? Answer : yes
- Do we require streaming responses for long LLM outputs? (Phase two; contract assumes synchronous responses.)
- Where to persist sessions in production (Redis vs SQLite)? Decision needed before implementing session manager persistence layer. Answer: use sqlite

## Testing Notes
- Backend: unit test `InterviewSessionManager` start/turn flows including invalid answers, missing sessions, and expired sessions.
- Backend: integration test warmup → competency → wrap-up progression to confirm event emissions, checkpoints, and competency snapshots.
- Frontend: component tests mocking `/start` and `/turn` to verify chat log updates, progress widgets, score tables, and completion handling.
- End-to-end: manual scenario covering warmup prompt, multiple competency turns with hints, wrap-up completion, and error surfacing for 502/410 responses.
