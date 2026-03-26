"""
Smart Search - Natural language movie discovery without external AI APIs.
Uses keyword extraction + TMDB /discover/movie endpoint.
"""
import re
import httpx
from typing import Optional, List, Dict, Any
from services.tmdb import TMDB_API_KEY, BASE_URL, IMAGE_BASE, GENRE_MAP, format_movie

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
    "sci-fi": 878, "scifi": 878, "science fiction": 878, "space": 878,
    "thriller": 53, "suspense": 53, "war": 10752, "western": 37,
    # Russian
    "боевик": 28, "приключения": 12, "мультфильм": 16, "мультик": 16,
    "комедия": 35, "смешной": 35, "криминал": 80, "документальный": 99,
    "драма": 18, "семейный": 10751, "фэнтези": 14, "магия": 14,
    "история": 36, "исторический": 36, "ужасы": 27, "страшный": 27,
    "монстр": 27, "зомби": 27, "музыкальный": 10402, "мистика": 9648,
    "романтика": 10749, "мелодрама": 10749, "фантастика": 878,
    "триллер": 53, "война": 10752, "вестерн": 37,
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


async def smart_search(query: str) -> Dict[str, Any]:
    """
    Parse natural language query and return TMDB discover results.
    Returns: {"results": [...], "params_used": {...}, "description": "..."}
    """
    params = extract_params(query)
    actor_name = params.pop("_actor_name", None)
    keywords_hint = params.pop("_keywords", [])

    # Resolve actor to TMDB person ID
    if actor_name:
        actor_id = await lookup_actor_id(actor_name)
        if actor_id:
            params["with_cast"] = actor_id

    # Build discover request
    discover_params = {
        "api_key": TMDB_API_KEY,
        "language": "en-US",
        "sort_by": "vote_average.desc",
        "vote_count.gte": params.pop("vote_count.gte", 50),
        "include_adult": False,
        "page": 1,
    }
    discover_params.update(params)

    results = []
    description_parts = []

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{BASE_URL}/discover/movie",
                params=discover_params
            )
            data = resp.json()
            results = [format_movie(m) for m in data.get("results", [])[:20]]
    except Exception as e:
        print(f"Discover error: {e}")

    # If discover returned nothing, fall back to keyword search
    if not results and keywords_hint:
        fallback_query = " ".join(keywords_hint[:3])
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{BASE_URL}/search/movie",
                    params={"api_key": TMDB_API_KEY, "query": fallback_query, "language": "en-US"}
                )
                data = resp.json()
                results = [format_movie(m) for m in data.get("results", [])[:20]]
        except Exception:
            pass

    # Build human-readable description of what we searched for
    if "with_genres" in discover_params:
        genre_ids = [int(g) for g in str(discover_params["with_genres"]).split(",")]
        genre_names = [GENRE_MAP.get(gid, str(gid)) for gid in genre_ids]
        description_parts.append(f"{', '.join(genre_names)}")
    if "primary_release_year" in discover_params:
        description_parts.append(f"from {discover_params['primary_release_year']}")
    if "primary_release_date.gte" in discover_params:
        yr = discover_params["primary_release_date.gte"][:4]
        description_parts.append(f"from the {yr}s")
    if actor_name:
        description_parts.append(f"with {actor_name.title()}")
    if "vote_average.gte" in discover_params:
        description_parts.append(f"rating ≥ {discover_params['vote_average.gte']}")

    desc = ", ".join(description_parts) if description_parts else "your description"

    return {
        "results": results,
        "count": len(results),
        "description": desc,
        "params_used": {k: v for k, v in discover_params.items() if k != "api_key"},
    }


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
