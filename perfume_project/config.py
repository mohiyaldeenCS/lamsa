import os
import secrets
from pathlib import Path

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'instance', 'perfumes.db')

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_SAMESITE = 'Lax'
    MAX_CONTENT_LENGTH = 1024 * 1024


def local_secret_key():
    """Keep local sessions valid across restarts without a shared default key."""
    path = Path(basedir) / 'instance' / '.secret_key'
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        key = path.read_text(encoding='ascii').strip()
        if len(key) < 32:
            raise RuntimeError('The local secret key file is invalid; configure SECRET_KEY.')
        return key
    key = secrets.token_hex(32)
    with os.fdopen(descriptor, 'w', encoding='ascii') as file:
        file.write(key)
    return key
