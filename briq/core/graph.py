import networkx as nx
from briq.core.project import Project


class DAGBuilder:
    def __init__(self, project: Project):
        self.project = project
        self.graph = nx.DiGraph()

    def build(self) -> nx.DiGraph:
        self.graph.clear()
        for name, model in self.project.models.items():
            self.graph.add_node(name, model=model)
        for name, model in self.project.models.items():
            for dep in model.upstream:
                if dep in self.project.models:
                    self.graph.add_edge(dep, name)
        return self.graph

    def execution_order(self, model_names: list[str] | None = None) -> list[str]:
        self.build()
        try:
            if model_names:
                subgraph = self.graph.subgraph(model_names)
                return list(nx.topological_sort(subgraph))
            return list(nx.topological_sort(self.graph))
        except nx.NetworkXUnfeasible:
            cycle = self._find_cycle()
            raise ValueError(
                f"Cycle detected in model dependencies: {' -> '.join(cycle)}"
            )

    def _find_cycle(self) -> list[str]:
        try:
            cycle = nx.find_cycle(self.graph)
            return [edge[0] for edge in cycle]
        except nx.NetworkXNoCycle:
            return []

    def upstream_models(self, model_name: str) -> set[str]:
        return nx.ancestors(self.graph, model_name)

    def downstream_models(self, model_name: str) -> set[str]:
        return nx.descendants(self.graph, model_name)

    def layers(self) -> list[list[str]]:
        self.build()
        return list(nx.topological_generations(self.graph))

    def select_models(self, select: list[str]) -> list[str]:
        self.build()
        selected = set()
        for s in select:
            if s.startswith("+"):
                name = s[1:]
                if name not in self.graph:
                    continue
                selected.add(name)
                selected |= nx.ancestors(self.graph, name)
            elif s.endswith("+"):
                name = s[:-1]
                if name not in self.graph:
                    continue
                selected.add(name)
                selected |= nx.descendants(self.graph, name)
            elif s.startswith("@"):
                name = s[1:]
                if name not in self.graph:
                    continue
                selected.add(name)
                selected |= nx.ancestors(self.graph, name)
                selected |= nx.descendants(self.graph, name)
            else:
                if s in self.graph:
                    selected.add(s)
        return [m for m in self.execution_order() if m in selected]
