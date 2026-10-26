from pwdlib import PasswordHash

# Argon2id with the library's recommended parameters.
_hasher = PasswordHash.recommended()

# Verified against when the email is unknown, so a failed login takes the same time
# whether or not the account exists (no user enumeration through timing).
_DUMMY_HASH = _hasher.hash("dummy password for constant-time login failures")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        _hasher.verify(password, _DUMMY_HASH)
        return False
    return _hasher.verify(password, password_hash)
