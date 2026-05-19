import hashlib
import hmac


def _digest(value: str, *, salt: str) -> str:
    if not salt:
        raise ValueError("salt is required for anonymization")
    return hmac.new(salt.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def hash_author_id(*, platform: str, raw_author_id: str, salt: str) -> str:
    if not raw_author_id:
        raise ValueError("raw_author_id is required")
    digest = _digest(f"{platform}:{raw_author_id}", salt=salt)
    return f"{platform}_{digest[:32]}"


def hash_optional_text(value: str | None, *, salt: str) -> str | None:
    if value is None:
        return None
    if value == "":
        return ""
    return _digest(value, salt=salt)[:32]
