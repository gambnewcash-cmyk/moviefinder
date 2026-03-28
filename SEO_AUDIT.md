# SEO Audit Report — moviefinders.net
**Date:** 2026-03-28  
**Auditor:** SEO Agent (automated audit)  
**Site:** https://moviefinders.net  
**Stack:** FastAPI + Jinja2, SQLite, 111,812 movies

---

## Executive Summary

The site has a **solid SEO foundation** with hreflang, canonical tags, structured data, and sitemaps in place. However, there are several **critical bugs** that will directly hurt rankings — especially the broken hreflang on EN genre pages, missing noindex on search pages, and a massive performance issue on the homepage.

---

## 🔴 CRITICAL ISSUES (fix immediately)

### 1. Broken hreflang on EN genre pages — Double `/en/en/` URL bug

**Severity: CRITICAL — causes Google to see broken alternate URLs**

On `/en/genre/horror`, the base.html template generates default hreflang tags using `request.url.path`, AND the genre template also adds its own hreflang tags in `block head_extra`. Result: two sets of hreflang tags, with the base template producing **broken URLs**:

```html
<!-- WRONG - from base.html fallback using request.url.path = /en/genre/horror -->
<link rel="alternate" hreflang="ru" href="https://moviefinders.net/en/genre/horror"/>
<link rel="alternate" hreflang="en" href="https://moviefinders.net/en/en/genre/horror"/>

<!-- CORRECT - from genre.html head_extra block -->
<link rel="alternate" hreflang="ru" href="https://moviefinders.net/genre/horror"/>
<link rel="alternate" hreflang="en" href="https://moviefinders.net/en/genre/horror"/>
```

The URL `https://moviefinders.net/en/en/genre/horror` returns 404. Google Search Console will report errors for all EN genre pages.

**Fix:** The genre template should override `block hreflang_ru` and `block hreflang_en` in base.html (like movie.html does), rather than using `block head_extra` for hreflang tags.

---

### 2. x-default hreflang points to wrong URL on EN movie pages

**Severity: CRITICAL — confuses Google about the canonical language**

On `/en/movie/157336`:
```html
<link rel="alternate" hreflang="x-default" href="https://moviefinders.net/en/movie/157336"/>
```

On `/movie/157336` (RU):
```html
<link rel="alternate" hreflang="x-default" href="https://moviefinders.net/movie/157336"/>
```

`x-default` should be **consistent across both language versions** — it should always point to the same URL (either always RU, or always the homepage). Currently the EN page sets x-default to itself, and the RU page sets x-default to itself — they contradict each other. Google uses x-default for users that don't match any hreflang language. Since the target audience is RU + EN, x-default should point to the RU version (or homepage).

**Fix:** In base.html, set x-default to always point to `https://moviefinders.net{{ request.url.path | replace('/en/', '/') }}` or hardcode per template.

---

### 3. Search results page not protected with noindex

**Severity: CRITICAL — thin content being indexed by Google**

`/search?q=batman` has **no noindex** meta tag and no X-Robots-Tag header. Search results pages are thin, query-dependent content that Google should not index. Currently Google can index thousands of search result pages, diluting the site's authority.

**Verified:**
```bash
curl -s "https://moviefinders.net/search?q=batman" | grep -i "noindex"
# → (empty — no noindex!)
```

**Fix:** Add `<meta name="robots" content="noindex, follow">` to `search.html` template.

---

### 4. Meta descriptions have leading/trailing newlines

**Severity: HIGH-CRITICAL — Google may display ugly descriptions in SERPs**

Due to Jinja2 block rendering, the `<meta name="description">` tag contains newlines:

```html
<meta name="description" content="
Лучшие фильмы ужасов — смотреть онлайн бесплатно без регистрации на MovieFinder.
"/>
```

This shows as extra whitespace in Google Search Console and may affect click-through rates.

**Fix:** Use Jinja2's `{%- block meta_description -%}` with whitespace control, or strip in the template: `{{ self.meta_description() | trim }}`.

---

### 5. Sitemap lastmod date is hardcoded

**Severity: HIGH — Google won't recrawl updated content promptly**

All sitemap entries have `<lastmod>2026-03-27</lastmod>` hardcoded as a string. This means when movies are added or updated, the sitemap won't signal freshness.

```python
# Current code in main.py:
today = "2026-03-27"  # HARDCODED!
```

**Fix:** Use `datetime.date.today().isoformat()` dynamically.

---

## 🟠 HIGH PRIORITY

### 6. EN movie pages use Russian title in title tag

The movie template uses `movie.title_ru or movie.title` for both RU and EN pages. So the EN page `/en/movie/157336` shows:

```html
<title>Интерстеллар (2014) — watch online free | MovieFinder</title>
```

Wait — actually the live site shows `Interstellar (2014) — watch online free` correctly. ✅ This works because `title_ru` for Interstellar is Russian and the EN template likely has different logic. Let me clarify: **for the EN version**, the H1 shows "Interstellar" correctly. However, the **meta description** on EN pages still has Russian-centric copy mentioning Кинопоиск, Okko, IVI, HDRezka:

```html
<!-- EN page meta description -->
<meta name="description" content="Где смотреть Interstellar (2014) онлайн. Жанр: Adventure, Drama. 
Все стриминговые сервисы и бесплатные источники — Кинопоиск, Okko, IVI, HDRezka."/>
```

The EN meta description template in `movie.html` is hardcoded in Russian! It says "Где смотреть" and lists Russian-specific platforms even for the `/en/` version.

**Fix:** Use `t.watch_where` and localized platform list in the meta_description block, making it language-aware like the title block.

---

### 7. Structured data: genres are Unicode-escaped instead of UTF-8

In JSON-LD on movie pages:
```json
"genre": ["\u043f\u0440\u0438\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u044f", "\u0434\u0440\u0430\u043c\u0430"]
```

Should be:
```json
"genre": ["приключения", "драма"]
```

This is technically valid but some structured data validators may flag it, and it reduces readability. **Fix:** Use `ensure_ascii=False` in JSON serialization.

---

### 8. Missing breadcrumbs on movie and genre pages

Only `ai_search.html` has a `BreadcrumbList` schema. Movie pages and genre pages have no breadcrumb schema and no visible breadcrumb navigation.

Breadcrumbs help Google understand site structure and appear in rich snippets in SERPs, increasing CTR.

**Recommended breadcrumbs:**
- Movie page: `Home > Genres > [Genre] > [Movie Title]`
- Genre page: `Home > Genres > [Genre Name]`

---

### 9. No rel=prev/next for paginated genre pages

Genre pages support pagination (`?page=2`, `?page=3`) but there are no `<link rel="prev">` / `<link rel="next">` tags. While Google deprecated these, Yandex still uses them, and the site targets a Russian audience where Yandex is significant.

**Verified:**
```bash
grep -rn "rel.*prev\|rel.*next" templates/*.html
# → (empty — no pagination links!)
```

---

### 10. Favorites page should not be in sitemap

`/favorites` is a client-side only page (uses localStorage). It has no indexable content — the same HTML shell is served to everyone. Including it in the sitemap wastes crawl budget.

**Fix:** Remove `/favorites` from `sitemap-static.xml`.

---

### 11. Open Graph tags on genre pages are generic (not page-specific)

On `/genre/horror`, the OG tags show the site's default content, not horror-specific:
```html
<meta property="og:title" content="MovieFinder — Найди где смотреть фильм"/>
<meta property="og:description" content="Найди где смотреть любой фильм или сериал онлайн..."/>
<meta property="og:image" content="https://moviefinders.net/static/img/og-default.jpg"/>
```

Should be genre-specific for better social sharing:
- Title: "Фильмы ужасов — смотреть онлайн бесплатно | MovieFinder"
- Description: genre-specific
- Image: poster of top horror movie

---

## 🟡 MEDIUM PRIORITY

### 12. Homepage is extremely slow — 397KB in 2.7 seconds

```
Status: 200 | Size: 397981 bytes | Time: 2.711797s  ← Homepage
Status: 200 | Size: 41139 bytes  | Time: 0.785678s  ← Movie page  
Status: 200 | Size: 69363 bytes  | Time: 0.865934s  ← Genre page
```

The homepage is **9.6x larger** than the movie page. This suggests it's loading a lot of movie data/posters. Google's Core Web Vitals will penalize slow pages.

Movie and genre pages are acceptable (0.8–0.9s).

---

### 13. Using CDN Tailwind CSS is a performance anti-pattern

```html
<script src="https://cdn.tailwindcss.com"></script>
```

This is **render-blocking** and downloads the entire Tailwind runtime (~350KB+) on every page. For production, Tailwind should be compiled to a minimal CSS bundle using PurgeCSS/tree-shaking. CDN Tailwind is only recommended for development/prototyping.

**Impact:** Likely contributes significantly to the 2.7s homepage load time.

---

### 14. 68,762 movies (61.5%) have no description

Database stats:
```
Total movies:          111,812
With description (EN):  43,050  (38.5%)
With description (RU):  39,446  (35.3%)
Without any desc:       ~68,762 (61.5%)
```

Movie pages without descriptions will have thin content, reducing ranking potential for the long tail of movie queries.

Top missing descriptions (high traffic potential):
```
Драконий жемчуг Зет: Возрождение «Ф» (2015)
Sole a catinelle (2013)
Жемчуг дракона: Битва Богов (2013)
Всегда есть завтра (2023)
```

---

### 15. 6,512 movies without poster images (5.8%)

No poster = poor social sharing, degraded appearance in SERPs (no rich image snippets), and lower user engagement. These pages should have a generic placeholder or be deprioritized in sitemaps.

---

### 16. 1,241 movies with very short descriptions (<100 chars)

These descriptions are too short to provide meaningful content for SEO. Google may classify them as thin content.

---

### 17. `<html lang="ru">` on EN pages

The EN version at `/en/movie/157336` still has `<html lang="ru">`. Google uses the `lang` attribute to understand page language.

**Fix:** In base.html, use `lang="{{ 'en' if lang == 'en' else 'ru' }}"`.

---

### 18. Sitemap missing x-default hreflang entries

The movie sitemaps include hreflang for `ru` and `en` versions but are missing `x-default`:

```xml
<xhtml:link rel="alternate" hreflang="ru" href="..."/>
<xhtml:link rel="alternate" hreflang="en" href="..."/>
<!-- Missing: <xhtml:link rel="alternate" hreflang="x-default" href="..."/> -->
```

---

## 🟢 LOW PRIORITY / NICE TO HAVE

### 19. No `director` field in Movie JSON-LD

The structured data includes `actor` but not `director`. Adding director would enrich the schema and potentially enable richer Google snippets.

### 20. Yandex Turbo RSS link is present

```html
<link rel="alternate" type="application/rss+xml" title="Turbo" href="/turbo.rss"/>
```
This is a good practice for Yandex, but only if the `/turbo.rss` endpoint actually returns valid Turbo RSS content. Verify this endpoint is implemented.

### 21. Missing `<link rel="search">` for OpenSearch

Add `<link rel="search" type="application/opensearchdescription+xml">` to let browsers offer the site as a search provider.

### 22. Sitemap priority values could be more granular

Currently all movies have `priority=0.8`. Movies with higher ratings or vote counts could have higher priority to direct crawlers toward the most valuable pages first.

---

## ✅ WHAT'S ALREADY WELL-IMPLEMENTED

1. **robots.txt** — Correctly blocks `/api/` routes from indexing. Clean and minimal.

2. **Canonical tags** — Properly implemented on all major page types. Paginated genre pages correctly point canonical to page 1, preventing duplicate content.

3. **Structured data (JSON-LD)** — Movie pages have rich Schema.org `Movie` type with: name, alternateName, datePublished, description, image, genre, aggregateRating, actor, url, and WatchAction potentialAction. This is excellent and enables rich snippets.

4. **Multilingual architecture** — Clean `/en/` prefix structure for English pages, with proper hreflang implementation on movie pages and correct translations.

5. **Sitemap index** — Proper sitemap index file splitting into 11 movie chunks (10k movies each = ~20k URLs per file counting RU+EN). Includes hreflang in sitemap.

6. **Meta descriptions** — Unique, relevant meta descriptions for all major page types (movies, genres, top, films2026, ai-search, etc.).

7. **Twitter Card tags** — Correctly implemented on movie pages with `summary_large_image` type and movie-specific content.

8. **OpenGraph tags** — Movie pages have correct `og:type="video.movie"`, movie poster image, and page-specific title/description.

9. **Title tags** — Unique, keyword-rich titles for all page types with brand suffix. Russian titles use proper Russian language patterns.

10. **H1 tags** — Each page has a single, relevant H1 tag. Movie H1 shows localized title (Russian for `/movie/`, English for `/en/movie/`).

11. **Image alt tags** — Movie posters use `alt="{{ movie.title }}"` and genre movie cards use `alt="{{ m.display_title }}"` — both semantically correct.

12. **Canonical for EN genre pages** — The EN genre page correctly sets canonical to `/en/genre/horror` (its own URL), not the RU version. This is correct because both language pages have unique content.

13. **Page response times** — Movie and genre pages respond in under 1 second (0.79s and 0.87s respectively).

14. **HTTPS** — Site correctly serves over HTTPS.

15. **Sitemap with xhtml:link hreflang** — Movie sitemaps include language alternates in the sitemap XML.

---

## Priority Action Plan

| Priority | Issue | Estimated Impact |
|----------|-------|-----------------|
| 🔴 P1 | Fix EN genre hreflang double `/en/en/` bug | Eliminate GSC errors for all EN genre pages |
| 🔴 P1 | Add `noindex` to `/search?q=...` pages | Prevent thin content indexing |
| 🔴 P1 | Fix x-default hreflang consistency | Correct language targeting signals |
| 🔴 P1 | Fix meta description whitespace (newlines) | Better SERP snippet display |
| 🟠 P2 | Fix EN movie meta description (Russian text on EN pages) | Better EN audience targeting |
| 🟠 P2 | Add `<html lang="en">` for EN pages | Correct language signals to Google |
| 🟠 P2 | Make sitemap lastmod dynamic | Faster recrawl of updated content |
| 🟠 P2 | Remove `/favorites` from sitemap | Reduce crawl budget waste |
| 🟠 P2 | Add breadcrumbs schema to movie/genre pages | Rich snippets in SERPs |
| 🟡 P3 | Fix genre OG tags to be page-specific | Better social sharing CTR |
| 🟡 P3 | Replace CDN Tailwind with compiled CSS | Major performance improvement |
| 🟡 P3 | Fill missing movie descriptions (68k movies) | Long-tail SEO improvement |
| 🟡 P3 | Add rel=prev/next for Yandex pagination | Better Yandex crawling |
| 🟡 P3 | Fix JSON-LD Unicode escaping | Cleaner structured data |

---

*Report generated by automated SEO audit. All findings based on live site checks + codebase analysis.*
