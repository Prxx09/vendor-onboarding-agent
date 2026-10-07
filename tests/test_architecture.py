import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_only_integrations_import_http_clients():
    source_paths = [path for folder in (ROOT / "app", ROOT / "tests", ROOT / "scripts")
                    for path in folder.rglob("*.py")]
    for path in source_paths:
        if "integrations" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [name.name for name in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            assert not any(name.startswith(("httpx", "requests")) for name in names), path


def test_application_rules_and_agents_are_isolated_from_adapters_and_repositories():
    for folder in (ROOT / "app" / "rules", ROOT / "app" / "agents"):
        for path in folder.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    assert not module.startswith("app.integrations.http"), path
                    assert not module.startswith("app.repositories"), path
                elif isinstance(node, ast.Import):
                    assert not any(name.name.startswith(("app.integrations.http", "app.repositories")) for name in node.names), path


def test_application_python_has_no_embedded_network_urls():
    url_prefixes = ("http" + "://", "https" + "://")
    source_paths = [path for folder in (ROOT / "app", ROOT / "tests", ROOT / "scripts")
                    for path in folder.rglob("*.py")]
    for path in source_paths:
        if "integrations" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        assert not any(prefix in source for prefix in url_prefixes), path

