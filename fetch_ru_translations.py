import sqlite3
import requests
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

TMDB_API_KEY = "8265bd1679663a7ea12ac168da84d2e8"
DB_PATH = "/home/moneyfast/projects/moviefinder/data/moviefinder.db"
BATCH_SIZE = 100
DELAY = 0.05  # 50ms between requests to stay under TMDB rate limit (40 req/10s)

def fetch_ru_data(tmdb_id):
    """Fetch Russian title and overview from TMDB."""
    try:
        url = f"https://api.themoviedb.org/3/movie/{tmdb_id}"
        r = requests.get(url, params={"api_key": TMDB_API_KEY, "language": "ru-RU"}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            title_ru = data.get("title", "")
            desc_ru = data.get("overview", "")
            return title_ru, desc_ru
        elif r.status_code == 429:
            logger.warning(f"Rate limit hit, sleeping 10s")
            time.sleep(10)
            return None, None
        else:
            return None, None
    except Exception as e:
        logger.error(f"Error fetching {tmdb_id}: {e}")
        return None, None

def main():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Get movies that don't have Russian title yet (title_ru = title or empty)
    c.execute("""
        SELECT id, tmdb_id, title FROM movies 
        WHERE (title_ru = title OR title_ru IS NULL OR title_ru = '')
        AND tmdb_id IS NOT NULL AND tmdb_id != ''
        ORDER BY id
    """)
    movies = c.fetchall()
    logger.info(f"Movies to process: {len(movies)}")
    
    updated = 0
    skipped = 0
    
    for i, (movie_id, tmdb_id, title) in enumerate(movies):
        title_ru, desc_ru = fetch_ru_data(tmdb_id)
        
        if title_ru and title_ru != title:
            c.execute(
                "UPDATE movies SET title_ru = ?, description_ru = ? WHERE id = ?",
                (title_ru, desc_ru or "", movie_id)
            )
            updated += 1
        else:
            skipped += 1
        
        # Commit every 500 records
        if (i + 1) % 500 == 0:
            conn.commit()
            logger.info(f"Progress: {i+1}/{len(movies)} | Updated: {updated} | Skipped: {skipped}")
        
        time.sleep(DELAY)
    
    conn.commit()
    logger.info(f"Done! Updated: {updated} | Skipped: {skipped}")
    conn.close()

if __name__ == "__main__":
    main()
