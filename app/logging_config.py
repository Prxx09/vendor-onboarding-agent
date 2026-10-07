import hashlib
import logging

from app.config import get_settings


def configure_logging() -> None:
    logging.basicConfig(
        level=get_settings().log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def text_fingerprint(value: str) -> dict[str, int | str]:
    encoded = value.encode("utf-8")
    return {"length": len(value), "sha256": hashlib.sha256(encoded).hexdigest()[:8]}
