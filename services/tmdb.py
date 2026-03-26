import httpx
import asyncio
from typing import Optional, List, Dict, Any

TMDB_API_KEY = "8265bd1679663a7ea12ac168da84d2e8"
BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

GENRE_MAP = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy",
    80: "Crime", 99: "Documentary", 18: "Drama", 10751: "Family",
    14: "Fantasy", 36: "History", 27: "Horror", 10402: "Music",
    9648: "Mystery", 10749: "Romance", 878: "Sci-Fi", 10770: "TV Movie",
    53: "Thriller", 10752: "War", 37: "Western"
}

LANG_TO_TMDB = {
    "ru": "ru-RU",
    "en": "en-US",
}


def format_movie(m: dict) -> dict:
    genres = [GENRE_MAP.get(g, "") for g in m.get("genre_ids", [])]
    genre_str = ", ".join([g for g in genres if g])
    release_date = m.get("release_date", "")
    year = int(release_date[:4]) if release_date and len(release_date) >= 4 else None
    poster = m.get("poster_path")
    return {
        "tmdb_id": m.get("id"),
        "title": m.get("title") or m.get("name", ""),
        "title_ru": m.get("title") or m.get("name", ""),
        "year": year,
        "rating": round(m.get("vote_average", 0), 1),
        "poster_url": f"{IMAGE_BASE}{poster}" if poster else None,
        "genre": genre_str,
        "description": m.get("overview", ""),
        "description_ru": m.get("overview", ""),
        "runtime": m.get("runtime"),
        "release_date": release_date,
        "backdrop_path": m.get("backdrop_path"),
    }


async def fetch_tmdb(endpoint: str, params: dict = None, lang: str = "en") -> dict:
    tmdb_lang = LANG_TO_TMDB.get(lang, "en-US")
    p = {"api_key": TMDB_API_KEY, "language": tmdb_lang}
    if params:
        p.update(params)
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{BASE_URL}{endpoint}", params=p)
        resp.raise_for_status()
        return resp.json()


async def search_movies(query: str, page: int = 1, lang: str = "en") -> List[dict]:
    data = await fetch_tmdb("/search/multi", {"query": query, "page": page, "include_adult": False}, lang=lang)
    results = []
    for m in data.get("results", []):
        if m.get("media_type") in ("movie", "tv") or "title" in m or "name" in m:
            results.append(format_movie(m))
    return results


async def get_movie_details(tmdb_id: int, media_type: str = "movie", lang: str = "en") -> Optional[dict]:
    try:
        data = await fetch_tmdb(f"/{media_type}/{tmdb_id}", {"append_to_response": "credits,similar,videos"}, lang=lang)
        m = format_movie(data)
        m["runtime"] = data.get("runtime")
        # Cast
        cast = data.get("credits", {}).get("cast", [])[:10]
        m["cast"] = [{"name": a["name"], "character": a.get("character", ""), "profile": f"https://image.tmdb.org/t/p/w185{a['profile_path']}" if a.get("profile_path") else None} for a in cast]
        # Similar
        similar_raw = data.get("similar", {}).get("results", [])[:8]
        m["similar"] = [format_movie(s) for s in similar_raw]
        # Trailer
        videos = data.get("videos", {}).get("results", [])
        trailer = next((v for v in videos if v.get("type") == "Trailer" and v.get("site") == "YouTube"), None)
        m["trailer_key"] = trailer["key"] if trailer else None
        # Genres as list
        genres_list = data.get("genres", [])
        m["genres_list"] = [g["name"] for g in genres_list]
        return m
    except Exception as e:
        print(f"Error fetching movie details: {e}")
        return None


async def get_trending(media_type: str = "all", time_window: str = "day", lang: str = "en") -> List[dict]:
    data = await fetch_tmdb(f"/trending/{media_type}/{time_window}", lang=lang)
    return [format_movie(m) for m in data.get("results", [])[:20]]


async def get_top_rated(media_type: str = "movie", lang: str = "en") -> List[dict]:
    data = await fetch_tmdb(f"/{media_type}/top_rated", lang=lang)
    return [format_movie(m) for m in data.get("results", [])[:20]]


async def get_now_playing(lang: str = "en") -> List[dict]:
    data = await fetch_tmdb("/movie/now_playing", lang=lang)
    return [format_movie(m) for m in data.get("results", [])[:20]]


async def get_upcoming(lang: str = "en") -> List[dict]:
    data = await fetch_tmdb("/movie/upcoming", lang=lang)
    return [format_movie(m) for m in data.get("results", [])[:20]]


async def get_popular_movies(pages: int = 3, lang: str = "en") -> List[dict]:
    all_movies = []
    tasks = [fetch_tmdb("/movie/popular", {"page": p}, lang=lang) for p in range(1, pages+1)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for data in results:
        if isinstance(data, dict):
            all_movies.extend([format_movie(m) for m in data.get("results", [])])
    return all_movies
