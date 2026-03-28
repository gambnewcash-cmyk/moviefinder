#!/usr/bin/env python3
"""
Крейк — генератор редакционных отзывов moviefinders.net
Пишет RU + EN тексты для фильмов 2025-2026
"""

import sqlite3
import psycopg2
import random
import re
import sys
import time

# === GENRE TEMPLATES ===

RU_TEMPLATES = {
    "Drama": {
        "p1": [
            "Кино, которое предпочитает тишину крику. Режиссёр работает с паузами, крупными планами и эмоциональным подтекстом — история рассказывается через взгляды, а не монологи.",
            "Камерная история с претензией на что-то большее. Авторы делают ставку на актёрскую игру и внутренние конфликты, не отвлекаясь на внешние события.",
            "Медленное, вдумчивое кино. Каждая сцена — это слой, который нужно снять, чтобы добраться до сути. Режиссёр не спешит и не объясняет.",
            "Эмоциональная драма с хорошо выстроенной атмосферой. Авторы знают цену деталям — интерьерам, паузам, необязательным разговорам, которые говорят всё.",
            "Классическая история через современную призму. Режиссура сдержанная, но точная — без лишних слов и лишних сцен.",
            "Глубокое погружение в человеческий опыт. Камера не отворачивается от неудобных моментов, и это требует от зрителя готовности смотреть честно.",
            "Авторское кино, где история важнее зрелища. Темп неспешный, но именно это создаёт нужное пространство для переживания.",
        ],
        "p2": [
            "Смотреть, если ценишь кино, которое остаётся с тобой. Пропустить, если ждёшь действия и быстрых поворотов сюжета.",
            "Это не развлечение на вечер — это разговор, к которому нужно быть готовым. Эмоционально плотно и требовательно к вниманию.",
            "Честный взгляд на трудные темы. Фильм не предлагает готовых ответов, что делает его одновременно сложным и ценным.",
            "Достойный выбор для тех, кто хочет чего-то настоящего. Не для тех, кто ищет лёгкий вечер — но оно того стоит.",
            "Может показаться медленным, но ритм работает на тему. Если войдёшь — не пожалеешь.",
            "Смотреть ради исполнения и атмосферы. Не смотреть, если хочется лёгкого выхода из будней.",
        ],
        "p3": [
            "Для тех, кто умеет ценить нюансы и неочевидные истории. Любителям психологического кино и сложных персонажей.",
            "Для зрителей, которым нужно кино, а не сериальный сторителлинг. Для терпеливых.",
            "Тем, кто ищет эмоционального резонанса. Подростки и взрослые найдут здесь разное, но оба — своё.",
            "Для киноманов и тех, кто устал от шаблонных историй. Требует настроя и тишины.",
        ],
        "vibe_ru": [
            "🕯️ Атмосфера для просмотра: Поздний вечер, приглушённый свет, без телефона. Лучше в одиночестве или с кем-то близким.",
            "🕯️ Атмосфера для просмотра: Осенний вечер с чашкой чего-то тёплого. Фильм требует тишины и присутствия.",
            "🕯️ Атмосфера для просмотра: В спокойный день, когда есть время на послевкусие. Не для фонового просмотра.",
            "🕯️ Атмосфера для просмотра: С человеком, с которым не страшно помолчать после. Разговор сам начнётся.",
        ],
        "p1_en": [
            "A film that chooses silence over spectacle. The director works with pauses, close-ups, and emotional subtext — the story is told through looks, not monologues.",
            "Chamber storytelling with larger ambitions. The filmmakers bet on performance and internal conflict, steering clear of external noise.",
            "Slow, deliberate cinema. Every scene is a layer to peel back before reaching the core. The director neither rushes nor explains.",
            "An emotional drama with a well-constructed atmosphere. The filmmakers know the value of detail — interiors, pauses, small conversations that say everything.",
        ],
        "p2_en": [
            "Watch it if you value films that stay with you. Skip it if you're expecting action or quick plot turns.",
            "This isn't easy entertainment — it's a conversation you need to be ready for. Emotionally dense and demanding of attention.",
            "An honest look at difficult themes. The film offers no easy answers, which makes it both challenging and valuable.",
            "A worthy choice for those wanting something real. Not for a light evening — but worth it.",
        ],
        "p3_en": [
            "For those who appreciate nuance and non-obvious storytelling. Made for fans of psychological cinema and complex characters.",
            "For viewers who want cinema, not serialized storytelling. For the patient.",
            "For those seeking emotional resonance. Teens and adults will each find something different — and their own.",
        ],
        "vibe_en": [
            "🕯️ Best Watched: Late evening, dimmed lights, phone off. Best alone or with someone close.",
            "🕯️ Best Watched: An autumn evening with something warm to drink. The film demands silence and presence.",
            "🕯️ Best Watched: On a calm day when you have time for the aftertaste. Not background viewing.",
        ],
    },
    "Comedy": {
        "p1": [
            "Лёгкое, воздушное кино без претензий на глубину. Режиссёр знает, что делает: темп держит, комедийные ситуации строит на узнаваемом, а не на пошлом.",
            "Комедия, которая не пытается быть умнее, чем нужно. Задача — рассмешить и отпустить, и с этим она справляется.",
            "Жанровое кино в хорошем смысле: все элементы на месте, ничего лишнего. Смешно там, где должно быть смешно.",
            "Ситуационная комедия с крепким кастом и достаточным количеством сцен, которые работают. Не гениально, но честно.",
            "Авторы не изобретают велосипед — они просто едут на нём уверенно и с улыбкой. Иногда этого достаточно.",
            "Фильм, который не требует ничего от зрителя, кроме готовности расслабиться. Лёгкая рука режиссуры, понятный юмор.",
        ],
        "p2": [
            "Смотреть, когда нужна передышка от серьёзного. Не смотреть, если ждёшь интеллектуального вызова.",
            "Отличный выбор для разгрузки. Ничего революционного, но хорошо сделано и не занимает лишнего времени.",
            "Работает как антидот от тяжёлого дня. Пропустить, если жанр не твой — здесь особой глубины нет.",
            "Смотреть ради хорошего настроения. Попытки читать между строк излишни — всё на поверхности.",
        ],
        "p3": [
            "Для широкой аудитории, которой нужен отдых. Хорошо зайдёт компанией или на семейный вечер.",
            "Для тех, кто ценит простые радости кино. Без возрастных ограничений по духу.",
            "Тем, кто устал от тяжёлого и хочет просто посмеяться. Компания — большой плюс.",
        ],
        "vibe_ru": [
            "🕯️ Атмосфера для просмотра: Пятничный вечер с друзьями и чем-нибудь вкусным. Или ленивое воскресное утро.",
            "🕯️ Атмосфера для просмотра: Компания, диван, напитки. Фильм не требует тишины — смеяться вслух приветствуется.",
            "🕯️ Атмосфера для просмотра: Когда нужно выдохнуть и не думать. Хорошо в компании, приятно в одиночестве.",
        ],
        "p1_en": [
            "Light, breezy cinema without pretensions to depth. The director knows what they're doing: pace is maintained, comedy comes from the relatable rather than the crude.",
            "A comedy that doesn't try to be smarter than it needs to be. The goal is to make you laugh and let go — and it delivers.",
            "Genre filmmaking in the good sense: all elements in place, nothing superfluous. Funny where it should be funny.",
        ],
        "p2_en": [
            "Watch when you need a break from the serious. Don't watch if you're expecting an intellectual challenge.",
            "Great choice for decompression. Nothing revolutionary, but well-made and doesn't overstay its welcome.",
            "Works as an antidote to a heavy day. Skip it if the genre isn't for you — there's no hidden depth here.",
        ],
        "p3_en": [
            "For a broad audience that needs a break. Works well with company or for a family evening.",
            "For those who appreciate simple cinematic pleasures. No real age limits by spirit.",
        ],
        "vibe_en": [
            "🕯️ Best Watched: Friday night with friends and snacks. Or a lazy Sunday morning.",
            "🕯️ Best Watched: Friends, couch, drinks. The film doesn't demand silence — laughing out loud is encouraged.",
        ],
    },
    "Horror": {
        "p1": [
            "Хоррор, который понимает, чего хочет зритель жанра. Режиссёр не торопится с пугалками — строит давление медленно, а потом разряжает его в нужный момент.",
            "Атмосферный ужас на грани психологического и физического. Камера умеет держать напряжение, не прибегая к дешёвым приёмам.",
            "Жанровое кино с уважением к правилам хоррора. Темп рассчитан, саспенс выстроен, а финал не обманывает.",
            "Фильм, который работает на уровне ощущений. Визуальный язык мрачный и конкретный — без излишней иронии.",
            "Современный хоррор с попыткой сказать что-то за пределами жанра. Страх здесь — метафора, а не цель сама по себе.",
            "Прямолинейный хоррор без претензий. Пугает там, где должен, атмосферу держит, аудиторию уважает.",
        ],
        "p2": [
            "Смотреть, если жанр твой и ты умеешь получать удовольствие от напряжения. Не для тех, кто надеется на философию.",
            "Добротный хоррор для ценителей. Атмосфера сильная, моменты есть. Пропустить, если нужна история, а не ощущение.",
            "Честное жанровое кино. Смотреть вечером, когда хочется адреналина.",
            "Работает лучше, чем большинство конкурентов из той же ниши. Пропустить, если хоррор тебе не близок.",
        ],
        "p3": [
            "Для поклонников жанра и тех, кто умеет наслаждаться страхом. Не для слабонервных и любителей лёгкого кино.",
            "Для взрослой аудитории с устойчивой нервной системой. Жанровых фанатов — приятно порадует.",
            "Тем, кто ищет именно хоррор. Без компромиссов и смягчений.",
        ],
        "vibe_ru": [
            "🕯️ Атмосфера для просмотра: Ночью, желательно с кем-то рядом. Темнота и тишина — обязательное условие.",
            "🕯️ Атмосфера для просмотра: Поздний вечер, одиночество или смелая компания. Не оставляйте свет.",
            "🕯️ Атмосфера для просмотра: В темноте, с хорошим звуком. Лучше не в одиночестве — если только вы не любите бояться одни.",
        ],
        "p1_en": [
            "Horror that understands what genre audiences want. The director doesn't rush the scares — builds pressure slowly, then releases it at the right moment.",
            "Atmospheric horror on the edge of psychological and physical. The camera knows how to hold tension without resorting to cheap tricks.",
            "Genre filmmaking with respect for horror's rules. Pacing is calculated, suspense is constructed, and the finale doesn't cheat.",
        ],
        "p2_en": [
            "Watch if the genre is yours and you know how to enjoy tension. Not for those hoping for philosophy.",
            "Solid horror for enthusiasts. Strong atmosphere, good moments. Skip if you need story over sensation.",
            "Honest genre filmmaking. Watch it in the evening when you want adrenaline.",
        ],
        "p3_en": [
            "For genre fans and those who enjoy being scared. Not for the faint-hearted or lovers of light entertainment.",
            "For adult audiences with steady nerves. Genre fans will be pleasantly surprised.",
        ],
        "vibe_en": [
            "🕯️ Best Watched: At night, preferably with someone nearby. Darkness and silence are required.",
            "🕯️ Best Watched: Late evening, alone or with a brave group. Don't leave the lights on.",
        ],
    },
    "Thriller": {
        "p1": [
            "Триллер, выстроенный на недоверии и нарастающем саспенсе. Режиссёр грамотно управляет информацией — давая достаточно, чтобы интриговать, и скрывая достаточно, чтобы держать.",
            "Психологически плотное кино. Авторы работают с тревогой как с инструментом — каждая сцена добавляет к общему давлению.",
            "Жанровый триллер с умной структурой. Повороты ощущаются заработанными, а не вставленными ради удивления.",
            "Кино, где напряжение важнее экшена. Режиссёр предпочитает намёки демонстрации, и это работает.",
            "Крепкий жанровый триллер. Сценарий держит темп, интерес к развязке не гаснет до финала.",
        ],
        "p2": [
            "Смотреть, если ценишь интеллектуальный саспенс и непредсказуемых персонажей. Не для тех, кто хочет чистого экшена.",
            "Достойный выбор для вечера — держит у экрана и не оставляет равнодушным.",
            "Работает лучше при первом просмотре, когда всё ещё неизвестно. Пересматривать имеет смысл только ради деталей.",
            "Смотреть ради умно выстроенного напряжения. Пропустить, если тебе нужны ответы, а не вопросы.",
        ],
        "p3": [
            "Для тех, кто любит разгадывать кино во время просмотра. Для фанатов жанра и психологических игр.",
            "Взрослая аудитория, которая ценит сценарное мастерство. Подростки тоже оценят — если готовы к медленному горению.",
            "Тем, кому нужен триллер с мозгом, а не только мышцами.",
        ],
        "vibe_ru": [
            "🕯️ Атмосфера для просмотра: Вечером, когда хочется загадки. Смотреть лучше без телефона — не отвлекайся.",
            "🕯️ Атмосфера для просмотра: Тихий вечер дома. Этот фильм требует полного внимания — и его заслуживает.",
        ],
        "p1_en": [
            "A thriller built on mistrust and mounting suspense. The director manages information skillfully — giving enough to intrigue, hiding enough to hold.",
            "Psychologically dense cinema. The filmmakers use anxiety as a tool — every scene adds to the cumulative pressure.",
            "A genre thriller with smart structure. Twists feel earned rather than inserted for shock value.",
        ],
        "p2_en": [
            "Watch if you value intellectual suspense and unpredictable characters. Not for those wanting pure action.",
            "A worthy evening choice — keeps you at the screen and doesn't leave you indifferent.",
            "Works best on a first watch, when everything is still unknown. Worth revisiting only for the details.",
        ],
        "p3_en": [
            "For those who like to decode a film while watching it. For genre fans and lovers of psychological games.",
            "Adult audience that values screenwriting craft. Teens will appreciate it too — if ready for slow burn.",
        ],
        "vibe_en": [
            "🕯️ Best Watched: Evening when you're in the mood for a puzzle. Best without your phone — don't get distracted.",
            "🕯️ Best Watched: Quiet evening at home. This film demands full attention — and earns it.",
        ],
    },
    "Action": {
        "p1": [
            "Экшен, который знает своё место и не пытается быть чем-то другим. Постановка сцен динамичная, монтаж не рубит действие на куски.",
            "Кино для тех, кто пришёл за адреналином. Режиссёр хорошо понимает физику действия — движение, пространство, ставки.",
            "Высокооктановое зрелище с правильным ритмом. Авторы не забывают про персонажей среди взрывов — и это выгодно отличает.",
            "Честный жанровый экшен. Не претендует на глубину, зато честно доставляет то, что обещает.",
            "Постановочное мастерство на переднем плане. Сцены движения выстроены с умом, кино смотрится динамично.",
        ],
        "p2": [
            "Смотреть, если хочется адреналина без лишних размышлений. Не смотреть в ожидании драматической глубины.",
            "Отличный выбор для разгрузки. Не заставляет думать, зато даёт то, что нужно жанру.",
            "Для вечера, когда хочется зрелища. Работает на экране побольше с хорошим звуком.",
        ],
        "p3": [
            "Для фанатов жанра и тех, кому нужен выброс эндорфинов. Хорошо смотрится компанией.",
            "Для широкой аудитории, которая любит динамичное кино. Возрастных ограничений по духу нет.",
        ],
        "vibe_ru": [
            "🕯️ Атмосфера для просмотра: Большой экран, громкий звук, компания. Фильм создан для совместного просмотра.",
            "🕯️ Атмосфера для просмотра: Вечер пятницы с едой на столе и друзьями рядом. Никакой философии — только кайф.",
        ],
        "p1_en": [
            "Action that knows its place and doesn't try to be something else. Scene staging is dynamic, editing doesn't chop the action into fragments.",
            "Cinema for those who came for adrenaline. The director understands the physics of action — movement, space, stakes.",
            "High-octane entertainment with the right rhythm. The filmmakers don't forget characters amid the explosions — and that's a point in their favor.",
        ],
        "p2_en": [
            "Watch if you want adrenaline without overthinking. Don't watch expecting dramatic depth.",
            "Excellent choice for unwinding. Doesn't make you think, but delivers what the genre promises.",
        ],
        "p3_en": [
            "For genre fans and those needing an endorphin release. Works great with company.",
            "For a broad audience that loves dynamic cinema. No real age limits by spirit.",
        ],
        "vibe_en": [
            "🕯️ Best Watched: Big screen, loud sound, company. This film was made for group viewing.",
            "🕯️ Best Watched: Friday evening with food on the table and friends nearby. No philosophy — just enjoyment.",
        ],
    },
    "Documentary": {
        "p1": [
            "Документалистика в лучшем своём виде — портретная съёмка, честный монтаж, отсутствие искусственного драматизма. Материал говорит сам за себя.",
            "Документальный фильм с чёткой авторской позицией. Режиссёр не прячется за объективность — и это делает кино честнее.",
            "Хорошая документалистика не объясняет — она показывает. Здесь именно так: камера следит, а зритель делает выводы сам.",
            "Тематический документальный фильм с качественным материалом. Структура крепкая, угол зрения свежий.",
            "Авторское документальное кино. Режиссёр выбирает личный взгляд вместо энциклопедической полноты — и выигрывает.",
        ],
        "p2": [
            "Смотреть, если тема близка или незнакома — в обоих случаях узнаешь что-то новое. Не для тех, кто ищет развлечение.",
            "Меняет или уточняет понимание темы. Для жанра — высокий уровень.",
            "Честный разговор о важном. Не всегда приятный, но необходимый.",
            "Хорошо сделанная работа. Смотреть всем, кому интересна тема.",
        ],
        "p3": [
            "Для тех, кто уже знает что-то о теме и хочет глубины. Новичкам может не хватить контекста.",
            "Для широкой аудитории: хороший документальный фильм не требует предварительных знаний.",
            "Для любознательных, которым интересен мир за пределами экрана.",
        ],
        "vibe_ru": [
            "🕯️ Атмосфера для просмотра: В спокойный день, когда есть время подумать после. Хорошо в небольшой компании с разговором потом.",
            "🕯️ Атмосфера для просмотра: Воскресный день или вдумчивый вечер. Этот фильм даёт много материала для размышлений.",
        ],
        "p1_en": [
            "Documentary filmmaking at its best — portrait cinematography, honest editing, no artificial drama. The material speaks for itself.",
            "A documentary with a clear authorial stance. The director doesn't hide behind objectivity — and that makes the film more honest.",
            "Good documentary doesn't explain — it shows. That's exactly what happens here: the camera observes, and the viewer draws their own conclusions.",
        ],
        "p2_en": [
            "Watch if the topic is familiar or unfamiliar — in both cases, you'll learn something. Not for those seeking entertainment.",
            "Changes or clarifies understanding of the subject. For the genre — a high standard.",
            "An honest conversation about something important. Not always comfortable, but necessary.",
        ],
        "p3_en": [
            "For those who already know something about the subject and want depth. Newcomers may lack context.",
            "For a broad audience: a good documentary doesn't require prior knowledge.",
        ],
        "vibe_en": [
            "🕯️ Best Watched: On a calm day when you have time to think afterward. Good in a small group with conversation to follow.",
            "🕯️ Best Watched: A Sunday afternoon or thoughtful evening. This film gives plenty to think about.",
        ],
    },
    "Romance": {
        "p1": [
            "Романтическое кино с тонким пониманием жанра. Режиссёр не делает ставку на пафос — доверяет актёрской химии и небольшим деталям.",
            "Лирическое, неторопливое кино о близости. Авторы умеют передать ощущение влюблённости через атмосферу, а не объяснения.",
            "Романтическая история без лишней сентиментальности. Персонажи настоящие, отношения — убедительные.",
            "Светлое кино о человеческой близости. Режиссёр избегает клише и ставит на подлинность эмоций.",
        ],
        "p2": [
            "Смотреть, если ценишь тонкую романтику без мелодраматического перебора. Пропустить, если жанр не твой.",
            "Тёплое, искреннее кино. Хорошо работает как antidote на холодный день.",
            "Честная история о чувствах. Не без слабостей, но с настоящим сердцем.",
        ],
        "p3": [
            "Для тех, кто ценит романтику без сахарного сиропа. Парам и одиночкам — одинаково.",
            "Для всех, кому нужно что-то тёплое и человеческое. Хороший выбор для совместного вечера.",
        ],
        "vibe_ru": [
            "🕯️ Атмосфера для просмотра: Вечером вдвоём с чем-нибудь вкусным. Или в одиночестве, когда хочется тепла.",
            "🕯️ Атмосфера для просмотра: Спокойный вечер с любимым человеком или мечтой о нём. Свечи — по желанию.",
        ],
        "p1_en": [
            "Romantic cinema with a subtle understanding of the genre. The director doesn't rely on pathos — trusts chemistry between actors and small details.",
            "Lyrical, unhurried cinema about closeness. The filmmakers convey the feeling of being in love through atmosphere, not explanation.",
            "A romantic story without excess sentimentality. The characters feel real, the relationship — convincing.",
        ],
        "p2_en": [
            "Watch if you value subtle romance without melodramatic excess. Skip if the genre isn't for you.",
            "Warm, sincere cinema. Works well as an antidote on a cold day.",
        ],
        "p3_en": [
            "For those who appreciate romance without syrup. Works equally for couples and singles.",
            "For anyone needing something warm and human. A good choice for a shared evening.",
        ],
        "vibe_en": [
            "🕯️ Best Watched: An evening for two with something good to eat. Or alone, when you want warmth.",
            "🕯️ Best Watched: A quiet evening with someone you love, or the thought of someone. Candles optional.",
        ],
    },
    "Animation": {
        "p1": [
            "Анимационное кино, которое работает одновременно на детей и взрослых. Визуальный язык яркий, история — неожиданно многослойная.",
            "Анимация с характером. Авторы не ограничивают себя детской аудиторией — история говорит о взрослых вещах через простые образы.",
            "Красиво нарисованное, умно рассказанное. Студия знает что делает — каждый кадр проработан, эмоции настоящие.",
            "Анимационный фильм с душой. Визуальный стиль цельный, персонажи узнаваемые, юмор — для всех возрастов.",
        ],
        "p2": [
            "Смотреть всем. Особенно тем, кто думает, что анимация — это только для детей.",
            "Отличный выбор для семейного просмотра. Взрослые найдут больше смыслов — дети получат радость.",
            "Хорошая анимация всегда оправдывает просмотр. Этот фильм — не исключение.",
        ],
        "p3": [
            "Для всей семьи. Особенно для тех, кто любит качественную анимацию вне зависимости от возраста.",
            "Дети полюбят за динамику и визуал. Взрослые — за то, что спрятано между строк.",
        ],
        "vibe_ru": [
            "🕯️ Атмосфера для просмотра: Семейный вечер с попкорном. Или уютное воскресенье с детьми — или внутренним ребёнком.",
            "🕯️ Атмосфера для просмотра: С детьми или с теми, кто не боится быть немного ребёнком. Восторг гарантирован.",
        ],
        "p1_en": [
            "Animation that works simultaneously for children and adults. The visual language is vivid, the story — surprisingly layered.",
            "Animation with character. The filmmakers don't limit themselves to a child audience — the story speaks about adult things through simple imagery.",
            "Beautifully drawn, cleverly told. The studio knows what it's doing — every frame is crafted, emotions are real.",
        ],
        "p2_en": [
            "Watch it with anyone. Especially those who think animation is only for kids.",
            "Excellent choice for family viewing. Adults will find more meaning — children will find joy.",
        ],
        "p3_en": [
            "For the whole family. Especially for those who love quality animation regardless of age.",
            "Kids will love the energy and visuals. Adults — what's hidden between the lines.",
        ],
        "vibe_en": [
            "🕯️ Best Watched: Family evening with popcorn. Or a cozy Sunday with children — or your inner child.",
            "🕯️ Best Watched: With kids or with those who aren't afraid to be a little childlike. Wonder guaranteed.",
        ],
    },
    "Sci-Fi": {
        "p1": [
            "Научная фантастика с серьёзным отношением к идеям. Авторы используют жанр не как декорацию, а как способ говорить о настоящем через будущее.",
            "Спекулятивное кино с визуальной концепцией. Режиссёр выстраивает мир убедительно — детали работают на атмосферу, а не противоречат ей.",
            "Фантастика, в которой технологии — это метафора. Идея важнее зрелища, хотя и со зрелищем всё в порядке.",
            "Жанровая фантастика с крепким фундаментом. Мир проработан, логика последовательна, интерес к истории не гаснет.",
        ],
        "p2": [
            "Смотреть, если ценишь фантастику с мозгом. Пропустить, если нужен только визуальный аттракцион.",
            "Достойный выбор для жанровых фанатов. Уделяет внимание идеям, а не только спецэффектам.",
            "Интересный взгляд на то, что может быть. Смотреть всем, кому близка умная фантастика.",
        ],
        "p3": [
            "Для фанатов жанра и тех, кто думает о будущем. Для тех, кому нужна фантастика с вопросами.",
            "Для широкой аудитории — от подростков до взрослых. Лучше работает для зрителей с воображением.",
        ],
        "vibe_ru": [
            "🕯️ Атмосфера для просмотра: Ночью, когда можно дать волю мыслям. Хорошо в одиночестве — или с кем-то, кто любит поговорить после.",
            "🕯️ Атмосфера для просмотра: Вечером с хорошим экраном. Фантастика требует погружения.",
        ],
        "p1_en": [
            "Science fiction that takes its ideas seriously. The filmmakers use the genre not as decoration but as a way to speak about the present through the future.",
            "Speculative cinema with a visual concept. The director builds a convincing world — details support the atmosphere rather than contradict it.",
            "Sci-fi where technology is a metaphor. Ideas matter more than spectacle, though the spectacle is also solid.",
        ],
        "p2_en": [
            "Watch if you value sci-fi with a brain. Skip if you only need a visual ride.",
            "A worthy choice for genre fans. Pays attention to ideas, not just special effects.",
        ],
        "p3_en": [
            "For genre fans and those who think about the future. For those who need sci-fi with questions.",
            "For a broad audience — from teens to adults. Works best for viewers with imagination.",
        ],
        "vibe_en": [
            "🕯️ Best Watched: At night, when you can let your mind wander. Good alone — or with someone who likes to talk afterward.",
            "🕯️ Best Watched: Evening with a good screen. Sci-fi requires immersion.",
        ],
    },
    "Family": {
        "p1": [
            "Семейное кино, сделанное с пониманием, что «семейное» не значит «простое». История говорит о важных вещах понятным языком.",
            "Светлое, доброе кино без фальши. Авторы избегают сахарного сиропа и делают ставку на настоящие эмоции.",
            "Правильное семейное кино — то, которое смотрят вместе и обсуждают потом. Здесь есть о чём говорить.",
        ],
        "p2": [
            "Смотреть всей семьёй. Взрослые найдут своё, дети — своё, и это большая редкость.",
            "Отличный выбор для совместного вечера. Тёплое, умное, без лишней назидательности.",
        ],
        "p3": [
            "Для семей с детьми любого возраста. Работает лучше всего, когда смотришь не один.",
            "Для всех, кто ценит доброе кино. Без возрастных ограничений по духу.",
        ],
        "vibe_ru": [
            "🕯️ Атмосфера для просмотра: Семейный вечер с едой и смехом. Лучше смотреть вместе — кино создано для этого.",
            "🕯️ Атмосфера для просмотра: Воскресный вечер всей семьёй. Дети будут рады, взрослые — не пожалеют.",
        ],
        "p1_en": [
            "Family cinema made with the understanding that 'family' doesn't mean 'simple'. The story speaks about important things in accessible language.",
            "Bright, genuine cinema without falseness. The filmmakers avoid sentimentality and bet on real emotions.",
        ],
        "p2_en": [
            "Watch as a family. Adults will find their thing, children theirs — and that's rare.",
            "Excellent choice for a shared evening. Warm, smart, without excessive moralizing.",
        ],
        "p3_en": [
            "For families with children of any age. Works best when you're not watching alone.",
            "For anyone who appreciates good-hearted cinema. No real age limits by spirit.",
        ],
        "vibe_en": [
            "🕯️ Best Watched: Family evening with food and laughter. Better together — the film was made for it.",
            "🕯️ Best Watched: Sunday evening with the whole family. Kids will be happy, adults won't regret it.",
        ],
    },
    "Mystery": {
        "p1": [
            "Детектив или мистика, выстроенная как шахматная партия. Режиссёр раздаёт карты дозированно — зрителю хватает, чтобы думать, но недостаточно, чтобы угадать.",
            "Загадочное, неоднозначное кино. Ответы не приходят легко, и авторы знают цену этому ощущению.",
            "Жанровая мистика с хорошим темпом. Вопросы накапливаются правильно — финал оправдывает ожидание.",
        ],
        "p2": [
            "Смотреть, если любишь разгадывать по ходу. Пропустить, если хочется чёткой линейной истории.",
            "Держит у экрана от начала до конца. Хорошо выстроенная загадка — редкость.",
        ],
        "p3": [
            "Для тех, кто любит интеллектуальные головоломки в кино. Детективам и любителям загадок — обязательно.",
            "Для терпеливых зрителей, которым нравится думать.",
        ],
        "vibe_ru": [
            "🕯️ Атмосфера для просмотра: Тихий вечер, всё внимание на экране. Зрители, любящие обсуждать версии по ходу, найдут компанию.",
            "🕯️ Атмосфера для просмотра: В одиночестве или с кем-то таким же любопытным. Пауза посередине — не грех.",
        ],
        "p1_en": [
            "Detective or mystery built like a chess game. The director deals cards sparingly — enough to keep you thinking, not enough to let you guess.",
            "Enigmatic, ambiguous cinema. Answers don't come easily, and the filmmakers understand the value of that feeling.",
        ],
        "p2_en": [
            "Watch if you like to solve as you go. Skip if you want a clear linear story.",
            "Holds you from start to finish. A well-constructed puzzle is rare.",
        ],
        "p3_en": [
            "For those who enjoy intellectual puzzles in cinema. Mystery and detective fans — essential viewing.",
            "For patient viewers who enjoy thinking.",
        ],
        "vibe_en": [
            "🕯️ Best Watched: Quiet evening, full attention on screen. Viewers who like to discuss theories as they go will find company.",
            "🕯️ Best Watched: Alone or with someone equally curious. Pausing halfway through is not a sin.",
        ],
    },
    "Crime": {
        "p1": [
            "Криминальное кино с нужным количеством цинизма. Режиссёр не романтизирует и не осуждает — просто показывает систему изнутри.",
            "Жанровое кино о преступлении с хорошо выстроенной атмосферой. Детали мира убедительные, персонажи — живые.",
            "Криминальная драма с умом и стилем. Знает своих предшественников, но не копирует — у неё своя интонация.",
        ],
        "p2": [
            "Смотреть, если ценишь жанровое кино с настроением. Пропустить, если устал от преступного мира.",
            "Добротное жанровое кино. Атмосфера сильная, история держит.",
        ],
        "p3": [
            "Для фанатов криминальных историй и нуара. Взрослая аудитория с хорошим вкусом к жанру.",
            "Тем, кто любит тёмные истории о людях с непростой судьбой.",
        ],
        "vibe_ru": [
            "🕯️ Атмосфера для просмотра: Поздний вечер, темнота и хороший звук. Одному или с тем, кто понимает жанр.",
            "🕯️ Атмосфера для просмотра: Вечером, когда хочется чего-то тёмного и стильного. Не для воскресного семейного просмотра.",
        ],
        "p1_en": [
            "Crime cinema with the right amount of cynicism. The director neither romanticizes nor condemns — just shows the system from within.",
            "Genre filmmaking about crime with a well-constructed atmosphere. The world details are convincing, the characters — alive.",
        ],
        "p2_en": [
            "Watch if you value genre cinema with mood. Skip if you're tired of the criminal world.",
            "Solid genre filmmaking. Strong atmosphere, the story holds.",
        ],
        "p3_en": [
            "For fans of crime stories and noir. Adult audience with a good taste for the genre.",
            "For those who love dark stories about people with complicated fates.",
        ],
        "vibe_en": [
            "🕯️ Best Watched: Late evening, darkness and good sound. Alone or with someone who understands the genre.",
            "🕯️ Best Watched: Evening when you want something dark and stylish. Not for Sunday family viewing.",
        ],
    },
    "Adventure": {
        "p1": [
            "Приключенческое кино с правильным духом. Режиссёр выстраивает ощущение пути — не только физического, но и внутреннего.",
            "Зрелищное, бодрое кино о том, что за горизонтом. Авторы умеют передать чувство открытия.",
            "Жанровое приключение с живыми персонажами. Движение и эмоция работают вместе.",
        ],
        "p2": [
            "Смотреть, когда хочется куда-то улететь в мыслях. Хорошее эскапистское кино.",
            "Бодрое и тёплое кино. Смотреть с удовольствием — без лишних вопросов.",
        ],
        "p3": [
            "Для всех, кому нужен выход за пределы повседневного. Хорошо заходит молодёжи и семьям.",
            "Для тех, в ком ещё живёт ребёнок с тягой к приключениям.",
        ],
        "vibe_ru": [
            "🕯️ Атмосфера для просмотра: Выходной день, когда хочется куда-то отправиться. Компания добавит настроения.",
            "🕯️ Атмосфера для просмотра: С теми, кто ещё умеет удивляться. Приключение начинается с первых кадров.",
        ],
        "p1_en": [
            "Adventure cinema with the right spirit. The director builds a sense of journey — not only physical, but internal.",
            "Spectacular, energetic cinema about what's beyond the horizon. The filmmakers know how to convey the feeling of discovery.",
        ],
        "p2_en": [
            "Watch when you want to travel in your mind. Good escapist cinema.",
            "Energetic and warm filmmaking. Watch with pleasure — no need for deeper questions.",
        ],
        "p3_en": [
            "For anyone needing to escape the everyday. Works well for young audiences and families.",
            "For those who still have a child inside with a hunger for adventure.",
        ],
        "vibe_en": [
            "🕯️ Best Watched: A day off when you want to go somewhere. Company will add to the mood.",
            "🕯️ Best Watched: With those who still know how to be surprised. The adventure begins from the first frame.",
        ],
    },
    "Fantasy": {
        "p1": [
            "Фэнтези, которое верит в собственный мир. Авторы потрудились над деталями — смотришь и доверяешь тому, что видишь.",
            "Жанровое фэнтези с цельной визуальной концепцией. Мир проработан, магия логична, история не теряется в декорациях.",
            "Тёмное или светлое — зависит от жанрового выбора, но сделано с душой. Фэнтези как оно должно быть.",
        ],
        "p2": [
            "Смотреть, если умеешь верить в придуманные миры. Пропустить, если фэнтези не твой жанр.",
            "Для жанра — высокий уровень. Смотреть тем, кому нужно куда-то уйти.",
        ],
        "p3": [
            "Для фанатов жанра и всех, кто ещё верит в магию. Дети и взрослые найдут здесь своё.",
            "Для тех, кому нужно настоящее фэнтези — не разбавленное и не упрощённое.",
        ],
        "vibe_ru": [
            "🕯️ Атмосфера для просмотра: С теми, кто умеет верить в придуманные миры. Полное погружение обязательно.",
            "🕯️ Атмосфера для просмотра: Вечером, когда хочется другого измерения. Хороший экран — обязателен.",
        ],
        "p1_en": [
            "Fantasy that believes in its own world. The filmmakers put work into the details — you watch and trust what you see.",
            "Genre fantasy with a coherent visual concept. The world is detailed, magic is logical, the story doesn't get lost in the sets.",
        ],
        "p2_en": [
            "Watch if you can believe in invented worlds. Skip if fantasy isn't your genre.",
            "For the genre — a high standard. Watch it if you need somewhere to escape.",
        ],
        "p3_en": [
            "For genre fans and all who still believe in magic. Children and adults will each find something here.",
            "For those who need real fantasy — undiluted and uncompromised.",
        ],
        "vibe_en": [
            "🕯️ Best Watched: With those who can believe in invented worlds. Full immersion required.",
            "🕯️ Best Watched: Evening when you want another dimension. A good screen is essential.",
        ],
    },
    "Music": {
        "p1": [
            "Музыкальное кино, в котором звук — это не фон, а главный герой. Режиссёр выстраивает кино вокруг ритма и эмоции.",
            "Фильм о музыке и через музыку. Сцены выступлений живые, закулисье — честное.",
            "Лирическое, ритмичное кино. Авторы понимают, что музыка — это язык, и говорят на нём.",
        ],
        "p2": [
            "Смотреть, если музыка — это часть твоей жизни. Пропустить, если ждёшь история без саундтрека.",
            "Хорошее кино для меломанов и тех, кто умеет слышать.",
        ],
        "p3": [
            "Для музыкантов, меломанов и всех, кто знает, что такое настоящая страсть к звуку.",
            "Для широкой аудитории — музыка универсальна.",
        ],
        "vibe_ru": [
            "🕯️ Атмосфера для просмотра: С хорошим звуком и открытой душой. Музыка здесь — главное.",
            "🕯️ Атмосфера для просмотра: В компании или в одиночестве — но обязательно с хорошей акустикой.",
        ],
        "p1_en": [
            "Musical cinema where sound is the main character, not the background. The director builds the film around rhythm and emotion.",
            "A film about music and through music. Performance scenes feel alive, the backstage is honest.",
        ],
        "p2_en": [
            "Watch if music is part of your life. Skip if you're expecting a story without a soundtrack.",
            "Good cinema for music lovers and those who know how to listen.",
        ],
        "p3_en": [
            "For musicians, music lovers, and all who know what real passion for sound means.",
            "For a broad audience — music is universal.",
        ],
        "vibe_en": [
            "🕯️ Best Watched: With good sound and an open heart. Music is the main thing here.",
            "🕯️ Best Watched: In company or alone — but with good acoustics, always.",
        ],
    },
    "History": {
        "p1": [
            "Историческое кино с уважением к эпохе. Авторы не осовременивают — они воссоздают, и это чувствуется в каждом кадре.",
            "Реконструкция прошлого с авторской интерпретацией. Факты и вымысел сплетены умно — история живёт, а не иллюстрирует.",
            "Академически точное или вольное — но убедительное. Кино, которое заставляет гуглить после просмотра.",
        ],
        "p2": [
            "Смотреть, если интересует эпоха или личность. Пропустить, если ждёшь боевика с историческими декорациями.",
            "Хорошее историческое кино — редкость. Это один из тех случаев.",
        ],
        "p3": [
            "Для тех, кому интересна история — живая, а не учебниковая. Для эрудитов и любопытных.",
            "Для широкой аудитории, которая умеет ценить прошлое.",
        ],
        "vibe_ru": [
            "🕯️ Атмосфера для просмотра: В спокойный день, с готовностью погрузиться в другое время. Одному или с тем, кто любит историю.",
            "🕯️ Атмосфера для просмотра: Воскресный вечер с чаем. Кино требует внимания и вознаграждает его.",
        ],
        "p1_en": [
            "Historical cinema with respect for the era. The filmmakers don't modernize — they recreate, and you feel it in every frame.",
            "A reconstruction of the past with authorial interpretation. Facts and fiction are woven smartly — history lives rather than illustrates.",
        ],
        "p2_en": [
            "Watch if you're interested in the era or person. Skip if you're expecting an action film with historical decoration.",
            "Good historical cinema is rare. This is one of those cases.",
        ],
        "p3_en": [
            "For those interested in history — alive, not textbook. For the erudite and the curious.",
            "For a broad audience that knows how to appreciate the past.",
        ],
        "vibe_en": [
            "🕯️ Best Watched: On a calm day, ready to immerse in another time. Alone or with someone who loves history.",
            "🕯️ Best Watched: Sunday evening with tea. The film demands attention and rewards it.",
        ],
    },
    "War": {
        "p1": [
            "Военное кино без прославления и без морализаторства. Режиссёр показывает войну как она есть — жестокую, запутанную, человеческую.",
            "Серьёзное военное кино с антиромантическим взглядом. Авторы знают: настоящие истории войны — не про победу, а про выживание.",
            "Кино о людях на войне — не о войне как таковой. Этот нюанс делает фильм живым.",
        ],
        "p2": [
            "Смотреть, если готов к честному взгляду на тему. Не для лёгкого вечера.",
            "Важное кино. Тяжёлое — но именно поэтому нужное.",
        ],
        "p3": [
            "Для взрослой аудитории с интересом к военной теме. Для тех, кто умеет смотреть на войну без иллюзий.",
            "Для тех, кому важно помнить — через кино.",
        ],
        "vibe_ru": [
            "🕯️ Атмосфера для просмотра: В тихий вечер, когда готов к серьёзному разговору. Не для развлечения.",
            "🕯️ Атмосфера для просмотра: Когда есть настрой и силы на тяжёлое кино. Стоит смотреть не откладывая.",
        ],
        "p1_en": [
            "War cinema without glorification and without moralizing. The director shows war as it is — brutal, confusing, human.",
            "Serious war cinema with an anti-romantic perspective. The filmmakers know: real war stories aren't about victory, but about survival.",
        ],
        "p2_en": [
            "Watch if you're ready for an honest look at the subject. Not for a light evening.",
            "Important cinema. Heavy — but precisely because of that, necessary.",
        ],
        "p3_en": [
            "For adult audiences interested in war themes. For those who can look at war without illusions.",
            "For those who need to remember — through film.",
        ],
        "vibe_en": [
            "🕯️ Best Watched: A quiet evening when you're ready for a serious conversation. Not for entertainment.",
            "🕯️ Best Watched: When you have the mindset and strength for heavy cinema. Worth watching without postponing.",
        ],
    },
    "Western": {
        "p1": [
            "Вестерн — жанр с кодексом. Этот фильм знает правила и либо чтит их, либо осознанно нарушает. В обоих случаях — с умом.",
            "Пространство и молчание — вот язык хорошего вестерна. Здесь этот язык освоен.",
            "Жанровый вестерн с правильным настроением. Пыль, горизонт, характеры — всё на месте.",
        ],
        "p2": [
            "Смотреть, если любишь жанр или хочешь понять его. Пропустить, если вестерны кажутся архаикой.",
            "Хорошее жанровое кино для тех, кто умеет ценить классику.",
        ],
        "p3": [
            "Для фанатов вестернов и всех, кто умеет ценить неторопливое кино с характером.",
            "Для взрослой аудитории с вкусом к классике.",
        ],
        "vibe_ru": [
            "🕯️ Атмосфера для просмотра: Вечером с тёмным напитком и уважением к жанру. Одному или с тем, кто знает Серджо Леоне.",
            "🕯️ Атмосфера для просмотра: Тихий вечер с хорошим экраном. Вестерн требует пространства — дайте его ему.",
        ],
        "p1_en": [
            "A western — a genre with a code. This film knows the rules and either honors them or consciously breaks them. Either way — with intelligence.",
            "Space and silence — that's the language of a good western. That language is mastered here.",
        ],
        "p2_en": [
            "Watch if you love the genre or want to understand it. Skip if westerns seem archaic to you.",
            "Good genre filmmaking for those who appreciate the classics.",
        ],
        "p3_en": [
            "For western fans and all who appreciate unhurried cinema with character.",
            "For adult audiences with a taste for the classics.",
        ],
        "vibe_en": [
            "🕯️ Best Watched: Evening with a dark drink and respect for the genre. Alone or with someone who knows Sergio Leone.",
            "🕯️ Best Watched: Quiet evening with a good screen. A western needs space — give it that.",
        ],
    },
}

# Default fallback templates
DEFAULT_GENRE = "Drama"

def get_genre_key(genre_str):
    """Get the best matching genre key from our templates"""
    if not genre_str:
        return DEFAULT_GENRE
    genres = [g.strip() for g in genre_str.split(',')]
    # Priority order
    priority = ["Horror", "Sci-Fi", "War", "Western", "Animation", "Mystery", "Crime",
                "Thriller", "Action", "Adventure", "Fantasy", "Music", "History",
                "Romance", "Documentary", "Comedy", "Family", "Drama"]
    for p in priority:
        if p in genres:
            return p
    return DEFAULT_GENRE

def pick(lst):
    return random.choice(lst)

def generate_review_ru(tmdb_id, title_ru, title, year, genre, description_ru, description):
    """Generate Russian editorial review"""
    g = get_genre_key(genre)
    t = RU_TEMPLATES.get(g, RU_TEMPLATES[DEFAULT_GENRE])
    
    p1 = pick(t["p1"])
    p2 = pick(t["p2"])
    p3 = pick(t["p3"])
    vibe = pick(t["vibe_ru"])
    
    return f"{p1}\n\n{p2}\n\n{p3}\n\n{vibe}"

def generate_review_en(tmdb_id, title_ru, title, year, genre, description_ru, description):
    """Generate English editorial review"""
    g = get_genre_key(genre)
    t = RU_TEMPLATES.get(g, RU_TEMPLATES[DEFAULT_GENRE])
    
    p1 = pick(t["p1_en"])
    p2 = pick(t["p2_en"])
    p3 = pick(t["p3_en"])
    vibe = pick(t["vibe_en"])
    
    return f"{p1}\n\n{p2}\n\n{p3}\n\n{vibe}"

def main():
    random.seed(42)
    
    print("🎬 Крейк — запуск генерации отзывов")
    
    pg = psycopg2.connect("postgresql://postgres:OLIBHomUThkXFlbrgpJWyeZblHZdJQvj@gondola.proxy.rlwy.net:54122/railway")
    pg.autocommit = False
    cur = pg.cursor()
    
    cur.execute("SELECT tmdb_id FROM ai_reviews WHERE lang='ru'")
    done = set(r[0] for r in cur.fetchall())
    print(f"Уже готово: {len(done)} отзывов RU")
    
    db = sqlite3.connect("/home/moneyfast/projects/moviefinder/data/moviefinder.db")
    movies = db.execute("""
        SELECT tmdb_id, title_ru, title, year, genre, description_ru, description
        FROM movies
        WHERE year IN (2025, 2026)
        ORDER BY year DESC, rating DESC
    """).fetchall()
    
    todo = [m for m in movies if m[0] not in done]
    total = len(todo)
    print(f"Осталось: {total} фильмов 2025-2026")
    print()
    
    batch_size = 30
    done_count = 0
    errors = 0
    
    for i, movie in enumerate(todo):
        tmdb_id, title_ru, title, year, genre, description_ru, description = movie
        
        try:
            ru_text = generate_review_ru(tmdb_id, title_ru, title, year, genre, description_ru, description)
            en_text = generate_review_en(tmdb_id, title_ru, title, year, genre, description_ru, description)
            
            cur.execute(
                "INSERT INTO ai_reviews (tmdb_id, lang, review) VALUES (%s,%s,%s) ON CONFLICT (tmdb_id, lang) DO UPDATE SET review=EXCLUDED.review",
                (tmdb_id, 'ru', ru_text)
            )
            cur.execute(
                "INSERT INTO ai_reviews (tmdb_id, lang, review) VALUES (%s,%s,%s) ON CONFLICT (tmdb_id, lang) DO UPDATE SET review=EXCLUDED.review",
                (tmdb_id, 'en', en_text)
            )
            
            done_count += 1
            
            # Commit every 30
            if done_count % batch_size == 0:
                pg.commit()
                print(f"  Батч #{done_count // batch_size}: сохранено {batch_size} отзывов")
            
            # Report every 300
            if done_count % 300 == 0:
                print(f"✅ {done_count}/{total} готово")
                sys.stdout.flush()
                
        except Exception as e:
            errors += 1
            print(f"  ⚠️ Ошибка tmdb_id={tmdb_id}: {e}")
            if errors > 10:
                print("  ❌ Слишком много ошибок, останавливаюсь")
                pg.rollback()
                break
    
    # Final commit
    try:
        pg.commit()
        print(f"\n✅ Финальный коммит выполнен")
    except Exception as e:
        print(f"❌ Ошибка финального коммита: {e}")
    
    print(f"\n🎬 Готово! Обработано {done_count}/{total} фильмов. Ошибок: {errors}")
    
    # Stats
    cur.execute("SELECT COUNT(*) FROM ai_reviews WHERE lang='ru'")
    total_ru = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ai_reviews WHERE lang='en'")
    total_en = cur.fetchone()[0]
    print(f"📊 Итого в базе: RU={total_ru}, EN={total_en}")

if __name__ == "__main__":
    main()
