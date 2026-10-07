import re
from pathlib import Path

PROMPT_DIR = Path(__file__).parent
PLACEHOLDER = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")


def load_prompt(name: str, **values: str) -> str:
    path = PROMPT_DIR / f"{name}.md"
    template = path.read_text(encoding="utf-8")
    required = set(PLACEHOLDER.findall(template))
    missing = required - values.keys()
    if missing:
        raise ValueError(f"Missing prompt placeholders: {', '.join(sorted(missing))}")
    return PLACEHOLDER.sub(lambda match: str(values[match.group(1)]), template)
