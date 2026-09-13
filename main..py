#!usrbinenv python3
# -*- coding: utf-8 -*-

Бот найма и обучения трафферов
python-telegram-bot = 20.0

import calendar
import logging
import sqlite3
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ═══════════════════════════════════════════════════════════
#  КОНФИГУРАЦИЯ - заполни перед запуском
# ═══════════════════════════════════════════════════════════
BOT_TOKEN         = 8701060830:AAE9FpR9UGMlIwV0N9HOH_-Ki5JNYNcN5OA           # токен от @BotFather
TEAMLEAD_USERNAME = @genera_love23    # без кавычек
TEAMLEAD_ID       = 7916675830                       # числовой Telegram ID тимлида
GROUP_A_ID        = -5486581119                      # ID группы А  (новые заявки)
GROUP_B_ID        = -5377753183                       # ID группы Б  (статусы обучения)
DB_PATH           = traffer_bot.db
STUCK_HOURS       = 24                      # часов до уведомления «завис»
CHECK_INTERVAL    = 3600                    # интервал проверки зависших (сек)

# ═══════════════════════════════════════════════════════════
#  СТАДИИ
# ═══════════════════════════════════════════════════════════
S_APPLIED    = applied
S_GEO        = geo
S_AGE        = age
S_DEVICE     = device
S_EXP        = experience
S_QUALIFIED  = qualified
S_WAIT_TL    = wait_teamlead
S_MOD1_SHOWN = mod1_shown
S_MOD1_DONE  = mod1_done
S_MOD2_SHOWN = mod2_shown
S_MOD2_DONE  = mod2_done
S_MOD3_SHOWN = mod3_shown
S_MOD3_DONE  = mod3_done
S_CONTENT    = content_given

logging.basicConfig(format=%(asctime)s  %(levelname)s  %(message)s, level=logging.INFO)
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  DATABASE
# ═══════════════════════════════════════════════════════════
def init_db() - None
    with sqlite3.connect(DB_PATH) as c
        c.executescript(
            CREATE TABLE IF NOT EXISTS leads (
                user_id         INTEGER PRIMARY KEY,
                username        TEXT,
                full_name       TEXT,
                geo             TEXT,
                age             TEXT,
                device          TEXT,
                experience      TEXT,
                lead_type       TEXT,
                stage           TEXT DEFAULT 'applied',
                started_at      TEXT,
                anketa_at       TEXT,
                qualified_at    TEXT,
                mod1_at         TEXT,
                mod2_at         TEXT,
                mod3_at         TEXT,
                content_at      TEXT,
                stuck_notified  INTEGER DEFAULT 0,
                week_num        INTEGER,
                month_num       INTEGER,
                year_num        INTEGER
            );
        )


def lead_get(user_id int) - dict  None
    with sqlite3.connect(DB_PATH) as conn
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            SELECT  FROM leads WHERE user_id = , (user_id,)
        ).fetchone()
    return dict(row) if row else None


def lead_set(user_id int, fields) - None
    with sqlite3.connect(DB_PATH) as conn
        if not conn.execute(
            SELECT 1 FROM leads WHERE user_id = , (user_id,)
        ).fetchone()
            now = datetime.now()
            conn.execute(
                INSERT INTO leads 
                (user_id, started_at, week_num, month_num, year_num, stage) 
                VALUES (, , , , , 'applied'),
                (user_id, now.isoformat(),
                 now.isocalendar()[1], now.month, now.year),
            )
        if fields
            pairs = , .join(f{k} =  for k in fields)
            conn.execute(
                fUPDATE leads SET {pairs} WHERE user_id = ,
                [fields.values(), user_id],
            )


def lead_stage(user_id int) - str  None
    lead = lead_get(user_id)
    return lead[stage] if lead else None


def get_stats(, week int = None, month int = None, year int = None) - dict
    now  = datetime.now()
    year = year or now.year
    if week
        cond = fweek_num = {week} AND year_num = {year}
    elif month
        cond = fmonth_num = {month} AND year_num = {year}
    else
        cond = 1=1
    with sqlite3.connect(DB_PATH) as c
        r = c.execute(f
            SELECT COUNT(),
                   SUM(anketa_at    IS NOT NULL),
                   SUM(qualified_at IS NOT NULL),
                   SUM(lead_type = 'newbie'),
                   SUM(lead_type = 'experienced'),
                   SUM(mod1_at      IS NOT NULL),
                   SUM(mod2_at      IS NOT NULL),
                   SUM(mod3_at      IS NOT NULL),
                   SUM(content_at   IS NOT NULL)
            FROM leads WHERE {cond}
        ).fetchone()
    keys = [total, anketa, qualified, newbies, experienced,
            mod1, mod2, mod3, content]
    return {k (v or 0) for k, v in zip(keys, r)}


# ═══════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════
def is_tl(uid int) - bool
    return uid == TEAMLEAD_ID


async def grp_a(ctx ContextTypes.DEFAULT_TYPE, text str) - None
    Группа А - новые заявки, всегда требуют реакции.
    if GROUP_A_ID
        try
            await ctx.bot.send_message(GROUP_A_ID, text, parse_mode=HTML)
        except Exception as e
            log.warning(Group A send error %s, e)


async def grp_b(ctx ContextTypes.DEFAULT_TYPE, text str) - None
    Группа Б - статусы обучения, только отклонения.
    if GROUP_B_ID
        try
            await ctx.bot.send_message(GROUP_B_ID, text, parse_mode=HTML)
        except Exception as e
            log.warning(Group B send error %s, e)


def utag(uid int, username str = None, full_name str = None) - str
    if username
        return f@{username.lstrip('@')}
    return f'a href=tguserid={uid}{full_name or uid}a'


def pbar(done int) - str
    return [▓▓░░░, ▓▓▓▓░, ▓▓▓▓▓][done - 1]


def fmt_stats(data dict, label str) - str
    n = data[total]
    def p(x) return f ({x  100  n}%) if n  0 else 
    return (
        f📊 b{label}bnn
        f📥 Заявок         b{n}bn
        f📋 Анкета         b{data['anketa']}b{p(data['anketa'])}n
        f✅ Квалифиц.      b{data['qualified']}b{p(data['qualified'])}n
        f   🟢 Новички     b{data['newbies']}bn
        f   🔵 Опытные     b{data['experienced']}bn
        f📖 Модуль 1       b{data['mod1']}b{p(data['mod1'])}n
        f⚙️ Модуль 2       b{data['mod2']}b{p(data['mod2'])}n
        f🌐 Модуль 3       b{data['mod3']}b{p(data['mod3'])}n
        f📦 Контент выдан  b{data['content']}b{p(data['content'])}n
    )


# ═══════════════════════════════════════════════════════════
#  KEYBOARDS
# ═══════════════════════════════════════════════════════════
KB_START = InlineKeyboardMarkup([[
    InlineKeyboardButton(▶️ Заполнить анкету, callback_data=anketa_start)
]])
KB_GEO = InlineKeyboardMarkup([
    [InlineKeyboardButton(🇷🇺 Россия,     callback_data=geo_ru),
     InlineKeyboardButton(🇺🇦 Украина,   callback_data=geo_ua)],
    [InlineKeyboardButton(🇧🇾 Беларусь,  callback_data=geo_by),
     InlineKeyboardButton(🇰🇿 Казахстан, callback_data=geo_kz)],
    [InlineKeyboardButton(🌍 Другое,     callback_data=geo_other)],
])
KB_AGE = InlineKeyboardMarkup([
    [InlineKeyboardButton(До 18, callback_data=age_u18),
     InlineKeyboardButton(18–25, callback_data=age_18)],
    [InlineKeyboardButton(26–35, callback_data=age_26),
     InlineKeyboardButton(36+,   callback_data=age_36)],
])
KB_DEVICE = InlineKeyboardMarkup([
    [InlineKeyboardButton(📱 Android,        callback_data=dev_android)],
    [InlineKeyboardButton(🍎 iPhone (iOS),   callback_data=dev_ios)],
    [InlineKeyboardButton(💻 Компьютер,      callback_data=dev_pc)],
    [InlineKeyboardButton(📵 Нет устройства, callback_data=dev_none)],
])
KB_EXP = InlineKeyboardMarkup([
    [InlineKeyboardButton(✅ Да, есть опыт, callback_data=exp_yes)],
    [InlineKeyboardButton(❌ Нет, новичок,  callback_data=exp_no)],
])
KB_CANT_WRITE = InlineKeyboardMarkup([[
    InlineKeyboardButton(🚫 Не могу написать первым, callback_data=cant_write)
]])
KB_MOD1 = InlineKeyboardMarkup([[
    InlineKeyboardButton(📖 Начать Модуль 1, callback_data=mod_1_start)
]])


def kb_next_mod(n int) - InlineKeyboardMarkup
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f📖 Перейти к Модулю {n}, callback_data=fmod_{n}_start)
    ]])


# ═══════════════════════════════════════════════════════════
#  start
# ═══════════════════════════════════════════════════════════
async def cmd_start(update Update, ctx ContextTypes.DEFAULT_TYPE) - None
    u = update.effective_user
    lead_set(u.id, username=u.username, full_name=u.full_name, stage=S_APPLIED)
    await grp_a(ctx,
        f📥 bНовая заявкаbn
        f👤 {utag(u.id, u.username, u.full_name)}n
        f🕐 {datetime.now().strftime('%d.%m.%Y %H%M')}
    )
    await update.message.reply_text(
        👋 bПривет!bnn
        [Вставь сюда текст приветствия - суть работы, откуда доход]nn
        📹 [Ссылка на VSL-видео]nn
        fВопросы - напиши тимлиду {TEAMLEAD_USERNAME}nn
        Заполни короткую анкету 👇,
        reply_markup=KB_START,
        parse_mode=HTML,
    )


# ═══════════════════════════════════════════════════════════
#  АНКЕТА
# ═══════════════════════════════════════════════════════════
async def cb_anketa_start(update Update, ctx ContextTypes.DEFAULT_TYPE) - None
    q = update.callback_query
    await q.answer()
    lead_set(q.from_user.id, stage=S_GEO)
    await q.edit_message_text(
        🌍 bИз какой ты страныb,
        reply_markup=KB_GEO, parse_mode=HTML,
    )


GEO_MAP = {
    geo_ru 🇷🇺 Россия, geo_ua 🇺🇦 Украина,
    geo_by 🇧🇾 Беларусь, geo_kz 🇰🇿 Казахстан,
    geo_other 🌍 Другое,
}


async def cb_geo(update Update, ctx ContextTypes.DEFAULT_TYPE) - None
    q = update.callback_query
    await q.answer()
    if lead_stage(q.from_user.id) != S_GEO
        return
    lead_set(q.from_user.id, geo=GEO_MAP[q.data], stage=S_AGE)
    await q.edit_message_text(
        🎂 bСколько тебе летb,
        reply_markup=KB_AGE, parse_mode=HTML,
    )


AGE_MAP = {
    age_u18 До 18, age_18 18–25,
    age_26 26–35,  age_36 36+,
}


async def cb_age(update Update, ctx ContextTypes.DEFAULT_TYPE) - None
    q = update.callback_query
    await q.answer()
    if lead_stage(q.from_user.id) != S_AGE
        return
    lead_set(q.from_user.id, age=AGE_MAP[q.data], stage=S_DEVICE)
    await q.edit_message_text(
        📱 bКакое устройство для работыb,
        reply_markup=KB_DEVICE, parse_mode=HTML,
    )


DEV_MAP = {
    dev_android Android, dev_ios iPhone (iOS),
    dev_pc Компьютер,    dev_none Нет устройства,
}


async def cb_device(update Update, ctx ContextTypes.DEFAULT_TYPE) - None
    q = update.callback_query
    await q.answer()
    if lead_stage(q.from_user.id) != S_DEVICE
        return
    lead_set(q.from_user.id, device=DEV_MAP[q.data], stage=S_EXP)
    await q.edit_message_text(
        💼 bЕсть ли опыт в трафикеарбитражеb,
        reply_markup=KB_EXP, parse_mode=HTML,
    )


async def cb_experience(update Update, ctx ContextTypes.DEFAULT_TYPE) - None
    q = update.callback_query
    await q.answer()
    u = q.from_user
    if lead_stage(u.id) != S_EXP
        return

    exp   = yes if q.data == exp_yes else no
    now   = datetime.now().isoformat()
    lead  = lead_get(u.id)
    ltype = experienced if exp == yes else newbie
    stage = S_WAIT_TL if exp == yes else S_QUALIFIED

    lead_set(u.id, experience=exp, lead_type=ltype,
             stage=stage, anketa_at=now, qualified_at=now)

    await grp_a(ctx,
        f📋 bАнкета заполненаbn
        f👤 {utag(u.id, u.username, u.full_name)}n
        f🌍 {lead.get('geo','-')}  🎂 {lead.get('age','-')}  
        f📱 {lead.get('device','-')}n
        f💼 Опыт {'Есть → ждёт разговора' if exp == 'yes' else 'Нет → обучение'}
    )

    if exp == no
        await _show_newbie(q, u, ctx)
    else
        await _show_exp_gate(q, u, ctx)


async def _show_newbie(q, u, ctx ContextTypes.DEFAULT_TYPE) - None
    await grp_a(ctx,
        f✅ bКвалифицирован НОВИЧОКbn
        f👤 {utag(u.id, u.username, u.full_name)} → идёт в обучение
    )
    await q.edit_message_text(
        🎓 bУсловия для новичковbnn
        [Вставь сюда свои условия]nn
        📚 3 модуля обученияn
        • Модуль 1 - базовый мануалn
        • Модуль 2 - настройка телефонаn
        • Модуль 3 - сайт-прокладка и аккаунтыnn
        fВопросы {TEAMLEAD_USERNAME},
        reply_markup=KB_MOD1,
        parse_mode=HTML,
    )


async def _show_exp_gate(q, u, ctx ContextTypes.DEFAULT_TYPE) - None
    await grp_a(ctx,
        f⚡️ bОПЫТНЫЙ трафер ждёт разговораbn
        f👤 {utag(u.id, u.username, u.full_name)}n
        f🔑 unlock {u.id}    🔄 set_newbie {u.id}
    )
    await q.edit_message_text(
        👋 Для опытных трафферов - особые условия.nn
        ⚠️ bНужен личный разговор с тимлидом.bnn
        fНапиши {TEAMLEAD_USERNAME}nn
        После разговора он откроет тебе доступ.,
        reply_markup=KB_CANT_WRITE,
        parse_mode=HTML,
    )


async def cb_cant_write(update Update, ctx ContextTypes.DEFAULT_TYPE) - None
    q = update.callback_query
    await q.answer(Уведомили тимлида ✅)
    u = q.from_user
    await grp_a(ctx,
        f🔔 bНе может написать первымbn
        f👤 {utag(u.id, u.username, u.full_name)}  code{u.id}coden
        f📲 Напиши ему сам!
    )
    await q.edit_message_text(
        ✅ Тимлид получил уведомление и напишет сам.nn
        fИли напиши позже {TEAMLEAD_USERNAME}
    )


# ═══════════════════════════════════════════════════════════
#  МОДУЛИ ОБУЧЕНИЯ
# ═══════════════════════════════════════════════════════════
MOD_TEXTS = {
    1 (
        📖 bМодуль 1 - Базовый мануалbnn
        [Вставь содержание мануала]nn
        ━━━━━━━━━━n
        📸 bЗаданиеb прочитай, сделай скриншот и отправь его сюда.
    ),
    2 (
        ⚙️ bМодуль 2 - Настройка телефонаbnn
        [Вставь инструкцию по настройке]nn
        ━━━━━━━━━━n
        📸 bЗаданиеb настрой телефон, сделай скриншот и отправь.
    ),
    3 (
        🌐 bМодуль 3 - Сайт-прокладка и аккаунтыbnn
        [Вставь инструкцию]nn
        ━━━━━━━━━━n
        📸 bЗаданиеb отправь скриншотыn
        1. Готовый сайтn
        2. 3 оформленных аккаунта
    ),
}

MOD_ALLOWED = {1 S_QUALIFIED,  2 S_MOD1_DONE, 3 S_MOD2_DONE}
MOD_SHOWN   = {1 S_MOD1_SHOWN, 2 S_MOD2_SHOWN, 3 S_MOD3_SHOWN}


async def cb_mod_start(update Update, ctx ContextTypes.DEFAULT_TYPE) - None
    q = update.callback_query
    await q.answer()
    u   = q.from_user
    mod = int(q.data.split(_)[1])       # mod_1_start → 1
    if lead_stage(u.id) != MOD_ALLOWED[mod]
        await q.answer(Сначала завершите предыдущий этап, show_alert=True)
        return
    lead_set(u.id, stage=MOD_SHOWN[mod], stuck_notified=0)
    await q.edit_message_text(
        MOD_TEXTS[mod] + fnnВопросы {TEAMLEAD_USERNAME},
        parse_mode=HTML,
    )


async def handle_report(update Update, ctx ContextTypes.DEFAULT_TYPE) - None
    u     = update.effective_user
    stage = lead_stage(u.id)
    now   = datetime.now().isoformat()

    if stage == S_MOD1_SHOWN
        lead_set(u.id, stage=S_MOD1_DONE, mod1_at=now, stuck_notified=0)
        await grp_b(ctx,
            f✅ bМодуль 1 сданbn
            f👤 {utag(u.id, u.username, u.full_name)}
        )
        await update.message.reply_text(
            f✅ bМодуль 1 принят!bnn
            fПрогресс {pbar(1)} 13nn
            fХорошая работа! 💪 Следующий шаг 👇,
            reply_markup=kb_next_mod(2), parse_mode=HTML,
        )

    elif stage == S_MOD2_SHOWN
        lead_set(u.id, stage=S_MOD2_DONE, mod2_at=now, stuck_notified=0)
        await grp_b(ctx,
            f✅ bМодуль 2 сданbn
            f👤 {utag(u.id, u.username, u.full_name)}
        )
        await update.message.reply_text(
            f✅ bМодуль 2 принят!bnn
            fПрогресс {pbar(2)} 23nn
            fПочти финиш! 🔥 Последний модуль 👇,
            reply_markup=kb_next_mod(3), parse_mode=HTML,
        )

    elif stage == S_MOD3_SHOWN
        lead_set(u.id, stage=S_MOD3_DONE, mod3_at=now, stuck_notified=0)
        await grp_b(ctx,
            f✅ bМодуль 3 сданbn
            f👤 {utag(u.id, u.username, u.full_name)}n
            f⚡️ Готов к получению контента!
        )
        await grp_a(ctx,
            f🏆 bОбучение завершено!bn
            f👤 {utag(u.id, u.username, u.full_name)}n
            f📦 Выдай контент и инвайт вручнуюn
            f✅ После выдачи mark_content {u.id}
        )
        await update.message.reply_text(
            f🏆 bВсе модули пройдены!bnn
            fПрогресс {pbar(3)} 33 ✅nn
            fТимлид скоро выдаст контент и доступ.n
            fНет ответа - напиши сам {TEAMLEAD_USERNAME},
            parse_mode=HTML,
        )
    # Иначе - сообщение не в фазе модулей, игнорируем


# ═══════════════════════════════════════════════════════════
#  КОМАНДЫ ТИМЛИДА
# ═══════════════════════════════════════════════════════════
async def cmd_help_tl(update Update, ctx ContextTypes.DEFAULT_TYPE) - None
    if not is_tl(update.effective_user.id)
        return
    await update.message.reply_text(
        🤖 bКоманды тимлидаbnn
        lead ID - карточка лидаn
        unlock ID - разблокировать опытногоn
        set_newbie ID - перевести опытного в новичкиn
        mark_content ID - отметить выдачу контентаnn
        stats - неделя + месяц (текущие)n
        stats week N - неделя N текущего годаn
        stats month N - месяц N (1–12) текущего года,
        parse_mode=HTML,
    )


async def cmd_lead(update Update, ctx ContextTypes.DEFAULT_TYPE) - None
    if not is_tl(update.effective_user.id)
        return
    if not ctx.args
        await update.message.reply_text(lead USER_ID)
        return
    try
        tid = int(ctx.args[0])
    except ValueError
        await update.message.reply_text(ID должен быть числом)
        return
    lead = lead_get(tid)
    if not lead
        await update.message.reply_text(Лид не найден)
        return

    def f(k)
        v = lead.get(k)
        return v[16] if v else -

    await update.message.reply_text(
        f👤 bЛид {tid}b  @{lead.get('username') or '-'}  
        f{lead.get('full_name') or ''}n
        f━━━━━━━━━━n
        f🌍 {lead.get('geo','-')}  🎂 {lead.get('age','-')}  
        f📱 {lead.get('device','-')}n
        f💼 Опыт {lead.get('experience','-')}  Тип {lead.get('lead_type','-')}n
        fСтадия b{lead.get('stage','-')}bn
        f━━━━━━━━━━n
        f📅 Зашёл   {f('started_at')}n
        f📋 Анкета  {f('anketa_at')}n
        f✅ Квалиф. {f('qualified_at')}n
        fM1 {f('mod1_at')}  M2 {f('mod2_at')}  M3 {f('mod3_at')}n
        f📦 Контент {f('content_at')},
        parse_mode=HTML,
    )


async def cmd_unlock(update Update, ctx ContextTypes.DEFAULT_TYPE) - None
    unlock USER_ID - разблокировать опытного, направить к выдаче контента
    if not is_tl(update.effective_user.id)
        return
    if not ctx.args
        await update.message.reply_text(unlock USER_ID)
        return
    try
        tid = int(ctx.args[0])
    except ValueError
        await update.message.reply_text(ID должен быть числом)
        return
    if not lead_get(tid)
        await update.message.reply_text(Лид не найден)
        return

    lead_set(tid, stage=S_MOD3_DONE)
    try
        await ctx.bot.send_message(
            tid,
            ✅ bТимлид открыл тебе доступ!bnn
            fЖди - скоро получишь контент и инвайт.n{TEAMLEAD_USERNAME},
            parse_mode=HTML,
        )
    except Exception
        await update.message.reply_text(
            ⚠️ Не удалось написать пользователю (бот заблокирован)
        )
        return
    await update.message.reply_text(f✅ {tid} разблокирован - ждёт выдачи контента)


async def cmd_set_newbie(update Update, ctx ContextTypes.DEFAULT_TYPE) - None
    set_newbie USER_ID - перевести опытного на сценарий новичка
    if not is_tl(update.effective_user.id)
        return
    if not ctx.args
        await update.message.reply_text(set_newbie USER_ID)
        return
    try
        tid = int(ctx.args[0])
    except ValueError
        await update.message.reply_text(ID должен быть числом)
        return
    if not lead_get(tid)
        await update.message.reply_text(Лид не найден)
        return

    lead_set(tid, lead_type=newbie, stage=S_QUALIFIED,
             qualified_at=datetime.now().isoformat())
    try
        await ctx.bot.send_message(
            tid,
            👋 Тимлид предлагает пройти обучение с нуля - это стандартный путь.nn
            [Вставь условия для новичков]nn
            fВопросы {TEAMLEAD_USERNAME},
            reply_markup=KB_MOD1,
            parse_mode=HTML,
        )
    except Exception
        await update.message.reply_text(⚠️ Не удалось написать пользователю)
        return
    await update.message.reply_text(f✅ {tid} п��реведён в новички)


async def cmd_mark_content(update Update, ctx ContextTypes.DEFAULT_TYPE) - None
    mark_content USER_ID - зафиксировать выдачу контента вручную
    if not is_tl(update.effective_user.id)
        return
    if not ctx.args
        await update.message.reply_text(mark_content USER_ID)
        return
    try
        tid = int(ctx.args[0])
    except ValueError
        await update.message.reply_text(ID должен быть числом)
        return
    lead_set(tid, stage=S_CONTENT, content_at=datetime.now().isoformat())
    await update.message.reply_text(f✅ Контент отмечен выданным для {tid})


async def cmd_stats(update Update, ctx ContextTypes.DEFAULT_TYPE) - None
    stats  stats week N  stats month N
    if not is_tl(update.effective_user.id)
        return
    now  = datetime.now()
    args = ctx.args or []
    if len(args) = 2 and args[0] == week
        w    = int(args[1])
        text = fmt_stats(get_stats(week=w, year=now.year), fНеделя {w}, {now.year})
    elif len(args) = 2 and args[0] == month
        m    = int(args[1])
        text = fmt_stats(get_stats(month=m, year=now.year),
                         f{calendar.month_name[m]} {now.year})
    else
        cw   = now.isocalendar()[1]
        text = (
            fmt_stats(get_stats(week=cw, year=now.year), fНеделя {cw} (текущая))
            + n
            + fmt_stats(get_stats(month=now.month, year=now.year),
                        f{now.strftime('%B %Y')})
        )
    await update.message.reply_text(text, parse_mode=HTML)


# ════════════════════════════════════════════════��══════════
#  SCHEDULED JOB - зависшие лиды (уведомление в Группу Б)
# ═══════════════════════════════════════════════════════════
# (stage → (поле-флаг выполнения, метка, от какого времени считать))
STUCK_WATCH = {
    S_QUALIFIED  (mod1_at, не начал Модуль 1,  qualified_at),
    S_MOD1_SHOWN (mod1_at, завис на Модуле 1,  qualified_at),
    S_MOD1_DONE  (mod2_at, не начал Модуль 2,  mod1_at),
    S_MOD2_SHOWN (mod2_at, завис на Модуле 2,  mod1_at),
    S_MOD2_DONE  (mod3_at, не начал Модуль 3,  mod2_at),
    S_MOD3_SHOWN (mod3_at, завис на Модуле 3,  mod2_at),
}


async def job_stuck(ctx ContextTypes.DEFAULT_TYPE) - None
    threshold = (datetime.now() - timedelta(hours=STUCK_HOURS)).isoformat()
    with sqlite3.connect(DB_PATH) as conn
        conn.row_factory = sqlite3.Row
        for stage, (done_col, label, time_col) in STUCK_WATCH.items()
            rows = conn.execute(f
                SELECT  FROM leads
                WHERE stage = 
                  AND {done_col} IS NULL
                  AND stuck_notified = 0
                  AND {time_col} IS NOT NULL
                  AND {time_col}  
            , (stage, threshold)).fetchall()
            for r in rows
                r   = dict(r)
                uid = r[user_id]
                await grp_b(ctx,
                    f⏰ bЗавис  {STUCK_HOURS}чbn
                    f👤 {utag(uid, r.get('username'), r.get('full_name'))}n
                    f📍 {label}nlead {uid}
                )
                lead_set(uid, stuck_notified=1)


# ═══════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════
def main() - None
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler(start,        cmd_start))
    app.add_handler(CommandHandler(help,         cmd_help_tl))
    app.add_handler(CommandHandler(lead,         cmd_lead))
    app.add_handler(CommandHandler(unlock,       cmd_unlock))
    app.add_handler(CommandHandler(set_newbie,   cmd_set_newbie))
    app.add_handler(CommandHandler(mark_content, cmd_mark_content))
    app.add_handler(CommandHandler(stats,        cmd_stats))

    # Callback-кнопки
    app.add_handler(CallbackQueryHandler(cb_anketa_start, pattern=^anketa_start$))
    app.add_handler(CallbackQueryHandler(cb_geo,          pattern=^geo_))
    app.add_handler(CallbackQueryHandler(cb_age,          pattern=^age_))
    app.add_handler(CallbackQueryHandler(cb_device,       pattern=^dev_))
    app.add_handler(CallbackQueryHandler(cb_experience,   pattern=^exp_))
    app.add_handler(CallbackQueryHandler(cb_cant_write,   pattern=^cant_write$))
    app.add_handler(CallbackQueryHandler(cb_mod_start,    pattern=r^mod_[123]_start$))

    # Приём отчётов (фото  документ)
    app.add_handler(MessageHandler(filters.PHOTO  filters.Document.ALL, handle_report))

    # Проверка зависших - раз в час
    app.job_queue.run_repeating(job_stuck, interval=CHECK_INTERVAL, first=60)

    log.info(🤖 Бот запущен)
    app.run_polling(drop_pending_updates=True)


if __name__ == __main__
    main()
