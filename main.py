import asyncio
import os
import sys
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

from database import init_db, log_search, get_trending_searches, save_movie, get_movie_by_tmdb, get_recent_movies, get_top_rated_db
from services.tmdb import search_movies, get_movie_details, get_trending, get_top_rated, get_now_playing, get_upcoming, get_popular_movies, get_new_2026, get_popular_tv, get_oscar_winners, get_romance_comedy, get_top_horror
from services.sources import get_all_sources, get_watch_sources
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

        sources = await get_all_sources(tmdb_id, movie["title"], movie.get("year"), title_ru=movie.get("title_ru"))

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
        result = await smart_search(q)
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
    if not title:
        # Try to get title from DB
        movie = get_movie_by_tmdb(tmdb_id)
        if movie:
            title = movie.get("title", "")
            title_ru = movie.get("title_ru", "")
            year = movie.get("year", 0) or 0
            if not imdb_id:
                imdb_id = movie.get("imdb_id", "") or ""

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

BASE_URL = "https://moviefinder-production.up.railway.app"
SITEMAP_CHUNK_SIZE = 10000

@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt():
    return """User-agent: *
Allow: /
Disallow: /api/
Disallow: /static/

Sitemap: https://moviefinder-production.up.railway.app/sitemap-index.xml
"""

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
    today = "2026-03-27"
    
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
    today = "2026-03-27"
    static_pages = [
        ("/", "1.0", "daily"),
        ("/ai-search", "0.9", "weekly"),
        ("/favorites", "0.5", "monthly"),
    ]
    
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
    today = "2026-03-27"
    
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
        urls.append(f"""  <url>
    <loc>{url}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
    <xhtml:link rel="alternate" hreflang="ru" href="{url}?lang=ru"/>
    <xhtml:link rel="alternate" hreflang="en" href="{url}?lang=en"/>
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
    import httpx
    async with httpx.AsyncClient(verify=False, follow_redirects=True) as client:
        result = await _fetch_kinopoisk(client, title, title_ru or None, year)
    if result:
        return {"url": result["url"]}
    return {"url": f"https://www.kinopoisk.ru/index.php?first=yes&what=&kp_query={title}"}
