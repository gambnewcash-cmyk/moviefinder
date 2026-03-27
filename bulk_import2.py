"""
Phase 2 bulk import: get remaining movies to reach 100k.
Strategy: discover/movie with multiple sort_by options (500 pages each = 10k each)
"""
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

async def discover_movies(client, params, page):
    try:
        p = dict(params)
        p["page"] = page
        p["api_key"] = TMDB_API_KEY
        r = await client.get(f"{BASE_URL}/discover/movie", params=p, timeout=15)
        if r.status_code == 200:
            data = r.json()
            return data.get("results", []), data.get("total_pages", 0)
        elif r.status_code == 429:
            await asyncio.sleep(10)
            return await discover_movies(client, params, page)
        return [], 0
    except Exception as e:
        return [], 0

async def main():
    conn = get_db()
    existing = conn.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
    print(f"Starting with {existing} movies in DB")

    seen_ids = set()
    existing_ids = conn.execute("SELECT tmdb_id FROM movies").fetchall()
    for row in existing_ids:
        seen_ids.add(row[0])
    print(f"Loaded {len(seen_ids)} existing IDs")

    total_saved = 0

    # Multiple discover strategies
    strategies = [
        # Sort by different criteria - each gives different order = different movies per page
        {"sort_by": "popularity.desc", "vote_count.gte": 1},
        {"sort_by": "vote_count.desc", "vote_count.gte": 1},
        {"sort_by": "revenue.desc", "vote_count.gte": 1},
        {"sort_by": "primary_release_date.desc", "vote_count.gte": 1},
        {"sort_by": "primary_release_date.asc", "vote_count.gte": 1},
        {"sort_by": "vote_average.desc", "vote_count.gte": 50},
        {"sort_by": "popularity.asc", "vote_count.gte": 1},
        # By decade ranges with popularity sort
        {"sort_by": "popularity.desc", "primary_release_date.gte": "2020-01-01", "vote_count.gte": 1},
        {"sort_by": "popularity.desc", "primary_release_date.gte": "2015-01-01", "primary_release_date.lte": "2019-12-31", "vote_count.gte": 1},
        {"sort_by": "popularity.desc", "primary_release_date.gte": "2010-01-01", "primary_release_date.lte": "2014-12-31", "vote_count.gte": 1},
        {"sort_by": "popularity.desc", "primary_release_date.gte": "2005-01-01", "primary_release_date.lte": "2009-12-31", "vote_count.gte": 1},
        {"sort_by": "popularity.desc", "primary_release_date.gte": "2000-01-01", "primary_release_date.lte": "2004-12-31", "vote_count.gte": 1},
        {"sort_by": "popularity.desc", "primary_release_date.gte": "1990-01-01", "primary_release_date.lte": "1999-12-31", "vote_count.gte": 1},
        {"sort_by": "popularity.desc", "primary_release_date.gte": "1980-01-01", "primary_release_date.lte": "1989-12-31", "vote_count.gte": 1},
        {"sort_by": "popularity.desc", "primary_release_date.gte": "1960-01-01", "primary_release_date.lte": "1979-12-31", "vote_count.gte": 1},
        {"sort_by": "popularity.desc", "primary_release_date.lte": "1959-12-31", "vote_count.gte": 1},
    ]

    async with httpx.AsyncClient() as client:
        for strategy in strategies:
            if existing + total_saved >= 100000:
                break
            
            label = strategy.get("sort_by", "?")
            date_range = ""
            if "primary_release_date.gte" in strategy:
                date_range = f" [{strategy.get('primary_release_date.gte','')[:4]}-{strategy.get('primary_release_date.lte','now')[:4]}]"
            print(f"\n--- discover sort={label}{date_range} ---")
            
            params = {"language": "ru-RU"}
            params.update(strategy)
            
            # First page to get total_pages
            results, total_pages = await discover_movies(client, params, 1)
            max_pages = min(total_pages, 500)
            print(f"  Total pages available: {total_pages} (using {max_pages})")
            
            # Process page 1
            batch_saved = 0
            for m in results:
                mid = m.get("id")
                if mid and mid not in seen_ids:
                    seen_ids.add(mid)
                    if save_movie_bulk(conn, format_movie_simple(m)):
                        batch_saved += 1
                        total_saved += 1
            await asyncio.sleep(0.1)
            
            # Process remaining pages
            for page in range(2, max_pages + 1):
                if existing + total_saved >= 100000:
                    print(f"  Reached 100k target!")
                    break
                
                results, _ = await discover_movies(client, params, page)
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
                
                if page % 50 == 0:
                    conn.commit()
                    print(f"  p{page}/{max_pages}: +{batch_saved} | total: {existing + total_saved:,}")
                
                await asyncio.sleep(0.1)
            
            conn.commit()
            print(f"  Strategy done. Total: {existing + total_saved:,}")

    conn.commit()
    final = conn.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
    print(f"\n=== DONE ===")
    print(f"Added this run: {total_saved:,}")
    print(f"Total in DB: {final:,}")
    conn.close()

asyncio.run(main())
