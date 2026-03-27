import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "data", "moviefinder.db"))

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY,
            tmdb_id INTEGER UNIQUE,
            title TEXT,
            title_ru TEXT,
            year INTEGER,
            rating FLOAT,
            poster_url TEXT,
            genre TEXT,
            description TEXT,
            description_ru TEXT,
            runtime INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS watch_sources (
            id INTEGER PRIMARY KEY,
            movie_id INTEGER REFERENCES movies(id),
            source_name TEXT,
            source_type TEXT,
            url TEXT,
            quality TEXT,
            is_available INTEGER DEFAULT 1,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS search_log (
            id INTEGER PRIMARY KEY,
            query TEXT,
            searched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def log_search(query: str):
    with get_db() as conn:
        conn.execute("INSERT INTO search_log (query) VALUES (?)", (query,))

def get_trending_searches(limit: int = 10) -> list:
    """Get top N search queries from last 24 hours."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT query, COUNT(*) as count
            FROM search_log
            WHERE searched_at > datetime('now', '-1 day')
            GROUP BY LOWER(query)
            ORDER BY count DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]

def save_movie(movie_data: dict):
    with get_db() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO movies
            (tmdb_id, title, title_ru, year, rating, poster_url, genre, description, description_ru, runtime, updated_at)
            VALUES (:tmdb_id, :title, :title_ru, :year, :rating, :poster_url, :genre, :description, :description_ru, :runtime, CURRENT_TIMESTAMP)
        """, movie_data)

def get_movie_by_tmdb(tmdb_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM movies WHERE tmdb_id = ?", (tmdb_id,)).fetchone()
        return dict(row) if row else None

def get_recent_movies(limit=30):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM movies ORDER BY updated_at DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]

def get_top_rated_db(limit=20):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM movies WHERE rating IS NOT NULL ORDER BY rating DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]

def save_watch_source(movie_db_id: int, source: dict):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO watch_sources (movie_id, source_name, source_type, url, quality, is_available, updated_at)
            VALUES (?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
        """, (movie_db_id, source['source_name'], source['source_type'], source['url'], source.get('quality', '1080p')))

def get_watch_sources(movie_db_id: int):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM watch_sources WHERE movie_id = ? AND is_available = 1
        """, (movie_db_id,)).fetchall()
        return [dict(r) for r in rows]
