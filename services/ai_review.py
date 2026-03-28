"""
AI-generated unique editorial reviews for movie pages.
Uses Groq API, caches results in SQLite to avoid repeat API calls.
"""
import sqlite3
import os
import httpx
import asyncio

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "movies.db")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_reviews (
            tmdb_id INTEGER,
            lang TEXT,
            review TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tmdb_id, lang)
        )
    """)
    conn.commit()
    return conn

def get_cached_review(tmdb_id: int, lang: str) -> str | None:
    try:
        conn = _get_db()
        row = conn.execute(
            "SELECT review FROM ai_reviews WHERE tmdb_id=? AND lang=?",
            (tmdb_id, lang)
        ).fetchone()
        conn.close()
        return row[0] if row else None
    except:
        return None

def save_review(tmdb_id: int, lang: str, review: str):
    try:
        conn = _get_db()
        conn.execute(
            "INSERT OR REPLACE INTO ai_reviews (tmdb_id, lang, review) VALUES (?,?,?)",
            (tmdb_id, lang, review)
        )
        conn.commit()
        conn.close()
    except:
        pass

async def generate_review(movie: dict, lang: str) -> str:
    """Generate unique review via Groq. Returns empty string on failure."""
    if not GROQ_API_KEY:
        return ""
    
    title = movie.get("title_ru") or movie.get("title", "") if lang == "ru" else movie.get("title_en") or movie.get("title", "")
    description = movie.get("description", "") or ""
    rating = movie.get("rating") or 0
    year = movie.get("year") or ""
    genre = movie.get("genre") or ""
    cast_list = movie.get("cast") or []
    cast_names = ", ".join([c["name"] for c in cast_list[:3]]) if cast_list else ""
    director = movie.get("director") or ""

    if lang == "ru":
        prompt = f"""Напиши короткий уникальный редакционный отзыв о фильме для сайта MovieFinder. 
Фильм: «{title}» ({year}), жанр: {genre}, рейтинг TMDB: {rating}/10.
{"Режиссёр: " + director if director else ""}
{"В ролях: " + cast_names if cast_names else ""}
Краткое описание: {description[:400] if description else "нет данных"}

Напиши 2-3 предложения — живым журналистским языком, не шаблонно. 
Упомяни что-то конкретное из описания, жанра или состава. 
Не начинай со слова "Этот". Без markdown, только текст."""
    else:
        prompt = f"""Write a short unique editorial review for the movie on MovieFinder website.
Movie: "{title}" ({year}), genre: {genre}, TMDB rating: {rating}/10.
{"Director: " + director if director else ""}
{"Cast: " + cast_names if cast_names else ""}
Synopsis: {description[:400] if description else "no data"}

Write 2-3 sentences in a lively journalistic tone, not generic.
Mention something specific from the synopsis, genre or cast.
Don't start with "This". No markdown, plain text only."""

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 200,
                    "temperature": 0.8,
                }
            )
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"AI review error: {e}")
        return ""

async def get_or_generate_review(movie: dict, lang: str) -> str:
    """Get from cache or generate. Non-blocking — returns empty string if fails."""
    tmdb_id = movie.get("tmdb_id") or movie.get("id")
    if not tmdb_id:
        return ""
    
    cached = get_cached_review(tmdb_id, lang)
    if cached:
        return cached
    
    review = await generate_review(movie, lang)
    if review:
        save_review(tmdb_id, lang, review)
    return review
