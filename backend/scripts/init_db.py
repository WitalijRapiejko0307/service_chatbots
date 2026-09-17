#!/usr/bin/env python3
"""Initialize PostgreSQL database schema and bootstrap admin user if missing."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _ensure_sslmode(url: str) -> str:
    """Add sslmode=require only when URL has no sslmode (e.g. Railway)."""
    if "sslmode=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return url + f"{sep}sslmode=require"


async def _bootstrap_admin(conn) -> None:
    email = os.environ.get("ADMIN_BOOTSTRAP_EMAIL", "admin@example.com").lower()
    password = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD", "changeme123")
    if not email or not password:
        print("Bootstrap admin skipped (ADMIN_BOOTSTRAP_EMAIL/PASSWORD empty).")
        return

    row = await conn.fetchrow("SELECT id FROM admin_users WHERE email=$1", email)
    if row:
        print(f"Bootstrap admin already exists: {email}")
        return

    from app.services.password_service import hash_password

    password_hash = hash_password(password)
    await conn.execute(
        "INSERT INTO admin_users (email, created_by, password_hash, is_active) VALUES ($1, $2, $3, true)",
        email,
        "bootstrap",
        password_hash,
    )
    print(f"Bootstrap admin created: {email}")


async def main() -> None:
    database_url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PUBLIC_URL")
    if not database_url:
        print("Error: DATABASE_URL or DATABASE_PUBLIC_URL must be set")
        sys.exit(1)
    database_url = _ensure_sslmode(database_url)
    print("Connecting to database...")

    try:
        import asyncpg
    except ImportError:
        print("Error: asyncpg not installed. Run: pip install asyncpg")
        sys.exit(1)

    migrations_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "migrations")
    migration_files = sorted(
        [name for name in os.listdir(migrations_dir) if name.endswith(".sql")]
    )

    statements = []
    for name in migration_files:
        path = os.path.join(migrations_dir, name)
        with open(path, "r") as f:
            sql = f.read()
        for block in sql.split(";"):
            lines = []
            for line in block.split("\n"):
                if line.strip().startswith("--"):
                    continue
                lines.append(line)
            stmt = "\n".join(lines).strip()
            if stmt:
                statements.append(stmt + ";")

    urls_to_try = [database_url]
    other = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
    if other and other != database_url:
        urls_to_try.append(_ensure_sslmode(other))

    conn = None
    last_error = None
    for url in urls_to_try:
        for attempt in range(3):
            try:
                conn = await asyncpg.connect(url, timeout=30)
                break
            except Exception as e:
                last_error = e
                if attempt < 2:
                    print(f"Attempt {attempt + 1} failed, retrying in 3s: {e}")
                    await asyncio.sleep(3)
        if conn is not None:
            break
    if conn is None:
        print(f"Failed to connect. Last error: {last_error}")
        raise last_error

    try:
        for i, stmt in enumerate(statements):
            try:
                await conn.execute(stmt)
                first_line = stmt.split("\n")[0][:70]
                print(f"OK: {first_line}...")
            except Exception as e:
                err_msg = str(e).lower()
                if "already exists" in err_msg:
                    print(f"Skip (exists): {stmt.split(chr(10))[0][:50]}...")
                elif "duplicate key" in err_msg or "unique constraint" in err_msg:
                    print(f"Skip (duplicate): {stmt.split(chr(10))[0][:50]}...")
                elif "extension" in err_msg and "not available" in err_msg:
                    print(f"Skip (extension not available): {stmt.split(chr(10))[0][:50]}...")
                else:
                    print(f"Error executing statement {i + 1}: {e}")
                    raise
        await _bootstrap_admin(conn)
        print("Migration completed successfully.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
