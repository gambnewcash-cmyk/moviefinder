#!/usr/bin/env python3
"""
Крейк — генератор редакционных отзывов для moviefinders.net
Пишет тексты сам, без внешних API.
"""

import sqlite3
import psycopg2
import time
import sys
import re

# ─── DB ───────────────────────────────────────────────────────
pg = psycopg2.connect("postgresql://postgres:OLIBHomUThkXFlbrgpJWyeZblHZdJQvj@gondola.proxy.rlwy.net:54122/railway")
pg.autocommit = False
cur = pg.cursor()

cur.execute("SELECT tmdb_id FROM ai_reviews WHERE lang='ru'")
done_ru = set(r[0] for r in cur.fetchall())
cur.execute("SELECT tmdb_id FROM ai_reviews WHERE lang='en'")
done_en = set(r[0] for r in cur.fetchall())
done = done_ru & done_en  # оба языка уже есть

db = sqlite3.connect("/home/moneyfast/projects/moviefinder/data/moviefinder.db")
movies = db.execute("""
    SELECT tmdb_id, title_ru, title, year, genre, description_ru, description
    FROM movies
    WHERE (description IS NOT NULL AND description != '') OR (description_ru IS NOT NULL AND description_ru != '')
    ORDER BY CASE WHEN year=2026 THEN 0 WHEN year=2025 THEN 1 WHEN rating>=7.0 THEN 2 ELSE 3 END,
             year DESC, rating DESC
""").fetchall()

todo = [m for m in movies if m[0] not in done]
print(f"Todo: {len(todo)} films (done_ru={len(done_ru)}, done_en={len(done_en)})")


# ─── ЖАНРОВЫЕ МАППИНГИ ────────────────────────────────────────
GENRE_TONE_RU = {
    "Horror": ("напряжённым", "нагнетает тревогу", "любителей хоррора"),
    "Comedy": ("лёгким и ироничным", "умеет рассмешить без натуги", "тех кто хочет просто отдохнуть"),
    "Drama": ("глубоким и эмоциональным", "работает с тонкими человеческими состояниями", "тех кто готов к сильным эмоциям"),
    "Action": ("динамичным и напряжённым", "держит в тонусе от начала до конца", "поклонников энергичного кино"),
    "Thriller": ("сжатым и нервным", "строит саспенс методично", "тех кто любит когда кино держит в напряжении"),
    "Romance": ("мягким и тёплым", "делает ставку на чувства", "тех кто ищет историю о любви"),
    "Science Fiction": ("футуристичным и концептуальным", "ставит большие вопросы через фантастическое допущение", "фанатов научной фантастики"),
    "Fantasy": ("сказочным и атмосферным", "строит целый мир с нуля", "любителей жанрового фэнтези"),
    "Animation": ("ярким и живым", "работает сразу на нескольких уровнях восприятия", "семей и любителей анимации"),
    "Documentary": ("честным и прямым", "документирует реальность без прикрас", "тех кто ценит правду больше вымысла"),
    "Crime": ("жёстким и циничным", "не делает скидок на мораль", "поклонников криминального жанра"),
    "Western": ("суровым и атмосферным", "дышит пылью прерий и усталостью людей", "любителей классического вестерна"),
    "History": ("масштабным и обстоятельным", "восстанавливает эпоху с вниманием к деталям", "тех кто интересуется историей"),
    "Music": ("ритмичным и эмоциональным", "живёт в музыке и вокруг неё", "тех кто чувствует кино через звук"),
    "Family": ("добрым и светлым", "рассчитан на совместный просмотр", "всей семьи"),
    "Mystery": ("загадочным и неспешным", "умеет держать зрителя в неведении до конца", "любителей детективной атмосферы"),
    "War": ("тяжёлым и бескомпромиссным", "не героизирует войну", "тех кто готов к честному разговору о цене конфликта"),
    "Adventure": ("захватывающим и широким", "разворачивается с размахом", "любителей приключенческого жанра"),
}

GENRE_TONE_EN = {
    "Horror": ("tense and unsettling", "builds dread with precision", "horror fans"),
    "Comedy": ("light and sharp", "earns its laughs honestly", "those who just want to unwind"),
    "Drama": ("deep and emotionally demanding", "works with nuanced human states", "those ready for strong feelings"),
    "Action": ("kinetic and high-energy", "keeps the pulse elevated throughout", "fans of visceral cinema"),
    "Thriller": ("tight and nerve-wracking", "constructs suspense methodically", "those who like films that keep them on edge"),
    "Romance": ("warm and tender", "bets everything on emotion", "those looking for a love story"),
    "Science Fiction": ("futuristic and conceptual", "asks big questions through speculative premises", "sci-fi enthusiasts"),
    "Fantasy": ("immersive and otherworldly", "builds an entire world from scratch", "fantasy genre fans"),
    "Animation": ("vibrant and layered", "operates on multiple levels of perception", "families and animation lovers"),
    "Documentary": ("honest and direct", "documents reality without softening the edges", "those who value truth over fiction"),
    "Crime": ("gritty and cynical", "makes no moral concessions", "fans of crime cinema"),
    "Western": ("rugged and atmospheric", "breathes dust and human exhaustion", "classic Western lovers"),
    "History": ("expansive and thorough", "reconstructs an era with careful attention", "those interested in history"),
    "Music": ("rhythmic and emotionally alive", "lives in and around music", "those who feel cinema through sound"),
    "Family": ("warm and wholesome", "designed for shared viewing", "the whole family"),
    "Mystery": ("enigmatic and unhurried", "knows how to keep the audience guessing", "mystery atmosphere enthusiasts"),
    "War": ("heavy and uncompromising", "doesn't glorify combat", "those ready for an honest conversation about conflict"),
    "Adventure": ("sweeping and expansive", "unfolds with genuine scale", "adventure genre fans"),
}


def get_genre_info(genre_str, lang):
    if not genre_str:
        return ("самобытным", "находит свой голос", "широкой аудитории") if lang == "ru" else ("distinctive", "finds its own voice", "a wide audience")
    table = GENRE_TONE_RU if lang == "ru" else GENRE_TONE_EN
    for g, val in table.items():
        if g.lower() in (genre_str or "").lower():
            return val
    if lang == "ru":
        return ("самобытным", "идёт своей дорогой", "широкой аудитории")
    return ("distinctive", "charts its own course", "a wide audience")


def classify_film(title_ru, title, year, genre, desc_ru, desc):
    """Определяем базовый 'профиль' фильма для генерации"""
    g = (genre or "").lower()
    desc_text = (desc_ru or desc or "").lower()
    
    is_horror = "horror" in g
    is_comedy = "comedy" in g
    is_drama = "drama" in g
    is_action = "action" in g
    is_thriller = "thriller" in g
    is_scifi = "science fiction" in g or "sci-fi" in g
    is_animation = "animation" in g or "animated" in g
    is_documentary = "documentary" in g
    is_western = "western" in g
    is_crime = "crime" in g
    is_family = "family" in g
    is_romance = "romance" in g
    is_war = "war" in g
    is_history = "history" in g or "historical" in g
    is_fantasy = "fantasy" in g
    is_adventure = "adventure" in g
    
    recent = year and year >= 2023
    old = year and year < 2000
    
    return {
        "horror": is_horror, "comedy": is_comedy, "drama": is_drama,
        "action": is_action, "thriller": is_thriller, "scifi": is_scifi,
        "animation": is_animation, "documentary": is_documentary,
        "western": is_western, "crime": is_crime, "family": is_family,
        "romance": is_romance, "war": is_war, "history": is_history,
        "fantasy": is_fantasy, "adventure": is_adventure,
        "recent": recent, "old": old, "year": year
    }


# ─── ШАБЛОНЫ ОТЗЫВОВ (RU) ────────────────────────────────────
# Множество вариантов чтобы не повторяться

RU_P1_HORROR = [
    "Режиссёр выстраивает напряжение не через шок, а через ощущение — когда зритель уже понимает что что-то не так, задолго до того как это становится очевидным. Атмосфера здесь важнее любого поворота сюжета.",
    "Фильм работает в жанре хоррора честно: не торопится пугать, даёт пространству дышать тревогой. Это кино про ощущение неправильности — медленное, но неотступное.",
    "Здесь страх живёт в деталях — в кадре, в тишине, в паузах между репликами. Режиссёр умеет держать зрителя в состоянии готовности, когда мышцы сжимаются сами.",
    "Кино нагнетает тревогу методично, слой за слоем. Жанровые инструменты используются умело — без дешёвых скримеров, с опорой на настоящее беспокойство.",
]

RU_P2_HORROR = [
    "Смотреть стоит тем кто устал от предсказуемых хорроров. Здесь есть характер и внутренняя логика. Если ждёшь быстрого адреналина — лучше выбрать что-то другое.",
    "Это не фильм для слабонервных и не фильм для искушённых зрителей которые ничего не боятся. Он существует где-то посередине — давит психологически, а не физически.",
    "Фильм не спешит. Это его главная сила и главный риск: если ты не готов к медленному ужасу — он тебя утомит. Если готов — не отпустит.",
    "Стоит смотреть ради атмосферы и работы с пространством. Концовка может разочаровать — жанр есть жанр. Но путь к ней сделан хорошо.",
]

RU_P3_HORROR = [
    "Подойдёт ценителям атмосферного хоррора, которым важна тревога а не только страх.",
    "Для тех кто любит кино которое работает с ощущением, а не со сценарными твистами.",
    "Идеально для поклонников психологического жанра. Любителям слэшеров — не сюда.",
    "Для зрителей которым нужна напряжённость, а не просто набор пугающих сцен.",
]

RU_ATM_HORROR = [
    "🕯️ Атмосфера для просмотра: Поздно ночью, в одиночестве или с кем-то кому тоже не страшно признаться что страшно. Свет выключить.",
    "🕯️ Атмосфера для просмотра: Ночью, когда за окном темно. Лучше вдвоём — не потому что страшно, а потому что потом есть о чём поговорить.",
    "🕯️ Атмосфера для просмотра: Тёмным вечером, когда дома тихо. Наушники — обязательно, звук здесь половина фильма.",
    "🕯️ Атмосфера для просмотра: Поздним вечером вдвоём. Заварить чай, убрать телефон, не включать свет.",
]

RU_P1_COMEDY = [
    "Фильм не пытается быть смешнее чем есть — и в этом его честность. Юмор здесь вырастает из ситуаций и характеров, а не из заготовленных шуток.",
    "Режиссёр не давит на педаль юмора — позволяет сцене развиваться в своём ритме. Комедийный эффект возникает естественно, без подсказок для зрителя.",
    "Кино работает в лёгком регистре — но не поверхностно. За каждой шуткой стоит наблюдение за людьми, а не просто желание рассмешить.",
    "Это комедия которая знает меру. Не лезет в гротеск когда хватает и иронии, не требует от зрителя принимать происходящее слишком серьёзно.",
]

RU_P2_COMEDY = [
    "Смотреть стоит ради хорошего настроения и пары по-настоящему смешных моментов. Глубины не обещает — но и не притворяется что она есть.",
    "Фильм делает ровно то для чего создан: даёт передышку. Без претензий на большее, зато честно и без провисаний.",
    "Если ты ищешь лёгкое кино на вечер — это оно. Если ищешь что-то что изменит взгляд на жизнь — смотри дальше.",
    "Смотрится легко, оставляет хорошее послевкусие. Не все шутки работают одинаково — но общий тон держится.",
]

RU_P3_COMEDY = [
    "Подойдёт тем кто хочет просто отдохнуть. Не требует ничего — только время и готовность улыбнуться.",
    "Для просмотра с теми кому нужна разрядка после тяжёлого дня. Не для тех кто ищет глубину.",
    "Хороший выбор для компании. В одиночестве тоже работает, но вместе смешнее.",
    "Для тех кто умеет ценить простое удовольствие без лишних усилий.",
]

RU_ATM_COMEDY = [
    "🕯️ Атмосфера для просмотра: В пятницу вечером с едой и компанией. Не обязательно смотреть внимательно — фоном тоже зайдёт.",
    "🕯️ Атмосфера для просмотра: Выходной день, диван, что-нибудь перекусить. Отключить голову и просто наслаждаться.",
    "🕯️ Атмосфера для просмотра: С друзьями или с партнёром когда не хочется ничего сложного. Хорошее настроение гарантировано.",
    "🕯️ Атмосфера для просмотра: После долгого дня, когда нужна простая радость. Лучше вдвоём — смеяться веселее.",
]

RU_P1_DRAMA = [
    "Кино не торопится. Оно доверяет зрителю — даёт время вжиться в характеры, понять что происходит на самом деле. Режиссура здесь служит актёрам, а не подавляет их.",
    "Это кино которое работает тихо. Без громких событий, без кризисных поворотов — только люди и то как они проживают то что с ними происходит.",
    "Режиссёр ставит на детали: жест, взгляд, пауза. В хорошей драме именно это и говорит больше всего — и здесь этот принцип выдержан.",
    "Фильм живёт в ритме повседневности — и в этом его сила. Никакого кино про «большие события», только про то как люди живут, ошибаются и понимают себя.",
]

RU_P2_DRAMA = [
    "Смотреть стоит ради актёрской работы и искренности. Если ждёшь событий — их немного. Если ждёшь ощущения — будет.",
    "Это кино которое не развлекает — оно говорит. Если ты к этому готов, оно оставит след. Если нет — покажется медленным.",
    "Сильные стороны: атмосфера, актёры, точность в деталях. Слабые: темп не для всех, концовка может показаться незавершённой.",
    "Стоит смотреть если у тебя есть настроение на серьёзное кино. Это не фоновый просмотр — оно требует внимания.",
]

RU_P3_DRAMA = [
    "Подойдёт зрителям которые умеют смотреть медленное кино и ценят человеческое в историях.",
    "Для тех кто ищет кино про людей, а не про события. Если тебе нужен экшн — не сюда.",
    "Хороший выбор для тех кто ценит тонкую режиссуру и честную актёрскую игру.",
    "Для людей которые смотрят кино ради ощущений, а не ради развлечения.",
]

RU_ATM_DRAMA = [
    "🕯️ Атмосфера для просмотра: Вечером, когда спокойно на душе. С тем с кем можно помолчать после. Вино или чай.",
    "🕯️ Атмосфера для просмотра: В тишине, вечером. Лучше одному или с тем кто умеет смотреть кино серьёзно.",
    "🕯️ Атмосфера для просмотра: Когда есть настроение на разговор о жизни. С партнёром или другом, которому можно доверять.",
    "🕯️ Атмосфера для просмотра: Не спеша, вечером в будний день. Телефон убрать, дать фильму работать.",
]

RU_P1_ACTION = [
    "Фильм не делает вид что он про что-то кроме действия — и это честная позиция. Режиссёр строит сцены с пониманием пространства, темпа и ритма.",
    "Экшн здесь не для галочки — он продуманный, с внутренней логикой. Постановка боёв и погонь говорит о том что режиссёр знает жанр изнутри.",
    "Динамика выдержана от первой до последней сцены. Режиссёр умеет дать зрителю передышку не теряя напряжения — и это ценно в жанре.",
    "Кино знает свои сильные стороны и играет на них честно. Визуальный стиль и темп согласованы, не возникает ощущения что смотришь разные фильмы склеенные вместе.",
]

RU_P2_ACTION = [
    "Смотреть стоит ради крепко сделанных сцен и общей энергии. Сюжет не претендует на откровения — зато не мешает.",
    "Если ты любишь жанр — это добротный образец. Если ты равнодушен к экшну — ничего сверхъестественного здесь нет.",
    "Хорошо сделанный аттракцион. Не претендует на глубину, зато делает своё дело честно и без скуки.",
    "Смотрится на одном дыхании. Логика сюжета вторична — главное здесь движение и ритм, и с этим всё в порядке.",
]

RU_P3_ACTION = [
    "Для поклонников жанра — обязательно. Для тех кто ищет что-то глубже — возможно, не то кино.",
    "Подойдёт тем кто хочет переключиться и получить дозу адреналина без лишних вопросов.",
    "Хороший выбор для просмотра с компанией когда не хочется думать, а хочется наблюдать.",
    "Для тех кто ценит крепко сделанный жанровый фильм без лишних претензий.",
]

RU_ATM_ACTION = [
    "🕯️ Атмосфера для просмотра: В компании с попкорном. Громко, с большим экраном — именно для этого снималось.",
    "🕯️ Атмосфера для просмотра: Вечером с друзьями, громкость на максимум. Обсуждать во время просмотра не возбраняется.",
    "🕯️ Атмосфера для просмотра: С едой и хорошим настроением. Идеально для пятницы или выходного вечера в компании.",
    "🕯️ Атмосфера для просмотра: Большой экран, нормальный звук. Это кино которое должно звучать и занимать пространство.",
]

RU_P1_THRILLER = [
    "Режиссёр строит напряжение экономно — не тратит его попусту, держит в резерве. Фильм прижимает к спинке кресла методично, без спешки.",
    "Это триллер который уважает зрителя: не объясняет всё и не торопит события. Напряжение здесь создаётся атмосферой, а не механическими поворотами.",
    "Кино работает с тревогой как с инструментом: применяет точно, в нужных местах. Не даёт расслабиться, но и не перегибает.",
    "Жанровый триллер сделанный с умом. Режиссёр понимает разницу между саспенсом и шоком — и выбирает первое.",
]

RU_P2_THRILLER = [
    "Смотреть стоит ради атмосферы и структуры. Финал может не всем понравиться — но дорога к нему стоит потраченного времени.",
    "Держит напряжение ровно до тех пор пока это нужно. Потом может немного просесть — но общий уровень хорош.",
    "Хороший выбор если ты устал от предсказуемых жанровых формул. Здесь чувствуется что создатели думали о чём снимают.",
    "Триллер который работает и после первого просмотра: некоторые вещи замечаешь только потом. Стоит пересмотреть.",
]

RU_P3_THRILLER = [
    "Для любителей саспенса и психологического напряжения. Если нужен экшн — это другое кино.",
    "Подойдёт тем кто любит кино которое держит в состоянии неопределённости до конца.",
    "Для зрителей которые ценят интеллигентный жанр без упрощений.",
    "Хороший выбор для тех кто ищет напряжённое кино без лишнего шума.",
]

RU_ATM_THRILLER = [
    "🕯️ Атмосфера для просмотра: Вечером с тем кто выдерживает напряжение. Не паузить, не отвлекаться на телефон.",
    "🕯️ Атмосфера для просмотра: Тёмным вечером, в тишине. Лучше вдвоём — потом будет о чём поговорить.",
    "🕯️ Атмосфера для просмотра: Поздно ночью когда можно полностью отдаться фильму. Не фоном — только целиком.",
    "🕯️ Атмосфера для просмотра: В одиночестве или с партнёром. Тихо, темно. Телефон на беззвучном.",
]

RU_P1_SCIFI = [
    "Научная фантастика здесь — не декорация а язык. Режиссёр использует фантастическое допущение чтобы говорить о вещах которые иначе не скажешь.",
    "Фильм строит мир методично, без спешки — давая зрителю время привыкнуть к правилам реальности которую он описывает. Это ценно в жанре где часто всё объясняют в лоб.",
    "Визуальный язык и концептуальная основа работают в одну сторону. Это не просто кино с космическими кораблями — здесь есть идея которую стоит проследить.",
    "Режиссёр не боится сложных вопросов и не торопится с ответами. Фантастика как зеркало настоящего — именно это здесь и происходит.",
]

RU_P2_SCIFI = [
    "Смотреть стоит ради концепции и того как она развёрнута. Темп медленный — но он оправдан. Зрителям которым нужна постоянная динамика — будет тяжело.",
    "Хорошая научная фантастика всегда немного сложнее чем кажется при первом просмотре. Этот фильм именно такой — награждает внимательных.",
    "Если ты устал от блокбастеров где фантастика — просто фон для взрывов, здесь найдёшь другое. Кино про идеи, а не про спецэффекты.",
    "Не без слабых мест — но задача поставлена серьёзно и выполнена с уважением к зрителю.",
]

RU_P3_SCIFI = [
    "Для поклонников жанровой фантастики которым важна идея а не только зрелище.",
    "Подойдёт тем кто любит думать о кино после — здесь есть над чем.",
    "Хороший выбор для любителей концептуальной фантастики в духе Дика или Лема.",
    "Для зрителей которые готовы к медленному разворачиванию идеи.",
]

RU_ATM_SCIFI = [
    "🕯️ Атмосфера для просмотра: Ночью, когда голова свободна. С кем-то кто любит порассуждать о больших темах после просмотра.",
    "🕯️ Атмосфера для просмотра: В тишине, не торопясь. Это кино требует присутствия а не фонового внимания.",
    "🕯️ Атмосфера для просмотра: Вечером вдвоём, с чем-нибудь тёплым. После — долгий разговор.",
    "🕯️ Атмосфера для просмотра: Одному или с тем кто умеет смотреть кино молча и думать.",
]

RU_P1_DOCUMENTARY = [
    "Документальное кино в лучшем своём виде не делает выводы за зрителя — оно показывает. Этот фильм именно такой: честный и без лишних комментариев.",
    "Режиссёр доверяет материалу. Не навязывает интерпретацию — даёт событиям и людям говорить самим за себя. Это требует смелости.",
    "Документалистика как жанр требует дисциплины: не украшать, не упрощать. Здесь это правило выдержано.",
    "Фильм смотрит на своего героя или тему без сентиментальности — и это делает его честнее многих игровых картин.",
]

RU_P2_DOCUMENTARY = [
    "Смотреть стоит ради возможности узнать что-то настоящее. Не всегда удобное — но настоящее.",
    "Если тебе важна правда больше чем зрелище — это твоё кино. Если нет — оно может показаться скучным.",
    "Хорошая документалистика меняет что-то в голове. Этот фильм — не исключение. Стоит посмотреть хотя бы раз.",
    "Информативно, честно, без прикрас. Именно за это и ценят хороший документальный фильм.",
]

RU_P3_DOCUMENTARY = [
    "Для тех кому интересна тема. И для тех кому казалось что она неинтересна — иногда документалистика открывает неожиданное.",
    "Подойдёт любопытным. Если ты смотришь только игровое кино — попробуй, это другой опыт.",
    "Для людей которые хотят понять мир лучше, а не просто развлечься.",
    "Хороший выбор для просмотра одному, когда есть время подумать.",
]

RU_ATM_DOCUMENTARY = [
    "🕯️ Атмосфера для просмотра: Днём или спокойным вечером. Одному или с тем кому тоже интересна тема. Потом обсудить.",
    "🕯️ Атмосфера для просмотра: В тишине, без отвлечений. Этот тип кино требует внимания и даёт взамен много.",
    "🕯️ Атмосфера для просмотра: Вечером когда хочется чего-то настоящего. С блокнотом если склонен записывать мысли.",
    "🕯️ Атмосфера для просмотра: Одному в спокойный вечер. Или с кем-то кто умеет слушать и думать.",
]

RU_P1_GENERIC = [
    "Режиссёр знает что хочет сказать — и это чувствуется в каждом кадре. Фильм не распыляется на лишнее, держит выбранный тон от начала до конца.",
    "Это кино с характером. Оно не пытается понравиться всем сразу — у него есть своя позиция, своя интонация.",
    "Постановка уверенная — режиссёр управляет темпом и пространством с ощущением что знает зачем каждая сцена здесь.",
    "Фильм существует в своём ритме. Не торопит зрителя, не подсказывает как реагировать — доверяет собственному материалу.",
    "Визуальный стиль и нарративная структура здесь не конфликтуют — они работают вместе. Это заметно и создаёт ощущение цельности.",
]

RU_P2_GENERIC = [
    "Смотреть стоит ради общего качества исполнения. Не открытие жанра — но добротная работа которая уважает зрителя.",
    "Есть что-то что делает его выше среднего по жанру. Не без слабых мест, но с достаточно сильными сторонами чтобы рекомендовать.",
    "Фильм честен со своим зрителем. Не обещает больше чем даёт — и это само по себе ценно.",
    "Смотрится ровно. Провалов нет, откровений тоже. Но есть достоинство в ремесле — и оно здесь присутствует.",
    "Если жанр близок — смотреть стоит. Если нет — возможно, не самый очевидный выбор, но сюрприз не исключён.",
]

RU_P3_GENERIC = [
    "Подойдёт тем кто ценит жанровое кино сделанное с умом и без снобизма.",
    "Для зрителей которые смотрят много и умеют отличать ремесло от случайности.",
    "Хороший выбор для вечера когда хочется кино — просто хорошего кино.",
    "Для тех кто умеет находить удовольствие в деталях а не только в поворотах сюжета.",
    "Широкая аудитория оценит. Особенно те кто любит жанр.",
]

RU_ATM_GENERIC = [
    "🕯️ Атмосфера для просмотра: Вечером с тем кто любит говорить о кино после. Хороший фон для спокойного вечера.",
    "🕯️ Атмосфера для просмотра: В удобный вечер, с чем-нибудь вкусным. Одному или вдвоём — работает в обоих форматах.",
    "🕯️ Атмосфера для просмотра: Выходной вечер, диван, тишина. Не требует особого настроя — само создаёт нужный.",
    "🕯️ Атмосфера для просмотра: Вечером без спешки. С тем кому тоже интересен этот тип кино.",
    "🕯️ Атмосфера для просмотра: С кем-то близким, когда есть время и настроение. Фоном — не стоит, оно требует внимания.",
]

# ─── ШАБЛОНЫ ОТЗЫВОВ (EN) ────────────────────────────────────

EN_P1_HORROR = [
    "The director builds tension not through shock, but through feeling — the viewer senses something is wrong long before it becomes obvious. Atmosphere matters more than any plot twist.",
    "The film operates honestly within the horror genre: doesn't rush to frighten, lets the space breathe with anxiety. It's about the feeling of wrongness — slow, but relentless.",
    "Fear lives in the details here — in the frame, in the silence, in the pauses between lines. The director knows how to keep the viewer in a state of readiness, muscles tensing on their own.",
    "The film builds dread methodically, layer by layer. Genre tools are used skillfully — no cheap jump scares, relying instead on genuine unease.",
]

EN_P2_HORROR = [
    "Worth watching for those tired of predictable horror. There's character and internal logic here. If you want quick adrenaline — better choose something else.",
    "This isn't a film for the faint-hearted, nor for seasoned viewers who claim to fear nothing. It exists somewhere between — pressing psychologically rather than physically.",
    "The film doesn't rush. That's its greatest strength and greatest risk: if you're not ready for slow horror — it will exhaust you. If you are — it won't let go.",
    "Worth watching for the atmosphere and the use of space. The ending may disappoint — genre is genre. But the journey there is well-crafted.",
]

EN_P3_HORROR = [
    "For fans of atmospheric horror where dread matters more than fright.",
    "For those who want films that work with feeling rather than plot mechanics.",
    "Ideal for fans of psychological horror. Slasher fans should look elsewhere.",
    "For viewers who need sustained tension, not just a collection of scary moments.",
]

EN_ATM_HORROR = [
    "🕯️ Viewing atmosphere: Late at night, alone or with someone who won't be ashamed to admit they're scared. Lights off.",
    "🕯️ Viewing atmosphere: At night when it's dark outside. Better with someone — not because it's scary, but because there's something to discuss after.",
    "🕯️ Viewing atmosphere: A dark evening when the house is quiet. Headphones mandatory — the sound is half the film.",
    "🕯️ Viewing atmosphere: Late in the evening, with two people. Make tea, put away the phone, don't turn on the lights.",
]

EN_P1_COMEDY = [
    "The film doesn't try to be funnier than it is — and that's its honesty. The humor grows from situations and characters, not from pre-written jokes.",
    "The director doesn't push the comedy pedal — lets the scene develop at its own pace. The comedic effect arises naturally, without cuing the audience.",
    "The film operates in a light register — but not superficially. Behind each joke is an observation about people, not just a desire to amuse.",
    "This is a comedy that knows its limits. Doesn't reach for grotesque when irony is enough, doesn't ask the audience to take things too seriously.",
]

EN_P2_COMEDY = [
    "Worth watching for a good mood and a couple of genuinely funny moments. Doesn't promise depth — but doesn't pretend to have it either.",
    "The film does exactly what it was made for: gives you a break. No pretensions to more, but honest and without dead spots.",
    "If you're looking for light cinema for an evening — this is it. If you're looking for something that'll change your perspective on life — keep scrolling.",
    "Goes down easy, leaves a good aftertaste. Not every joke lands equally — but the overall tone holds.",
]

EN_P3_COMEDY = [
    "For those who just want to relax. Asks nothing — just time and a willingness to smile.",
    "Good for watching with people who need to unwind after a long day. Not for those seeking depth.",
    "A solid choice for company. Works alone too, but funnier together.",
    "For those who can appreciate simple pleasure without overthinking it.",
]

EN_ATM_COMEDY = [
    "🕯️ Viewing atmosphere: Friday evening with food and company. Doesn't require close attention — works as background too.",
    "🕯️ Viewing atmosphere: Weekend afternoon, the couch, something to snack on. Turn off your brain and enjoy.",
    "🕯️ Viewing atmosphere: With friends or a partner when you don't want anything complicated. Good mood guaranteed.",
    "🕯️ Viewing atmosphere: After a long day when you need simple joy. Better with company — laughing is more fun together.",
]

EN_P1_DRAMA = [
    "The film doesn't rush. It trusts the viewer — gives time to inhabit the characters, understand what's really happening. Direction here serves the actors rather than overwhelming them.",
    "This is quietly operating cinema. No big events, no crisis turns — just people and how they live through what happens to them.",
    "The director bets on details: a gesture, a glance, a pause. In a good drama this is what says the most — and that principle is upheld here.",
    "The film lives at the rhythm of everyday life — and that's its strength. No cinema about 'big events,' just about how people live, make mistakes, and understand themselves.",
]

EN_P2_DRAMA = [
    "Worth watching for the performances and the sincerity. If you're waiting for events — there aren't many. If you're waiting for feeling — it's there.",
    "This film doesn't entertain — it speaks. If you're ready for that, it'll leave a mark. If not — it'll seem slow.",
    "Strengths: atmosphere, actors, accuracy of detail. Weaknesses: the pace isn't for everyone, the ending may feel unresolved.",
    "Worth watching if you're in the mood for serious cinema. Not background viewing — it demands attention.",
]

EN_P3_DRAMA = [
    "For viewers who can watch slow cinema and value the human element in stories.",
    "For those looking for film about people, not events. If you need action — look elsewhere.",
    "A good choice for those who value subtle direction and honest performance.",
    "For people who watch films for feeling, not entertainment.",
]

EN_ATM_DRAMA = [
    "🕯️ Viewing atmosphere: An evening when your mind is at peace. With someone you can sit in silence with after. Wine or tea.",
    "🕯️ Viewing atmosphere: In quiet, in the evening. Better alone or with someone who watches films seriously.",
    "🕯️ Viewing atmosphere: When you're in the mood for a conversation about life. With a partner or friend you can trust.",
    "🕯️ Viewing atmosphere: Unhurried, on a weekday evening. Put down the phone, let the film work.",
]

EN_P1_ACTION = [
    "The film doesn't pretend to be about anything other than action — and that's an honest position. The director constructs scenes with a feel for space, pace, and rhythm.",
    "The action here isn't perfunctory — it's considered, with internal logic. The staging of fights and chases shows a director who knows the genre from the inside.",
    "Momentum is sustained from first scene to last. The director knows how to give the viewer breathing room without losing tension — and that's valuable in the genre.",
    "The film knows its strengths and plays to them honestly. Visual style and pacing are in sync; you never feel you're watching different films stitched together.",
]

EN_P2_ACTION = [
    "Worth watching for the solidly executed sequences and overall energy. The plot doesn't reach for revelation — but it doesn't get in the way.",
    "If you love the genre — this is a solid specimen. If you're indifferent to action — there's nothing extraordinary here to convert you.",
    "A well-made ride. Doesn't claim depth, but does its job honestly and without boredom.",
    "Watches in one breath. Plot logic is secondary — what matters here is movement and rhythm, and that's all in order.",
]

EN_P3_ACTION = [
    "For genre fans — essential viewing. For those looking for something deeper — possibly not the film.",
    "For those who want to switch off and get an adrenaline dose without complications.",
    "Good choice for group viewing when you want to watch rather than think.",
    "For those who appreciate a solidly made genre film without pretensions.",
]

EN_ATM_ACTION = [
    "🕯️ Viewing atmosphere: In company with popcorn. Loud, with a big screen — that's what it was made for.",
    "🕯️ Viewing atmosphere: Evening with friends, volume up. Talking during the film is acceptable.",
    "🕯️ Viewing atmosphere: With food and a good mood. Perfect for a Friday or weekend evening with company.",
    "🕯️ Viewing atmosphere: Big screen, decent sound. This is cinema that should sound loud and fill the room.",
]

EN_P1_THRILLER = [
    "The director builds tension economically — doesn't waste it, holds it in reserve. The film pins you to your seat methodically, without rushing.",
    "This is a thriller that respects the viewer: doesn't explain everything, doesn't rush events. Tension is created through atmosphere, not mechanical twists.",
    "The film uses anxiety as a tool: applied precisely, in the right places. Doesn't let you relax, but doesn't overdo it.",
    "A genre thriller made with intelligence. The director understands the difference between suspense and shock — and chooses the former.",
]

EN_P2_THRILLER = [
    "Worth watching for the atmosphere and structure. The finale may not please everyone — but the road there is worth the time.",
    "Sustains tension exactly as long as needed. May dip slightly after — but the overall level is good.",
    "A solid choice if you're tired of predictable genre formulas. You can sense the creators were thinking about what they were making.",
    "A thriller that rewards on repeat viewing: you notice things the second time around. Worth revisiting.",
]

EN_P3_THRILLER = [
    "For fans of suspense and psychological tension. If you need action — this is a different film.",
    "For those who like films that keep them in a state of uncertainty until the end.",
    "For viewers who appreciate intelligent genre work without dumbing down.",
    "Good choice for those seeking tense cinema without unnecessary noise.",
]

EN_ATM_THRILLER = [
    "🕯️ Viewing atmosphere: Evening with someone who can handle tension. Don't pause, don't check your phone.",
    "🕯️ Viewing atmosphere: A dark evening, in quiet. Better with someone — there'll be things to talk about after.",
    "🕯️ Viewing atmosphere: Late at night when you can give yourself fully to the film. Not as background — fully present.",
    "🕯️ Viewing atmosphere: Alone or with a partner. Quiet, dark. Phone on silent.",
]

EN_P1_GENERIC = [
    "The director knows what they want to say — and that shows in every frame. The film doesn't scatter itself on unnecessary things, holds its chosen tone from start to finish.",
    "This is cinema with character. It doesn't try to please everyone at once — it has its own position, its own intonation.",
    "The direction is assured — the director controls pace and space with a sense of knowing why each scene belongs here.",
    "The film exists at its own rhythm. Doesn't rush the viewer, doesn't suggest how to react — trusts its own material.",
    "Visual style and narrative structure don't conflict here — they work together. It's noticeable and creates a sense of wholeness.",
]

EN_P2_GENERIC = [
    "Worth watching for the overall quality of execution. Not a genre landmark — but solid work that respects the viewer.",
    "There's something that puts it above the genre average. Not without weak points, but with strong enough merits to recommend.",
    "The film is honest with its audience. Doesn't promise more than it delivers — and that itself has value.",
    "Watches evenly. No lows, no revelations. But there's dignity in the craft — and it's present here.",
    "If the genre speaks to you — worth watching. If not — not the most obvious choice, but a pleasant surprise isn't impossible.",
]

EN_P3_GENERIC = [
    "For those who appreciate genre cinema made with intelligence and without snobbery.",
    "For viewers who watch a lot and can distinguish craft from accident.",
    "A good choice for an evening when you want a film — just a good film.",
    "For those who find pleasure in details, not just in plot turns.",
    "A wide audience will appreciate it. Especially those who love the genre.",
]

EN_ATM_GENERIC = [
    "🕯️ Viewing atmosphere: Evening with someone who likes to talk about cinema after. Good backdrop for a quiet evening.",
    "🕯️ Viewing atmosphere: A comfortable evening, something tasty. Alone or with someone — works both ways.",
    "🕯️ Viewing atmosphere: Weekend evening, couch, quiet. Doesn't require a special mood — creates one.",
    "🕯️ Viewing atmosphere: An unhurried evening. With someone who shares an interest in this type of cinema.",
    "🕯️ Viewing atmosphere: With someone close, when there's time and mood. Not as background — it asks for attention.",
]


# ─── ГЕНЕРАЦИЯ ────────────────────────────────────────────────

def pick(lst, idx):
    return lst[idx % len(lst)]


def generate_review_ru(tmdb_id, title_ru, title, year, genre, desc_ru, desc, idx):
    p = classify_film(title_ru, title, year, genre, desc_ru, desc)
    
    if p["horror"]:
        p1 = pick(RU_P1_HORROR, idx)
        p2 = pick(RU_P2_HORROR, idx + 1)
        p3 = pick(RU_P3_HORROR, idx + 2)
        atm = pick(RU_ATM_HORROR, idx + 3)
    elif p["comedy"]:
        p1 = pick(RU_P1_COMEDY, idx)
        p2 = pick(RU_P2_COMEDY, idx + 1)
        p3 = pick(RU_P3_COMEDY, idx + 2)
        atm = pick(RU_ATM_COMEDY, idx + 3)
    elif p["drama"] and not p["action"]:
        p1 = pick(RU_P1_DRAMA, idx)
        p2 = pick(RU_P2_DRAMA, idx + 1)
        p3 = pick(RU_P3_DRAMA, idx + 2)
        atm = pick(RU_ATM_DRAMA, idx + 3)
    elif p["action"]:
        p1 = pick(RU_P1_ACTION, idx)
        p2 = pick(RU_P2_ACTION, idx + 1)
        p3 = pick(RU_P3_ACTION, idx + 2)
        atm = pick(RU_ATM_ACTION, idx + 3)
    elif p["thriller"]:
        p1 = pick(RU_P1_THRILLER, idx)
        p2 = pick(RU_P2_THRILLER, idx + 1)
        p3 = pick(RU_P3_THRILLER, idx + 2)
        atm = pick(RU_ATM_THRILLER, idx + 3)
    elif p["scifi"]:
        p1 = pick(RU_P1_SCIFI, idx)
        p2 = pick(RU_P2_SCIFI, idx + 1)
        p3 = pick(RU_P3_SCIFI, idx + 2)
        atm = pick(RU_ATM_SCIFI, idx + 3)
    elif p["documentary"]:
        p1 = pick(RU_P1_DOCUMENTARY, idx)
        p2 = pick(RU_P2_DOCUMENTARY, idx + 1)
        p3 = pick(RU_P3_DOCUMENTARY, idx + 2)
        atm = pick(RU_ATM_DOCUMENTARY, idx + 3)
    else:
        p1 = pick(RU_P1_GENERIC, idx)
        p2 = pick(RU_P2_GENERIC, idx + 1)
        p3 = pick(RU_P3_GENERIC, idx + 2)
        atm = pick(RU_ATM_GENERIC, idx + 3)
    
    return f"{p1}\n\n{p2}\n\n{p3}\n\n{atm}"


def generate_review_en(tmdb_id, title_ru, title, year, genre, desc_ru, desc, idx):
    p = classify_film(title_ru, title, year, genre, desc_ru, desc)
    
    if p["horror"]:
        p1 = pick(EN_P1_HORROR, idx)
        p2 = pick(EN_P2_HORROR, idx + 1)
        p3 = pick(EN_P3_HORROR, idx + 2)
        atm = pick(EN_ATM_HORROR, idx + 3)
    elif p["comedy"]:
        p1 = pick(EN_P1_COMEDY, idx)
        p2 = pick(EN_P2_COMEDY, idx + 1)
        p3 = pick(EN_P3_COMEDY, idx + 2)
        atm = pick(EN_ATM_COMEDY, idx + 3)
    elif p["drama"] and not p["action"]:
        p1 = pick(EN_P1_DRAMA, idx)
        p2 = pick(EN_P2_DRAMA, idx + 1)
        p3 = pick(EN_P3_DRAMA, idx + 2)
        atm = pick(EN_ATM_DRAMA, idx + 3)
    elif p["action"]:
        p1 = pick(EN_P1_ACTION, idx)
        p2 = pick(EN_P2_ACTION, idx + 1)
        p3 = pick(EN_P3_ACTION, idx + 2)
        atm = pick(EN_ATM_ACTION, idx + 3)
    elif p["thriller"]:
        p1 = pick(EN_P1_THRILLER, idx)
        p2 = pick(EN_P2_THRILLER, idx + 1)
        p3 = pick(EN_P3_THRILLER, idx + 2)
        atm = pick(EN_ATM_THRILLER, idx + 3)
    elif p["scifi"]:
        p1 = pick(EN_P1_GENERIC, idx)
        p2 = pick(EN_P2_GENERIC, idx + 1)
        p3 = pick(EN_P3_GENERIC, idx + 2)
        atm = pick(EN_ATM_GENERIC, idx + 3)
    elif p["documentary"]:
        p1 = pick(EN_P1_DRAMA, idx)
        p2 = pick(EN_P2_DRAMA, idx + 1)
        p3 = pick(EN_P3_DRAMA, idx + 2)
        atm = pick(EN_ATM_DRAMA, idx + 3)
    else:
        p1 = pick(EN_P1_GENERIC, idx)
        p2 = pick(EN_P2_GENERIC, idx + 1)
        p3 = pick(EN_P3_GENERIC, idx + 2)
        atm = pick(EN_ATM_GENERIC, idx + 3)
    
    return f"{p1}\n\n{p2}\n\n{p3}\n\n{atm}"


def check_no_numbers(text):
    """Проверяем что нет чисел с точкой (рейтингов типа 7.8)"""
    if re.search(r'\d+\.\d+', text):
        return False
    if re.search(r'(?i)рейтинг|оценка|tmdb|imdb', text):
        return False
    return True


# ─── ОСНОВНОЙ ЦИКЛ ────────────────────────────────────────────

BATCH = 30
total_done = 0
errors = 0

for batch_start in range(0, len(todo), BATCH):
    batch = todo[batch_start:batch_start + BATCH]
    rows = []
    
    for i, (tmdb_id, title_ru, title, year, genre, desc_ru, desc) in enumerate(batch):
        global_idx = batch_start + i
        
        review_ru = generate_review_ru(tmdb_id, title_ru, title, year, genre, desc_ru, desc, global_idx)
        review_en = generate_review_en(tmdb_id, title_ru, title, year, genre, desc_ru, desc, global_idx)
        
        # Проверка
        if not check_no_numbers(review_ru) or not check_no_numbers(review_en):
            print(f"WARNING: numbers found in review for {tmdb_id}, skipping")
            errors += 1
            continue
        
        rows.append((tmdb_id, 'ru', review_ru))
        rows.append((tmdb_id, 'en', review_en))
    
    # Вставка батча
    try:
        cur.executemany(
            "INSERT INTO ai_reviews (tmdb_id, lang, review) VALUES (%s,%s,%s) ON CONFLICT (tmdb_id, lang) DO UPDATE SET review=EXCLUDED.review",
            rows
        )
        pg.commit()
        total_done += len(batch)
    except Exception as e:
        pg.rollback()
        print(f"ERROR batch {batch_start}: {e}")
        errors += 1
        continue
    
    # Прогресс каждые 300 фильмов
    if total_done % 300 == 0 or total_done == len(todo):
        print(f"\n[{total_done}/{len(todo)}] +{len(batch)} films, errors={errors}")
        # Пример последнего текста
        if rows:
            ex = rows[-2]
            print(f"--- EXAMPLE (tmdb_id={ex[0]}, lang={ex[1]}) ---")
            print(ex[2][:400])
            print("---")
        sys.stdout.flush()

print(f"\nDONE. Total generated: {total_done}, errors: {errors}")

# Финальная статистика
cur.execute("SELECT COUNT(*) FROM ai_reviews WHERE lang='ru'")
print(f"RU total in DB: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM ai_reviews WHERE lang='en'")
print(f"EN total in DB: {cur.fetchone()[0]}")
