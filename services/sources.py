import httpx
from urllib.parse import quote_plus
from typing import List, Dict, Optional

JUSTWATCH_API = "https://apis.justwatch.com/content/titles/movie/{tmdb_id}/locale/ru_RU"

PIRATE_SOURCES = [
    {
        "source_name": "HDRezka",
        "source_type": "pirate",
        "base_search": "https://hdrezka.ag/search/?do=search&subaction=search&q={query}",
        "quality": "1080p",
        "icon": "🎬"
    },
    {
        "source_name": "Kinogo",
        "source_type": "pirate",
        "base_search": "https://kinogo.lat/?s={query}",
        "quality": "1080p",
        "icon": "🎥"
    },
    {
        "source_name": "Filmix",
        "source_type": "pirate",
        "base_search": "https://filmix.ac/search/{query}",
        "quality": "720p",
        "icon": "📽️"
    },
]

PREMIUM_PROVIDERS = {
    8: {"name": "Netflix", "color": "#e50914", "icon": "N"},
    9: {"name": "Amazon Prime", "color": "#00a8e0", "icon": "P"},
    337: {"name": "Disney+", "color": "#113ccf", "icon": "D+"},
    384: {"name": "HBO Max", "color": "#5822b4", "icon": "HBO"},
    2: {"name": "Apple TV+", "color": "#555", "icon": ""},
    531: {"name": "Paramount+", "color": "#0064ff", "icon": "P+"},
    283: {"name": "Kinopoisk", "color": "#f60", "icon": "KP"},
}

async def get_pirate_search_links(title: str, year: Optional[int] = None) -> List[dict]:
    query = f"{title} {year}" if year else title
    encoded = quote_plus(query)
    sources = []
    for s in PIRATE_SOURCES:
        sources.append({
            "source_name": s["source_name"],
            "source_type": s["source_type"],
            "url": s["base_search"].format(query=encoded),
            "quality": s["quality"],
            "icon": s["icon"],
            "is_search": True,
        })
    return sources

async def get_justwatch_sources(tmdb_id: int, title: str) -> List[dict]:
    sources = []
    try:
        # Try JustWatch via TMDB ID lookup
        search_url = f"https://apis.justwatch.com/content/titles/en_US/popular?body={{\"query\":\"{title}\"}}"
        # Simplified - construct JustWatch search URL instead
        encoded_title = quote_plus(title)
        sources.append({
            "source_name": "JustWatch",
            "source_type": "premium",
            "url": f"https://www.justwatch.com/us/search?q={encoded_title}",
            "quality": "HD",
            "icon": "JW",
            "is_search": True,
        })
    except Exception as e:
        print(f"JustWatch error: {e}")
    return sources

async def get_all_sources(tmdb_id: int, title: str, year: Optional[int] = None) -> dict:
    pirate = await get_pirate_search_links(title, year)
    justwatch = await get_justwatch_sources(tmdb_id, title)
    
    # Build streaming platform links
    streaming = [
        {
            "source_name": "Netflix",
            "source_type": "premium",
            "url": f"https://www.netflix.com/search?q={quote_plus(title)}",
            "quality": "4K",
            "color": "#e50914",
            "icon": "N",
        },
        {
            "source_name": "Disney+",
            "source_type": "premium",
            "url": f"https://www.disneyplus.com/search/{quote_plus(title)}",
            "quality": "4K",
            "color": "#113ccf",
            "icon": "D+",
        },
        {
            "source_name": "HBO Max",
            "source_type": "premium",
            "url": f"https://www.max.com/search?q={quote_plus(title)}",
            "quality": "4K",
            "color": "#5822b4",
            "icon": "HBO",
        },
        {
            "source_name": "Amazon Prime",
            "source_type": "premium",
            "url": f"https://www.amazon.com/s?k={quote_plus(title)}&i=instant-video",
            "quality": "4K",
            "color": "#00a8e0",
            "icon": "P",
        },
        {
            "source_name": "Kinopoisk",
            "source_type": "premium",
            "url": f"https://www.kinopoisk.ru/index.php?kp_query={quote_plus(title)}",
            "quality": "1080p",
            "color": "#ff6600",
            "icon": "KP",
        },
    ]
    
    return {
        "streaming": streaming,
        "pirate": pirate,
        "justwatch": justwatch,
    }
