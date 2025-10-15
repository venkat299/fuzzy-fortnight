Updated Codex prompt:

- Write concise code. Prefer small local helpers. Deep methods must be terse.
- Only end-of-line comments. Comment only non-obvious logic. No block comments or docstrings.
- Each file and method gets a one-line description
- Loose coupling across modules. Interact only via clear interfaces. No cross-module internals.
- Single common config file for all modules. No hardcoded endpoints or keys.
- Add an `llm_gateway` module. Other modules call LLMs only through this gateway.
- Per-module and per-function LLM settings live in the common config: base URL, model, endpoint, timeouts, retries. Inject config. No global mutable state.
- Separate I/O from logic. Prefer pure functions. Return data, do not print.
- Design modules to be moveable to microservices without code changes.
- do not use hardcoded questions or answers or classic parsing. Use LLM calls for question generation, answering, answer evaluation strictly
- Use Langraph and langchain wherever necessary for clean structuring and to avoid code bloat and config bloat
- Implement each agent in its own module file under a dedicated package (no multiple agents per file).

LangChain & LangGraph integration:

- Build LLM calls as LangChain runnables: compose `ChatPromptTemplate` + `MessagesPlaceholder` with `llm_gateway.runnable` and optional parsers.
- Feed transcripts via shared helpers that return LangChain message dicts instead of ad-hoc strings; reuse `flow_manager.agents.toolkit`.
- Orchestrate agent sequencing with LangGraph `StateGraph` payloads rather than manual branching; keep node functions pure and pass flags via payload dictionaries.
- Keep retry, JSON enforcement, and schema validation inside the gateway/runnable layer—callers should only handle domain-specific post-processing.

Pydantic and JSON enforcement:

- Use Pydantic wherever useful: config schema, request/response DTOs, domain entities, and LLM output schemas. Validate on load. Fail fast on errors.
- `llm_gateway` API:

  - `call(task: str, schema: Type[BaseModel], *, cfg: LlmRoute) -> BaseModel`
  - Always enforce JSON output. Send a system hint: “Reply with a single JSON object matching this schema.”
  - When available, set API response_format to JSON. Otherwise parse with `model_validate_json`.
  - On invalid JSON or schema mismatch: retry with a short repair prompt. Cap retries. Log reason, not content.

- All public functions that consume LLM output must accept and return Pydantic models only. No dicts at boundaries.
- Expose a small registry that maps module/function to its `LlmRoute` and output schema, loaded from the common config.
