"""Encryption for third-party credentials held in the database.

Threat model, stated plainly: the encryption key is derived from the app's
SECRET_KEY, which lives either in the environment or in a `.secret_key` file
beside the database. This therefore protects a leaked *database* - a copied
backup, a stolen .db, an SQL dump - but NOT a full host compromise, where the
attacker can read the secret alongside the ciphertext.

That is still worth having: database backups get copied around far more
casually than whole machines do. It is not a substitute for keeping the host
secure, and it is not claimed to be.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

_SALT = b"strengthlab.credential.v1"


def _fernet(secret_key):
    if not secret_key:
        raise ValueError("A SECRET_KEY is required before credentials can be stored.")
    digest = hashlib.pbkdf2_hmac("sha256", secret_key.encode("utf-8"), _SALT, 200_000)
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext, secret_key):
    return _fernet(secret_key).encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext, secret_key):
    """Returns the plaintext, or None when it cannot be read.

    A rotated SECRET_KEY makes every stored credential undecryptable. That is
    recoverable by re-entering the keys, so it must not crash the app.
    """
    try:
        return _fernet(secret_key).decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return None


def mask_secret(plaintext):
    """A recognisable but useless fragment, for showing which key is stored."""
    if not plaintext:
        return ""
    if len(plaintext) <= 8:
        return "•" * len(plaintext)
    return f"{plaintext[:4]}{'•' * 8}{plaintext[-4:]}"
