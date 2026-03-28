import asyncio
import os
import sys
import httpx
from datetime import date
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

from database import init_db, log_search, get_trending_searches, save_movie, get_movie_by_tmdb, get_recent_movies, get_top_rated_db, get_movies_by_genre_db, get_vecher_movies_db, get_movies_2026_db
from services.tmdb import search_movies, get_movie_details, get_trending, get_top_rated, get_now_playing, get_upcoming, get_popular_movies, get_new_2026, get_popular_tv, get_oscar_winners, get_romance_comedy, get_top_horror, get_movies_by_genre, get_top_2025_2026, get_vecher_movies
from services.sources import get_all_sources, get_watch_sources
from services.smart_search import smart_search, get_typo_suggestions
from translations import get_translations, detect_language

app = FastAPI(title="MovieFinder")


@app.get("/yandex_afadf407fdf7e97f.html")
async def yandex_verify():
    return HTMLResponse('<html><head><meta http-equiv="Content-Type" content="text/html; charset=UTF-8"></head><body>Verification: afadf407fdf7e97f</body></html>')

@app.get("/googlef7a33d45345493f6.html", response_class=PlainTextResponse)
async def google_verify():
    return "google-site-verification: googlef7a33d45345493f6.html"


BASE_DIR = os.path.dirname(__file__)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


def get_lang(request: Request) -> str:
    """Determine language: query param first (for hreflang), then cookie, then Accept-Language header."""
    # Check query param first (for Google hreflang crawling)
    lang = request.query_params.get("lang")
    if lang in ("ru", "en"):
        return lang
    # Then cookie
    lang = request.cookies.get("lang")
    if lang in ("en", "ru"):
        return lang
    accept = request.headers.get("accept-language", "")
    return detect_language(accept)


@app.on_event("startup")
async def startup():
    init_db()
    # Seed DB in background
    asyncio.create_task(seed_database())


async def seed_database():
    try:
        movies = await get_popular_movies(pages=3)
        for m in movies[:50]:
            if m.get("tmdb_id"):
                save_movie({
                    "tmdb_id": m["tmdb_id"],
                    "title": m["title"],
                    "title_ru": m.get("title_ru", m["title"]),
                    "year": m.get("year"),
                    "rating": m.get("rating"),
                    "poster_url": m.get("poster_url"),
                    "genre": m.get("genre", ""),
                    "description": m.get("description", ""),
                    "description_ru": m.get("description", ""),
                    "runtime": m.get("runtime"),
                })
        print(f"Seeded {len(movies[:50])} movies")
    except Exception as e:
        print(f"Seed error: {e}")


@app.get("/api/set-language")
async def set_language(lang: str = "en"):
    """Set language preference via cookie."""
    if lang not in ("en", "ru"):
        lang = "en"
    response = JSONResponse({"lang": lang, "ok": True})
    response.set_cookie("lang", lang, max_age=60 * 60 * 24 * 365, samesite="lax")
    return response


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    lang = get_lang(request)
    t = get_translations(lang)
    try:
        trending_task = get_trending(lang=lang)
        top_rated_task = get_top_rated(lang=lang)
        new_2026_task = get_new_2026(lang=lang)
        popular_tv_task = get_popular_tv(lang=lang)
        oscar_task = get_oscar_winners(lang=lang)
        romance_task = get_romance_comedy(lang=lang)
        horror_task = get_top_horror(lang=lang)

        trending, top_rated, new_2026, popular_tv, oscar_winners, romance_comedy, top_horror = await asyncio.gather(
            trending_task, top_rated_task, new_2026_task, popular_tv_task, oscar_task, romance_task, horror_task,
            return_exceptions=True
        )

        if isinstance(trending, Exception): trending = []
        if isinstance(top_rated, Exception): top_rated = []
        if isinstance(new_2026, Exception): new_2026 = []
        if isinstance(popular_tv, Exception): popular_tv = []
        if isinstance(oscar_winners, Exception): oscar_winners = []
        if isinstance(romance_comedy, Exception): romance_comedy = []
        if isinstance(top_horror, Exception): top_horror = []

        trending_searches = get_trending_searches(10)

        return templates.TemplateResponse(request, "index.html", {
            "trending": trending[:20],
            "top_rated": top_rated[:20],
            "new_2026": new_2026[:20],
            "popular_tv": popular_tv[:20],
            "oscar_winners": oscar_winners[:20],
            "romance_comedy": romance_comedy[:20],
            "top_horror": top_horror[:20],
            "trending_searches": trending_searches,
            "lang": lang,
            "t": t,
        })
    except Exception as e:
        print(f"Index error: {e}")
        return templates.TemplateResponse(request, "index.html", {
            "trending": [], "top_rated": [], "new_2026": [], "popular_tv": [], "oscar_winners": [], "romance_comedy": [], "top_horror": [],
            "trending_searches": [],
            "lang": lang,
            "t": t,
        })


@app.get("/search", response_class=HTMLResponse)
async def search_page(request: Request, q: str = ""):
    lang = get_lang(request)
    t = get_translations(lang)
    results = []
    if q:
        log_search(q)
        try:
            results = await search_movies(q, lang=lang)
            # Set display title based on language
            for m in results:
                if lang == "ru" and m.get("title_ru"):
                    m["display_title"] = m["title_ru"]
                else:
                    m["display_title"] = m["title"]
        except Exception as e:
            print(f"Search error: {e}")
    return templates.TemplateResponse(request, "search.html", {
        "query": q,
        "results": results,
        "lang": lang,
        "t": t,
    })


@app.get("/movie/{tmdb_id}", response_class=HTMLResponse)
async def movie_page(request: Request, tmdb_id: int, media_type: str = "movie"):
    lang = get_lang(request)
    t = get_translations(lang)
    try:
        movie = await get_movie_details(tmdb_id, media_type, lang=lang)
        if not movie:
            return templates.TemplateResponse(request, "404.html", {"request": request, "lang": lang, "t": t}, status_code=404)

        sources = await get_all_sources(tmdb_id, movie["title"], movie.get("year"), title_ru=movie.get("title_ru"), media_type=media_type)

        return templates.TemplateResponse(request, "movie.html", {
            "movie": movie,
            "sources": sources,
            "lang": lang,
            "t": t,
        })
    except Exception as e:
        print(f"Movie page error: {e}")
        return HTMLResponse(f"Error loading movie: {e}", status_code=500)


# API endpoints
@app.get("/api/search")
async def api_search(request: Request, q: str = Query(...)):
    if not q:
        return {"results": []}
    lang = get_lang(request)
    log_search(q)
    results = await search_movies(q, lang=lang)
    return {"results": results}


@app.get("/api/trending")
async def api_trending(request: Request):
    lang = get_lang(request)
    data = await get_trending(lang=lang)
    return {"results": data[:10]}


@app.get("/api/smart-search")
async def api_smart_search(q: str = Query(...)):
    if not q or len(q) < 3:
        return {"results": [], "description": "", "count": 0}
    log_search(q)
    result = await smart_search(q)
    return result


@app.get("/api/suggestions")
async def api_suggestions(q: str = Query(...)):
    if not q or len(q) < 2:
        return {"suggestions": []}
    suggestions = await get_typo_suggestions(q, limit=5)
    return {"suggestions": suggestions}


@app.get("/smart-search", response_class=HTMLResponse)
async def smart_search_page(request: Request, q: str = ""):
    lang = get_lang(request)
    t = get_translations(lang)
    result = {"results": [], "description": "", "count": 0}
    if q:
        log_search(q)
        result = await smart_search(q, lang=lang)
        for m in result["results"]:
            if lang == "ru" and m.get("title_ru"):
                m["display_title"] = m["title_ru"]
            else:
                m["display_title"] = m["title"]
    return templates.TemplateResponse(request, "search.html", {
        "query": q,
        "results": result["results"],
        "smart_mode": True,
        "smart_description": result.get("description") or "",
        "smart_count": result.get("count", 0),
        "lang": lang,
        "t": t,
    })


@app.get("/ai-search", response_class=HTMLResponse)
async def ai_search_page(request: Request, q: str = ""):
    lang = get_lang(request)
    t = get_translations(lang)
    result = {"results": [], "description": "", "count": 0}
    if q:
        log_search(q)
        result = await smart_search(q, lang=lang)
    return templates.TemplateResponse(request, "ai_search.html", {
        "query": q,
        "results": result["results"],
        "smart_mode": True,
        "smart_description": result.get("description") or "",
        "smart_count": result.get("count", 0),
        "lang": lang,
        "t": t,
    })


@app.get("/favorites", response_class=HTMLResponse)
async def favorites_page(request: Request):
    lang = get_lang(request)
    t = get_translations(lang)
    return templates.TemplateResponse(request, "favorites.html", {
        "lang": lang,
        "t": t,
    })


@app.get("/api/movie/{tmdb_id}")
async def api_movie(request: Request, tmdb_id: int, media_type: str = "movie"):
    lang = get_lang(request)
    movie = await get_movie_details(tmdb_id, media_type, lang=lang)
    if not movie:
        return JSONResponse({"error": "Not found"}, status_code=404)
    sources = await get_all_sources(tmdb_id, movie["title"], movie.get("year"), title_ru=movie.get("title_ru"))
    return {"movie": movie, "sources": sources}


@app.get("/api/sources/{tmdb_id}")
async def api_sources(
    request: Request,
    tmdb_id: int,
    title: str = Query(""),
    year: int = Query(0),
    title_ru: str = Query(""),
    country: str = Query("US"),
    imdb_id: str = Query(""),
    media_type: str = Query("movie"),
):
    """
    Live source lookup for a movie.
    Returns all streaming options from JustWatch + pirate sites.
    Results cached for 7 days in DB.
    """
    # Always try to enrich with DB data (title_ru is critical for RU scrapers)
    movie_db = get_movie_by_tmdb(tmdb_id)
    if movie_db:
        if not title:
            title = movie_db.get("title", "")
        if not title_ru:
            title_ru = movie_db.get("title_ru", "") or ""
        if not year:
            year = movie_db.get("year", 0) or 0
        if not imdb_id:
            imdb_id = movie_db.get("imdb_id", "") or ""

    result = await get_watch_sources(
        title=title,
        year=year,
        tmdb_id=tmdb_id,
        title_ru=title_ru or None,
        country=country,
        imdb_id=imdb_id or None,
        media_type=media_type,
    )
    sources = result.get("sources", [])

    # Group by offer type for structured response
    grouped = {
        "subscription": [s for s in sources if s.get("monetization") in ("FLATRATE", "FLATRATE_AND_BUY")],
        "rent": [s for s in sources if s.get("monetization") == "RENT"],
        "buy": [s for s in sources if s.get("monetization") == "BUY"],
        "free": [s for s in sources if s.get("monetization") in ("FREE", "ADS")],
        "pirate": [s for s in sources if s.get("source_type") == "pirate"],
    }

    return {
        "tmdb_id": tmdb_id,
        "title": title,
        "year": year,
        "cached": result.get("cached", False),
        "total": len(sources),
        "grouped": grouped,
        "all": sources,
    }


# ============================================================
# SEO ROUTES
# ============================================================

BASE_URL = "https://moviefinders.net"
SITEMAP_CHUNK_SIZE = 10000

TMDB_API_KEY = "8265bd1679663a7ea12ac168da84d2e8"

GENRE_MAP = {
    "drama":         {"tmdb": "Drama",       "tmdb_id": 18,   "ru": "Драмы",                  "en": "Drama Films",       "slug": "drama"},
    "comedy":        {"tmdb": "Comedy",      "tmdb_id": 35,   "ru": "Комедии",                 "en": "Comedy Films",      "slug": "comedy"},
    "horror":        {"tmdb": "Horror",      "tmdb_id": 27,   "ru": "Фильмы ужасов",           "en": "Horror Films",      "slug": "horror"},
    "action":        {"tmdb": "Action",      "tmdb_id": 28,   "ru": "Боевики",                 "en": "Action Films",      "slug": "action"},
    "thriller":      {"tmdb": "Thriller",    "tmdb_id": 53,   "ru": "Триллеры",                "en": "Thrillers",         "slug": "thriller"},
    "romance":       {"tmdb": "Romance",     "tmdb_id": 10749,"ru": "Романтические фильмы",    "en": "Romance Films",     "slug": "romance"},
    "animation":     {"tmdb": "Animation",   "tmdb_id": 16,   "ru": "Мультфильмы",             "en": "Animation Films",   "slug": "animation"},
    "documentary":   {"tmdb": "Documentary", "tmdb_id": 99,   "ru": "Документальные фильмы",   "en": "Documentary Films", "slug": "documentary"},
    "voennye":       {"tmdb": "War",         "tmdb_id": 10752,"ru": "Военные фильмы",          "en": "War Films",         "slug": "voennye"},
    "fantastika":    {"tmdb": "Sci-Fi",      "tmdb_id": 878,  "ru": "Фантастика",              "en": "Sci-Fi Films",      "slug": "fantastika"},
    "istoricheskie": {"tmdb": "History",     "tmdb_id": 36,   "ru": "Исторические фильмы",     "en": "Historical Films",  "slug": "istoricheskie"},
    "muzyka":        {"tmdb": "Music",       "tmdb_id": 10402,"ru": "Музыкальные фильмы",      "en": "Music Films",       "slug": "muzyka"},
    "crime":         {"tmdb": "Crime",       "tmdb_id": 80,   "ru": "Криминальные фильмы",     "en": "Crime Films",       "slug": "crime"},
}


@app.get("/favicon.ico")
async def favicon():
    from fastapi.responses import FileResponse
    return FileResponse("static/img/favicon.ico", media_type="image/x-icon")

@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt():
    return """User-agent: *
Allow: /
Disallow: /api/

Sitemap: https://moviefinders.net/sitemap-index.xml
"""



async def fetch_tmdb_discover(sort_by: str, lang: str, page: int, extra_params: dict = {}) -> dict:
    """Fetch discover/movie from TMDB directly."""
    tmdb_lang = "ru-RU" if lang == "ru" else "en-US"
    params = {
        "api_key": TMDB_API_KEY,
        "language": tmdb_lang,
        "sort_by": sort_by,
        "page": min(page, 50),
        **extra_params,
    }
    if sort_by == "vote_average.desc":
        params.setdefault("vote_count.gte", 500)
    async with httpx.AsyncClient() as client:
        r = await client.get("https://api.themoviedb.org/3/discover/movie", params=params, timeout=10)
        if r.status_code != 200:
            return {"movies": [], "total_pages": 1}
        data = r.json()
        movies = []
        for m in data.get("results", []):
            poster = m.get("poster_path", "")
            movies.append({
                "tmdb_id": m.get("id"),
                "title": m.get("title", ""),
                "title_ru": m.get("title", ""),
                "display_title": m.get("title", ""),
                "year": (m.get("release_date") or "")[:4],
                "rating": m.get("vote_average", 0),
                "poster_url": f"{TMDB_IMAGE_BASE}{poster}" if poster else "",
                "media_type": "movie",
            })
        return {"movies": movies, "total_pages": min(data.get("total_pages", 1), 50)}


@app.get("/top", response_class=HTMLResponse)
async def top_movies_page(request: Request, page: int = 1, sort: str = "popular"):
    lang = get_lang(request)
    t = get_translations(lang)
    page = max(1, page)
    if sort not in ("new", "rating", "popular"):
        sort = "popular"
    sort_map = {
        "popular":  ("popularity.desc",        {"primary_release_date.gte": "2024-01-01", "vote_count.gte": 50}),
        "rating":   ("vote_average.desc",       {"primary_release_date.gte": "2024-01-01", "vote_count.gte": 500}),
        "new":      ("primary_release_date.desc", {"primary_release_date.gte": "2024-01-01", "vote_count.gte": 10}),
    }
    sort_by, extra = sort_map[sort]
    try:
        result = await fetch_tmdb_discover(sort_by, lang, page, extra)
        movies = result["movies"]
        total_pages = result["total_pages"]
    except Exception as e:
        print(f"Top page error: {e}")
        movies = []
        total_pages = 1
    return templates.TemplateResponse(request, "top.html", {
        "movies": movies, "lang": lang, "t": t,
        "current_page": page, "total_pages": total_pages,
        "current_sort": sort, "base_url": "/top",
    })


@app.get("/films/2026", response_class=HTMLResponse)
async def films_2026_page(request: Request, page: int = 1, sort: str = "new"):
    lang = get_lang(request)
    t = get_translations(lang)
    page = max(1, page)
    if sort not in ("new", "rating", "popular"):
        sort = "new"
    sort_map = {
        "popular":  ("popularity.desc",         {"primary_release_year": 2026, "vote_count.gte": 5}),
        "rating":   ("vote_average.desc",        {"primary_release_year": 2026, "vote_count.gte": 100}),
        "new":      ("primary_release_date.desc", {"primary_release_year": 2026, "vote_count.gte": 5}),
    }
    sort_by, extra = sort_map[sort]
    try:
        result = await fetch_tmdb_discover(sort_by, lang, page, extra)
        movies = result["movies"]
        total_pages = result["total_pages"]
    except Exception as e:
        print(f"Films 2026 error: {e}")
        movies = []
        total_pages = 1
    return templates.TemplateResponse(request, "films_2026.html", {
        "movies": movies, "lang": lang, "t": t,
        "current_page": page, "total_pages": total_pages,
        "current_sort": sort, "base_url": "/films/2026",
    })


@app.get("/genres", response_class=HTMLResponse)
async def genres_page(request: Request):
    lang = get_lang(request)
    t = get_translations(lang)
    return templates.TemplateResponse(request, "genres.html", {
        "genres": GENRE_MAP, "lang": lang, "t": t,
    })


# TMDB sort map for genre pages
TMDB_SORT_MAP = {
    "popular": "popularity.desc",
    "rating":  "vote_average.desc",
    "new":     "primary_release_date.desc",
}
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

async def fetch_genre_from_tmdb(genre_id: int, page: int, sort_by: str, lang: str) -> dict:
    """Fetch genre movies directly from TMDB API."""
    tmdb_lang = "ru-RU" if lang == "ru" else "en-US"
    params = {
        "api_key": TMDB_API_KEY,
        "language": tmdb_lang,
        "sort_by": sort_by,
        "with_genres": genre_id,
        "vote_count.gte": 10,
        "page": min(page, 50),  # TMDB max 500 pages but we limit to 50 (1000 movies)
    }
    if sort_by == "vote_average.desc":
        params["vote_count.gte"] = 200  # avoid low-vote trash in rating sort
    async with httpx.AsyncClient() as client:
        r = await client.get(
            "https://api.themoviedb.org/3/discover/movie",
            params=params, timeout=10
        )
        if r.status_code != 200:
            return {"movies": [], "total_pages": 1}
        data = r.json()
        movies = []
        for m in data.get("results", []):
            poster = m.get("poster_path", "")
            movies.append({
                "tmdb_id": m.get("id"),
                "title": m.get("title", ""),
                "title_ru": m.get("title", ""),  # ru-RU response already has Russian title
                "display_title": m.get("title", ""),
                "year": (m.get("release_date") or "")[:4],
                "rating": m.get("vote_average", 0),
                "poster_url": f"{TMDB_IMAGE_BASE}{poster}" if poster else "",
                "media_type": "movie",
            })
        return {
            "movies": movies,
            "total_pages": min(data.get("total_pages", 1), 50),
        }

@app.get("/genre/{slug}", response_class=HTMLResponse)
async def genre_page(request: Request, slug: str, page: int = 1, sort: str = "popular"):
    lang = get_lang(request)
    t = get_translations(lang)

    genre_info = GENRE_MAP.get(slug)
    if not genre_info:
        return templates.TemplateResponse(request, "404.html", {"request": request, "lang": lang, "t": t}, status_code=404)

    page = max(1, page)
    if sort not in ("new", "rating", "popular"):
        sort = "popular"

    sort_by = TMDB_SORT_MAP[sort]
    try:
        result = await fetch_genre_from_tmdb(genre_info["tmdb_id"], page=page, sort_by=sort_by, lang=lang)
        movies = result["movies"]
        total_pages = result["total_pages"]
    except Exception as e:
        print(f"Genre TMDB error: {e}")
        # Fallback to DB
        try:
            result = get_movies_by_genre_db(genre_info["tmdb"], page=page, sort=sort)
            movies = result["movies"]
            total_pages = result["total_pages"]
        except:
            movies = []
            total_pages = 1

    genre_name = genre_info["ru"] if lang == "ru" else genre_info["en"]

    return templates.TemplateResponse(request, "genre.html", {
        "movies": movies, "lang": lang, "t": t,
        "genre_info": genre_info, "genre_name": genre_name,
        "slug": slug,
        "current_page": page,
        "total_pages": total_pages,
        "total": total_pages * 20,
        "base_url": f"/genre/{slug}",
        "current_sort": sort,
    })


@app.get("/films/vecher", response_class=HTMLResponse)
async def films_vecher_page(request: Request, page: int = 1):
    lang = get_lang(request)
    t = get_translations(lang)
    page = max(1, page)
    try:
        result = get_vecher_movies_db(page=page)
        movies = result["movies"]
        total_pages = result["total_pages"]
    except Exception as e:
        print(f"Vecher page DB error: {e}")
        movies = []
        total_pages = 1
    for m in movies:
        m["display_title"] = m.get("title_ru") or m.get("title", "") if lang == "ru" else m.get("title", "")
    return templates.TemplateResponse(request, "films_vecher.html", {
        "movies": movies, "lang": lang, "t": t,
        "current_page": page,
        "total_pages": total_pages,
        "base_url": "/films/vecher",
    })

@app.get("/sitemap-index.xml")
async def sitemap_index():
    import sqlite3, math
    from database import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM movies")
    total = cur.fetchone()[0]
    conn.close()
    
    num_chunks = math.ceil(total / SITEMAP_CHUNK_SIZE)
    today = date.today().isoformat()
    
    urls = []
    urls.append(f"  <sitemap>\n    <loc>{BASE_URL}/sitemap-static.xml</loc>\n    <lastmod>{today}</lastmod>\n  </sitemap>")
    for i in range(1, num_chunks + 1):
        urls.append(f"  <sitemap>\n    <loc>{BASE_URL}/sitemap-movies-{i}.xml</loc>\n    <lastmod>{today}</lastmod>\n  </sitemap>")
    
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml += "\n".join(urls)
    xml += "\n</sitemapindex>"
    
    return Response(content=xml, media_type="application/xml")


@app.get("/sitemap-static.xml")
async def sitemap_static():
    today = date.today().isoformat()
    static_pages = [
        ("/", "1.0", "daily"),
        ("/ai-search", "0.9", "weekly"),
        ("/top", "0.9", "weekly"),
        ("/films/2026", "0.9", "daily"),
        ("/genres", "0.8", "weekly"),
        ("/films/vecher", "0.8", "weekly"),
        ("/en/top", "0.8", "weekly"),
        ("/en/films/2026", "0.8", "daily"),
    ] + [("/genre/" + slug, "0.8", "weekly") for slug in GENRE_MAP.keys()] + [("/en/genre/" + slug, "0.7", "weekly") for slug in GENRE_MAP.keys()]
    
    urls = []
    for path, priority, changefreq in static_pages:
        urls.append(f"""  <url>
    <loc>{BASE_URL}{path}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>{changefreq}</changefreq>
    <priority>{priority}</priority>
  </url>""")
    
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml += "\n".join(urls)
    xml += "\n</urlset>"
    
    return Response(content=xml, media_type="application/xml")


@app.get("/sitemap-movies-{chunk}.xml")
async def sitemap_movies(chunk: int):
    import sqlite3
    from database import DB_PATH
    
    if chunk < 1:
        return Response(content="Invalid chunk", status_code=400)
    
    offset = (chunk - 1) * SITEMAP_CHUNK_SIZE
    today = date.today().isoformat()
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT tmdb_id FROM movies ORDER BY id LIMIT ? OFFSET ?", (SITEMAP_CHUNK_SIZE, offset))
    rows = cur.fetchall()
    conn.close()
    
    if not rows:
        return Response(content="<?xml version=\"1.0\" encoding=\"UTF-8\"?><urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\"></urlset>", media_type="application/xml")
    
    urls = []
    for (tmdb_id,) in rows:
        url = f"{BASE_URL}/movie/{tmdb_id}"
        url_en = f"{BASE_URL}/en/movie/{tmdb_id}"
        urls.append(f"""  <url>
    <loc>{url}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
    <xhtml:link rel="alternate" hreflang="ru" href="{url}"/>
    <xhtml:link rel="alternate" hreflang="en" href="{url_en}"/>
  </url>""")
        urls.append(f"""  <url>
    <loc>{url_en}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.7</priority>
    <xhtml:link rel="alternate" hreflang="ru" href="{url}"/>
    <xhtml:link rel="alternate" hreflang="en" href="{url_en}"/>
  </url>""")
    
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
    xml += '        xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
    xml += "\n".join(urls)
    xml += "\n</urlset>"
    
    return Response(content=xml, media_type="application/xml")


# Alias sitemap.xml → sitemap-index.xml
@app.get("/sitemap.xml")
async def sitemap_xml_alias():
    return await sitemap_index()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8767, reload=False)


@app.get("/api/clear-cache/all")
async def clear_all_cache(secret: str = Query("")):
    """Clear ALL sources cache. Requires ADMIN_SECRET env var."""
    admin_secret = os.environ.get("ADMIN_SECRET", "")
    if admin_secret and secret != admin_secret:
        return JSONResponse({"error": "Unauthorized"}, status_code=403)
    import sqlite3
    from database import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM sources_cache")
    count = cur.fetchone()[0]
    cur.execute("DELETE FROM sources_cache")
    conn.commit()
    conn.close()
    return {"ok": True, "deleted": count, "message": "All cache cleared"}

@app.get("/api/clear-cache/{tmdb_id}")
async def clear_source_cache(tmdb_id: int, secret: str = Query("")):
    """Clear cached sources for a specific movie (forces re-fetch). Requires ADMIN_SECRET env var."""
    admin_secret = os.environ.get("ADMIN_SECRET", "")
    if admin_secret and secret != admin_secret:
        return JSONResponse({"error": "Unauthorized"}, status_code=403)
    import sqlite3, os
    db_path = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "data", "moviefinder.db"))
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("DELETE FROM sources_cache WHERE tmdb_id = ?", (tmdb_id,))
        deleted = cur.rowcount
        conn.commit()
        conn.close()
        return {"ok": True, "deleted": deleted, "tmdb_id": tmdb_id}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/kp-url/{tmdb_id}")
async def kp_url(tmdb_id: int, title: str = "", title_ru: str = "", year: int = 0):
    """Get direct Kinopoisk URL for a movie."""
    from services.sources import _fetch_kinopoisk
    async with httpx.AsyncClient(verify=False, follow_redirects=True) as client:
        result = await _fetch_kinopoisk(client, title, title_ru or None, year)
    if result:
        return {"url": result["url"]}
    return {"url": f"https://www.kinopoisk.ru/index.php?first=yes&what=&kp_query={title}"}


# ============================================================
# ENGLISH ROUTES - /en/ prefix for EN SEO
# ============================================================

@app.get("/en/movie/{tmdb_id}", response_class=HTMLResponse)
async def en_movie_page(request: Request, tmdb_id: int, media_type: str = "movie"):
    lang = "en"
    t = get_translations(lang)
    try:
        movie = await get_movie_details(tmdb_id, media_type, lang=lang)
        if not movie:
            return templates.TemplateResponse(request, "404.html", {"request": request, "lang": lang, "t": t}, status_code=404)
        db_movie = get_movie_by_tmdb(tmdb_id)
        if db_movie and db_movie.get("title_en"):
            movie["display_title"] = db_movie["title_en"]
        sources = await get_all_sources(tmdb_id, movie["title"], movie.get("year"), title_ru=movie.get("title_ru"), media_type=media_type)
        return templates.TemplateResponse(request, "movie.html", {
            "movie": movie, "sources": sources, "lang": lang, "t": t,
            "hreflang_ru": f"https://moviefinders.net/movie/{tmdb_id}",
            "hreflang_en": f"https://moviefinders.net/en/movie/{tmdb_id}",
        })
    except Exception as e:
        return HTMLResponse(f"Error: {e}", status_code=500)


@app.get("/en/genre/{slug}", response_class=HTMLResponse)
async def en_genre_page(request: Request, slug: str, page: int = 1, sort: str = "popular"):
    lang = "en"
    t = get_translations(lang)
    genre_info = GENRE_MAP.get(slug)
    if not genre_info:
        return templates.TemplateResponse(request, "404.html", {"request": request, "lang": lang, "t": t}, status_code=404)
    page = max(1, page)
    if sort not in ("new", "rating", "popular"):
        sort = "popular"
    sort_by = TMDB_SORT_MAP[sort]
    try:
        result = await fetch_genre_from_tmdb(genre_info["tmdb_id"], page=page, sort_by=sort_by, lang=lang)
        movies = result["movies"]
        total_pages = result["total_pages"]
    except:
        movies = []; total_pages = 1
    return templates.TemplateResponse(request, "genre.html", {
        "movies": movies, "lang": lang, "t": t,
        "genre_info": genre_info, "genre_name": genre_info["en"],
        "slug": slug, "current_page": page, "total_pages": total_pages,
        "total": total_pages * 20, "base_url": f"/en/genre/{slug}",
        "current_sort": sort,
        "hreflang_ru": f"https://moviefinders.net/genre/{slug}",
        "hreflang_en": f"https://moviefinders.net/en/genre/{slug}",
    })


@app.get("/en/top", response_class=HTMLResponse)
async def en_top_page(request: Request, page: int = 1, sort: str = "popular"):
    lang = "en"
    t = get_translations(lang)
    page = max(1, page)
    if sort not in ("new", "rating", "popular"):
        sort = "popular"
    sort_map = {
        "popular": ("popularity.desc", {"primary_release_date.gte": "2024-01-01", "vote_count.gte": 50}),
        "rating":  ("vote_average.desc", {"primary_release_date.gte": "2024-01-01", "vote_count.gte": 500}),
        "new":     ("primary_release_date.desc", {"primary_release_date.gte": "2024-01-01", "vote_count.gte": 10}),
    }
    sort_by, extra = sort_map[sort]
    try:
        result = await fetch_tmdb_discover(sort_by, lang, page, extra)
        movies = result["movies"]; total_pages = result["total_pages"]
    except:
        movies = []; total_pages = 1
    return templates.TemplateResponse(request, "top.html", {
        "movies": movies, "lang": lang, "t": t,
        "current_page": page, "total_pages": total_pages,
        "current_sort": sort, "base_url": "/en/top",
        "hreflang_ru": "https://moviefinders.net/top",
        "hreflang_en": "https://moviefinders.net/en/top",
    })


@app.get("/en/films/2026", response_class=HTMLResponse)
async def en_films_2026_page(request: Request, page: int = 1, sort: str = "new"):
    lang = "en"
    t = get_translations(lang)
    page = max(1, page)
    if sort not in ("new", "rating", "popular"):
        sort = "new"
    sort_map = {
        "popular": ("popularity.desc", {"primary_release_year": 2026, "vote_count.gte": 5}),
        "rating":  ("vote_average.desc", {"primary_release_year": 2026, "vote_count.gte": 100}),
        "new":     ("primary_release_date.desc", {"primary_release_year": 2026, "vote_count.gte": 5}),
    }
    sort_by, extra = sort_map[sort]
    try:
        result = await fetch_tmdb_discover(sort_by, lang, page, extra)
        movies = result["movies"]; total_pages = result["total_pages"]
    except:
        movies = []; total_pages = 1
    return templates.TemplateResponse(request, "films_2026.html", {
        "movies": movies, "lang": lang, "t": t,
        "current_page": page, "total_pages": total_pages,
        "current_sort": sort, "base_url": "/en/films/2026",
        "hreflang_ru": "https://moviefinders.net/films/2026",
        "hreflang_en": "https://moviefinders.net/en/films/2026",
    })


@app.get("/en/ai-search", response_class=HTMLResponse)
async def en_ai_search_page(request: Request, q: str = ""):
    lang = "en"
    t = get_translations(lang)
    result = {"results": [], "description": "", "count": 0}
    if q:
        log_search(q)
        result = await smart_search(q, lang=lang)
    return templates.TemplateResponse(request, "ai_search.html", {
        "query": q,
        "results": result["results"],
        "smart_mode": True,
        "smart_description": result.get("description") or "",
        "smart_count": result.get("count", 0),
        "lang": lang,
        "t": t,
        "hreflang_ru": "https://moviefinders.net/ai-search",
        "hreflang_en": "https://moviefinders.net/en/ai-search",
        "canonical_url": "https://moviefinders.net/en/ai-search",
    })


@app.get("/en/films/vecher", response_class=HTMLResponse)
async def en_films_vecher_page(request: Request, page: int = 1, sort: str = "popular"):
    lang = "en"
    t = get_translations(lang)
    page = max(1, page)
    if sort not in ("new", "rating", "popular"):
        sort = "popular"
    sort_map = {
        "popular": ("popularity.desc", {"with_genres": "35,18,10749", "vote_count.gte": 50, "vote_average.gte": 7.0}),
        "rating":  ("vote_average.desc", {"with_genres": "35,18,10749", "vote_count.gte": 200}),
        "new":     ("primary_release_date.desc", {"with_genres": "35,18,10749", "vote_count.gte": 10}),
    }
    sort_by, extra = sort_map[sort]
    try:
        result = await fetch_tmdb_discover(sort_by, lang, page, extra)
        movies = result["movies"]
        total_pages = result["total_pages"]
    except Exception as e:
        movies = []
        total_pages = 1
    return templates.TemplateResponse(request, "films_vecher.html", {
        "movies": movies, "lang": lang, "t": t,
        "current_page": page, "total_pages": total_pages,
        "current_sort": sort, "base_url": "/en/films/vecher",
        "hreflang_ru": "https://moviefinders.net/films/vecher",
        "hreflang_en": "https://moviefinders.net/en/films/vecher",
        "canonical_url": "https://moviefinders.net/en/films/vecher",
    })


@app.get("/en/", response_class=HTMLResponse)
@app.get("/en", response_class=HTMLResponse)
async def en_homepage(request: Request):
    """English homepage - redirect to main with EN lang set."""
    from fastapi.responses import RedirectResponse
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie("lang", "en", max_age=31536000)
    return response
