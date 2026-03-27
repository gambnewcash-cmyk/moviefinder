"""
Weekly updater: fetch new 2025-2026 releases from TMDB.
Adds only new movies (skips existing by tmdb_id).
Run manually or via cron: python3 update_new_releases.py
"""
import sqlite3
import asyncio
import httpx
import os
from datetime import datetime

TMDB_API_KEY = os.getenv("TMDB_API_KEY", "8265bd1679663a7ea12ac168da84d2e8")
BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
DB_PATH = "/home/moneyfast/projects/moviefinder/data/moviefinder.db"

def get_db():
    return sqlite3.connect(DB_PATH)

def save_movie(conn, m):
    tmdb_id = m.get("id")
    if not tmdb_id:
        return False
    release_date = m.get("release_date", "")
    year = int(release_date[:4]) if release_date and len(release_date) >= 4 else None
    title = m.get("title", "") or m.get("name", "")
    title_ru = m.get("title_ru", "") or title
    rating = m.get("vote_average", 0) or 0
    poster = m.get("poster_path", "")
    poster_url = f"{IMAGE_BASE}{poster}" if poster else ""
    genre_ids = m.get("genre_ids", [])
    genre = m.get("genre_str", "")
    description = m.get("overview", "") or ""
    vote_count = m.get("vote_count", 0) or 0
    popularity = m.get("popularity", 0.0) or 0.0

    existing = conn.execute("SELECT id FROM movies WHERE tmdb_id=?", (tmdb_id,)).fetchone()
    if existing:
        # Update vote_count and popularity for existing
        title_ru_val = m.get("title_ru", "") or m.get("title", "")
        conn.execute(
            "UPDATE movies SET vote_count=?, popularity=?, rating=?, title_ru=? WHERE tmdb_id=?",
            (vote_count, popularity, rating, title_ru_val, tmdb_id)
        )
        return True  # count as updated

    if not poster_url:
        return False

    conn.execute(
        """INSERT INTO movies (tmdb_id, title, title_ru, year, rating, poster_url, genre, 
           description, description_ru, vote_count, popularity)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (tmdb_id, title, title_ru, year, rating, poster_url, genre,
         description, "", vote_count, popularity)
    )
    return True

GENRE_MAP = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy",
    80: "Crime", 99: "Documentary", 18: "Drama", 10751: "Family",
    14: "Fantasy", 36: "History", 27: "Horror", 10402: "Music",
    9648: "Mystery", 10749: "Romance", 878: "Science Fiction",
    10770: "TV Movie", 53: "Thriller", 10752: "War", 37: "Western"
}

async def fetch_year(client, year, seen_ids, conn):
    added = 0
    updated = 0
    for page in range(1, 26):
        try:
            r = await client.get(
                f"{BASE_URL}/discover/movie",
                params={
                    "api_key": TMDB_API_KEY,
                    "language": "ru-RU",
                    "sort_by": "popularity.desc",
                    "primary_release_year": year,
                    "vote_count.gte": 5,
                    "page": page,
                },
                timeout=15,
            )
            if r.status_code == 429:
                print(f"  Rate limit, sleeping 10s...")
                await asyncio.sleep(10)
                continue
            if r.status_code != 200:
                break
            results = r.json().get("results", [])
            if not results:
                break
            for m in results:
                mid = m.get("id")
                if not mid:
                    continue
                if mid in seen_ids:
                    # Still update popularity/vote_count for existing
                    pass
                seen_ids.add(mid)
                # Add genre string
                genre_ids = m.get("genre_ids", [])
                m["genre_str"] = ", ".join(GENRE_MAP.get(gid, "") for gid in genre_ids if gid in GENRE_MAP)
                is_new = save_movie(conn, m)
                if is_new:
                    added += 1
                else:
                    updated += 1
            conn.commit()
            await asyncio.sleep(0.05)
        except Exception as e:
            print(f"  Error year={year} page={page}: {e}")
            break
    return added, updated

async def main():
    conn = get_db()
    before = conn.execute("SELECT COUNT(*) FROM movies").fetchone()[0]

    # Load existing IDs
    seen_ids = set(int(r[0]) for r in conn.execute("SELECT tmdb_id FROM movies WHERE tmdb_id IS NOT NULL").fetchall())
    print(f"Existing movies: {before:,} | Starting update for 2026, 2025...")

    total_added = 0
    total_updated = 0

    async with httpx.AsyncClient() as client:
        for year in [2026, 2025]:
            added, updated = await fetch_year(client, year, seen_ids, conn)
            total_added += added
            total_updated += updated
            print(f"Year {year}: +{added} new, {updated} updated")

    after = conn.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
    conn.close()
    print(f"\nDone! Added: {total_added} | Updated: {total_updated} | Total: {after:,}")
    print(f"Run completed at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")

if __name__ == "__main__":
    asyncio.run(main())
