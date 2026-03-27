import httpx
import asyncio
import os
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
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


def format_movie(m: dict, en_title: Optional[str] = None) -> dict:
    genres = [GENRE_MAP.get(g, "") for g in m.get("genre_ids", [])]
    genre_str = ", ".join([g for g in genres if g])
    release_date = m.get("release_date") or m.get("first_air_date", "")
    year = int(release_date[:4]) if release_date and len(release_date) >= 4 else None
    poster = m.get("poster_path")
    
    # title_ru: what TMDB returned (could be Russian if language=ru-RU was used)
    title_from_tmdb = m.get("title") or m.get("name", "")
    # For TV: ensure media_type is set correctly
    
    # title (English): use explicit en_title if provided, else use what TMDB returned
    title_en = en_title if en_title else title_from_tmdb
    
    return {
        "tmdb_id": m.get("id"),
        "title": title_en,
        "title_ru": title_from_tmdb,
        "year": year,
        "rating": round(m.get("vote_average", 0), 1),
        "poster_url": f"{IMAGE_BASE}{poster}" if poster else None,
        "genre": genre_str,
        "vote_count": m.get("vote_count"),
        "description": m.get("overview", ""),
        "description_ru": m.get("overview", ""),
        "runtime": m.get("runtime"),
        "release_date": release_date,
        "backdrop_path": m.get("backdrop_path"),
        "imdb_id": m.get("imdb_id"),
        "media_type": m.get("media_type", "movie"),
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


async def _fetch_tmdb_both_langs(endpoint: str, params: dict = None) -> tuple:
    """Fetch TMDB endpoint with both ru-RU and en-US in parallel. Returns (ru_data, en_data)."""
    p_ru = {"api_key": TMDB_API_KEY, "language": "ru-RU"}
    p_en = {"api_key": TMDB_API_KEY, "language": "en-US"}
    if params:
        p_ru.update(params)
        p_en.update(params)
    async with httpx.AsyncClient(timeout=10) as client:
        ru_resp, en_resp = await asyncio.gather(
            client.get(f"{BASE_URL}{endpoint}", params=p_ru),
            client.get(f"{BASE_URL}{endpoint}", params=p_en),
        )
        ru_resp.raise_for_status()
        en_resp.raise_for_status()
        return ru_resp.json(), en_resp.json()


async def search_movies(query: str, page: int = 1, lang: str = "en") -> List[dict]:
    if lang == "ru":
        # Fetch both languages in parallel to get proper title (EN) and title_ru (RU)
        ru_data, en_data = await _fetch_tmdb_both_langs(
            "/search/multi",
            {"query": query, "page": page, "include_adult": False}
        )
        # Build lookup: tmdb_id -> en_title from en_data
        en_titles = {}
        for m in en_data.get("results", []):
            tmdb_id = m.get("id")
            if tmdb_id:
                en_titles[tmdb_id] = m.get("title") or m.get("name", "")
        
        results = []
        for m in ru_data.get("results", []):
            if m.get("media_type") in ("movie", "tv") or "title" in m or "name" in m:
                en_title = en_titles.get(m.get("id"))
                results.append(format_movie(m, en_title=en_title))
        return results
    else:
        data = await fetch_tmdb("/search/multi", {"query": query, "page": page, "include_adult": False}, lang=lang)
        results = []
        for m in data.get("results", []):
            if m.get("media_type") in ("movie", "tv") or "title" in m or "name" in m:
                results.append(format_movie(m))
        return results


async def get_movie_details(tmdb_id: int, media_type: str = "movie", lang: str = "en") -> Optional[dict]:
    try:
        extra_params = {"append_to_response": "credits,similar,videos"}
        if lang == "ru":
            # Fetch both languages: ru for display, en for JustWatch title
            ru_data, en_data = await _fetch_tmdb_both_langs(
                f"/{media_type}/{tmdb_id}", extra_params
            )
            en_title = en_data.get("title") or en_data.get("name", "")
            # Normalize TV show fields before format_movie
            if media_type == "tv":
                ru_data["title"] = ru_data.get("name", ru_data.get("title", ""))
                ru_data["release_date"] = ru_data.get("first_air_date", "")
                ru_data["original_title"] = ru_data.get("original_name", ru_data.get("original_title", ""))
                ru_data["media_type"] = "tv"
                en_data["title"] = en_data.get("name", en_data.get("title", ""))
                en_title = en_data.get("title", "")
            m = format_movie(ru_data, en_title=en_title)
            # Use Russian description but also store English description for JustWatch compatibility
            m["description"] = ru_data.get("overview", "") or en_data.get("overview", "")
            m["runtime"] = ru_data.get("runtime")
            # H2 FIX: TV seasons/episodes
            if media_type == "tv":
                ep_runtime = ru_data.get("episode_run_time", [])
                m["runtime"] = ep_runtime[0] if ep_runtime else None
                m["number_of_seasons"] = ru_data.get("number_of_seasons")
                m["number_of_episodes"] = ru_data.get("number_of_episodes")
            # Similar movies - fetch with ru lang for display
            similar_raw = ru_data.get("similar", {}).get("results", [])[:8]
            en_similar = en_data.get("similar", {}).get("results", [])
            en_sim_titles = {s.get("id"): s.get("title") or s.get("name") for s in en_similar}
            # For TV shows, similar items are also TV shows - set media_type
            if media_type == "tv":
                for s in similar_raw:
                    if "media_type" not in s:
                        s["media_type"] = "tv"
                        s["title"] = s.get("name", s.get("title", ""))
                        s["release_date"] = s.get("first_air_date", "")
            m["similar"] = [format_movie(s, en_title=en_sim_titles.get(s.get("id"))) for s in similar_raw]
            # Trailer
            videos = ru_data.get("videos", {}).get("results", [])
            trailer = next((v for v in videos if v.get("type") == "Trailer" and v.get("site") == "YouTube"), None)
            m["trailer_key"] = trailer["key"] if trailer else None
            # Cast
            cast = ru_data.get("credits", {}).get("cast", [])[:10]
            m["cast"] = [{"name": a["name"], "character": a.get("character", ""), "profile": f"https://image.tmdb.org/t/p/w185{a['profile_path']}" if a.get("profile_path") else None} for a in cast]
            # Genres as list
            genres_list = ru_data.get("genres", [])
            m["genres_list"] = [g["name"] for g in genres_list]
        else:
            data = await fetch_tmdb(f"/{media_type}/{tmdb_id}", extra_params, lang=lang)
            # Normalize TV show fields before format_movie
            if media_type == "tv":
                data["title"] = data.get("name", data.get("title", ""))
                data["release_date"] = data.get("first_air_date", "")
                data["original_title"] = data.get("original_name", data.get("original_title", ""))
                data["media_type"] = "tv"
            m = format_movie(data)
            m["runtime"] = data.get("runtime")
            # H2 FIX: TV seasons/episodes
            if media_type == "tv":
                ep_runtime = data.get("episode_run_time", [])
                m["runtime"] = ep_runtime[0] if ep_runtime else None
                m["number_of_seasons"] = data.get("number_of_seasons")
                m["number_of_episodes"] = data.get("number_of_episodes")
            # Cast
            cast = data.get("credits", {}).get("cast", [])[:10]
            m["cast"] = [{"name": a["name"], "character": a.get("character", ""), "profile": f"https://image.tmdb.org/t/p/w185{a['profile_path']}" if a.get("profile_path") else None} for a in cast]
            # Similar
            similar_raw = data.get("similar", {}).get("results", [])[:8]
            # For TV shows, similar items are also TV shows - set media_type
            if media_type == "tv":
                for s in similar_raw:
                    if "media_type" not in s:
                        s["media_type"] = "tv"
                        s["title"] = s.get("name", s.get("title", ""))
                        s["release_date"] = s.get("first_air_date", "")
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
    if lang == "ru":
        ru_data, en_data = await _fetch_tmdb_both_langs(f"/trending/{media_type}/{time_window}")
        en_titles = {m.get("id"): m.get("title") or m.get("name") for m in en_data.get("results", [])}
        return [format_movie(m, en_title=en_titles.get(m.get("id"))) for m in ru_data.get("results", [])[:20]]
    data = await fetch_tmdb(f"/trending/{media_type}/{time_window}", lang=lang)
    return [format_movie(m) for m in data.get("results", [])[:20]]


async def get_top_rated(media_type: str = "movie", lang: str = "en") -> List[dict]:
    params = {"sort_by": "vote_average.desc", "vote_count.gte": 5000, "primary_release_date.gte": "1990-01-01", "include_adult": False}
    if lang == "ru":
        ru_data, en_data = await _fetch_tmdb_both_langs("/discover/movie", params)
        en_titles = {m.get("id"): m.get("title") or m.get("name") for m in en_data.get("results", [])}
        return [format_movie(m, en_title=en_titles.get(m.get("id"))) for m in ru_data.get("results", [])[:20]]
    data = await fetch_tmdb("/discover/movie", params, lang=lang)
    return [format_movie(m) for m in data.get("results", [])[:20]]


async def get_now_playing(lang: str = "en") -> List[dict]:
    if lang == "ru":
        ru_data, en_data = await _fetch_tmdb_both_langs("/movie/now_playing")
        en_titles = {m.get("id"): m.get("title") or m.get("name") for m in en_data.get("results", [])}
        return [format_movie(m, en_title=en_titles.get(m.get("id"))) for m in ru_data.get("results", [])[:20]]
    data = await fetch_tmdb("/movie/now_playing", lang=lang)
    return [format_movie(m) for m in data.get("results", [])[:20]]


async def get_upcoming(lang: str = "en") -> List[dict]:
    if lang == "ru":
        ru_data, en_data = await _fetch_tmdb_both_langs("/movie/upcoming")
        en_titles = {m.get("id"): m.get("title") or m.get("name") for m in en_data.get("results", [])}
        return [format_movie(m, en_title=en_titles.get(m.get("id"))) for m in ru_data.get("results", [])[:20]]
    data = await fetch_tmdb("/movie/upcoming", lang=lang)
    return [format_movie(m) for m in data.get("results", [])[:20]]


async def get_popular_movies(pages: int = 3, lang: str = "en") -> List[dict]:
    all_movies = []
    if lang == "ru":
        tasks_ru = [_fetch_tmdb_both_langs("/movie/popular", {"page": p}) for p in range(1, pages+1)]
        both_results = await asyncio.gather(*tasks_ru, return_exceptions=True)
        for res in both_results:
            if isinstance(res, tuple):
                ru_data, en_data = res
                en_titles = {m.get("id"): m.get("title") or m.get("name") for m in en_data.get("results", [])}
                all_movies.extend([format_movie(m, en_title=en_titles.get(m.get("id"))) for m in ru_data.get("results", [])])
        return all_movies
    tasks = [fetch_tmdb("/movie/popular", {"page": p}, lang=lang) for p in range(1, pages+1)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for data in results:
        if isinstance(data, dict):
            all_movies.extend([format_movie(m) for m in data.get("results", [])])
    return all_movies


async def get_new_2026(lang: str = "en") -> List[dict]:
    params = {"primary_release_year": 2026, "sort_by": "popularity.desc", "include_adult": False}
    if lang == "ru":
        ru_data, en_data = await _fetch_tmdb_both_langs("/discover/movie", params)
        en_titles = {m.get("id"): m.get("title") for m in en_data.get("results", [])}
        return [format_movie(m, en_title=en_titles.get(m.get("id"))) for m in ru_data.get("results", [])[:20]]
    data = await fetch_tmdb("/discover/movie", params, lang=lang)
    return [format_movie(m) for m in data.get("results", [])[:20]]


async def get_popular_tv(lang: str = "en") -> List[dict]:
    if lang == "ru":
        ru_data, en_data = await _fetch_tmdb_both_langs("/tv/popular")
        en_titles = {m.get("id"): m.get("name") for m in en_data.get("results", [])}
        results = []
        for m in ru_data.get("results", [])[:20]:
            m["media_type"] = "tv"
            m["title"] = m.get("name", m.get("title", ""))
            m["release_date"] = m.get("first_air_date", "")
            results.append(format_movie(m, en_title=en_titles.get(m.get("id"))))
        return results
    data = await fetch_tmdb("/tv/popular", lang=lang)
    results = []
    for m in data.get("results", [])[:20]:
        m["media_type"] = "tv"
        m["title"] = m.get("name", m.get("title", ""))
        m["release_date"] = m.get("first_air_date", "")
        results.append(format_movie(m))
    return results


async def get_oscar_winners(lang: str = "en") -> List[dict]:
    # Award-winning films: high vote average, lots of votes, drama genre
    params = {"sort_by": "vote_average.desc", "vote_count.gte": 5000, "with_genres": "18", "include_adult": False}
    if lang == "ru":
        ru_data, en_data = await _fetch_tmdb_both_langs("/discover/movie", params)
        en_titles = {m.get("id"): m.get("title") for m in en_data.get("results", [])}
        return [format_movie(m, en_title=en_titles.get(m.get("id"))) for m in ru_data.get("results", [])[:20]]
    data = await fetch_tmdb("/discover/movie", params, lang=lang)
    return [format_movie(m) for m in data.get("results", [])[:20]]


async def get_romance_comedy(lang: str = "en") -> List[dict]:
    params = {"sort_by": "popularity.desc", "with_genres": "10749,35", "vote_count.gte": 1000, "primary_release_date.gte": "2000-01-01", "include_adult": False}
    if lang == "ru":
        ru_data, en_data = await _fetch_tmdb_both_langs("/discover/movie", params)
        en_titles = {m.get("id"): m.get("title") for m in en_data.get("results", [])}
        return [format_movie(m, en_title=en_titles.get(m.get("id"))) for m in ru_data.get("results", [])[:20]]
    data = await fetch_tmdb("/discover/movie", params, lang=lang)
    return [format_movie(m) for m in data.get("results", [])[:20]]


async def get_top_horror(lang: str = "en") -> List[dict]:
    params = {"sort_by": "vote_average.desc", "with_genres": "27", "vote_count.gte": 1000, "primary_release_date.gte": "1990-01-01", "include_adult": False}
    if lang == "ru":
        ru_data, en_data = await _fetch_tmdb_both_langs("/discover/movie", params)
        en_titles = {m.get("id"): m.get("title") for m in en_data.get("results", [])}
        return [format_movie(m, en_title=en_titles.get(m.get("id"))) for m in ru_data.get("results", [])[:20]]
    data = await fetch_tmdb("/discover/movie", params, lang=lang)
    return [format_movie(m) for m in data.get("results", [])[:20]]


# TMDB genre ID mapping
TMDB_GENRE_IDS = {
    "horror": 27, "comedy": 35, "action": 28, "drama": 18,
    "thriller": 53, "romance": 10749, "animation": 16, "documentary": 99,
    "voennye": 10752, "fantastika": 878, "istoricheskie": 36,
    "muzyka": 10402, "crime": 80
}


async def get_movies_by_genre(genre_slug: str, pages: int = 5, lang: str = "en") -> List[dict]:
    """Get movies by genre slug using TMDB discover API."""
    genre_id = TMDB_GENRE_IDS.get(genre_slug)
    if not genre_id:
        return []
    all_movies = []
    params = {
        "with_genres": genre_id,
        "sort_by": "vote_average.desc",
        "vote_count.gte": 200,
        "include_adult": False,
    }
    if lang == "ru":
        for page in range(1, pages + 1):
            p = dict(params)
            p["page"] = page
            try:
                ru_data, en_data = await _fetch_tmdb_both_langs("/discover/movie", p)
                en_titles = {m.get("id"): m.get("title") for m in en_data.get("results", [])}
                all_movies.extend([format_movie(m, en_title=en_titles.get(m.get("id"))) for m in ru_data.get("results", [])])
            except Exception:
                break
        return all_movies[:100]
    for page in range(1, pages + 1):
        p = dict(params)
        p["page"] = page
        try:
            data = await fetch_tmdb("/discover/movie", p, lang=lang)
            all_movies.extend([format_movie(m) for m in data.get("results", [])])
        except Exception:
            break
    return all_movies[:100]


async def get_top_2025_2026(lang: str = "en") -> List[dict]:
    """Top 100 movies from 2025-2026 by rating."""
    params = {
        "sort_by": "vote_average.desc",
        "vote_count.gte": 100,
        "primary_release_date.gte": "2025-01-01",
        "include_adult": False,
    }
    all_movies = []
    if lang == "ru":
        for page in range(1, 6):
            p = dict(params)
            p["page"] = page
            try:
                ru_data, en_data = await _fetch_tmdb_both_langs("/discover/movie", p)
                en_titles = {m.get("id"): m.get("title") for m in en_data.get("results", [])}
                all_movies.extend([format_movie(m, en_title=en_titles.get(m.get("id"))) for m in ru_data.get("results", [])])
            except Exception:
                break
        return all_movies[:100]
    for page in range(1, 6):
        p = dict(params)
        p["page"] = page
        try:
            data = await fetch_tmdb("/discover/movie", p, lang=lang)
            all_movies.extend([format_movie(m) for m in data.get("results", [])])
        except Exception:
            break
    return all_movies[:100]


async def get_vecher_movies(lang: str = "en") -> List[dict]:
    """Cozy evening movies: Comedy + Drama + Romance, rating 7+."""
    all_movies = []
    for genre_id in [35, 18, 10749]:  # Comedy, Drama, Romance
        params = {
            "with_genres": genre_id,
            "sort_by": "vote_average.desc",
            "vote_count.gte": 500,
            "include_adult": False,
            "page": 1,
        }
        try:
            if lang == "ru":
                ru_data, en_data = await _fetch_tmdb_both_langs("/discover/movie", params)
                en_titles = {m.get("id"): m.get("title") for m in en_data.get("results", [])}
                all_movies.extend([format_movie(m, en_title=en_titles.get(m.get("id"))) for m in ru_data.get("results", [])])
            else:
                data = await fetch_tmdb("/discover/movie", params, lang=lang)
                all_movies.extend([format_movie(m) for m in data.get("results", [])])
        except Exception:
            pass
    # Sort by rating, deduplicate
    seen = set()
    result = []
    for m in sorted(all_movies, key=lambda x: x.get("rating", 0), reverse=True):
        if m.get("tmdb_id") not in seen:
            seen.add(m.get("tmdb_id"))
            result.append(m)
    return result[:100]
