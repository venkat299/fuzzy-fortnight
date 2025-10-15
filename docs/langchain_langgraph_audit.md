# LangChain and LangGraph Usage Audit

## Current Integrations
- `candidate_agent/auto_reply.py` uses `ChatPromptTemplate` to format auto-reply prompts and relies on `InMemoryChatMessageHistory`, `HumanMessage`, and `AIMessage` to replay transcript memory before calling the gateway.
- Warmup, competency, persona, and evaluator agents build their payloads with `ChatPromptTemplate` before sending tasks to the `llm_gateway`, without deeper LangChain abstractions.
- `flow_manager/__init__.py` instantiates a `StateGraph` from the local `langgraph` stub to route between the warmup node and the end of the setup flow.
- `langchain_core` and `langgraph` packages inside the repo are lightweight stubs that shadow the real libraries, so the project is not exercising official LangChain or LangGraph capabilities.

## Improvement Plan
1. **Adopt real LangChain runtimes**: wrap each agent as a LangChain `Runnable` pipeline (prompt → model → parser), swap manual JSON parsing for `PydanticOutputParser`, and feed shared memory via `ConversationBufferMemory`.
2. **Centralize structured retries**: implement `llm_gateway.call` using LangChain's `with_structured_output` and retry handlers to remove bespoke normalization like `_normalize_score`.
3. **Refactor flow orchestration with LangGraph**: rebuild `flow_manager` flow as a typed LangGraph with conditional edges, checkpointers, and per-node configurations loaded from `AppConfig`.
4. **Modular subgraphs**: encapsulate warmup, competency, and evaluation stages as reusable LangGraph subgraphs composed of LangChain runnables for easier reuse and testing.
5. **Shared prompt/memory utilities**: move duplicated formatting logic into LangChain prompt/memory helpers to reduce verbosity and keep persona, warmup, and competency agents aligned.
