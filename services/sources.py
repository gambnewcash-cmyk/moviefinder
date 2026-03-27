"""
sources.py - Live "Where to Watch" search.

Parallel requests to:
  1. JustWatch GraphQL - ALL providers dynamically (flatrate/rent/buy/free)
  2. HDRezka AJAX search - real movie URL
  3. Kinogo search - real movie URL
  4. Filmix AJAX search - real movie URL
  5. Kinopoisk search - info URL

Results cached in DB forever.
"""

import asyncio
import json
import os
import re
import time
from typing import List, Dict, Optional
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
KP_API_KEY = os.getenv('KP_API_KEY', '')
_PROXY_USA = os.getenv('PROXY_USA')
_PROXY_DE = os.getenv('PROXY_DE')
HDREZKA_PROXIES_ENV = [p for p in [_PROXY_USA, _PROXY_DE] if p]

# --- Constants ---
CACHE_TTL = 7 * 24 * 3600  # 7 days — prevents stale/wrong URLs from persisting forever
REQUEST_TIMEOUT = 8.0

JUSTWATCH_GQL = "https://apis.justwatch.com/graphql"

JUSTWATCH_QUERY = """
query GetTitleSources($country: Country!, $language: Language!, $query: String!) {
  popularTitles(
    country: $country
    language: $language
    filter: { searchQuery: $query, objectTypes: [MOVIE, SHOW] }
    first: 5
  ) {
    edges {
      node {
        ... on Movie {
          id
          objectId
          content(country: $country, language: $language) {
            title
            originalReleaseYear
          }
          offers(country: $country, platform: WEB) {
            monetizationType
            package {
              clearName
              icon
            }
            standardWebURL
          }
        }
        ... on Show {
          id
          objectId
          content(country: $country, language: $language) {
            title
            originalReleaseYear
          }
          offers(country: $country, platform: WEB) {
            monetizationType
            package {
              clearName
              icon
            }
            standardWebURL
          }
        }
      }
    }
  }
}
"""

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}


# ---------------------------------------------------------------------------
# Title matching helper
# ---------------------------------------------------------------------------

def _word_match(word: str, text: str) -> bool:
    """Word boundary match supporting both Cyrillic and ASCII.
    Prevents substring false positives like 'Она' matching inside 'Иконы'.
    """
    try:
        return bool(re.search(r'(?<![\w\u0400-\u04FF])' + re.escape(word.lower()) + r'(?![\w\u0400-\u04FF])', text.lower()))
    except Exception:
        return word.lower() in text.lower()



# ---------------------------------------------------------------------------
# JustWatch
# ---------------------------------------------------------------------------

def _justwatch_type_label(monetization: str) -> str:
    mapping = {
        "FLATRATE": "subscription",
        "RENT": "rent",
        "BUY": "buy",
        "FREE": "free",
        "ADS": "free (ads)",
        "FLATRATE_AND_BUY": "subscription",
    }
    return mapping.get(monetization, monetization.lower())


def _pick_best_justwatch_movie(edges: list, title_en: str, year: int) -> Optional[dict]:
    """
    Pick the best matching movie from JustWatch results.
    Uses scoring: exact title = 10pts, partial title = 3pts, year match = 5pts.
    Returns None if no title match found (prevents returning random movie).
    """
    title_lower = title_en.lower()
    best = None
    best_score = 0

    for e in edges:
        node = e.get("node", {})
        content = node.get("content", {})
        node_title = (content.get("title") or "").lower()
        node_year = content.get("originalReleaseYear")

        score = 0
        # Exact title match
        if node_title == title_lower:
            score += 10
        # Partial title match (first word)
        elif title_lower.split()[0] in node_title:
            score += 3

        # Year match
        if year and node_year == year:
            score += 5

        if score > best_score:
            best_score = score
            best = node

    # Only return if we have a reasonable match (score >= 3 means at least title word matched)
    # If score is 0, nothing matched - return None instead of random movie
    if best_score >= 3:
        return best
    return None  # Don't return random movie when nothing matches


async def _fetch_justwatch(
    client: httpx.AsyncClient,
    title_en: str,
    title_ru: Optional[str],
    year: int,
    country: str = "US",
    language: str = "en",
) -> List[Dict]:
    """
    Query JustWatch GraphQL for ALL streaming offers for the movie.
    Returns list of offer dicts grouped by type.
    """
    sources: List[Dict] = []
    try:
        payload = {
            "operationName": "GetTitleSources",
            "variables": {
                "country": country,
                "language": language,
                "query": title_en,
            },
            "query": JUSTWATCH_QUERY,
        }
        r = await client.post(
            JUSTWATCH_GQL,
            json=payload,
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
            timeout=REQUEST_TIMEOUT,
        )
        if r.status_code != 200:
            return sources

        data = r.json()
        edges = (
            data.get("data", {})
            .get("popularTitles", {})
            .get("edges", [])
        )

        movie_node = _pick_best_justwatch_movie(edges, title_en, year)
        if not movie_node:
            return sources

        offers = movie_node.get("offers", [])

        # Deduplicate by (package clearName + url) - JustWatch sometimes duplicates
        seen = set()
        for offer in offers:
            pkg = offer.get("package", {})
            provider_name = pkg.get("clearName", "Unknown")
            url = offer.get("standardWebURL", "")
            mon_type = offer.get("monetizationType", "")
            key = (provider_name, mon_type)
            if key in seen:
                continue
            seen.add(key)

            price = offer.get("retailPrice")
            price_str = f"${price:.2f}" if price else None

            sources.append({
                "source_name": provider_name,
                "source_type": "justwatch",
                "offer_type": _justwatch_type_label(mon_type),
                "monetization": mon_type,
                "url": url,
                "quality": "HD",
                "icon_url": ("https://images.justwatch.com" + pkg.get("icon", "").replace("{profile}", "s100").replace("{format}", "webp")) if pkg.get("icon") else None,
                "price": price_str,
            })

    except Exception as e:
        print(f"[sources] JustWatch error: {e}")

    return sources


# ---------------------------------------------------------------------------
# HDRezka
# ---------------------------------------------------------------------------

async def _fetch_hdrezka(
    client: httpx.AsyncClient,
    title_en: str,
    title_ru: Optional[str],
    year: int,
    media_type: str = "movie",
) -> Optional[Dict]:
    """Search HDRezka via GET search endpoint (AJAX POST is broken, returns homepage)."""
    query = title_ru or title_en
    icon_url = "https://hdrezka.film/favicon.ico"
    origins = ["https://hdrezka.film", "https://hdrezka.me", "https://hdrezka-home.tv"]
    for origin in origins:
        for search_query in ([f"{query} {year}", query] if year else [query]):
            try:
                r = await client.get(
                    f"{origin}/?do=search&subaction=search&q={search_query}",
                    headers={**BROWSER_HEADERS, "Referer": f"{origin}/"},
                    timeout=REQUEST_TIMEOUT,
                )
                if r.status_code != 200 or len(r.text) < 5000:
                    continue

                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    text = a.get_text(strip=True)
                    if not href.startswith("http"):
                        href = origin + href
                    # Filter by media_type
                    if media_type == "tv":
                        if not re.search(r"hdrezka\.(film|me|tv)/serialy/\d+-[\w-]+\.html", href):
                            continue
                        if any(pat in href for pat in ["/multserial/", "/anime/"]):
                            continue
                    else:
                        if re.search(r"hdrezka\.(film|me|tv)/serialy/", href):
                            continue
                        if any(pat in href for pat in ["/multserial/", "/anime/"]):
                            continue
                        if not re.search(r"hdrezka\.(film|me|tv)/(filmy|multfilmy)/\d+-[\w-]+\.html", href):
                            continue
                    if True:
                        # Title match: ANY word from Russian title OR first word of English title
                        # Use word boundaries to avoid "Она" matching inside "Иконы", "Us" in "несокрушимые"
                        title_match = (
                            (title_ru and any(_word_match(w, text + " " + href) for w in title_ru.split() if len(w) > 2)) or
                            (title_en and _word_match(title_en.split()[0], text + " " + href))
                        )
                        if title_match:
                            return {
                                "source_name": "HDRezka",
                                "source_type": "pirate",
                                "offer_type": "free",
                                "url": href,
                                "quality": "1080p",
                                "icon_url": icon_url,
                            }
            except Exception as e:
                print(f"[sources] HDRezka {origin} error: {e}")
                continue

    return None


# ---------------------------------------------------------------------------
# Kinogo
# ---------------------------------------------------------------------------

async def _fetch_kinogo(
    client: httpx.AsyncClient,
    title_en: str,
    title_ru: Optional[str],
    year: int,
    media_type: str = "movie",
) -> Optional[Dict]:
    """Search kinogo.my, return direct movie URL if found.
    
    Note: Kinogo search breaks when year is added to query (returns error page).
    Always search by title only, then validate year from text content.
    """
    query = title_ru or title_en
    icon_url = "https://kinogo.my/favicon.ico"
    if media_type == "tv":
        skip_patterns = ["/anime/", "/doramy/"]
    else:
        skip_patterns = ["/tv-shou/", "/serialy/", "/multserial/", "/anime/", "/doramy/"]

    try:
        # Search by first 2 words only - long titles cause no results on Kinogo
        # Strip punctuation from query words
        import re as _re
        words = [_re.sub(r'[^\w\s]', '', w) for w in query.split() if _re.sub(r'[^\w\s]', '', w)]
        short_query = " ".join(words[:2]) if len(words) > 2 else " ".join(words)
        r = await client.post(
            "https://kinogo.my/",
            data={
                "do": "search",
                "subaction": "search",
                "story": short_query,  # use short query for better results
            },
            headers={
                **BROWSER_HEADERS,
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": "https://kinogo.my/",
                "Origin": "https://kinogo.my",
            },
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        )
        if r.status_code != 200 or len(r.text) < 1000:
            return None

        soup = BeautifulSoup(r.text, "html.parser")
        
        def _check_link(href, text):
            """Check if a kinogo link matches the movie we want."""
            if text in ("", "Смотреть"):
                return False
            if any(pat in href for pat in skip_patterns):
                return False
            if "kinogo.my" not in href:
                return False
            if not re.search(r"/\d+-[\w-]+\.html", href):
                return False
            # Title match: any significant word from Russian OR first word of English
            title_match = (
                (title_ru and any(_word_match(w, text) for w in title_ru.split() if len(w) > 2)) or
                (title_en and _word_match(title_en.split()[0], text))
            )
            if not title_match:
                return False
            # Year validation: if year provided, check text (which usually has year)
            # URL slugs on kinogo often have wrong years (e.g., Inception at nachalo-2010 slug says 2026 in URL)
            if year:
                year_in_text = str(year) in text
                # Accept if year matches in text, OR if we can't determine year from text
                if "(" in text and ")" in text:
                    # Text has year in parentheses like "Начало (2010)"
                    year_match = str(year) in text
                    if not year_match:
                        return False  # Wrong year movie
            return True
        
        # First check loader-here (structured search results)
        loader = soup.find(id="loader-here")
        if loader:
            articles = loader.find_all("div", class_="article")
            for article in articles:
                for a in article.find_all("a", href=True):
                    href = a["href"]
                    text = a.get_text(strip=True)
                    if _check_link(href, text):
                        return {
                            "source_name": "Kinogo",
                            "source_type": "pirate",
                            "offer_type": "free",
                            "url": href,
                            "quality": "1080p",
                            "icon_url": icon_url,
                        }

        # Broad search - scan all links on page
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if _check_link(href, text):
                return {
                    "source_name": "Kinogo",
                    "source_type": "pirate",
                    "offer_type": "free",
                    "url": href,
                    "quality": "1080p",
                    "icon_url": icon_url,
                }

        return None
    except Exception as e:
        print(f"[sources] Kinogo error: {e}")
        return None


# ---------------------------------------------------------------------------
# Filmix
# ---------------------------------------------------------------------------

async def _fetch_filmix(
    client: httpx.AsyncClient,
    title_en: str,
    title_ru: Optional[str],
    year: int,
    media_type: str = "movie",
) -> Optional[Dict]:
    """Search Filmix via AJAX, return direct movie URL if found."""
    query = title_ru or title_en
    icon_url = "https://filmix.my/favicon.ico"

    try:
        # Use AJAX search endpoint which works correctly
        r = await client.post(
            "https://filmix.my/engine/ajax/search.php",
            data={"query": query},
            headers={
                **BROWSER_HEADERS,
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://filmix.my/",
                "Origin": "https://filmix.my",
            },
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        )
        if r.status_code != 200 or len(r.text) < 50:
            return None  # Filmix not found

        # Parse AJAX response: <a href="URL"><span class="searchheading">TITLE</span>...
        # The links may redirect to the actual movie page
        matches = re.findall(
            r'<a href="([^"]+)"><span class="searchheading">([^<]+)</span>',
            r.text
        )
        for href, title_found in matches:
            title_found_lower = title_found.lower()
            # 1. Skip if URL looks like news (no /film/ or /serial/ or numeric ID pattern)
            if not re.search(r'/(film|serial|cartoon|anime|mults|seria|multser)/|/\d+-[\w-]+\.html', href):
                continue
            # 2. Skip news articles / unrelated content
            if any(skip in title_found_lower for skip in ["стал", "станет", "выйдет", "вручение", "заявк", "сикве", "номин", "наград"]):
                continue
            # 3. Title match: require at least 1 word > 3 chars matching
            words_match = sum(1 for w in (title_ru or title_en).lower().split()
                              if len(w) > 3 and w in title_found_lower)
            if words_match == 0:
                continue
            # 4. Year match for Filmix
            # Filmix AJAX search only reliably finds movies when year is in href/title
            # For ALL movies: require year in href OR title (Filmix URLs always have year)
            if year:
                # Extract year from href if present
                import re as _re3
                href_year_match = _re3.search(r'-(\d{4})[\.\-]', href)
                href_year = int(href_year_match.group(1)) if href_year_match else None
                title_has_year = str(year) in title_found
                href_has_year = str(year) in href
                if not title_has_year and not href_has_year:
                    # Year not found anywhere - check if href year is too far off
                    if href_year and abs(href_year - year) > 10:
                        continue  # Wrong year movie (allow 10 year tolerance for long-running TV shows)
                    elif href_year is None:
                        # No year in href at all - this is likely a news article, skip
                        # unless href contains /film/ or /seria/ pattern indicating real film/series page
                        # Also accept numeric IDs like /88952-klinika.html
                        if not _re3.search(r'/(film|mults|multser|seria|serial)/', href) and not _re3.search(r'/\d{4,}-', href):
                            continue
            return {
                "source_name": "Filmix",
                "source_type": "pirate",
                "offer_type": "free",
                "url": href if href.startswith("http") else f"https://filmix.my{href}",
                "quality": "720p",
                "icon_url": icon_url,
            }

        # Fallback: try with English title if Russian didn't match
        if title_ru and title_en:
            r2 = await client.post(
                "https://filmix.my/engine/ajax/search.php",
                data={"query": title_en},
                headers={
                    **BROWSER_HEADERS,
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": "https://filmix.my/",
                },
                timeout=REQUEST_TIMEOUT,
                follow_redirects=True,
            )
            if r2.status_code == 200 and len(r2.text) > 50:
                matches2 = re.findall(
                    r'<a href="([^"]+)"><span class="searchheading">([^<]+)</span>',
                    r2.text
                )
                for href, title_found in matches2:
                    title_found_lower = title_found.lower()
                    if not re.search(r'/(film|serial|cartoon|anime|mults|seria|multser)/|/[0-9]+-[\w-]+\.html', href):
                        continue
                    words_match = sum(1 for w in (title_ru or title_en).lower().split()
                                      if len(w) > 3 and w in title_found_lower)
                    if words_match == 0 and title_en.split()[0].lower() not in title_found_lower:
                        continue
                    # Strict year match for fallback too
                    if year and str(year) not in href and str(year) not in title_found:
                        continue
                    return {
                        "source_name": "Filmix",
                        "source_type": "pirate",
                        "offer_type": "free",
                        "url": href if href.startswith("http") else f"https://filmix.my{href}",
                        "quality": "720p",
                        "icon_url": icon_url,
                    }

        return None  # Filmix not found
    except Exception as e:
        print(f"[sources] Filmix error: {e}")
        return None


# ---------------------------------------------------------------------------
# LordFilm
# ---------------------------------------------------------------------------

async def _fetch_lordfilm(
    client: httpx.AsyncClient,
    title_en: str,
    title_ru: Optional[str],
    year: int,
    media_type: str = "movie",
) -> Optional[Dict]:
    """Search lordfilm.fi via DataLife Engine POST search, return direct movie URL."""
    query = title_ru or title_en
    icon_url = "https://lordfilm.fi/favicon.ico"
    if media_type == "tv":
        skip_patterns = ["/anime/", "/cartoon/", "/dokumentalny/"]
    else:
        skip_patterns = ["/serialy/", "/serial/", "/multfilm", "/anime/", "/cartoon/", "/show/", "/dokumentalny/"]

    try:
        # DataLife Engine search
        r = await client.post(
            "https://lordfilm.fi/index.php?do=search",
            data={
                "do": "search",
                "subaction": "search",
                "story": f"{query} {year}" if year else query,
            },
            headers={
                **BROWSER_HEADERS,
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": "https://lordfilm.fi/",
                "Origin": "https://lordfilm.fi",
            },
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        )
        if r.status_code != 200 or len(r.text) < 500:
            return None

        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("http"):
                href = "https://lordfilm.fi" + href
            text = a.get_text(strip=True)
            if any(pat in href for pat in skip_patterns):
                continue
            # LordFilm URLs: https://lordfilm.fi/XXXX-slug-YYYY.html
            if re.search(r"lordfilm\.fi/\d+-[\w-]+\.html", href):
                title_match = (
                    (title_ru and any(_word_match(w, text + " " + href) for w in title_ru.split()[:2])) or
                    (title_en and _word_match(title_en.split()[0], text + " " + href))
                )
                year_match = (not year) or (str(year) in href) or (str(year) in text)
                if title_match and year_match:
                    return {
                        "source_name": "LordFilm",
                        "source_type": "pirate",
                        "offer_type": "free",
                        "url": href,
                        "quality": "HD",
                        "icon_url": icon_url,
                    }

        # Broader search without year
        if year:
            r2 = await client.post(
                "https://lordfilm.fi/index.php?do=search",
                data={"do": "search", "subaction": "search", "story": query},
                headers={**BROWSER_HEADERS, "Content-Type": "application/x-www-form-urlencoded", "Referer": "https://lordfilm.fi/"},
                timeout=REQUEST_TIMEOUT,
                follow_redirects=True,
            )
            if r2.status_code == 200:
                soup2 = BeautifulSoup(r2.text, "html.parser")
                for a in soup2.find_all("a", href=True):
                    href = a["href"]
                    if not href.startswith("http"):
                        href = "https://lordfilm.fi" + href
                    text = a.get_text(strip=True)
                    if any(pat in href for pat in skip_patterns):
                        continue
                    if re.search(r"lordfilm\.fi/\d+-[\w-]+\.html", href):
                        title_match = (
                            (title_ru and any(_word_match(w, text + " " + href) for w in title_ru.split()[:2])) or
                            (title_en and _word_match(title_en.split()[0], text + " " + href))
                        )
                        # Broader search: accept if title matches and year is not too far off
                        # Extract year from href/text to avoid returning obvious wrong versions
                        year_ok = True
                        if year:
                            year_match2 = (str(year) in href) or (str(year) in text)
                            # Reject only if we find a DIFFERENT year in the href/text
                            href_year_match = None
                            import re as _re2
                            m = _re2.search(r'-((?:19|20)\d{2})\.html', href)
                            if m:
                                href_year_match = int(m.group(1))
                            if href_year_match and abs(href_year_match - year) > 2:
                                year_ok = False  # Clearly wrong year
                        if title_match and year_ok:
                            return {
                                "source_name": "LordFilm",
                                "source_type": "pirate",
                                "offer_type": "free",
                                "url": href,
                                "quality": "HD",
                                "icon_url": icon_url,
                            }
        return None
    except Exception as e:
        print(f"[sources] LordFilm error: {e}")
        return None


# ---------------------------------------------------------------------------
# Kinopoisk
# ---------------------------------------------------------------------------

async def _fetch_kinopoisk(
    client: httpx.AsyncClient,
    title_en: str,
    title_ru: Optional[str],
    year: int,
    imdb_id: Optional[str] = None,
) -> Optional[Dict]:
    """Search Kinopoisk via unofficial API to get direct movie URL."""
    icon_url = "https://st.kp.yandex.net/images/favicon.ico"
    
    query = title_ru or title_en
    try:
        r = await client.get(
            "https://kinopoiskapiunofficial.tech/api/v2.1/films/search-by-keyword",
            params={"keyword": query, "page": 1},
            headers={"X-API-KEY": KP_API_KEY},
            timeout=REQUEST_TIMEOUT,
        )
        
        # Rate limited - don't show Kinopoisk
        if r.status_code == 429:
            print("[sources] Kinopoisk API rate limit reached")
            return None
        
        if r.status_code != 200:
            return None
        
        films = r.json().get("films", [])
        for film in films:
            film_id = film.get("filmId")
            name_ru = (film.get("nameRu") or "").lower()
            film_year = str(film.get("year") or "")
            
            if not film_id:
                continue
            
            # Match by title and year
            title_match = (
                (title_ru and any(_word_match(w, name_ru) for w in title_ru.split()[:2])) or
                (title_en and _word_match(title_en.split()[0], name_ru))
            )
            year_match = (not year) or (str(year) in film_year)
            
            if title_match and year_match:
                return {
                    "source_name": "Кинопоиск",
                    "source_type": "info",
                    "offer_type": "free",
                    "url": f"https://www.kinopoisk.ru/film/{film_id}/",
                    "quality": "",
                    "icon_url": icon_url,
                }
        
        # Not found - don't show
        return None
        
    except Exception as e:
        print(f"[sources] Kinopoisk error: {e}")
        return None


# ---------------------------------------------------------------------------
# Cache helpers (inline, using same DB as rest of app)
# ---------------------------------------------------------------------------

def _load_cache(tmdb_id: int, country: str = "US") -> Optional[List[Dict]]:
    """Load cached sources from DB, respecting CACHE_TTL."""
    try:
        import sqlite3
        from database import DB_PATH
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT sources_json, cached_at FROM sources_cache WHERE tmdb_id = ? AND country = ?",
            (tmdb_id, country),
        ).fetchone()
        conn.close()
        if row:
            cached_at = row["cached_at"]
            if CACHE_TTL is None or (time.time() - cached_at < CACHE_TTL):
                return json.loads(row["sources_json"])
    except Exception as e:
        print(f"[sources] Cache load error: {e}")
    return None


def _save_cache(tmdb_id: int, sources: List[Dict], country: str = "US") -> None:
    """Save sources to cache table."""
    try:
        import sqlite3
        from database import DB_PATH
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            """
            INSERT OR REPLACE INTO sources_cache (tmdb_id, country, sources_json, cached_at)
            VALUES (?, ?, ?, ?)
            """,
            (tmdb_id, country, json.dumps(sources, ensure_ascii=False), time.time()),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[sources] Cache save error: {e}")


def _ensure_cache_table() -> None:
    """Create sources_cache table if it doesn't exist. Migrates from old schema if needed."""
    try:
        import sqlite3
        from database import DB_PATH
        conn = sqlite3.connect(DB_PATH)
        # Check if country column exists (migration check)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(sources_cache)").fetchall()]
        if cols and 'country' not in cols:
            # Old schema without country - migrate by dropping and recreating
            # (cache data is just a performance optimization, safe to clear)
            conn.execute("DROP TABLE sources_cache")
            conn.commit()
            print("[sources] Migrated sources_cache table to include country column")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sources_cache (
                tmdb_id INTEGER,
                country TEXT NOT NULL DEFAULT 'US',
                sources_json TEXT NOT NULL,
                cached_at REAL NOT NULL,
                PRIMARY KEY (tmdb_id, country)
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[sources] Cache table init error: {e}")


# ---------------------------------------------------------------------------
# Perplexity fallback
# ---------------------------------------------------------------------------

PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")

MIRROR_WHITELIST = {
    "hdrezka": ["hdrezka.film", "hdrezka.me", "hdrezka.info", "hdrezka.club", "hdrezka-home.tv",
                "hdrezka.website", "rezka.ag", "hdrezka.my", "hdrezka.fans"],
    "kinogo": ["kinogo.my", "kinogo.pro", "kinogo.club", "kinogo.online", "kinogo.li", "kinogo.skin",
               "kinogo.ec", "kinogo.fm", "hd.kinogo.fm", "kinogo.run"],
    "filmix": ["filmix.my", "filmix.me", "filmix.biz", "filmix.ac", "filmix.fan", "filmix.day", "filmix.shop"],
    "lordfilm": ["lordfilm.fi", "lordfilm.top", "lordflim.org", "lord-film.net", "lordfilm.film",
                 "lordfilmplay.cc", "lordfilms-online.top", "lord-film-tv.ru", "lordfilms.world", "lord-film.ru"],
}

SCRAPER_ICONS = {
    "hdrezka": "https://hdrezka.film/favicon.ico",
    "kinogo": "https://kinogo.my/favicon.ico",
    "filmix": "https://filmix.my/favicon.ico",
    "lordfilm": "https://lordfilm.fi/favicon.ico",
}

SCRAPER_NAMES = {
    "hdrezka": "HDRezka",
    "kinogo": "Kinogo",
    "filmix": "Filmix",
    "lordfilm": "LordFilm",
}


async def _fetch_perplexity_fallback(
    client: httpx.AsyncClient,
    title_en: str,
    title_ru: Optional[str],
    year: int,
    missing_services: list,
) -> List[Dict]:
    """Ask Perplexity to find movie links for missing services."""
    if not missing_services or not PERPLEXITY_API_KEY:
        return []

    movie_name = f"{title_ru} ({title_en})" if title_ru and title_ru != title_en else (title_en or title_ru)

    prompt = (
        f"Мне нужны ПРЯМЫЕ ССЫЛКИ на страницу фильма/сериала \'{movie_name}\' {year} года на пиратских сайтах.\\n"
        f"Найди прямую ссылку на КАЖДЫЙ из этих сайтов: {', '.join(missing_services)}.\\n\\n"
        f"ВАЖНО:\\n"
        f"- Ссылка должна вести НАПРЯМУЮ на страницу именно этого фильма/сериала\\n"
        f"- НЕ давай ссылки на главную страницу или поиск\\n"
        f"- НЕ давай ссылки на другие фильмы\\n"
        f"- Если фильма нет на сайте — напиши \'не найдено\' для этого сайта\\n\\n"
        f"Формат ответа (строго):\\n"
        f"kinogo: https://kinogo.my/...\\n"
        f"filmix: https://filmix.my/...\\n"
        f"(и т.д. для каждого запрошенного сайта)"
    )

    try:
        r = await client.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "sonar-small",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 500,
            },
            timeout=15,
        )
        if r.status_code != 200:
            print(f"Perplexity returned status {r.status_code}: {r.text[:200]}")
            return []

        data = r.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        citations = data.get("citations", [])

        # Better URL extraction:
        # 1. First parse "service: url" lines from content
        # 2. Filter out category/pagination pages
        # 3. Only fall back to citations if no URL found in content

        url_pattern = re.compile(r'https?://[^\s\)\[\]\'"<>]+')

        def is_good_movie_url(url: str) -> bool:
            """Return True if URL looks like a specific movie page, not a category/pagination page."""
            # Strip citation markers like [1], [2] from end of url
            url = re.sub(r'\[\d+\]?$', '', url).rstrip(',.')
            # These segments indicate pagination or non-movie pages
            bad_segments = ['/pages/', '/page/', '/catalog/', '/search/', '/genre/',
                            '/gernes/', '/comments/', '/commentary/', '/t1/', '/t2/',
                            '/t3/', '/t4/', '/t5/']
            if any(seg in url for seg in bad_segments):
                return False
            # Must have a numeric ID (>=3 digits) somewhere in path indicating a specific item
            has_id = bool(re.search(r'/\d{3,}', url))
            return has_id

        # Step 1: parse "service: url" lines from content text
        service_url_map: Dict[str, str] = {}
        for line in content.split('\n'):
            line = line.strip()
            for service in missing_services:
                if service in service_url_map:
                    continue
                if line.lower().startswith(service + ':') or line.lower().startswith(service.capitalize() + ':'):
                    urls_in_line = url_pattern.findall(line)
                    if urls_in_line:
                        service_url_map[service] = urls_in_line[0]

        # Step 2: fallback — check citations for whitelisted domains
        for citation_url in citations:
            for service in missing_services:
                if service in service_url_map:
                    continue
                domains = MIRROR_WHITELIST.get(service, [])
                if any(domain in citation_url for domain in domains):
                    service_url_map[service] = citation_url

        # Step 3: build results, filtering out bad URLs
        results = []
        for service, url in service_url_map.items():
            domains = MIRROR_WHITELIST.get(service, [])
            if not any(domain in url for domain in domains):
                continue
            if not is_good_movie_url(url):
                print(f"[perplexity] Skipping bad URL for {service}: {url}")
                continue
            results.append({
                "source_name": SCRAPER_NAMES[service],
                "source_type": "pirate",
                "offer_type": "free",
                "url": url,
                "quality": "HD",
                "icon_url": SCRAPER_ICONS[service],
                "via_ai": True,
            })

        print(f"[perplexity] Found {len(results)} results for missing: {missing_services}")
        return results
    except Exception as e:
        print(f"Perplexity fallback error: {e}")
        return []


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def get_watch_sources(
    title: str,
    year: int,
    tmdb_id: int,
    title_ru: Optional[str] = None,
    country: str = "US",
    imdb_id: Optional[str] = None,
    media_type: str = "movie",
) -> Dict:
    """
    Fetch "Where to Watch" sources for a movie.
    Returns dict with keys: justwatch (list), pirate (list), cached (bool).
    Caches in DB forever.
    """
    _ensure_cache_table()

    # Check cache first
    cached = _load_cache(tmdb_id, country=country)
    if cached is not None:
        return {"sources": cached, "cached": True}

    # Parallel requests
    async with httpx.AsyncClient(verify=False, follow_redirects=True) as client:
        tasks = [
            _fetch_justwatch(client, title, title_ru, year, country=country),
            _fetch_hdrezka(client, title, title_ru, year, media_type=media_type),
            _fetch_kinogo(client, title, title_ru, year, media_type=media_type),
            _fetch_filmix(client, title, title_ru, year, media_type=media_type),
            _fetch_lordfilm(client, title, title_ru, year, media_type=media_type),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    jw_sources, hdrezka, kinogo, filmix, lordfilm = results

    # Determine which scrapers returned nothing
    missing_services = []
    if not isinstance(hdrezka, dict): missing_services.append("hdrezka")
    if not isinstance(kinogo, dict): missing_services.append("kinogo")
    if not isinstance(filmix, dict): missing_services.append("filmix")
    if not isinstance(lordfilm, dict): missing_services.append("lordfilm")

    # Perplexity fallback for missing scrapers
    perplexity_results: List[Dict] = []
    # Only call Perplexity when ALL 4 scrapers found nothing (cost saving)
    if len(missing_services) >= 3:
        async with httpx.AsyncClient(verify=False, follow_redirects=True) as px_client:
            perplexity_results = await _fetch_perplexity_fallback(
                px_client, title, title_ru, year, missing_services
            )

    # Build combined list
    all_sources: List[Dict] = []

    # JustWatch - list of offers
    if isinstance(jw_sources, list):
        all_sources.extend(jw_sources)

    # Pirate/info sources - single result each
    for src in [hdrezka, kinogo, filmix, lordfilm]:
        if src and isinstance(src, dict):
            all_sources.append(src)

    # Add Perplexity AI-found sources
    all_sources.extend(perplexity_results)

    if all_sources:  # H4 FIX: only cache if we found something
        _save_cache(tmdb_id, all_sources, country=country)

    return {"sources": all_sources, "cached": False}


async def fetch_sources(
    tmdb_id: int,
    title_en: str,
    title_ru: Optional[str] = None,
    year: int = 0,
    country: str = "US",
) -> Dict:
    """
    Fetch sources for a movie. Returns categorized dict.
    Signature compatible with test calls: fetch_sources(tmdb_id, title_en, title_ru, year, country=...)
    """
    result = await get_watch_sources(title_en, year, tmdb_id, title_ru=title_ru, country=country)
    sources = result.get("sources", [])

    jw = [s for s in sources if s.get("source_type") == "justwatch"]
    pirate = [s for s in sources if s.get("source_type") == "pirate"]  # exclude "info" (kinopoisk)

    flatrate = [s for s in jw if s.get("monetization") in ("FLATRATE", "FLATRATE_AND_BUY")]
    rent = [s for s in jw if s.get("monetization") == "RENT"]
    buy = [s for s in jw if s.get("monetization") == "BUY"]
    free = [s for s in jw if s.get("monetization") in ("FREE", "ADS")]

    return {
        "justwatch_flatrate": flatrate,
        "justwatch_rent": rent,
        "justwatch_buy": buy,
        "justwatch_free": free,
        "pirate": pirate,
        "all": sources,
        "cached": result.get("cached", False),
    }


# ---------------------------------------------------------------------------
# Legacy: keep get_all_sources for backwards compat with movie.html template
# ---------------------------------------------------------------------------

async def get_all_sources(tmdb_id: int, title: str, year: Optional[int] = None, title_ru: Optional[str] = None, media_type: str = "movie") -> dict:
    """
    Legacy wrapper - returns sources in old format for the Jinja template.
    Now also triggers live lookup and returns structured data.
    """
    result = await get_watch_sources(title, year or 0, tmdb_id, title_ru=title_ru, media_type=media_type)
    sources = result.get("sources", [])

    # Split by type for template
    jw = [s for s in sources if s["source_type"] == "justwatch"]
    pirate = [s for s in sources if s["source_type"] == "pirate"]  # exclude "info" (kinopoisk)

    # Group JustWatch by offer type
    flatrate = [s for s in jw if s.get("monetization") in ("FLATRATE", "FLATRATE_AND_BUY")]
    rent = [s for s in jw if s.get("monetization") == "RENT"]
    buy = [s for s in jw if s.get("monetization") == "BUY"]
    free = [s for s in jw if s.get("monetization") in ("FREE", "ADS")]

    return {
        "justwatch_flatrate": flatrate,
        "justwatch_rent": rent,
        "justwatch_buy": buy,
        "justwatch_free": free,
        "pirate": pirate,
        "all": sources,
        "cached": result.get("cached", False),
    }
