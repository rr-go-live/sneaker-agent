"""
auth.py
-------
Password hashing and verification for local username/password login.

Uses PBKDF2-HMAC-SHA256 (Python's stdlib hashlib — no extra dependency)
with a random per-user salt and an iteration count in line with current
OWASP guidance. Stored as "salt_hex$hash_hex" in User.password_hash.
"""

import hashlib
import hmac
import secrets

# OWASP's 2023+ minimum recommendation for PBKDF2-HMAC-SHA256.
_ITERATIONS = 260_000


def hash_password(password: str) -> str:
    """
    hash_password
    -------------
    Hashes a plaintext password with a fresh random salt.

    Args:
        password (str): plaintext password

    Returns:
        str: "salt_hex$hash_hex", safe to store in the database
    """
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), _ITERATIONS
    )
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """
    verify_password
    ----------------
    Checks a plaintext password attempt against a stored hash, using a
    constant-time comparison so response timing can't leak information
    about how much of the hash matched.

    Args:
        password (str): plaintext password attempt
        stored   (str): value previously returned by hash_password()

    Returns:
        bool: True if the password is correct
    """
    if not stored or "$" not in stored:
        return False

    salt, hash_hex = stored.split("$", 1)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), _ITERATIONS
    )
    return hmac.compare_digest(digest.hex(), hash_hex)
