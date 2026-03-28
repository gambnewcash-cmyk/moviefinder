import asyncio, httpx, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()
from services.tmdb import get_movie_details
from services.ai_review import get_or_generate_review, get_cached_review

async def get_all_tmdb_ids():
    ids = []
    async with httpx.AsyncClient(timeout=30) as client:
        for chunk in range(1, 12):
            try:
                resp = await client.get(f"https://moviefinders.net/sitemap-movies-{chunk}.xml")
                for line in resp.text.split("\n"):
                    if "/movie/" in line and "/en/movie/" not in line and "<loc>" in line:
                        tid = line.strip().replace("<loc>https://moviefinders.net/movie/","").replace("</loc>","").strip()
                        if tid.isdigit():
                            ids.append(int(tid))
            except: pass
    return ids

async def warmup():
    print("Fetching movie IDs from sitemap...")
    ids = await get_all_tmdb_ids()
    print(f"Found {len(ids)} movies. Starting warmup...")
    done = skipped = errors = 0
    for i, tmdb_id in enumerate(ids):
        ru_cached = get_cached_review(tmdb_id, "ru")
        en_cached = get_cached_review(tmdb_id, "en")
        if ru_cached and en_cached:
            skipped += 1
            continue
        try:
            movie = await get_movie_details(tmdb_id, "movie", lang="ru")
            if not movie:
                errors += 1; continue
            if not ru_cached:
                await get_or_generate_review(movie, "ru")
                await asyncio.sleep(2.5)
            if not en_cached:
                await get_or_generate_review(movie, "en")
                await asyncio.sleep(2.5)
            done += 1
            print(f"[{i+1}/{len(ids)}] ✓ {movie.get('title_ru') or movie.get('title','?')} | done={done} skip={skipped} err={errors}")
        except Exception as e:
            errors += 1
            print(f"[{i+1}/{len(ids)}] ✗ {tmdb_id}: {e}")
            await asyncio.sleep(5)
    print(f"\nComplete: generated={done}, skipped={skipped}, errors={errors}")

asyncio.run(warmup())
