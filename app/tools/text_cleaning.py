import re
import unicodedata

TRUNCATION_MARKER = "\n[TEXT TRUNCATED]"
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
MULTISPACE = re.compile(r"\s+")
THOUSANDS_SEPARATOR = re.compile(r"(?<=\d),(?=\d{3}(?:\D|$))")


def clean_text(text: str, max_length: int = 100_000) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = CONTROL_CHARS.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(MULTISPACE.sub(" ", line).strip() for line in text.splitlines())
    text = text.strip()
    if len(text) > max_length:
        if max_length <= len(TRUNCATION_MARKER):
            return TRUNCATION_MARKER[:max_length]
        keep = max(0, max_length - len(TRUNCATION_MARKER))
        return text[:keep] + TRUNCATION_MARKER
    return text


def normalize_for_matching(value: str | float) -> str:
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    text = text.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
    text = THOUSANDS_SEPARATOR.sub("", text)
    text = MULTISPACE.sub(" ", text).strip()
    return text


def normalize_text_for_matching(value: str | float) -> str:
    """Normalize punctuation and common date/number formats for containment checks."""
    text = normalize_for_matching(value)
    text = _normalize_dates(text)
    text = re.sub(r"(?<=\d)[, ](?=\d{3}(?:\D|$))", "", text)
    text = re.sub(r"(?<=\d)\.(?=\d{3}(?:\D|$))", "", text)
    text = re.sub(r"[^\w.]+", " ", text, flags=re.UNICODE)
    return MULTISPACE.sub(" ", text).strip()


def _normalize_dates(text: str) -> str:
    date_patterns = (
        (r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", "ymd"),
        (r"\b(\d{1,2})\s+([a-z]{3,9})\s+(\d{4})\b", "dmy_text"),
        (r"\b([a-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})\b", "mdy_text"),
    )
    months = {
        name.casefold(): number
        for number, names in enumerate(
            (("january", "jan"), ("february", "feb"), ("march", "mar"),
             ("april", "apr"), ("may",), ("june", "jun"), ("july", "jul"),
             ("august", "aug"), ("september", "sep", "sept"), ("october", "oct"),
             ("november", "nov"), ("december", "dec")),
            start=1,
        )
        for name in names
    }

    def replace(match: re.Match[str], kind: str) -> str:
        if kind == "ymd":
            year, month, day = map(int, match.groups())
        elif kind == "dmy_text":
            day, month_name, year = match.groups()
            month = months.get(month_name.casefold(), 0)
            day, year = int(day), int(year)
        else:
            month_name, day, year = match.groups()
            month = months.get(month_name.casefold(), 0)
            day, year = int(day), int(year)
        if not month or not 1 <= day <= 31:
            return match.group(0)
        return f" {year:04d}-{month:02d}-{day:02d} "

    for pattern, kind in date_patterns:
        text = re.sub(pattern, lambda match, kind=kind: replace(match, kind), text)
    return text


def mask_account_numbers(text: str) -> str:
    """Mask values following account-number labels while retaining at most four chars."""
    pattern = re.compile(
        r"(?i)(\b(?:account\s*(?:number|no\.?|#)|a/c\s*(?:number|no\.?|#)|iban)\s*[:#-]?\s*)"
        r"((?:\d[ -]?){7,30}\d|[A-Z0-9][A-Z0-9-]{7,33})"
    )

    def mask(match: re.Match[str]) -> str:
        account = re.sub(r"[^A-Z0-9]", "", match.group(2), flags=re.IGNORECASE)
        return f"{match.group(1)}****{account[-4:]}"

    return pattern.sub(mask, text)
