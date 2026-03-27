"""
Fetch English titles from TMDB for all movies.
Priority: popular (vote_count > 1000) → recent (2023-2026) → rest by year DESC
"""
import sqlite3
import asyncio
import httpx
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

TMDB_API_KEY = "8265bd1679663a7ea12ac168da84d2e8"
DB_PATH = "/home/moneyfast/projects/moviefinder/data/moviefinder.db"
CONCURRENCY = 15
BATCH = 300

async def fetch_en(client, semaphore, movie_id, tmdb_id):
    async with semaphore:
        try:
            r = await client.get(
                f"https://api.themoviedb.org/3/movie/{tmdb_id}",
                params={"api_key": TMDB_API_KEY, "language": "en-US"},
                timeout=10
            )
            if r.status_code == 200:
                d = r.json()
                return movie_id, d.get("title", "") or d.get("original_title", "")
            elif r.status_code == 429:
                await asyncio.sleep(15)
            return None
        except:
            return None

async def main():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # PRIORITY 1: Popular (vote_count > 1000) - most searched
    p1 = c.execute("""
        SELECT id, tmdb_id FROM movies
        WHERE (title_en IS NULL OR title_en = '') AND tmdb_id IS NOT NULL AND vote_count > 1000
        ORDER BY vote_count DESC
    """).fetchall()
    logger.info(f"P1 (popular): {len(p1)}")

    # PRIORITY 2: Recent 2023-2026
    p2 = c.execute("""
        SELECT id, tmdb_id FROM movies
        WHERE (title_en IS NULL OR title_en = '') AND tmdb_id IS NOT NULL
        AND year >= 2023 AND vote_count <= 1000
        ORDER BY year DESC, id DESC
    """).fetchall()
    logger.info(f"P2 (2023-2026): {len(p2)}")

    # PRIORITY 3: Rest by year DESC
    p3 = c.execute("""
        SELECT id, tmdb_id FROM movies
        WHERE (title_en IS NULL OR title_en = '') AND tmdb_id IS NOT NULL
        AND (year < 2023 OR year IS NULL) AND vote_count <= 1000
        ORDER BY year DESC NULLS LAST, id
    """).fetchall()
    logger.info(f"P3 (rest): {len(p3)}")

    all_movies = p1 + p2 + p3
    total = len(all_movies)
    logger.info(f"Total: {total}")

    semaphore = asyncio.Semaphore(CONCURRENCY)
    updated = 0

    async with httpx.AsyncClient() as client:
        for batch_start in range(0, total, BATCH):
            batch = all_movies[batch_start:batch_start + BATCH]
            tasks = [fetch_en(client, semaphore, mid, tmdb_id) for mid, tmdb_id in batch]
            results = await asyncio.gather(*tasks)

            for res in results:
                if res:
                    movie_id, title_en = res
                    if title_en:
                        conn.execute("UPDATE movies SET title_en=? WHERE id=?", (title_en, movie_id))
                        updated += 1

            conn.commit()
            done = batch_start + len(batch)
            if done % 3000 == 0 or done >= total:
                logger.info(f"Progress: {done}/{total} | Updated: {updated}")

    conn.close()
    logger.info(f"Done! {updated}/{total}")

if __name__ == "__main__":
    asyncio.run(main())
