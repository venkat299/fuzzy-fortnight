# Interview Session Agent Flow

## Configuration overview
- Flow controls live in `FlowSettings`, which exposes warmup question limits plus the competency follow-up ceiling and low-score trigger shared by all agents and loaded from `app_config.json`.【F:config.py†L22-L35】【F:app_config.json†L33-L36】
- The FastAPI server resolves agent routes and schemas from the registry so that every agent call is funneled through the common LLM gateway and configuration plumbing.【F:api_server.py†L283-L330】【F:config.py†L34-L50】

## Pre-session preparation
- When the UI requests either the interview context or the warmup kickoff, the server first primes project anchors by calling the competency primer agent so each competency pillar is mapped to a resume-sourced or hypothetical project.【F:api_server.py†L283-L304】【F:api_server.py†L430-L451】
- The primer agent packages job data, resume highlights, and competency names into a single prompt and returns a competency→project map that the flow context stores for later interviewer prompts.【F:flow_manager/agents/competency_primer.py†L14-L91】【F:api_server.py†L461-L493】
- The constructed `InterviewContext` begins in the warmup stage but already tracks the ordered competency list, criteria, seeded anchors, and empty coverage counters, enabling downstream agents to reason about progress from the first turn.【F:api_server.py†L461-L493】

## Warmup launch
- `start_session` ensures the warmup and evaluator agents are registered, seeds competency metadata, and runs a LangGraph router that invokes the warmup node when the stage is still `warmup` and the configured quota allows it.【F:flow_manager/__init__.py†L31-L65】
- The warmup agent receives resume summaries, highlighted experiences, and prior conversation, then appends a single interviewer message that sets the tone for the session.【F:flow_manager/agents/warmup.py†L31-L78】
- `_run_warmup` updates warmup counters and flips the stage to `competency` once the configured limit is reached, carrying forward the first competency’s project anchor so the next loop can begin immediately.【F:flow_manager/__init__.py†L157-L185】

## Candidate answer evaluation cycle
- Each candidate reply funnels through `advance_session`, which rebuilds `FlowState`, finds the most recent interviewer/candidate pair, and classifies the exchange as warmup or competency based on the configured warmup limit.【F:flow_manager/__init__.py†L83-L138】
- The evaluator agent summarizes conversation history, keeps a running memory buffer, and returns updated anchors, rubric deltas, and (during competency) scored criteria for the latest answer.【F:flow_manager/agents/evaluator.py†L14-L87】
- `_apply_evaluation` merges evaluator memory, advances the stage when warmup questions are exhausted, and during competency updates coverage tracking and low-score counters that drive loop decisions.【F:flow_manager/__init__.py†L188-L241】

## Competency loop orchestration
- `_drive_competency_loop` checks whether the evaluator signaled sufficient coverage or repeated low scores and, when needed, moves to the next competency before issuing another interviewer question.【F:flow_manager/__init__.py†L244-L304】
- Coverage tracking deduplicates rubric hits drawn from evaluator notes and scores, considers a criterion set “mostly covered” once all or all-but-one items are evidenced, and increments low-score streaks against the configured threshold.【F:flow_manager/__init__.py†L307-L343】
- When advancing, `_advance_competency` resets per-competency counters, loads the next pillar’s project anchor, and eventually flips the context to the wrap-up stage after the final pillar.【F:flow_manager/__init__.py†L403-L448】
- The competency agent then generates the next interviewer prompt, linking the active project anchor, remaining criteria, and prior conversation while reusing the user-provided instruction block for first versus follow-up questions.【F:flow_manager/agents/competency.py†L14-L129】

## Wrap-up and downstream surfaces
- `_seed_competency_context` and `_current_project` keep the context synchronized so that transitions, anchors, and coverage survive across API calls and evaluator updates, letting the UI reflect the active competency and targeted criteria.【F:flow_manager/__init__.py†L451-L481】
- Session responses echo the updated context back to the client, including evaluator memory, competency counters, targeted criteria, and the latest interviewer follow-ups for rendering and for auto-reply prompts.【F:api_server.py†L283-L330】【F:api_server.py†L386-L427】
- The candidate auto-reply agent consumes the same competency, anchor, and criteria metadata to roleplay answers that stay aligned with the interviewer’s focus, keeping session automation consistent with the flow manager’s state.【F:candidate_agent/auto_reply.py†L42-L129】

## Sequence cheat sheet
```
Primer → Warmup Agent → Evaluator ↺ Competency Agent
   │           │              │             │
   │           │              └─ updates rubric, anchors, low-score streaks
   │           └─ emits warmup prompt then hands off to competency stage
   └─ seeds anchors per competency before the session starts
```
- If coverage is complete, follow-up quotas are exhausted, or low-score streaks trip the configured cap, the flow advances to the next competency; otherwise, the loop continues with another competency agent prompt.【F:flow_manager/__init__.py†L244-L304】【F:flow_manager/__init__.py†L307-L343】
- After the final competency, the context stage switches to `wrap_up`, signaling downstream features to conclude the interview.【F:flow_manager/__init__.py†L403-L448】
