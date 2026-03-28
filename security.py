import hashlib
import hmac
import os


PBKDF2_ITERS = 220_000


def hash_pin(pin: str) -> tuple[bytes, bytes]:
    p = str(pin or "").strip()
    if not p:
        raise ValueError("PIN is empty")
    if len(p) < 4 or len(p) > 12:
        raise ValueError("PIN must be 4..12 digits/characters")
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", p.encode("utf-8"), salt, PBKDF2_ITERS)
    return (salt, digest)


def verify_pin(pin: str, salt: bytes, digest: bytes) -> bool:
    p = str(pin or "").strip()
    if not p or not salt or not digest:
        return False
    try:
        derived = hashlib.pbkdf2_hmac("sha256", p.encode("utf-8"), salt, PBKDF2_ITERS)
        return hmac.compare_digest(derived, digest)
    except Exception:
        return False

