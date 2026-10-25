"""The module import graph, read from the real imports with ast."""

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[3] / "src" / "BleakLoop"

ORDER = ("Plumbing", "Adapters", "Core", "External")

LAYERS = {
    "__init__": "Plumbing",
    "surface": "Plumbing",
    "device": "Plumbing",
    "live_state": "Adapters",
    "live_actions": "Adapters",
    "Live": "External",
    "ableton.v3": "External",
}


def layer(module):
    # Every core module is Core, so a new one needs no edit here.
    if module == "core" or module.startswith("core."):
        return "Core"
    if module not in LAYERS:
        raise ValueError(f"{module} has no layer in LAYERS")
    return LAYERS[module]


def modules():
    # Dotted name relative to the package -> source path.
    found = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        parts = path.relative_to(PACKAGE).with_suffix("").parts
        if len(parts) > 1 and parts[-1] == "__init__":
            parts = parts[:-1]
        found[".".join(parts)] = path
    return found


def edges():
    """Set of (importer, imported, lazy); lazy means imported inside a function."""
    known = modules()
    found = {}
    for name, path in known.items():
        package = _package(name, path)
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node, lazy in _imports(tree, False):
            for target in _targets(node, package, known):
                key = (name, target)
                found[key] = found.get(key, True) and lazy
    return {(source, target, lazy) for (source, target), lazy in found.items()}


def mermaid():
    graph = edges()
    nodes = {source for source, _, _ in graph} | {target for _, target, _ in graph}
    lines = ["```mermaid", "flowchart TD"]
    for name in ORDER:
        lines.append(f"  subgraph {name}")
        for node in sorted(n for n in nodes if layer(n) == name):
            lines.append(f'    {_id(node)}["{_label(node)}"]')
        lines.append("  end")
    for source, target, lazy in sorted(graph):
        arrow = "-.->|lazy|" if lazy else "-->"
        lines.append(f"  {_id(source)} {arrow} {_id(target)}")
    lines.append("```")
    return "\n".join(lines) + "\n"


def _package(name, path):
    # The package a module's relative imports resolve against, as path parts.
    parts = name.split(".") if name != "__init__" else []
    return parts if path.name == "__init__.py" else parts[:-1]


def _imports(node, lazy):
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.Import, ast.ImportFrom)):
            yield child, lazy
        inner = lazy or isinstance(
            child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
        )
        yield from _imports(child, inner)


def _targets(node, package, known):
    if isinstance(node, ast.Import):
        return {t for alias in node.names if (t := _external(alias.name))}
    if node.level == 0:
        target = _external(node.module)
        return {target} if target else set()
    base = package[: len(package) - (node.level - 1)]
    if node.module:
        base = base + node.module.split(".")
    targets = set()
    for alias in node.names:
        submodule = ".".join(base + [alias.name])
        targets.add(submodule if submodule in known else ".".join(base) or "__init__")
    return targets


def _external(module):
    root = module.split(".")[0]
    if root == "Live":
        return "Live"
    if root == "ableton":
        return "ableton.v3"
    return None


def _id(module):
    return module.replace(".", "_")


def _label(module):
    return module if layer(module) == "External" else module.split(".")[-1]
