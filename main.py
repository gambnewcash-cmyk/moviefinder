import asyncio
import os
import sys
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

from database import init_db, log_search, get_trending_searches, save_movie, get_movie_by_tmdb, get_recent_movies, get_top_rated_db
from services.tmdb import search_movies, get_movie_details, get_trending, get_top_rated, get_now_playing, get_upcoming, get_popular_movies
from services.sources import get_all_sources
from services.smart_search import smart_search, get_typo_suggestions
from translations import get_translations, detect_language

app = FastAPI(title="MovieFinder")

BASE_DIR = os.path.dirname(__file__)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


def get_lang(request: Request) -> str:
    """Determine language: cookie first, then Accept-Language header."""
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
        now_playing_task = get_now_playing(lang=lang)
        upcoming_task = get_upcoming(lang=lang)

        trending, top_rated, now_playing, upcoming = await asyncio.gather(
            trending_task, top_rated_task, now_playing_task, upcoming_task,
            return_exceptions=True
        )

        if isinstance(trending, Exception): trending = []
        if isinstance(top_rated, Exception): top_rated = []
        if isinstance(now_playing, Exception): now_playing = []
        if isinstance(upcoming, Exception): upcoming = []

        trending_searches = get_trending_searches(10)

        return templates.TemplateResponse(request, "index.html", {
            "trending": trending[:10],
            "top_rated": top_rated[:10],
            "now_playing": now_playing[:10],
            "upcoming": upcoming[:10],
            "trending_searches": trending_searches,
            "lang": lang,
            "t": t,
        })
    except Exception as e:
        print(f"Index error: {e}")
        return templates.TemplateResponse(request, "index.html", {
            "trending": [], "top_rated": [], "now_playing": [], "upcoming": [],
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
            return HTMLResponse("Movie not found", status_code=404)

        sources = await get_all_sources(tmdb_id, movie["title"], movie.get("year"))

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
        result = await smart_search(q)
    return templates.TemplateResponse(request, "search.html", {
        "query": q,
        "results": result["results"],
        "smart_mode": True,
        "smart_description": result.get("description", ""),
        "smart_count": result.get("count", 0),
        "lang": lang,
        "t": t,
    })


@app.get("/api/movie/{tmdb_id}")
async def api_movie(request: Request, tmdb_id: int, media_type: str = "movie"):
    lang = get_lang(request)
    movie = await get_movie_details(tmdb_id, media_type, lang=lang)
    if not movie:
        return JSONResponse({"error": "Not found"}, status_code=404)
    sources = await get_all_sources(tmdb_id, movie["title"], movie.get("year"))
    return {"movie": movie, "sources": sources}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8767, reload=False)
