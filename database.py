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

        CREATE TABLE IF NOT EXISTS user_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tmdb_id INTEGER NOT NULL,
            author TEXT NOT NULL,
            review_text TEXT NOT NULL,
            score INTEGER DEFAULT NULL,
            lang TEXT DEFAULT 'ru',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_user_reviews_tmdb ON user_reviews(tmdb_id);
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


def get_user_reviews(tmdb_id: int, lang: str = None) -> list:
    with get_db() as conn:
        if lang:
            rows = conn.execute(
                "SELECT author, review_text, score, lang, created_at FROM user_reviews WHERE tmdb_id=? AND lang=? ORDER BY created_at DESC LIMIT 50",
                (tmdb_id, lang)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT author, review_text, score, lang, created_at FROM user_reviews WHERE tmdb_id=? ORDER BY created_at DESC LIMIT 50",
                (tmdb_id,)
            ).fetchall()
        return [{"author": r[0], "text": r[1], "score": r[2], "lang": r[3], "date": r[4]} for r in rows]

def add_user_review(tmdb_id: int, author: str, review_text: str, score: int = None, lang: str = 'ru') -> bool:
    # Basic validation
    if not author.strip():
        return False
    if len(author) > 50 or len(review_text) > 2000:
        return False
    if score is not None:
        if not isinstance(score, int) or score < 1 or score > 10:
            return False
    with get_db() as conn:
        conn.execute(
            "INSERT INTO user_reviews (tmdb_id, author, review_text, score, lang) VALUES (?, ?, ?, ?, ?)",
            (tmdb_id, author.strip()[:50], review_text.strip()[:2000], score, lang)
        )
    return True

def get_movie_score(tmdb_id: int) -> dict:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT score FROM user_reviews WHERE tmdb_id=? AND score IS NOT NULL",
            (tmdb_id,)
        ).fetchall()
        scores = [r[0] for r in rows]
        count = len(scores)
        avg = round(sum(scores) / count, 1) if count > 0 else None
        distribution = {str(i): 0 for i in range(1, 11)}
        for s in scores:
            distribution[str(s)] = distribution.get(str(s), 0) + 1
        return {"avg_score": avg, "count": count, "distribution": distribution}


def get_db_connection():
    import sqlite3 as _sqlite3
    conn = _sqlite3.connect(DB_PATH)
    conn.row_factory = _sqlite3.Row
    return conn


def get_movies_by_genre_db(genre_tmdb: str, page: int = 1, sort: str = "new", per_page: int = 20) -> dict:
    """Get movies from local SQLite by genre with pagination and sorting."""
    sort_map = {
        "new": ("year DESC, rating DESC", "genre LIKE ? AND poster_url IS NOT NULL AND poster_url != ''"),
        "rating": ("rating DESC, year DESC", "genre LIKE ? AND rating < 10.0 AND rating >= 5.0 AND vote_count >= 100 AND poster_url IS NOT NULL AND poster_url != ''"),
        "popular": ("popularity DESC, vote_count DESC", "genre LIKE ? AND poster_url IS NOT NULL AND poster_url != ''"),
    }
    order_by, where_extra = sort_map.get(sort, sort_map["new"])
    offset = (page - 1) * per_page
    with get_db() as conn:
        count_row = conn.execute(
            f"SELECT COUNT(*) FROM movies WHERE {where_extra}",
            (f'%{genre_tmdb}%',)
        ).fetchone()
        total = count_row[0] if count_row else 0
        total_pages = max(1, (total + per_page - 1) // per_page)
        rows = conn.execute(
            f"SELECT tmdb_id, title, title_ru, year, rating, poster_url, genre FROM movies WHERE {where_extra} ORDER BY {order_by} LIMIT ? OFFSET ?",
            (f'%{genre_tmdb}%', per_page, offset)
        ).fetchall()
        movies = []
        for r in rows:
            tmdb_id, title, title_ru, year, rating, poster_url, genre = r
            movies.append({
                "tmdb_id": tmdb_id, "title": title or "", "title_ru": title_ru or "",
                "display_title": title or "", "year": year, "rating": rating,
                "poster_url": poster_url, "genre": genre or "", "media_type": "movie",
            })
        return {"movies": movies, "total_pages": total_pages, "current_page": page, "total": total}


def get_vecher_movies_db(page: int = 1, per_page: int = 20) -> dict:
    """Evening movies: Comedy + Drama + Romance, rating >= 7.0, from SQLite."""
    offset = (page - 1) * per_page
    with get_db() as conn:
        count_row = conn.execute(
            "SELECT COUNT(*) FROM movies WHERE (genre LIKE '%Comedy%' OR genre LIKE '%Drama%' OR genre LIKE '%Romance%') AND rating >= 7.0 AND poster_url IS NOT NULL AND poster_url != ''",
        ).fetchone()
        total = count_row[0] if count_row else 0
        total_pages = max(1, (total + per_page - 1) // per_page)
        rows = conn.execute(
            "SELECT tmdb_id, title, title_ru, year, rating, poster_url, genre FROM movies WHERE (genre LIKE '%Comedy%' OR genre LIKE '%Drama%' OR genre LIKE '%Romance%') AND rating >= 7.0 AND poster_url IS NOT NULL AND poster_url != '' ORDER BY rating DESC, year DESC LIMIT ? OFFSET ?",
            (per_page, offset)
        ).fetchall()
        movies = []
        for r in rows:
            tmdb_id, title, title_ru, year, rating, poster_url, genre = r
            movies.append({
                "tmdb_id": tmdb_id, "title": title or "", "title_ru": title_ru or "",
                "display_title": title or "", "year": year, "rating": rating,
                "poster_url": poster_url, "genre": genre or "", "media_type": "movie",
            })
        return {"movies": movies, "total_pages": total_pages, "current_page": page, "total": total}


def get_movies_2026_db(page: int = 1, per_page: int = 20, sort: str = "new") -> dict:
    """Movies from 2026, with sort support."""
    offset = (page - 1) * per_page
    sort_configs = {
        "new": ("created_at DESC", "year = 2026 AND rating > 0"),
        "rating": ("rating DESC", "year = 2026 AND rating < 10.0 AND rating >= 5.0 AND vote_count >= 10"),
        "popular": ("popularity DESC, vote_count DESC", "year = 2026 AND rating > 0"),
    }
    order_by, where_2026 = sort_configs.get(sort, sort_configs["new"])
    with get_db() as conn:
        count_row = conn.execute(
            f"SELECT COUNT(*) FROM movies WHERE {where_2026} AND poster_url IS NOT NULL AND poster_url != ''",
        ).fetchone()
        total = count_row[0] if count_row else 0
        total_pages = max(1, (total + per_page - 1) // per_page)
        rows = conn.execute(
            f"SELECT tmdb_id, title, title_ru, year, rating, poster_url, genre FROM movies WHERE {where_2026} AND poster_url IS NOT NULL AND poster_url != '' ORDER BY {order_by} LIMIT ? OFFSET ?",
            (per_page, offset)
        ).fetchall()
        movies = []
        for r in rows:
            tmdb_id, title, title_ru, year, rating, poster_url, genre = r
            movies.append({
                "tmdb_id": tmdb_id, "title": title or "", "title_ru": title_ru or "",
                "display_title": title or "", "year": year, "rating": rating,
                "poster_url": poster_url, "genre": genre or "", "media_type": "movie",
            })
        return {"movies": movies, "total_pages": total_pages, "current_page": page, "total": total}
