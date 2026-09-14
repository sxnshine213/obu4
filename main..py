#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
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

# =============================================================
#  CONFIG
# =============================================================
BOT_TOKEN         = "8701060830:AAE9FpR9UGMlIwV0N9HOH_-Ki5JNYNcN5OA"
TEAMLEAD_USERNAME = "@genera_love23"
TEAMLEAD_ID       = 7916675830
GROUP_A_ID        = -5486581119
GROUP_B_ID        = -5377753183
DB_PATH           = "traffer_bot.db"
STUCK_HOURS       = 24
CHECK_INTERVAL    = 3600

# =============================================================
#  STADII
# =============================================================
S_APPLIED    = "applied"
S_GEO        = "geo"
S_AGE        = "age"
S_DEVICE     = "device"
S_EXP        = "experience"
S_QUALIFIED  = "qualified"
S_WAIT_TL    = "wait_teamlead"
S_MOD1_SHOWN = "mod1_shown"
S_MOD1_DONE  = "mod1_done"
S_MOD2_SHOWN = "mod2_shown"
S_MOD2_DONE  = "mod2_done"
S_MOD3_SHOWN = "mod3_shown"
S_MOD3_DONE  = "mod3_done"
S_CONTENT    = "content_given"
S_BLOCKED    = "blocked"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)


# =============================================================
#  DATABASE
# =============================================================
def init_db():
    with sqlite3.connect(DB_PATH) as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS leads (
                user_id         INTEGER PRIMARY KEY,
                username        TEXT,
                full_name       TEXT,
                geo             TEXT,
                age             INTEGER,
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
        """)


def lead_get(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM leads WHERE user_id = ?", (user_id,)
        ).fetchone()
    return dict(row) if row else None


def lead_set(user_id, **fields):
    with sqlite3.connect(DB_PATH) as conn:
        if not conn.execute(
            "SELECT 1 FROM leads WHERE user_id = ?", (user_id,)
        ).fetchone():
            now = datetime.now()
            conn.execute(
                "INSERT INTO leads "
                "(user_id, started_at, week_num, month_num, year_num, stage) "
                "VALUES (?, ?, ?, ?, ?, 'applied')",
                (user_id, now.isoformat(),
                 now.isocalendar()[1], now.month, now.year),
            )
        if fields:
            pairs = ", ".join("{} = ?".format(k) for k in fields)
            conn.execute(
                "UPDATE leads SET {} WHERE user_id = ?".format(pairs),
                list(fields.values()) + [user_id],
            )


def lead_stage(user_id):
    lead = lead_get(user_id)
    return lead["stage"] if lead else None


def get_stats(week=None, month=None, year=None):
    now  = datetime.now()
    year = year or now.year
    if week:
        cond = "week_num = {} AND year_num = {}".format(week, year)
    elif month:
        cond = "month_num = {} AND year_num = {}".format(month, year)
    else:
        cond = "1=1"
    with sqlite3.connect(DB_PATH) as c:
        r = c.execute("""
            SELECT
                COUNT(*),
                SUM(anketa_at IS NOT NULL),
                SUM(qualified_at IS NOT NULL),
                SUM(lead_type = 'newbie'),
                SUM(lead_type = 'experienced'),
                SUM(stage = 'blocked'),
                SUM(stage IN ('mod1_shown','mod1_done','mod2_shown','mod2_done','mod3_shown','mod3_done','content_given')),
                SUM(stage IN ('mod2_shown','mod2_done','mod3_shown','mod3_done','content_given')),
                SUM(stage IN ('mod3_shown','mod3_done','content_given')),
                SUM(mod1_at IS NOT NULL),
                SUM(mod2_at IS NOT NULL),
                SUM(mod3_at IS NOT NULL),
                SUM(content_at IS NOT NULL)
            FROM leads WHERE {}
        """.format(cond)).fetchone()
    keys = [
        "total", "anketa", "qualified", "newbies", "experienced",
        "blocked",
        "on_mod1", "on_mod2", "on_mod3",
        "done_mod1", "done_mod2", "done_mod3",
        "content"
    ]
    return {k: (v or 0) for k, v in zip(keys, r)}


# =============================================================
#  HELPERS
# =============================================================
def is_tl(uid):
    return uid == TEAMLEAD_ID


async def grp_a(ctx, text):
    if GROUP_A_ID:
        try:
            await ctx.bot.send_message(GROUP_A_ID, text, parse_mode="HTML")
        except Exception as e:
            log.warning("Group A send error: %s", e)


async def grp_b(ctx, text):
    if GROUP_B_ID:
        try:
            await ctx.bot.send_message(GROUP_B_ID, text, parse_mode="HTML")
        except Exception as e:
            log.warning("Group B send error: %s", e)


def utag(uid, username=None, full_name=None):
    if username:
        return "@{}".format(username.lstrip("@"))
    return '<a href="tg://user?id={}">{}</a>'.format(uid, full_name or uid)


def pbar(done):
    return ["[1 из 3]", "[2 из 3]", "[3 из 3]"][done - 1]


def fmt_stats(data, label):
    n = data["total"]
    def p(x):
        return " ({}%)".format(x * 100 // n) if n > 0 else ""
    lines = [
        "<b>Статистика: {}</b>\n".format(label),
        "Запустили бота:        <b>{}</b>".format(n),
        "Заполнили анкету:      <b>{}</b>{}".format(data["anketa"], p(data["anketa"])),
        "Квалифицированы:       <b>{}</b>{}".format(data["qualified"], p(data["qualified"])),
        "  Новички:             <b>{}</b>".format(data["newbies"]),
        "  Опытные:             <b>{}</b>".format(data["experienced"]),
        "Заблокировано (до 18): <b>{}</b>".format(data["blocked"]),
        "",
        "--- Обучение ---",
        "Начали обучение:       <b>{}</b>{}".format(data["on_mod1"], p(data["on_mod1"])),
        "Дошли до модуля 2:     <b>{}</b>{}".format(data["on_mod2"], p(data["on_mod2"])),
        "Дошли до модуля 3:     <b>{}</b>{}".format(data["on_mod3"], p(data["on_mod3"])),
        "Сдали модуль 1:        <b>{}</b>".format(data["done_mod1"]),
        "Сдали модуль 2:        <b>{}</b>".format(data["done_mod2"]),
        "Сдали модуль 3:        <b>{}</b>".format(data["done_mod3"]),
        "Контент выдан:         <b>{}</b>{}".format(data["content"], p(data["content"])),
    ]
    return "\n".join(lines)


# =============================================================
#  KEYBOARDS
# =============================================================
KB_START = InlineKeyboardMarkup([[
    InlineKeyboardButton("Заполнить анкету", callback_data="anketa_start")
]])

KB_GEO = InlineKeyboardMarkup([
    [InlineKeyboardButton("Россия",    callback_data="geo_ru"),
     InlineKeyboardButton("Украина",   callback_data="geo_ua")],
    [InlineKeyboardButton("Казахстан", callback_data="geo_kz"),
     InlineKeyboardButton("Европа",    callback_data="geo_eu")],
    [InlineKeyboardButton("Азия",      callback_data="geo_asia")],
])

GEO_MAP = {
    "geo_ru":   "Россия",
    "geo_ua":   "Украина",
    "geo_kz":   "Казахстан",
    "geo_eu":   "Европа",
    "geo_asia": "Азия",
}

KB_DEVICE = InlineKeyboardMarkup([
    [InlineKeyboardButton("Android",        callback_data="dev_android")],
    [InlineKeyboardButton("iPhone (iOS)",   callback_data="dev_ios")],
    [InlineKeyboardButton("Компьютер",      callback_data="dev_pc")],
    [InlineKeyboardButton("Нет устройства", callback_data="dev_none")],
])

DEV_MAP = {
    "dev_android": "Android",
    "dev_ios":     "iPhone (iOS)",
    "dev_pc":      "Компьютер",
    "dev_none":    "Нет устройства",
}

KB_EXP = InlineKeyboardMarkup([
    [InlineKeyboardButton("Да, есть опыт", callback_data="exp_yes")],
    [InlineKeyboardButton("Нет, новичок",  callback_data="exp_no")],
])

KB_CANT_WRITE = InlineKeyboardMarkup([[
    InlineKeyboardButton("Не могу написать первым", callback_data="cant_write")
]])

KB_MOD1 = InlineKeyboardMarkup([[
    InlineKeyboardButton("Начать Модуль 1", callback_data="mod_1_start")
]])


def kb_next_mod(n):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "Перейти к Модулю {}".format(n),
            callback_data="mod_{}_start".format(n)
        )
    ]])


# =============================================================
#  /start
# =============================================================
async def cmd_start(update, ctx):
    u = update.effective_user
    lead_set(u.id, username=u.username, full_name=u.full_name, stage=S_APPLIED)
    await grp_a(ctx,
        "<b>Новая заявка</b>\n"
        "Пользователь: {}\n"
        "Время: {}".format(
            utag(u.id, u.username, u.full_name),
            datetime.now().strftime("%d.%m.%Y %H:%M")
        )
    )
    await update.message.reply_text(
        "Привет!\n\n"
        "[ТЕКСТ_ПРИВЕТСТВИЯ]\n\n"
        "[ССЫЛКА_НА_ВИДЕО]\n\n"
        "Вопросы — напиши тимлиду: {}\n\n"
        "Заполни короткую анкету:".format(TEAMLEAD_USERNAME),
        reply_markup=KB_START,
        parse_mode="HTML",
    )


# =============================================================
#  ANKETA
# =============================================================
async def cb_anketa_start(update, ctx):
    q = update.callback_query
    await q.answer()
    lead_set(q.from_user.id, stage=S_GEO)
    await q.edit_message_text(
        "<b>Из какой ты страны?</b>",
        reply_markup=KB_GEO,
        parse_mode="HTML",
    )


async def cb_geo(update, ctx):
    q = update.callback_query
    await q.answer()
    if lead_stage(q.from_user.id) != S_GEO:
        return
    lead_set(q.from_user.id, geo=GEO_MAP[q.data], stage=S_AGE)
    await q.edit_message_text(
        "<b>Сколько тебе лет?</b>\n\n"
        "Напиши цифрой, например: 22",
        parse_mode="HTML",
    )


async def handle_age_input(update, ctx):
    u     = update.effective_user
    stage = lead_stage(u.id)

    if stage != S_AGE:
        return

    text = update.message.text.strip()

    if not text.isdigit():
        await update.message.reply_text(
            "Пожалуйста, напиши возраст цифрой, например: 22"
        )
        return

    age = int(text)

    if age < 1 or age > 100:
        await update.message.reply_text(
            "Пожалуйста, укажи реальный возраст."
        )
        return

    if age < 18:
        lead_set(u.id, age=age, stage=S_BLOCKED)
        await grp_a(ctx,
            "<b>Заблокирован — до 18 лет</b>\n"
            "Пользователь: {}\n"
            "Возраст: {}".format(utag(u.id, u.username, u.full_name), age)
        )
        await update.message.reply_text(
            "К сожалению, мы не можем принять тебя на работу.\n"
            "Минимальный возраст для участия — 18 лет.\n\n"
            "Удачи!"
        )
        return

    lead_set(u.id, age=age, stage=S_DEVICE)
    await update.message.reply_text(
        "<b>Какое устройство для работы?</b>",
        reply_markup=KB_DEVICE,
        parse_mode="HTML",
    )


async def cb_device(update, ctx):
    q = update.callback_query
    await q.answer()
    if lead_stage(q.from_user.id) != S_DEVICE:
        return
    lead_set(q.from_user.id, device=DEV_MAP[q.data], stage=S_EXP)
    await q.edit_message_text(
        "<b>Есть ли опыт в трафике/арбитраже?</b>",
        reply_markup=KB_EXP,
        parse_mode="HTML",
    )


async def cb_experience(update, ctx):
    q = update.callback_query
    await q.answer()
    u = q.from_user
    if lead_stage(u.id) != S_EXP:
        return

    exp   = "yes" if q.data == "exp_yes" else "no"
    now   = datetime.now().isoformat()
    lead  = lead_get(u.id)
    ltype = "experienced" if exp == "yes" else "newbie"
    stage = S_WAIT_TL if exp == "yes" else S_QUALIFIED

    lead_set(u.id, experience=exp, lead_type=ltype,
             stage=stage, anketa_at=now, qualified_at=now)

    opyt_text = "Есть — ждёт разговора" if exp == "yes" else "Нет — идёт в обучение"
    await grp_a(ctx,
        "<b>Анкета заполнена</b>\n"
        "Пользователь: {}\n"
        "Страна: {} | Возраст: {} | Устройство: {}\n"
        "Опыт: {}".format(
            utag(u.id, u.username, u.full_name),
            lead.get("geo", "-"),
            lead.get("age", "-"),
            lead.get("device", "-"),
            opyt_text
        )
    )

    if exp == "no":
        await _show_newbie(q, u, ctx)
    else:
        await _show_exp_gate(q, u, ctx)


async def _show_newbie(q, u, ctx):
    await grp_a(ctx,
        "<b>Квалифицирован: НОВИЧОК</b>\n"
        "Пользователь: {} — идёт в обучение".format(
            utag(u.id, u.username, u.full_name)
        )
    )
    await q.edit_message_text(
        "<b>Условия для новичков:</b>\n\n"
        "[УСЛОВИЯ_НОВИЧОК]\n\n"
        "3 модуля обучения:\n"
        "- Модуль 1 — базовый мануал\n"
        "- Модуль 2 — настройка телефона\n"
        "- Модуль 3 — сайт-прокладка и аккаунты\n\n"
        "Вопросы? {}".format(TEAMLEAD_USERNAME),
        reply_markup=KB_MOD1,
        parse_mode="HTML",
    )


async def _show_exp_gate(q, u, ctx):
    await grp_a(ctx,
        "<b>ОПЫТНЫЙ трафер ждёт разговора</b>\n"
        "Пользователь: {}\n"
        "/unlock {}  |  /set_newbie {}".format(
            utag(u.id, u.username, u.full_name), u.id, u.id
        )
    )
    await q.edit_message_text(
        "Для опытных трафферов — особые условия.\n\n"
        "<b>Нужен личный разговор с тимлидом.</b>\n\n"
        "Напиши: {}\n\n"
        "После разговора он откроет тебе доступ.".format(TEAMLEAD_USERNAME),
        reply_markup=KB_CANT_WRITE,
        parse_mode="HTML",
    )


async def cb_cant_write(update, ctx):
    q = update.callback_query
    await q.answer("Уведомили тимлида")
    u = q.from_user
    await grp_a(ctx,
        "<b>Не может написать первым</b>\n"
        "Пользователь: {} | <code>{}</code>\n"
        "Напиши ему сам!".format(utag(u.id, u.username, u.full_name), u.id)
    )
    await q.edit_message_text(
        "Тимлид получил уведомление и напишет сам.\n\n"
        "Или напиши позже: {}".format(TEAMLEAD_USERNAME)
    )


# =============================================================
#  MODULI
# =============================================================
MOD_TEXTS = {
    1: (
        "<b>Модуль 1 — Базовый мануал</b>\n\n"
        "[СОДЕРЖАНИЕ_МОДУЛЯ_1]\n\n"
        "----------\n"
        "<b>Задание:</b> прочитай, сделай скриншот и отправь его сюда."
    ),
    2: (
        "<b>Модуль 2 — Настройка телефона</b>\n\n"
        "[ИНСТРУКЦИЯ_НАСТРОЙКИ]\n\n"
        "----------\n"
        "<b>Задание:</b> настрой телефон, сделай скриншот и отправь."
    ),
    3: (
        "<b>Модуль 3 — Сайт-прокладка и аккаунты</b>\n\n"
        "[ИНСТРУКЦИЯ_МОДУЛЯ_3]\n\n"
        "----------\n"
        "<b>Задание:</b> отправь скриншоты:\n"
        "1. Готовый сайт\n"
        "2. 3 оформленных аккаунта"
    ),
}

MOD_ALLOWED = {1: S_QUALIFIED, 2: S_MOD1_DONE, 3: S_MOD2_DONE}
MOD_SHOWN   = {1: S_MOD1_SHOWN, 2: S_MOD2_SHOWN, 3: S_MOD3_SHOWN}


async def cb_mod_start(update, ctx):
    q = update.callback_query
    await q.answer()
    u   = q.from_user
    mod = int(q.data.split("_")[1])
    if lead_stage(u.id) != MOD_ALLOWED[mod]:
        await q.answer("Сначала завершите предыдущий этап", show_alert=True)
        return
    lead_set(u.id, stage=MOD_SHOWN[mod], stuck_notified=0)
    await q.edit_message_text(
        MOD_TEXTS[mod] + "\n\nВопросы? {}".format(TEAMLEAD_USERNAME),
        parse_mode="HTML",
    )


async def handle_report(update, ctx):
    u     = update.effective_user
    stage = lead_stage(u.id)
    now   = datetime.now().isoformat()

    if stage == S_MOD1_SHOWN:
        lead_set(u.id, stage=S_MOD1_DONE, mod1_at=now, stuck_notified=0)
        await grp_b(ctx,
            "<b>Модуль 1 сдан</b>\n"
            "Пользователь: {}".format(utag(u.id, u.username, u.full_name))
        )
        await update.message.reply_text(
            "<b>Модуль 1 принят!</b>\n\n"
            "Прогресс: {}\n\n"
            "Отличная работа! Следующий шаг:".format(pbar(1)),
            reply_markup=kb_next_mod(2),
            parse_mode="HTML",
        )

    elif stage == S_MOD2_SHOWN:
        lead_set(u.id, stage=S_MOD2_DONE, mod2_at=now, stuck_notified=0)
        await grp_b(ctx,
            "<b>Модуль 2 сдан</b>\n"
            "Пользователь: {}".format(utag(u.id, u.username, u.full_name))
        )
        await update.message.reply_text(
            "<b>Модуль 2 принят!</b>\n\n"
            "Прогресс: {}\n\n"
            "Почти финиш! Последний модуль:".format(pbar(2)),
            reply_markup=kb_next_mod(3),
            parse_mode="HTML",
        )

    elif stage == S_MOD3_SHOWN:
        lead_set(u.id, stage=S_MOD3_DONE, mod3_at=now, stuck_notified=0)
        await grp_b(ctx,
            "<b>Модуль 3 сдан</b>\n"
            "Пользователь: {}\n"
            "Готов к получению контента!".format(utag(u.id, u.username, u.full_name))
        )
        await grp_a(ctx,
            "<b>Обучение завершено!</b>\n"
            "Пользователь: {}\n"
            "Выдай контент и инвайт вручную\n"
            "После выдачи: /mark_content {}".format(
                utag(u.id, u.username, u.full_name), u.id
            )
        )
        await update.message.reply_text(
            "<b>Все модули пройдены!</b>\n\n"
            "Прогресс: {}\n\n"
            "Тимлид скоро выдаст контент и доступ.\n"
            "Нет ответа — напиши сам: {}".format(pbar(3), TEAMLEAD_USERNAME),
            parse_mode="HTML",
        )


# =============================================================
#  KOMANDY TIMLIDA
# =============================================================
async def cmd_help_tl(update, ctx):
    if not is_tl(update.effective_user.id):
        return
    await update.message.reply_text(
        "<b>Команды тимлида</b>\n\n"
        "/lead ID — карточка лида\n"
        "/unlock ID — разблокировать опытного\n"
        "/set_newbie ID — перевести опытного в новички\n"
        "/mark_content ID — отметить выдачу контента\n\n"
        "/stats — текущая неделя + месяц\n"
        "/stats week N — неделя N\n"
        "/stats month N — месяц N (1-12)",
        parse_mode="HTML",
    )


async def cmd_lead(update, ctx):
    if not is_tl(update.effective_user.id):
        return
    if not ctx.args:
        await update.message.reply_text("/lead USER_ID")
        return
    try:
        tid = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("ID должен быть числом")
        return
    lead = lead_get(tid)
    if not lead:
        await update.message.reply_text("Лид не найден")
        return

    def f(k):
        v = lead.get(k)
        return v[:16] if v else "-"

    await update.message.reply_text(
        "<b>Лид {}</b>  @{}  {}\n"
        "----------\n"
        "Страна: {} | Возраст: {} | Устройство: {}\n"
        "Опыт: {} | Тип: {}\n"
        "Стадия: <b>{}</b>\n"
        "----------\n"
        "Зашёл:   {}\n"
        "Анкета:  {}\n"
        "Квалиф.: {}\n"
        "М1: {}  М2: {}  М3: {}\n"
        "Контент: {}".format(
            tid,
            lead.get("username") or "-",
            lead.get("full_name") or "",
            lead.get("geo", "-"),
            lead.get("age", "-"),
            lead.get("device", "-"),
            lead.get("experience", "-"),
            lead.get("lead_type", "-"),
            lead.get("stage", "-"),
            f("started_at"),
            f("anketa_at"),
            f("qualified_at"),
            f("mod1_at"),
            f("mod2_at"),
            f("mod3_at"),
            f("content_at"),
        ),
        parse_mode="HTML",
    )


async def cmd_unlock(update, ctx):
    if not is_tl(update.effective_user.id):
        return
    if not ctx.args:
        await update.message.reply_text("/unlock USER_ID")
        return
    try:
        tid = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("ID должен быть числом")
        return
    if not lead_get(tid):
        await update.message.reply_text("Лид не найден")
        return

    lead_set(tid, stage=S_MOD3_DONE)
    try:
        await ctx.bot.send_message(
            tid,
            "<b>Тимлид открыл тебе доступ!</b>\n\n"
            "Жди — скоро получишь контент и инвайт.\n{}".format(TEAMLEAD_USERNAME),
            parse_mode="HTML",
        )
    except Exception:
        await update.message.reply_text("Не удалось написать пользователю (бот заблокирован?)")
        return
    await update.message.reply_text("{} разблокирован — ждёт выдачи контента".format(tid))


async def cmd_set_newbie(update, ctx):
    if not is_tl(update.effective_user.id):
        return
    if not ctx.args:
        await update.message.reply_text("/set_newbie USER_ID")
        return
    try:
        tid = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("ID должен быть числом")
        return
    if not lead_get(tid):
        await update.message.reply_text("Лид не найден")
        return

    lead_set(tid, lead_type="newbie", stage=S_QUALIFIED,
             qualified_at=datetime.now().isoformat())
    try:
        await ctx.bot.send_message(
            tid,
            "Тимлид предлагает пройти обучение с нуля.\n\n"
            "[УСЛОВИЯ_НОВИЧОК]\n\n"
            "Вопросы? {}".format(TEAMLEAD_USERNAME),
            reply_markup=KB_MOD1,
            parse_mode="HTML",
        )
    except Exception:
        await update.message.reply_text("Не удалось написать пользователю")
        return
    await update.message.reply_text("{} переведён в новички".format(tid))


async def cmd_mark_content(update, ctx):
    if not is_tl(update.effective_user.id):
        return
    if not ctx.args:
        await update.message.reply_text("/mark_content USER_ID")
        return
    try:
        tid = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("ID должен быть числом")
        return
    lead_set(tid, stage=S_CONTENT, content_at=datetime.now().isoformat())
    await update.message.reply_text("Контент отмечен выданным для {}".format(tid))


async def cmd_stats(update, ctx):
    if not is_tl(update.effective_user.id):
        return
    now  = datetime.now()
    args = ctx.args or []
    if len(args) >= 2 and args[0] == "week":
        w    = int(args[1])
        text = fmt_stats(
            get_stats(week=w, year=now.year),
            "Неделя {}, {}".format(w, now.year)
        )
    elif len(args) >= 2 and args[0] == "month":
        m    = int(args[1])
        text = fmt_stats(
            get_stats(month=m, year=now.year),
            "{} {}".format(calendar.month_name[m], now.year)
        )
    else:
        cw   = now.isocalendar()[1]
        text = (
            fmt_stats(
                get_stats(week=cw, year=now.year),
                "Неделя {} (текущая)".format(cw)
            )
            + "\n\n"
            + fmt_stats(
                get_stats(month=now.month, year=now.year),
                now.strftime("%B %Y")
            )
        )
    await update.message.reply_text(text, parse_mode="HTML")


# =============================================================
#  STUCK JOB
# =============================================================
STUCK_WATCH = {
    S_QUALIFIED:  ("mod1_at", "не начал Модуль 1", "qualified_at"),
    S_MOD1_SHOWN: ("mod1_at", "завис на Модуле 1", "qualified_at"),
    S_MOD1_DONE:  ("mod2_at", "не начал Модуль 2", "mod1_at"),
    S_MOD2_SHOWN: ("mod2_at", "завис на Модуле 2", "mod1_at"),
    S_MOD2_DONE:  ("mod3_at", "не начал Модуль 3", "mod2_at"),
    S_MOD3_SHOWN: ("mod3_at", "завис на Модуле 3", "mod2_at"),
}


async def check_stuck_loop(app):
    while True:
        await asyncio.sleep(CHECK_INTERVAL)
        threshold = (datetime.now() - timedelta(hours=STUCK_HOURS)).isoformat()
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            for stage, (done_col, label, time_col) in STUCK_WATCH.items():
                rows = conn.execute(
                    "SELECT * FROM leads "
                    "WHERE stage = ? "
                    "AND {} IS NULL ".format(done_col) +
                    "AND stuck_notified = 0 "
                    "AND {} IS NOT NULL ".format(time_col) +
                    "AND {} < ?".format(time_col),
                    (stage, threshold)
                ).fetchall()
                for r in rows:
                    r   = dict(r)
                    uid = r["user_id"]
                    try:
                        await app.bot.send_message(
                            GROUP_B_ID,
                            "<b>Завис более {}ч</b>\n"
                            "Пользователь: {}\n"
                            "Стадия: {}\n"
                            "/lead {}".format(
                                STUCK_HOURS,
                                utag(uid, r.get("username"), r.get("full_name")),
                                label,
                                uid
                            ),
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        log.warning("Stuck notify error: %s", e)
                    lead_set(uid, stuck_notified=1)


# =============================================================
#  MAIN
# =============================================================
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",        cmd_start))
    app.add_handler(CommandHandler("help",         cmd_help_tl))
    app.add_handler(CommandHandler("lead",         cmd_lead))
    app.add_handler(CommandHandler("unlock",       cmd_unlock))
    app.add_handler(CommandHandler("set_newbie",   cmd_set_newbie))
    app.add_handler(CommandHandler("mark_content", cmd_mark_content))
    app.add_handler(CommandHandler("stats",        cmd_stats))

    app.add_handler(CallbackQueryHandler(cb_anketa_start, pattern="^anketa_start$"))
    app.add_handler(CallbackQueryHandler(cb_geo,          pattern="^geo_"))
    app.add_handler(CallbackQueryHandler(cb_device,       pattern="^dev_"))
    app.add_handler(CallbackQueryHandler(cb_experience,   pattern="^exp_"))
    app.add_handler(CallbackQueryHandler(cb_cant_write,   pattern="^cant_write$"))
    app.add_handler(CallbackQueryHandler(cb_mod_start,    pattern=r"^mod_[123]_start$"))

    # текстовый ввод возраста — перед обработчиком фото
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_age_input))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_report))

    async def post_init(application):
        asyncio.create_task(check_stuck_loop(application))

    app.post_init = post_init

    log.info("Бот запущен")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
