"""
Smart TMDB meta fetch: title_ru + vote_count + popularity
Priority order:
  1. Years 2025-2026 (newest, most important for SEO)
  2. High rating movies (rating >= 7.0, most searched)  
  3. Everything else
"""
import sqlite3
import asyncio
import httpx
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

TMDB_API_KEY = "8265bd1679663a7ea12ac168da84d2e8"
DB_PATH = "/home/moneyfast/projects/moviefinder/data/moviefinder.db"
CONCURRENCY = 10
BATCH_COMMIT = 200

async def fetch_one(client, semaphore, movie_id, tmdb_id, title):
    async with semaphore:
        try:
            r = await client.get(
                f"https://api.themoviedb.org/3/movie/{tmdb_id}",
                params={"api_key": TMDB_API_KEY, "language": "ru-RU"},
                timeout=10
            )
            if r.status_code == 200:
                d = r.json()
                return (
                    movie_id,
                    d.get("title", "") or title,
                    int(d.get("vote_count", 0) or 0),
                    float(d.get("popularity", 0) or 0),
                )
            elif r.status_code == 429:
                await asyncio.sleep(15)
            return None
        except:
            return None

async def process_batch(client, semaphore, conn, movies, label):
    updated = 0
    tasks = [fetch_one(client, semaphore, mid, tmdb_id, title) for mid, tmdb_id, title in movies]
    results = await asyncio.gather(*tasks)
    for res in results:
        if not res:
            continue
        movie_id, title_ru, vote_count, popularity = res
        orig = conn.execute("SELECT title FROM movies WHERE id=?", (movie_id,)).fetchone()
        orig_title = orig[0] if orig else ""
        if title_ru and title_ru != orig_title:
            conn.execute(
                "UPDATE movies SET title_ru=?, vote_count=?, popularity=? WHERE id=?",
                (title_ru, vote_count, popularity, movie_id)
            )
        else:
            conn.execute(
                "UPDATE movies SET vote_count=?, popularity=? WHERE id=?",
                (vote_count, popularity, movie_id)
            )
        updated += 1
    conn.commit()
    return updated

async def main():
    conn = sqlite3.connect(DB_PATH)

    # PRIORITY 1: 2025-2026 (newest, SEO critical)
    conn.execute("SELECT 1").fetchone()  # wake up
    p1 = conn.execute("""
        SELECT id, tmdb_id, title FROM movies
        WHERE vote_count = 0 AND tmdb_id IS NOT NULL AND year IN (2025, 2026)
        ORDER BY year DESC, id DESC
    """).fetchall()
    logger.info(f"Priority 1 (2025-2026): {len(p1)} movies")

    # PRIORITY 2: High rated (rating >= 7.0, popular movies)
    p2 = conn.execute("""
        SELECT id, tmdb_id, title FROM movies
        WHERE vote_count = 0 AND tmdb_id IS NOT NULL AND rating >= 7.0
        AND year NOT IN (2025, 2026)
        ORDER BY rating DESC
    """).fetchall()
    logger.info(f"Priority 2 (rating >= 7.0): {len(p2)} movies")

    # PRIORITY 3: Rest
    p3 = conn.execute("""
        SELECT id, tmdb_id, title FROM movies
        WHERE vote_count = 0 AND tmdb_id IS NOT NULL AND rating < 7.0
        ORDER BY year DESC, id
    """).fetchall()
    logger.info(f"Priority 3 (rest): {len(p3)} movies")

    all_movies = p1 + p2 + p3
    total = len(all_movies)
    logger.info(f"Total to process: {total}")

    semaphore = asyncio.Semaphore(CONCURRENCY)
    grand_total = 0

    async with httpx.AsyncClient() as client:
        for batch_start in range(0, total, BATCH_COMMIT):
            batch = all_movies[batch_start:batch_start + BATCH_COMMIT]
            updated = await process_batch(client, semaphore, conn, batch, "")
            grand_total += updated
            done = batch_start + len(batch)
            if done % 1000 == 0 or done >= total:
                logger.info(f"Progress: {done}/{total} | Updated: {grand_total}")

    conn.close()
    logger.info(f"Done! {grand_total}/{total}")

if __name__ == "__main__":
    asyncio.run(main())
