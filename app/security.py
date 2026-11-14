import base64
import hashlib
import hmac
import secrets


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Geslo mora vsebovati najmanj 12 znakov.")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**15, r=8, p=1, dklen=64, maxmem=128 * 1024 * 1024)
    return "scrypt$32768$8$1${}${}".format(
        base64.urlsafe_b64encode(salt).decode(),
        base64.urlsafe_b64encode(digest).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, n, r, p, salt_text, digest_text = stored.split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode())
        expected = base64.urlsafe_b64decode(digest_text.encode())
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected), maxmem=128 * 1024 * 1024
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False
