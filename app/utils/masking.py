import re

_ACCOUNT_LABEL = re.compile(
    r"(?i)(\b(?:account\s*(?:number|no\.?|#)|a/c\s*(?:number|no\.?|#)|iban)\s*[:#-]?\s*)"
    r"((?:\d[ -]?){7,30}\d|[A-Z0-9][A-Z0-9-]{7,33})"
)


def mask_account_number(value: str | None) -> str | None:
    """Return an account value with all but its final four alphanumeric characters masked."""
    if value is None or not value.strip():
        return value

    def redact(match: re.Match[str]) -> str:
        return f"{match.group(1)}{_mask_raw(match.group(2))}"

    if _ACCOUNT_LABEL.search(value):
        return _ACCOUNT_LABEL.sub(redact, value)
    return _mask_raw(value)


def _mask_raw(value: str) -> str:
    normalized = "".join(character for character in value if character.isalnum())
    if not normalized:
        return "****"
    return f"****{normalized[-4:]}"
