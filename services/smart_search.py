"""
Smart Search - Natural language movie discovery without external AI APIs.
Uses keyword extraction + TMDB /discover/movie endpoint.
"""
import re
import os
import httpx
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
from services.tmdb import TMDB_API_KEY, BASE_URL, IMAGE_BASE, GENRE_MAP, format_movie

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"

# Reverse map: keyword -> genre_id
GENRE_KEYWORDS: Dict[str, int] = {
    # English
    "action": 28, "adventure": 12, "animation": 16, "animated": 16,
    "cartoon": 16, "comedy": 35, "funny": 35, "humour": 35, "humor": 35,
    "crime": 80, "documentary": 99, "doc": 99, "drama": 18,
    "family": 10751, "kids": 10751, "children": 10751,
    "fantasy": 14, "magic": 14, "history": 36, "historical": 36,
    "horror": 27, "scary": 27, "monster": 27, "zombie": 27, "ghost": 27,
    "music": 10402, "musical": 10402, "mystery": 9648,
    "romance": 10749, "romantic": 10749, "love": 10749,
    "sci-fi": 878, "scifi": 878, "science fiction": 878, "sci fi": 878, "space": 878,
    "thriller": 53, "suspense": 53, "war": 10752, "western": 37,
    # Russian - base forms
    "боевик": 28, "приключения": 12, "мультфильм": 16, "мультик": 16,
    "комедия": 35, "смешной": 35, "криминал": 80, "документальный": 99,
    "драма": 18, "семейный": 10751, "фэнтези": 14, "магия": 14,
    "история": 36, "исторический": 36, "ужасы": 27, "страшный": 27,
    "монстр": 27, "зомби": 27, "музыкальный": 10402, "мистика": 9648,
    "романтика": 10749, "мелодрама": 10749, "фантастика": 878,
    "триллер": 53, "война": 10752, "вестерн": 37,
    # Russian - inflections (plurals, genitive)
    "боевики": 28, "боевиков": 28,
    "комедии": 35, "комедий": 35, "комедию": 35,
    "драмы": 18, "драм": 18, "драму": 18,
    "ужасов": 27, "хоррор": 27,
    "триллеры": 53, "триллеров": 53,
    "романтические": 10749, "мелодрамы": 10749,
    "фантастики": 878,
    "мультфильмы": 16, "аниме": 16, "анимация": 16,
    "криминальные": 80, "криминального": 80, "детектив": 80, "детективы": 80,
    "приключений": 12, "приключенческие": 12,
    "мистики": 9648,
    "документальные": 99, "документалки": 99,
    "семейные": 10751,
    "исторические": 36,
    "музыкальные": 10402,
    "военный": 10752, "военные": 10752, "войны": 10752,
    "вестерны": 37,
}

DECADE_MAP = {
    "90s": (1990, 1999), "нулевые": (2000, 2009), "00s": (2000, 2009),
    "2000s": (2000, 2009), "10s": (2010, 2019), "2010s": (2010, 2019),
    "20s": (2020, 2029), "2020s": (2020, 2029), "80s": (1980, 1989),
    "70s": (1970, 1979), "60s": (1960, 1969),
    "девяностые": (1990, 1999), "восьмидесятые": (1980, 1989),
}

RATING_KEYWORDS = {
    "good rating": 7.0, "great rating": 7.5, "excellent": 8.0,
    "top rated": 8.0, "best": 8.0, "highly rated": 7.5,
    "хорошим рейтингом": 7.0, "высоким рейтингом": 7.5,
    "лучший": 8.0, "отличный": 8.0,
}

KNOWN_ACTORS = [
    "will smith", "tom hanks", "leonardo dicaprio", "brad pitt", "morgan freeman",
    "denzel washington", "robert downey", "scarlett johansson", "meryl streep",
    "jennifer lawrence", "ryan reynolds", "chris evans", "chris hemsworth",
    "keanu reeves", "johnny depp", "arnold schwarzenegger", "sylvester stallone",
    "bruce willis", "tom cruise", "matt damon", "mark wahlberg",
    "dwayne johnson", "samuel jackson", "samuel l. jackson", "adam sandler",
    "jim carrey", "robin williams", "eddie murphy",
]

def extract_params(query: str) -> Dict[str, Any]:
    """Extract search params from natural language query."""
    q_lower = query.lower()
    params = {}

    # Extract 4-digit year
    year_match = re.search(r'\b(19[0-9]{2}|20[0-2][0-9])\b', q_lower)
    if year_match:
        params["primary_release_year"] = int(year_match.group(1))

    # Extract decade
    for decade_key, (y_from, y_to) in DECADE_MAP.items():
        if decade_key in q_lower:
            params["primary_release_date.gte"] = f"{y_from}-01-01"
            params["primary_release_date.lte"] = f"{y_to}-12-31"
            break

    # Extract genre(s)
    genres_found = []
    # Try multi-word first (longer matches)
    for kw in sorted(GENRE_KEYWORDS.keys(), key=len, reverse=True):
        if kw in q_lower and GENRE_KEYWORDS[kw] not in genres_found:
            genres_found.append(GENRE_KEYWORDS[kw])
            if len(genres_found) >= 2:
                break
    if genres_found:
        params["with_genres"] = ",".join(str(g) for g in genres_found)

    # Extract minimum rating
    for kw, min_rating in RATING_KEYWORDS.items():
        if kw in q_lower:
            params["vote_average.gte"] = min_rating
            params["vote_count.gte"] = 100
            break

    # Extract actor (search TMDB for person ID)
    actor_found = None
    for actor in KNOWN_ACTORS:
        if actor in q_lower:
            actor_found = actor
            break
    # Also try to detect actor patterns like "with FirstName LastName"
    if not actor_found:
        actor_match = re.search(r'\bwith\s+([A-Z][a-z]+\s+[A-Z][a-z]+)', query)
        if actor_match:
            actor_found = actor_match.group(1)

    # Russian actor detection: "фильмы с [Имя Фамилия]", "с участием [Имя]"
    if not actor_found:
        ru_actor_match = re.search(
            r'(?:с\s+|с участием\s+)([А-ЯЁа-яёA-Za-z][а-яёa-z]+(?:\s+[А-ЯЁа-яёA-Za-z][а-яёa-z]+)?)',
            query
        )
        if ru_actor_match:
            actor_found = ru_actor_match.group(1)

    params["_actor_name"] = actor_found  # store for async lookup

    # Extract keywords for fallback text search
    stop_words = {"i", "want", "a", "an", "the", "movie", "film", "show", "series",
                  "from", "with", "about", "and", "or", "in", "on", "at", "to",
                  "that", "is", "are", "was", "were", "have", "has", "good", "great",
                  "russian", "english", "american", "фильм", "кино", "сериал",
                  "хочу", "хочется", "посмотреть", "про", "о"}
    words = re.findall(r'[a-zа-яё]+', q_lower)
    keywords = [w for w in words if len(w) > 3 and w not in stop_words
                and w not in GENRE_KEYWORDS and not w.isdigit()]
    params["_keywords"] = keywords[:5]

    return params


async def lookup_actor_id(actor_name: str) -> Optional[int]:
    """Get TMDB person ID by name."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                f"{BASE_URL}/search/person",
                params={"api_key": TMDB_API_KEY, "query": actor_name}
            )
            data = resp.json()
            results = data.get("results", [])
            if results:
                return results[0]["id"]
    except Exception:
        pass
    return None


async def parse_query_with_ai(query: str) -> Optional[dict]:
    """Use Groq LLM to parse natural language search query into structured params."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": GROQ_MODEL,
                    "messages": [
                        {"role": "system", "content": """You are a movie/TV show search assistant. Extract search parameters from the user's query and return ONLY valid JSON, nothing else.

Return this JSON structure:
{
  "search_type": "similar|title|discover|actor",
  "title": "exact movie/show title if searching by title",
  "similar_to": "reference title for похожие на queries",
  "genres": [],
  "year_gte": null,
  "year_lte": null,
  "year_exact": null,
  "actor": null,
  "min_rating": null,
  "media_type": "movie|tv|any",
  "description": "human-readable description"
}

Rules:
- search_type similar: похожие на X, как X, в стиле X, similar to X
- search_type title: searching specific movie/show by name  
- search_type discover: genre/year/mood browsing
- search_type actor: фильмы с X, movies with X
- search_type description: user describes plot/characters without knowing title - YOU must identify the movie and set title field
- genres from: action, comedy, drama, horror, thriller, romance, sci-fi, animation, crime, adventure, fantasy, mystery, documentary, family, history, war, western
- year_gte: year FROM which (не старше 2020 = year_gte=2020, вышедшие после 2015 = year_gte=2015, после 2020 = year_gte=2020, от 2020 = year_gte=2020, начиная с = year_gte)
- year_lte: year BEFORE which (до 2020 = year_lte=2020, вышедшие до 2020 = year_lte=2020, старше 2000 = year_lte=2000)
- CRITICAL: "не старше 2020" means year_gte=2020 (films from 2020 onwards, NOT older than 2020)
- CRITICAL: "после 2020", "от 2020", "не старше 2020" ALL mean year_gte=2020
- min_rating: numeric only (6.5, 7.0, 8.0) - if user says хороший/good rating use 6.5, очень хороший use 7.0, отличный/excellent use 8.0
- IMPORTANT: If user describes a plot ("фильм где...", "там где...", "про то как..."), use search_type=description and identify the movie. Set title to the movie name you identified.
- Example: "фильм где здоровый и маленький убегали от полиции" -> {"search_type": "description", "title": "Central Intelligence", "description": "Полтора шпиона - комедия с Дуэйном Джонсоном и Кевином Хартом"}
- Return ONLY JSON, no explanation"""},
                        {"role": "user", "content": query}
                    ],
                    "max_tokens": 300,
                    "temperature": 0.1
                }
            )
            if r.status_code == 200:
                content_str = r.json()["choices"][0]["message"]["content"].strip()
                import json as json_lib
                start = content_str.find("{")
                end = content_str.rfind("}") + 1
                if start >= 0 and end > start:
                    return json_lib.loads(content_str[start:end])
    except Exception as e:
        print(f"[smart_search] Groq error: {e}")
    return None



async def smart_search(query: str, lang: str = "ru") -> Dict[str, Any]:
    """
    Parse natural language query using Groq AI, then search TMDB.
    Returns: {"results": [...], "params_used": {...}, "description": "..."}
    """
    # Try AI parsing first
    ai_params = await parse_query_with_ai(query)

    if ai_params:
        search_type = ai_params.get("search_type", "title")

        # Handle "similar to" queries
        if search_type == "similar" and ai_params.get("similar_to"):
            ref_title = ai_params["similar_to"]
            year_gte = ai_params.get("year_gte")
            year_lte = ai_params.get("year_lte")

            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    r = await client.get(
                        f"{BASE_URL}/search/multi",
                        params={"api_key": TMDB_API_KEY, "query": ref_title, "language": "ru-RU" if lang == "ru" else "en-US"}
                    )
                    ref_results = r.json().get("results", [])
                    if ref_results:
                        # Pick most popular movie (not TV show) from results
                        req_media_type = ai_params.get("media_type", "any")
                        movie_results = [x for x in ref_results if x.get("media_type") == "movie"] if req_media_type == "movie" else ref_results
                        # Sort by popularity to get most well-known title
                        movie_results.sort(key=lambda x: x.get("popularity", 0), reverse=True)
                        ref_item = movie_results[0] if movie_results else ref_results[0]
                        # C1 FIX: if popularity too low, retry with original query words
                        if ref_item.get('popularity', 0) < 5.0:
                            query_words = ' '.join([w for w in query.split() if len(w) > 3 and w not in ['похожие', 'найди', 'фильм', 'сериал', 'как', 'на', 'по']])
                            if query_words:
                                r2 = await client.get(
                                    f"{BASE_URL}/search/multi",
                                    params={"api_key": TMDB_API_KEY, "query": query_words, "language": "ru-RU" if lang == "ru" else "en-US"}
                                )
                                r2_results = r2.json().get("results", [])
                                r2_movies = [x for x in r2_results if x.get("media_type") == "movie"]
                                r2_movies.sort(key=lambda x: x.get("popularity", 0), reverse=True)
                                if r2_movies and r2_movies[0].get("popularity", 0) > ref_item.get("popularity", 0):
                                    ref_item = r2_movies[0]
                        ref_id = ref_item.get("id")
                        ref_media = ref_item.get("media_type", "movie")
                        ref_name = ref_item.get("title") or ref_item.get("name", ref_title)

                        rec_r = await client.get(f"{BASE_URL}/{ref_media}/{ref_id}/recommendations",
                            params={"api_key": TMDB_API_KEY, "language": "ru-RU" if lang == "ru" else "en-US"})
                        sim_r = await client.get(f"{BASE_URL}/{ref_media}/{ref_id}/similar",
                            params={"api_key": TMDB_API_KEY, "language": "ru-RU" if lang == "ru" else "en-US"})

                        recs = rec_r.json().get("results", [])
                        similar = sim_r.json().get("results", [])

                        seen = set()
                        combined = []
                        for item in recs + similar:
                            iid = item.get("id")
                            if iid and iid not in seen:
                                seen.add(iid)
                                if item.get("media_type") == "tv" or ref_media == "tv":
                                    item["title"] = item.get("name", item.get("title", ""))
                                    item["release_date"] = item.get("first_air_date", item.get("release_date", ""))
                                combined.append(item)

                        # Filter by year AND rating AND media_type
                        min_rating = ai_params.get("min_rating")
                        req_media = ai_params.get("media_type", "any")
                        filtered = []
                        for item in combined:
                            rd = item.get("release_date") or item.get("first_air_date", "")
                            item_year = int(rd[:4]) if rd and len(rd) >= 4 else None
                            item_rating = item.get("vote_average", 0)
                            item_media = item.get("media_type", "movie")
                            # Year filter
                            if item_year:
                                if year_gte and item_year < year_gte: continue
                                if year_lte and item_year > year_lte: continue
                            # Rating filter
                            try:
                                if min_rating and item_rating < float(min_rating): continue
                            except (TypeError, ValueError): pass  # skip invalid rating
                            # Media type filter
                            if req_media == "movie" and item_media == "tv": continue
                            if req_media == "tv" and item_media == "movie": continue
                            # Exclude animation if movie requested (genre_id 16)
                            if req_media == "movie":
                                genre_ids = item.get("genre_ids", [])
                                if 16 in genre_ids: continue  # skip animation
                            filtered.append(item)
                        if filtered:
                            combined = filtered

                        # Sort by rating (best first)
                        combined.sort(key=lambda x: x.get("vote_average", 0), reverse=True)
                        if combined:
                            desc = f"Похожие на «{ref_name}»"
                            if year_lte: desc += f" не старше {year_lte}"
                            if year_gte: desc += f" после {year_gte}"
                            return {
                                "results": [format_movie(m) for m in combined[:20]],
                                "params_used": {"similar_to": ref_name},
                                "description": desc,
                                "count": len(combined[:20]),
                            }
            except Exception as e:
                print(f"[smart_search] Similar-to AI error: {e}")

        # Handle direct title search
        elif search_type in ("title", "description") and ai_params.get("title"):
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    r_multi = await client.get(
                        f"{BASE_URL}/search/multi",
                        params={"api_key": TMDB_API_KEY, "query": ai_params["title"], "language": "ru-RU" if lang == "ru" else "en-US"}
                    )
                    results = r_multi.json().get("results", [])
                    combined = []
                    seen = set()
                    for m in results:
                        mid = m.get("id")
                        media = m.get("media_type", "movie")
                        if mid and mid not in seen and media in ("movie", "tv"):
                            seen.add(mid)
                            if media == "tv":
                                m["title"] = m.get("name", m.get("title", ""))
                                m["release_date"] = m.get("first_air_date", "")
                            combined.append(m)
                    if combined:
                        return {
                            "results": [format_movie(m) for m in combined[:20]],
                            "params_used": {"direct_search": ai_params["title"]},
                            "description": f"Результаты для «{ai_params['title']}»",
                            "count": len(combined),
                        }
            except Exception as e:
                print(f"[smart_search] Title AI error: {e}")

        # Handle actor search
        elif search_type == "actor" and ai_params.get("actor"):
            actor_id = await lookup_actor_id(ai_params["actor"])
            if actor_id:
                try:
                    async with httpx.AsyncClient(timeout=15) as client:
                        actor_params = {
                            "api_key": TMDB_API_KEY,
                            "language": "ru-RU" if lang == "ru" else "en-US",
                            "with_cast": actor_id,
                            "sort_by": "vote_average.desc",
                            "vote_count.gte": 50,
                        }
                        # Fetch 3 pages for more results
                        import asyncio as _asyncio
                        pages = await _asyncio.gather(
                            client.get(f"{BASE_URL}/discover/movie", params={**actor_params, "page": 1}),
                            client.get(f"{BASE_URL}/discover/movie", params={**actor_params, "page": 2}),
                            client.get(f"{BASE_URL}/discover/movie", params={**actor_params, "page": 3}),
                        )
                        results = []
                        seen = set()
                        for page in pages:
                            for m in page.json().get("results", []):
                                if m.get("id") not in seen:
                                    seen.add(m.get("id"))
                                    results.append(m)
                        if results:
                            return {
                                "results": [format_movie(m) for m in results[:60]],
                                "params_used": {"actor": ai_params["actor"]},
                                "description": f"Фильмы с {ai_params['actor']}",
                                "count": len(results),
                            }
                except Exception as e:
                    print(f"[smart_search] Actor AI error: {e}")

        # Handle discover (genre/year based)
        elif search_type == "discover":
            genre_map_local = {
                "action": 28, "comedy": 35, "drama": 18, "horror": 27,
                "thriller": 53, "romance": 10749, "sci-fi": 878, "animation": 16,
                "crime": 80, "adventure": 12, "fantasy": 14, "mystery": 9648,
                "documentary": 99, "family": 10751, "history": 36, "war": 10752,
                "western": 37, "music": 10402,
            }
            discover_p = {
                "api_key": TMDB_API_KEY,
                "language": "ru-RU" if lang == "ru" else "en-US",
                "sort_by": "vote_average.desc",
                "vote_count.gte": 100,
                "include_adult": False,
            }
            genres = ai_params.get("genres", [])
            if genres:
                genre_ids = [str(genre_map_local[g]) for g in genres if g in genre_map_local]
                if genre_ids:
                    discover_p["with_genres"] = ",".join(genre_ids)
            if ai_params.get("year_exact"):
                discover_p["primary_release_year"] = ai_params["year_exact"]
            elif ai_params.get("year_gte"):
                discover_p["primary_release_date.gte"] = f"{ai_params['year_gte']}-01-01"
            if ai_params.get("year_lte"):
                discover_p["primary_release_date.lte"] = f"{ai_params['year_lte']}-12-31"
            if ai_params.get("min_rating"):
                discover_p["vote_average.gte"] = ai_params["min_rating"]

            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    import asyncio as _aio
                    pages = await _aio.gather(*[
                        client.get(f"{BASE_URL}/discover/movie", params={**discover_p, "page": p})
                        for p in range(1, 6)
                    ])
                    results = []
                    seen = set()
                    for page in pages:
                        for m in page.json().get("results", []):
                            if m.get("id") not in seen:
                                seen.add(m.get("id"))
                                results.append(m)
                    if results:
                        return {
                            "results": [format_movie(m) for m in results[:100]],
                            "params_used": discover_p,
                            "description": ai_params.get("description") or "Результаты поиска",
                            "count": len(results),
                        }
            except Exception as e:
                print(f"[smart_search] Discover AI error: {e}")

    # Fallback: direct TMDB search with original query
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{BASE_URL}/search/multi",
                params={"api_key": TMDB_API_KEY, "query": query, "language": "ru-RU" if lang == "ru" else "en-US"}
            )
            results = r.json().get("results", [])
            combined = []
            seen = set()
            for m in results:
                mid = m.get("id")
                media = m.get("media_type", "movie")
                if mid and mid not in seen and media in ("movie", "tv"):
                    seen.add(mid)
                    if media == "tv":
                        m["title"] = m.get("name", m.get("title", ""))
                        m["release_date"] = m.get("first_air_date", "")
                    combined.append(m)
            if combined:
                return {
                    "results": [format_movie(m) for m in combined[:20]],
                    "params_used": {"fallback": query},
                    "description": f"Результаты для «{query}»",
                    "count": len(combined),
                }
    except Exception as e:
        print(f"[smart_search] Fallback error: {e}")

    return {"results": [], "params_used": {}, "description": "", "count": 0}


async def get_typo_suggestions(query: str, limit: int = 5) -> List[dict]:
    """
    Use TMDB fuzzy search to suggest corrections for misspelled titles.
    Returns top results as suggestions.
    """
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                f"{BASE_URL}/search/multi",
                params={
                    "api_key": TMDB_API_KEY,
                    "query": query,
                    "language": "en-US",
                    "include_adult": False,
                }
            )
            data = resp.json()
            results = data.get("results", [])[:limit]
            suggestions = []
            for r in results:
                title = r.get("title") or r.get("name", "")
                if title and title.lower() != query.lower():
                    suggestions.append({
                        "tmdb_id": r.get("id"),
                        "title": title,
                        "year": (r.get("release_date") or r.get("first_air_date") or "")[:4],
                        "media_type": r.get("media_type", "movie"),
                        "poster_url": f"https://image.tmdb.org/t/p/w92{r['poster_path']}" if r.get("poster_path") else None,
                    })
            return suggestions
    except Exception as e:
        print(f"Suggestion error: {e}")
        return []
