import asyncio
import httpx
import sqlite3
import os
from dotenv import load_dotenv

load_dotenv('.env')
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "8265bd1679663a7ea12ac168da84d2e8")
BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

GENRE_MAP = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy",
    80: "Crime", 99: "Documentary", 18: "Drama", 10751: "Family",
    14: "Fantasy", 36: "History", 27: "Horror", 10402: "Music",
    9648: "Mystery", 10749: "Romance", 878: "Sci-Fi", 10770: "TV Movie",
    53: "Thriller", 10752: "War", 37: "Western"
}

def get_db():
    conn = sqlite3.connect('data/moviefinder.db')
    conn.row_factory = sqlite3.Row
    return conn

def save_movie_bulk(conn, movie_data: dict):
    try:
        conn.execute("""
            INSERT OR IGNORE INTO movies 
            (tmdb_id, title, title_ru, year, rating, poster_url, genre, description, description_ru)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            movie_data.get("tmdb_id"),
            movie_data.get("title", ""),
            movie_data.get("title_ru") or movie_data.get("title", ""),
            movie_data.get("year"),
            movie_data.get("rating", 0),
            movie_data.get("poster_url"),
            movie_data.get("genre", ""),
            movie_data.get("description", "")[:500] if movie_data.get("description") else "",
            movie_data.get("description", "")[:500] if movie_data.get("description") else "",
        ))
        return True
    except Exception as e:
        return False

def format_movie_simple(m: dict) -> dict:
    genres = [GENRE_MAP.get(g, "") for g in m.get("genre_ids", [])]
    genre_str = ", ".join([g for g in genres if g])
    release_date = m.get("release_date", "")
    year = int(release_date[:4]) if release_date and len(release_date) >= 4 else None
    poster = m.get("poster_path")
    return {
        "tmdb_id": m.get("id"),
        "title": m.get("title", m.get("name", "")),
        "title_ru": m.get("title", m.get("name", "")),
        "year": year,
        "rating": round(m.get("vote_average", 0), 1),
        "poster_url": f"{IMAGE_BASE}{poster}" if poster else None,
        "genre": genre_str,
        "description": m.get("overview", "")[:500],
    }

async def fetch_endpoint(client, endpoint, page, lang="ru-RU"):
    try:
        r = await client.get(
            f"{BASE_URL}/movie/{endpoint}",
            params={"api_key": TMDB_API_KEY, "language": lang, "page": page},
            timeout=15,
        )
        if r.status_code == 200:
            return r.json().get("results", [])
        elif r.status_code == 429:
            await asyncio.sleep(10)
            return await fetch_endpoint(client, endpoint, page, lang)
        return []
    except:
        return []

async def main():
    conn = get_db()
    existing = conn.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
    print(f"Starting with {existing} movies in DB")

    seen_ids = set()
    existing_ids = conn.execute("SELECT tmdb_id FROM movies").fetchall()
    for row in existing_ids:
        seen_ids.add(row[0])

    total_saved = 0

    endpoints = [
        ("popular", "ru-RU"),
        ("top_rated", "ru-RU"),
        ("now_playing", "ru-RU"),
        ("upcoming", "ru-RU"),
    ]

    async with httpx.AsyncClient() as client:
        # Phase 1: Standard endpoints
        for endpoint, lang in endpoints:
            if total_saved + existing >= 100000:
                break
            print(f"\n--- /movie/{endpoint} ({lang}) ---")
            page_count = 0
            for page in range(1, 501):
                if total_saved + existing >= 100000:
                    print("Reached 100k target!")
                    break
                results = await fetch_endpoint(client, endpoint, page, lang)
                if not results:
                    break
                batch_saved = 0
                for m in results:
                    mid = m.get("id")
                    if mid and mid not in seen_ids:
                        seen_ids.add(mid)
                        if save_movie_bulk(conn, format_movie_simple(m)):
                            batch_saved += 1
                            total_saved += 1
                page_count += 1
                if page_count % 10 == 0:
                    conn.commit()
                    print(f"  p{page}: +{batch_saved} | total: {existing + total_saved:,}")
                await asyncio.sleep(0.1)
            conn.commit()

        # Phase 2: discover by year
        if total_saved + existing < 100000:
            print(f"\n--- Phase 2: discover/movie by year ---")
            for year in range(2024, 1960, -1):
                if total_saved + existing >= 100000:
                    break
                for page in range(1, 26):
                    if total_saved + existing >= 100000:
                        break
                    try:
                        r = await client.get(
                            f"{BASE_URL}/discover/movie",
                            params={
                                "api_key": TMDB_API_KEY,
                                "language": "ru-RU",
                                "sort_by": "vote_count.desc",
                                "primary_release_year": year,
                                "vote_count.gte": 5,
                                "page": page,
                            },
                            timeout=15,
                        )
                        if r.status_code == 429:
                            await asyncio.sleep(10)
                            continue
                        if r.status_code != 200:
                            break
                        results = r.json().get("results", [])
                        if not results:
                            break
                        batch_saved = 0
                        for m in results:
                            mid = m.get("id")
                            if mid and mid not in seen_ids:
                                seen_ids.add(mid)
                                if save_movie_bulk(conn, format_movie_simple(m)):
                                    batch_saved += 1
                                    total_saved += 1
                        if batch_saved > 0:
                            conn.commit()
                        await asyncio.sleep(0.1)
                    except Exception as e:
                        print(f"  Error year={year} p={page}: {e}")
                        break
                if (2024 - year) % 10 == 0:
                    print(f"  Year {year}: total {existing + total_saved:,}")

    conn.commit()
    final = conn.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
    print(f"\n=== DONE ===")
    print(f"Added: {total_saved:,}")
    print(f"Total: {final:,}")
    conn.close()

asyncio.run(main())
