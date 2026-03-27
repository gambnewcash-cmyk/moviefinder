# Технический SEO Чеклист — moviefinders.net

## ✅ УЖЕ СДЕЛАНО (хорошее состояние)
- [x] HTTPS + HTTP→HTTPS редирект (301) ✅
- [x] sitemap-index.xml с 100k+ страниц ✅
- [x] robots.txt настроен правильно ✅
- [x] Canonical URLs на всех страницах ✅
- [x] hreflang ru/en разметка ✅
- [x] og:title, og:description, og:image ✅
- [x] JSON-LD Schema на страницах фильмов ✅
- [x] Мобильная версия (viewport, адаптивный дизайн) ✅
- [x] Google Search Console подключён ✅
- [x] Яндекс Вебмастер подключён ✅
- [x] Sitemap подан в оба поисковика ✅

## ⚠️ НУЖНО СДЕЛАТЬ

### При изменении title/description главной:
- [ ] Проверить что изменения отобразились через: curl -s "https://moviefinders.net/" | grep "<title>"
- [ ] Через 3-5 дней проверить в Search Console — "URL Inspection" → главная страница

### При создании новых страниц (/top, /films/2026 и т.д.):
- [ ] Добавить в sitemap-static.xml (или создать отдельный sitemap-pages.xml)
- [ ] Добавить ItemList или CollectionPage Schema
- [ ] Добавить canonical URL
- [ ] Проверить мобильную версию
- [ ] Добавить внутренние ссылки (с главной, из меню, из footer)

### Schema для коллекционных страниц:
```json
{
  "@context": "https://schema.org",
  "@type": "ItemList",
  "name": "Лучшие фильмы всех времён",
  "description": "ТОП-100 лучших фильмов по рейтингу",
  "url": "https://moviefinders.net/top",
  "numberOfItems": 100,
  "itemListElement": [
    {
      "@type": "ListItem",
      "position": 1,
      "url": "https://moviefinders.net/movie/238",
      "name": "Крёстный отец"
    }
  ]
}
```

### Schema для жанровых страниц:
```json
{
  "@context": "https://schema.org",
  "@type": "CollectionPage",
  "name": "Военные фильмы",
  "description": "Лучшие военные фильмы — смотреть онлайн бесплатно",
  "url": "https://moviefinders.net/genre/voennye"
}
```

## 🔍 ПРОВЕРКИ ПЕРЕД КАЖДЫМ ДЕПЛОЕМ

```bash
# Синтаксис Python
python3 -c "import ast; ast.parse(open('main.py').read()); print('OK')"

# Проверить title главной
curl -s "https://moviefinders.net/" | grep -i "<title>"

# Проверить новую страницу
curl -s -o /dev/null -w "%{http_code}" "https://moviefinders.net/top"
# Должен быть 200, не 404

# Проверить sitemap
curl -s "https://moviefinders.net/sitemap-static.xml" | grep "top\|2026\|vecher"
```

## 📊 СКОРОСТЬ ЗАГРУЗКИ (текущее состояние)
- Главная: ~2.2 сек (нужно оптимизировать до <1.5с)
- Страница фильма: ~0.9 сек ✅

### Как улучшить скорость главной:
1. Добавить кеширование TMDB запросов (Redis или in-memory)
2. Загружать секции lazy (популярное, топ рейтинг) через JS после DOMContentLoaded
3. Сжать изображения постеров через WebP
