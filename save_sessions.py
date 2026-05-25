"""
Запустите этот скрипт после добавления аккаунта локально.
Он выведет base64-строки которые нужно добавить в GitHub Secrets.

Использование:
    python save_sessions.py
"""
import os
import base64
import tarfile
import io

SESSIONS_DIR = os.getenv("SESSIONS_DIR", "sessions")
DB_PATH = os.getenv("DB_PATH", "bot.db")


def encode_sessions() -> str | None:
    session_files = [
        f for f in os.listdir(SESSIONS_DIR)
        if f.endswith(".session")
    ] if os.path.isdir(SESSIONS_DIR) else []

    if not session_files:
        return None

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for fname in session_files:
            path = os.path.join(SESSIONS_DIR, fname)
            tar.add(path, arcname=fname)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def encode_db() -> str | None:
    if not os.path.exists(DB_PATH):
        return None
    with open(DB_PATH, "rb") as f:
        return base64.b64encode(f.read()).decode()


if __name__ == "__main__":
    print("=" * 60)
    print("Сохранение сессий для GitHub Secrets")
    print("=" * 60)

    sessions_b64 = encode_sessions()
    if sessions_b64:
        print(f"\n✅ SESSIONS_B64 (добавьте в GitHub Secrets):")
        print(f"\n{sessions_b64}\n")
    else:
        print("\n⚠️  Файлы сессий не найдены в папке sessions/")

    db_b64 = encode_db()
    if db_b64:
        print(f"\n✅ DB_B64 (добавьте в GitHub Secrets):")
        print(f"\n{db_b64}\n")
    else:
        print("\n⚠️  Файл базы данных не найден")

    print("=" * 60)
    print("Добавьте эти значения в:")
    print("GitHub репозиторий → Settings → Secrets → Actions")
    print("=" * 60)
