from __future__ import annotations  # Minimal StateGraph stub for tests

from typing import Any, Callable, Dict, Hashable


END = "__end__"  # Sentinel used by flow_manager during graph execution


class StateGraph:  # Simple sequential graph executor supporting conditional routing
    def __init__(self, _state_type: Any) -> None:
        self._nodes: Dict[Hashable, Callable[[Any], Any]] = {}
        self._edges: Dict[Hashable, list[Hashable]] = {}
        self._conditionals: Dict[Hashable, tuple[Callable[[Any], Hashable], Dict[Hashable, Hashable]]] = {}
        self._entry: Hashable | None = None

    def add_node(self, name: Hashable, func: Callable[[Any], Any]) -> None:
        self._nodes[name] = func

    def add_edge(self, source: Hashable, target: Hashable) -> None:
        self._edges.setdefault(source, []).append(target)

    def add_conditional_edges(
        self,
        source: Hashable,
        router: Callable[[Any], Hashable],
        mapping: Dict[Hashable, Hashable],
    ) -> None:
        self._conditionals[source] = (router, mapping)

    def set_entry_point(self, name: Hashable) -> None:
        self._entry = name

    def compile(self) -> "_CompiledGraph":
        if self._entry is None:
            raise ValueError("Entry point must be set before compilation")
        return _CompiledGraph(self)


class _CompiledGraph:  # Executes nodes respecting conditional edges
    def __init__(self, graph: StateGraph) -> None:
        self._graph = graph

    def invoke(self, payload: Any) -> Any:
        current = self._graph._entry
        state = payload
        while current is not None and current != END:
            node = self._graph._nodes.get(current)
            if node is None:
                raise KeyError(f"Node '{current}' not registered")
            state = node(state)
            if current in self._graph._conditionals:
                router, mapping = self._graph._conditionals[current]
                key = router(state)
                current = mapping.get(key, END)
            else:
                targets = self._graph._edges.get(current, [])
                current = targets[0] if targets else END
        return state


__all__ = ["END", "StateGraph"]
