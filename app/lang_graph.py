from dataclasses import dataclass
from typing import Any, Callable, Dict, List


GraphState = Dict[str, Any]


@dataclass
class LangGraphNode:
    name: str
    compute: Callable[[GraphState], Dict[str, Any]]
    dependencies: List[str]


class LangGraphRunner:
    def __init__(self):
        self.nodes: Dict[str, LangGraphNode] = {}

    def register(self, node: LangGraphNode) -> None:
        self.nodes[node.name] = node

    def run(self, state: GraphState) -> List[str]:
        pending: Dict[str, LangGraphNode] = dict(self.nodes)
        executed: List[str] = []

        while pending:
            ready = [
                node
                for node in pending.values()
                if all(dep in state["agents"] for dep in node.dependencies)
            ]

            if not ready:
                remaining = ", ".join(pending.keys())
                raise RuntimeError(f"Cannot resolve remaining LangGraph nodes: {remaining}")

            for node in ready:
                result = node.compute(state)
                state["agents"][node.name] = result["parsed"]
                state["agent_raw"][node.name] = result["raw"]
                warnings = result.get("warnings")
                if warnings:
                    state["agent_warnings"][node.name] = warnings
                executed.append(node.name)
                pending.pop(node.name, None)

        return executed
