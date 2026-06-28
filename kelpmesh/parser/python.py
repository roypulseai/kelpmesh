import ast


class PythonRefParser:
    """Extract ref() and source() calls from Python model source via AST."""

    @staticmethod
    def extract_refs(source: str) -> list[str]:
        tree = ast.parse(source)
        refs = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "ref" and node.args:
                    if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        refs.append(node.args[0].value)
        return refs

    @staticmethod
    def extract_sources(source: str) -> list[str]:
        """Extract source('name', 'table') calls — returns source names."""
        tree = ast.parse(source)
        sources = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "source" and node.args:
                    if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        sources.append(node.args[0].value)
        return sources
