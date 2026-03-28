"""
AI-generated unique editorial reviews for movie pages.
Uses PostgreSQL for shared storage between local Crake agent and Railway server.
"""
import os
import asyncio

PG_URL = os.getenv("PG_REVIEWS_URL", "postgresql://postgres:OLIBHomUThkXFlbrgpJWyeZblHZdJQvj@gondola.proxy.rlwy.net:54122/railway")

# Lazy import to avoid startup issues if psycopg2 not installed
_pg_conn = None

def _get_pg():
    global _pg_conn
    try:
        import psycopg2
        if _pg_conn is None or _pg_conn.closed:
            _pg_conn = psycopg2.connect(PG_URL)
            _pg_conn.autocommit = False
            _pg_conn.cursor().execute("""
                CREATE TABLE IF NOT EXISTS ai_reviews (
                    tmdb_id INTEGER,
                    lang TEXT,
                    review TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (tmdb_id, lang)
                )
            """)
            _pg_conn.commit()
        return _pg_conn
    except Exception as e:
        print(f"PG connect error: {e}")
        return None

def get_cached_review(tmdb_id: int, lang: str) -> str | None:
    try:
        conn = _get_pg()
        if not conn:
            return None
        cur = conn.cursor()
        cur.execute("SELECT review FROM ai_reviews WHERE tmdb_id=%s AND lang=%s", (tmdb_id, lang))
        row = cur.fetchone()
        return row[0] if row else None
    except Exception as e:
        print(f"PG read error: {e}")
        return None

def save_review(tmdb_id: int, lang: str, review: str):
    try:
        conn = _get_pg()
        if not conn:
            return
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO ai_reviews (tmdb_id, lang, review) VALUES (%s, %s, %s) ON CONFLICT (tmdb_id, lang) DO UPDATE SET review=%s",
            (tmdb_id, lang, review, review)
        )
        conn.commit()
    except Exception as e:
        print(f"PG write error: {e}")
        try:
            conn.rollback()
        except:
            pass

async def get_or_generate_review(movie: dict, lang: str) -> str:
    """Get from PostgreSQL cache. Generation is done by Crake agent separately."""
    tmdb_id = movie.get("tmdb_id") or movie.get("id")
    if not tmdb_id:
        return ""
    return get_cached_review(tmdb_id, lang) or ""
