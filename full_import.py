"""
Full TMDB import: all genres + top_rated + now_playing, max 50 pages each.
Upserts vote_count, popularity, title_ru for all.
"""
import sqlite3
import asyncio
import httpx
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

TMDB_API_KEY = "8265bd1679663a7ea12ac168da84d2e8"
DB_PATH = "/home/moneyfast/projects/moviefinder/data/moviefinder.db"
BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
MAX_PAGES = 50

GENRE_MAP = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy",
    80: "Crime", 99: "Documentary", 18: "Drama", 10751: "Family",
    14: "Fantasy", 36: "History", 27: "Horror", 10402: "Music",
    9648: "Mystery", 10749: "Romance", 878: "Science Fiction",
    53: "Thriller", 10752: "War", 37: "Western"
}

# All genre IDs to crawl
GENRES_TO_CRAWL = list(GENRE_MAP.keys())

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def upsert_movie(conn, m):
    tmdb_id = m.get("id")
    if not tmdb_id:
        return False, False
    release_date = m.get("release_date", "") or ""
    year = int(release_date[:4]) if len(release_date) >= 4 else None
    title = m.get("title", "") or ""
    title_ru = m.get("title_ru", "") or title
    rating = float(m.get("vote_average", 0) or 0)
    vote_count = int(m.get("vote_count", 0) or 0)
    popularity = float(m.get("popularity", 0) or 0)
    poster = m.get("poster_path", "")
    poster_url = f"{IMAGE_BASE}{poster}" if poster else ""
    genre_ids = m.get("genre_ids", [])
    genre = ", ".join(GENRE_MAP.get(gid, "") for gid in genre_ids if gid in GENRE_MAP)
    description = m.get("overview", "") or ""

    if not poster_url:
        return False, False

    existing = conn.execute("SELECT id FROM movies WHERE tmdb_id=?", (tmdb_id,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE movies SET vote_count=?, popularity=?, rating=?, title_ru=? WHERE tmdb_id=?",
            (vote_count, popularity, rating, title_ru, tmdb_id)
        )
        return False, True
    else:
        conn.execute(
            """INSERT INTO movies (tmdb_id, title, title_ru, year, rating, poster_url, genre,
               description, description_ru, vote_count, popularity)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (tmdb_id, title, title_ru, year, rating, poster_url, genre,
             description, "", vote_count, popularity)
        )
        return True, False

async def fetch_page(client, semaphore, url, params):
    async with semaphore:
        for attempt in range(3):
            try:
                r = await client.get(url, params=params, timeout=15)
                if r.status_code == 429:
                    logger.warning("Rate limit, sleeping 15s")
                    await asyncio.sleep(15)
                    continue
                if r.status_code == 200:
                    data = r.json()
                    return data.get("results", []), data.get("total_pages", 1)
                return [], 0
            except Exception as e:
                logger.error(f"Error: {e}")
                await asyncio.sleep(2)
        return [], 0

async def crawl_endpoint(client, semaphore, conn, label, url, base_params):
    """Crawl up to MAX_PAGES of an endpoint."""
    added = updated = 0

    # Page 1 first to get total_pages
    results, total_pages = await fetch_page(client, semaphore, url, {**base_params, "page": 1})
    for m in results:
        is_new, is_upd = upsert_movie(conn, m)
        added += is_new
        updated += is_upd

    # Remaining pages
    pages = min(total_pages, MAX_PAGES)
    if pages > 1:
        tasks = [fetch_page(client, semaphore, url, {**base_params, "page": p}) for p in range(2, pages + 1)]
        all_results = await asyncio.gather(*tasks)
        for page_results, _ in all_results:
            for m in page_results:
                is_new, is_upd = upsert_movie(conn, m)
                added += is_new
                updated += is_upd

    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
    logger.info(f"{label}: +{added} new, {updated} updated | DB: {total:,}")
    return added, updated

async def main():
    conn = get_db()
    before = conn.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
    logger.info(f"Starting. DB: {before:,} movies. Max {MAX_PAGES} pages per endpoint.")

    semaphore = asyncio.Semaphore(15)
    total_added = total_updated = 0

    base = {"api_key": TMDB_API_KEY, "language": "ru-RU"}

    async with httpx.AsyncClient() as client:

        # 1. Now Playing (актуальные в прокате)
        a, u = await crawl_endpoint(client, semaphore, conn,
            "now_playing",
            f"{BASE_URL}/movie/now_playing", base)
        total_added += a; total_updated += u

        # 2. Top Rated (топ всех времён)
        a, u = await crawl_endpoint(client, semaphore, conn,
            "top_rated",
            f"{BASE_URL}/movie/top_rated", base)
        total_added += a; total_updated += u

        # 3. Popular (популярные сейчас)
        a, u = await crawl_endpoint(client, semaphore, conn,
            "popular",
            f"{BASE_URL}/movie/popular", base)
        total_added += a; total_updated += u

        # 4. All genres - discover by genre, popularity.desc
        for genre_id, genre_name in GENRE_MAP.items():
            a, u = await crawl_endpoint(client, semaphore, conn,
                f"genre:{genre_name}",
                f"{BASE_URL}/discover/movie",
                {**base, "sort_by": "popularity.desc", "with_genres": genre_id, "vote_count.gte": 10})
            total_added += a; total_updated += u
            await asyncio.sleep(0.2)

        # 5. Years 2026-2020 (recent years full coverage)
        for year in range(2026, 2019, -1):
            a, u = await crawl_endpoint(client, semaphore, conn,
                f"year:{year}",
                f"{BASE_URL}/discover/movie",
                {**base, "sort_by": "popularity.desc", "primary_release_year": year, "vote_count.gte": 5})
            total_added += a; total_updated += u
            await asyncio.sleep(0.2)

    after = conn.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
    conn.close()
    logger.info(f"\nDone! +{total_added:,} new | {total_updated:,} updated | Final: {after:,}")

if __name__ == "__main__":
    asyncio.run(main())
