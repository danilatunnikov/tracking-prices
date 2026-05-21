import hashlib

def make_callback_key(url: str) -> str:
    """Генерирует короткий ключ (8 символов) для URL"""
    return hashlib.md5(url.encode('utf-8')).hexdigest()[:8]