"""
Fetch Russian titles, vote_count and popularity from TMDB for all movies.
One request per movie, ~1.5h for 100k movies.
"""
import sqlite3
import requests
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

TMDB_API_KEY = "8265bd1679663a7ea12ac168da84d2e8"
DB_PATH = "/home/moneyfast/projects/moviefinder/data/moviefinder.db"
DELAY = 0.05  # 50ms = 20 req/s, TMDB limit is 40/10s

def fetch_tmdb(tmdb_id):
    try:
        r = requests.get(
            f"https://api.themoviedb.org/3/movie/{tmdb_id}",
            params={"api_key": TMDB_API_KEY, "language": "ru-RU"},
            timeout=10
        )
        if r.status_code == 200:
            d = r.json()
            return {
                "title_ru": d.get("title", ""),
                "vote_count": d.get("vote_count", 0) or 0,
                "popularity": d.get("popularity", 0.0) or 0.0,
            }
        elif r.status_code == 429:
            logger.warning("Rate limit, sleeping 10s")
            time.sleep(10)
        return None
    except Exception as e:
        logger.error(f"Error {tmdb_id}: {e}")
        return None

def main():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Process all movies missing vote_count
    c.execute("""
        SELECT id, tmdb_id, title FROM movies
        WHERE vote_count = 0 AND tmdb_id IS NOT NULL AND tmdb_id != ''
        ORDER BY id
    """)
    movies = c.fetchall()
    logger.info(f"To process: {len(movies)}")

    updated = 0
    for i, (movie_id, tmdb_id, title) in enumerate(movies):
        data = fetch_tmdb(tmdb_id)
        if data:
            title_ru = data["title_ru"]
            # Only update title_ru if it's actually different (Russian translation exists)
            if title_ru and title_ru != title:
                c.execute(
                    "UPDATE movies SET title_ru=?, vote_count=?, popularity=? WHERE id=?",
                    (title_ru, data["vote_count"], data["popularity"], movie_id)
                )
            else:
                c.execute(
                    "UPDATE movies SET vote_count=?, popularity=? WHERE id=?",
                    (data["vote_count"], data["popularity"], movie_id)
                )
            updated += 1

        if (i + 1) % 500 == 0:
            conn.commit()
            logger.info(f"Progress: {i+1}/{len(movies)} | Updated: {updated}")

        time.sleep(DELAY)

    conn.commit()
    logger.info(f"Done! Updated: {updated}")
    conn.close()

if __name__ == "__main__":
    main()
