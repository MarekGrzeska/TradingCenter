"""The account session at rest: encrypted with a key that is never in the database.

The session string is a login to a Telegram account — dedicated to the bots, but still able to write as the bots the
operator trusts. It sits in the database, the database is dumped every night to the operator's computer, and a dump
without the server's key must not open the account. Fernet because it carries its own version and timestamp and
leaves no nonce for this file to get wrong.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


def check_key(key: str) -> str:
    """The key, or a refusal that names the setting and the one-line way to make a good one."""
    try:
        Fernet(key.encode())
    except (ValueError, TypeError) as err:
        raise ValueError(
            "TELEGRAM_SESSION_KEY is not a Fernet key (32 url-safe base64 bytes). Make one with "
            "`python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"`."
        ) from err
    return key


def encrypt(key: str, session: str) -> str:
    return Fernet(key.encode()).encrypt(session.encode()).decode()


def decrypt(key: str, token: str) -> str | None:
    """The session, or `None` when this key does not open it — a changed key and a damaged row are the same
    state, and the answer to both is to log the account in again."""
    try:
        return Fernet(key.encode()).decrypt(token.encode()).decode()
    except InvalidToken:
        return None
