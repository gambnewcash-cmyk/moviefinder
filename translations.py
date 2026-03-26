"""
Bilingual translations for MovieFinder (EN / RU)
"""

TRANSLATIONS = {
    "en": {
        # Nav
        "search": "Search",
        "trending": "Trending",
        "search_placeholder_nav": "Search movies, shows…",

        # Hero
        "hero_title": "Find where to",
        "hero_title_accent": "watch anything",
        "hero_subtitle": "Streaming services, free sites & more — all in one place.",
        "regular_search_btn": "🔍 Regular",
        "smart_search_btn": "🤖 Smart Search",
        "search_placeholder_main": "Search movies, TV shows…",
        "search_btn": "Search",
        "smart_placeholder": 'Describe what you want…\ne.g. "horror movie from 2020 with a monster"\nor "comedy with Will Smith from the 90s"',
        "smart_search_label": "Smart Search",
        "search_submit": "Find",

        # Sections
        "trending_today": "Trending Today",
        "top_rated": "Top Rated",
        "now_playing": "Now in Theaters",
        "upcoming": "Coming Soon",
        "trending_searches": "Popular Searches",
        "view_all": "View all",

        # Movie card / page
        "where_to_watch": "Where to Watch",
        "free_online": "Free Online",
        "premium": "Premium",
        "trailer": "Watch Trailer",
        "similar": "Similar Movies",
        "cast": "Cast",
        "rating": "Rating",
        "year": "Year",
        "genre": "Genre",
        "runtime": "Runtime",
        "min": "min",
        "back": "← Back",
        "find_btn": "Find",
        "no_sources": "No streaming sources found",
        "loading": "Loading…",
        "find_sources": "Find Sources",
        "sources_loading": "Searching all sources…",
        "watch_free": "Watch Free",
        "watch_now": "Watch Now",

        # Search page
        "search_results": "Search Results",
        "results_for": "Results for",
        "no_results": "No results found",
        "try_different": "Try a different search query",
        "smart_search_title": "Smart Search",
        "smart_found": "Found",
        "smart_movies": "movies",
        "search_again": "Search Again",

        # Footer
        "footer_desc": "Find where to watch any movie or TV show — streaming & more.",
        "footer_api": "Movie data provided by TMDB. This product uses the TMDB API but is not endorsed or certified by TMDB.",

        # Language switcher
        "lang_en": "🇬🇧 EN",
        "lang_ru": "🇷🇺 RU",
    },

    "ru": {
        # Nav
        "search": "Поиск",
        "trending": "Популярное",
        "search_placeholder_nav": "Поиск фильмов, сериалов…",

        # Hero
        "hero_title": "Найди где",
        "hero_title_accent": "смотреть всё",
        "hero_subtitle": "Стриминги, бесплатные сайты и многое другое — в одном месте.",
        "regular_search_btn": "🔍 Обычный",
        "smart_search_btn": "🤖 Умный поиск",
        "search_placeholder_main": "Поиск фильмов, сериалов…",
        "search_btn": "Найти",
        "smart_placeholder": 'Опишите что ищете…\nнапр. "ужастик 2020 года с монстром"\nили "комедия с Уиллом Смитом из 90-х"',
        "smart_search_label": "Умный поиск",
        "search_submit": "Найти",

        # Sections
        "trending_today": "Сейчас популярно",
        "top_rated": "Топ по рейтингу",
        "now_playing": "Сейчас в кино",
        "upcoming": "Скоро онлайн",
        "trending_searches": "Популярные запросы",
        "view_all": "Смотреть все",

        # Movie card / page
        "where_to_watch": "Где посмотреть",
        "free_online": "Бесплатно онлайн",
        "premium": "Премиум",
        "trailer": "Смотреть трейлер",
        "similar": "Похожие фильмы",
        "cast": "В ролях",
        "rating": "Рейтинг",
        "year": "Год",
        "genre": "Жанр",
        "runtime": "Длительность",
        "min": "мин",
        "back": "← Назад",
        "find_btn": "Найти",
        "no_sources": "Источники просмотра не найдены",
        "loading": "Загрузка…",
        "find_sources": "Найти источники",
        "sources_loading": "Ищем все источники…",
        "watch_free": "Смотреть бесплатно",
        "watch_now": "Смотреть",

        # Search page
        "search_results": "Результаты поиска",
        "results_for": "Результаты по запросу",
        "no_results": "Ничего не найдено",
        "try_different": "Попробуйте другой запрос",
        "smart_search_title": "Умный поиск",
        "smart_found": "Найдено",
        "smart_movies": "фильмов",
        "search_again": "Искать ещё",

        # Footer
        "footer_desc": "Найди где смотреть любой фильм или сериал — стриминги и не только.",
        "footer_api": "Данные о фильмах предоставлены TMDB. Этот продукт использует API TMDB, но не одобрен и не сертифицирован TMDB.",

        # Language switcher
        "lang_en": "🇬🇧 EN",
        "lang_ru": "🇷🇺 RU",
    }
}


def get_translations(lang: str) -> dict:
    """Return translation dict for given language code (en or ru)."""
    return TRANSLATIONS.get(lang, TRANSLATIONS["en"])


def detect_language(accept_language: str) -> str:
    """Detect language from Accept-Language header. Returns 'ru' or 'en'."""
    if not accept_language:
        return "en"
    # Parse primary languages
    parts = accept_language.lower().replace(" ", "").split(",")
    for part in parts:
        lang = part.split(";")[0].strip()
        if lang.startswith("ru") or lang.startswith("uk"):
            return "ru"
    return "en"
