#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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
            SELECT COUNT(*),
                   SUM(anketa_at    IS NOT NULL),
                   SUM(qualified_at IS NOT NULL),
                   SUM(lead_type = 'newbie'),
                   SUM(lead_type = 'experienced'),
                   SUM(mod1_at      IS NOT NULL),
                   SUM(mod2_at      IS NOT NULL),
                   SUM(mod3_at      IS NOT NULL),
                   SUM(content_at   IS NOT NULL)
            FROM leads WHERE {}
        """.format(cond)).fetchone()
    keys = ["total", "anketa", "qualified", "newbies", "experienced",
            "mod1", "mod2", "mod3", "content"]
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
    return ["[1/3]", "[2/3]", "[3/3]"][done - 1]


def fmt_stats(data, label):
    n = data["total"]
    def p(x):
        return " ({}%)".format(x * 100 // n) if n > 0 else ""
    return (
        "<b>Statistika: {}</b>\n\n".format(label) +
        "Zayavok:        <b>{}</b>\n".format(n) +
        "Anketa:         <b>{}</b>{}\n".format(data["anketa"], p(data["anketa"])) +
        "Kvalifits.:     <b>{}</b>{}\n".format(data["qualified"], p(data["qualified"])) +
        "  Novichki:     <b>{}</b>\n".format(data["newbies"]) +
        "  Opytnye:      <b>{}</b>\n".format(data["experienced"]) +
        "Modul 1:        <b>{}</b>{}\n".format(data["mod1"], p(data["mod1"])) +
        "Modul 2:        <b>{}</b>{}\n".format(data["mod2"], p(data["mod2"])) +
        "Modul 3:        <b>{}</b>{}\n".format(data["mod3"], p(data["mod3"])) +
        "Kontent vydan:  <b>{}</b>{}\n".format(data["content"], p(data["content"]))
    )


# =============================================================
#  KEYBOARDS
# =============================================================
KB_START = InlineKeyboardMarkup([[
    InlineKeyboardButton("Zapolnit anketu", callback_data="anketa_start")
]])

KB_GEO = InlineKeyboardMarkup([
    [InlineKeyboardButton("Rossiya",    callback_data="geo_ru"),
     InlineKeyboardButton("Ukraina",    callback_data="geo_ua")],
    [InlineKeyboardButton("Belarus",    callback_data="geo_by"),
     InlineKeyboardButton("Kazakhstan", callback_data="geo_kz")],
    [InlineKeyboardButton("Drugoe",     callback_data="geo_other")],
])

KB_AGE = InlineKeyboardMarkup([
    [InlineKeyboardButton("Do 18", callback_data="age_u18"),
     InlineKeyboardButton("18-25", callback_data="age_18")],
    [InlineKeyboardButton("26-35", callback_data="age_26"),
     InlineKeyboardButton("36+",   callback_data="age_36")],
])

KB_DEVICE = InlineKeyboardMarkup([
    [InlineKeyboardButton("Android",        callback_data="dev_android")],
    [InlineKeyboardButton("iPhone (iOS)",   callback_data="dev_ios")],
    [InlineKeyboardButton("Kompyuter",      callback_data="dev_pc")],
    [InlineKeyboardButton("Net ustrojstva", callback_data="dev_none")],
])

KB_EXP = InlineKeyboardMarkup([
    [InlineKeyboardButton("Da, est opyt",  callback_data="exp_yes")],
    [InlineKeyboardButton("Net, novichok", callback_data="exp_no")],
])

KB_CANT_WRITE = InlineKeyboardMarkup([[
    InlineKeyboardButton("Ne mogu napisat pervym", callback_data="cant_write")
]])

KB_MOD1 = InlineKeyboardMarkup([[
    InlineKeyboardButton("Nachat Modul 1", callback_data="mod_1_start")
]])


def kb_next_mod(n):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "Perejti k Modulyu {}".format(n),
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
        "<b>Novaya zayavka</b>\n"
        "User: {}\n"
        "Time: {}".format(
            utag(u.id, u.username, u.full_name),
            datetime.now().strftime("%d.%m.%Y %H:%M")
        )
    )
    await update.message.reply_text(
        "Privet!\n\n"
        "[TEKST_PRIVETSTVIYA]\n\n"
        "[SSYLKA_NA_VIDEO]\n\n"
        "Voprosy - napishi timlidu: {}\n\n"
        "Zapolni korotkuyu anketu:".format(TEAMLEAD_USERNAME),
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
        "<b>Iz kakoj ty strany?</b>",
        reply_markup=KB_GEO,
        parse_mode="HTML",
    )


GEO_MAP = {
    "geo_ru":    "Rossiya",
    "geo_ua":    "Ukraina",
    "geo_by":    "Belarus",
    "geo_kz":    "Kazakhstan",
    "geo_other": "Drugoe",
}


async def cb_geo(update, ctx):
    q = update.callback_query
    await q.answer()
    if lead_stage(q.from_user.id) != S_GEO:
        return
    lead_set(q.from_user.id, geo=GEO_MAP[q.data], stage=S_AGE)
    await q.edit_message_text(
        "<b>Skolko tebe let?</b>",
        reply_markup=KB_AGE,
        parse_mode="HTML",
    )


AGE_MAP = {
    "age_u18": "Do 18",
    "age_18":  "18-25",
    "age_26":  "26-35",
    "age_36":  "36+",
}


async def cb_age(update, ctx):
    q = update.callback_query
    await q.answer()
    if lead_stage(q.from_user.id) != S_AGE:
        return
    lead_set(q.from_user.id, age=AGE_MAP[q.data], stage=S_DEVICE)
    await q.edit_message_text(
        "<b>Kakoe ustrojstvo dlya raboty?</b>",
        reply_markup=KB_DEVICE,
        parse_mode="HTML",
    )


DEV_MAP = {
    "dev_android": "Android",
    "dev_ios":     "iPhone (iOS)",
    "dev_pc":      "Kompyuter",
    "dev_none":    "Net ustrojstva",
}


async def cb_device(update, ctx):
    q = update.callback_query
    await q.answer()
    if lead_stage(q.from_user.id) != S_DEVICE:
        return
    lead_set(q.from_user.id, device=DEV_MAP[q.data], stage=S_EXP)
    await q.edit_message_text(
        "<b>Est li opyt v trafike/arbitrazhe?</b>",
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

    opyt_text = "Est - zhdet razgovora" if exp == "yes" else "Net - obuchenie"
    await grp_a(ctx,
        "<b>Anketa zapolnena</b>\n"
        "User: {}\n"
        "Geo: {} | Age: {} | Device: {}\n"
        "Opyt: {}".format(
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
        "<b>Kvalifitsirovan: NOVICHOK</b>\n"
        "User: {} - idet v obuchenie".format(utag(u.id, u.username, u.full_name))
    )
    await q.edit_message_text(
        "<b>Usloviya dlya novichkov:</b>\n\n"
        "[USLOVIYA_NOVICHOK]\n\n"
        "3 modulya obucheniya:\n"
        "- Modul 1 - bazovyj manual\n"
        "- Modul 2 - nastrojka telefona\n"
        "- Modul 3 - sajt-prokladka i akkaunty\n\n"
        "Voprosy? {}".format(TEAMLEAD_USERNAME),
        reply_markup=KB_MOD1,
        parse_mode="HTML",
    )


async def _show_exp_gate(q, u, ctx):
    await grp_a(ctx,
        "<b>OPYTNYJ trafer zhdet razgovora</b>\n"
        "User: {}\n"
        "/unlock {}  |  /set_newbie {}".format(
            utag(u.id, u.username, u.full_name), u.id, u.id
        )
    )
    await q.edit_message_text(
        "Dlya opytnyh trafferov - osobye usloviya.\n\n"
        "<b>Nuzhen lichnyj razgovor s timlidom.</b>\n\n"
        "Napishi: {}\n\n"
        "Posle razgovora on otkroet tebe dostup.".format(TEAMLEAD_USERNAME),
        reply_markup=KB_CANT_WRITE,
        parse_mode="HTML",
    )


async def cb_cant_write(update, ctx):
    q = update.callback_query
    await q.answer("Uvedomili timlida")
    u = q.from_user
    await grp_a(ctx,
        "<b>Ne mozhet napisat pervym</b>\n"
        "User: {} | <code>{}</code>\n"
        "Napishi emu sam!".format(utag(u.id, u.username, u.full_name), u.id)
    )
    await q.edit_message_text(
        "Timlid poluchil uvedomlenie i napishет sam.\n\n"
        "Ili napishi pozzhe: {}".format(TEAMLEAD_USERNAME)
    )


# =============================================================
#  MODULI
# =============================================================
MOD_TEXTS = {
    1: (
        "<b>Modul 1 - Bazovyj manual</b>\n\n"
        "[SODERZHANIE_MODULYA_1]\n\n"
        "----------\n"
        "<b>Zadanie:</b> prochtaj, sdelaj skrinshot i otprav ego syuda."
    ),
    2: (
        "<b>Modul 2 - Nastrojka telefona</b>\n\n"
        "[INSTRUKCIYA_NASTROJKI]\n\n"
        "----------\n"
        "<b>Zadanie:</b> nastraj telefon, sdelaj skrinshot i otprav."
    ),
    3: (
        "<b>Modul 3 - Sajt-prokladka i akkaunty</b>\n\n"
        "[INSTRUKCIYA_MODULYA_3]\n\n"
        "----------\n"
        "<b>Zadanie:</b> otprav skrinshotы:\n"
        "1. Gotovyj sajt\n"
        "2. 3 oformlennykh akkaunta"
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
        await q.answer("Snachala zavershite predydushchij etap", show_alert=True)
        return
    lead_set(u.id, stage=MOD_SHOWN[mod], stuck_notified=0)
    await q.edit_message_text(
        MOD_TEXTS[mod] + "\n\nVoprosy? {}".format(TEAMLEAD_USERNAME),
        parse_mode="HTML",
    )


async def handle_report(update, ctx):
    u     = update.effective_user
    stage = lead_stage(u.id)
    now   = datetime.now().isoformat()

    if stage == S_MOD1_SHOWN:
        lead_set(u.id, stage=S_MOD1_DONE, mod1_at=now, stuck_notified=0)
        await grp_b(ctx,
            "<b>Modul 1 sdan</b>\n"
            "User: {}".format(utag(u.id, u.username, u.full_name))
        )
        await update.message.reply_text(
            "<b>Modul 1 prinyat!</b>\n\n"
            "Progress: {}\n\n"
            "Horoshaya rabota! Sleduyushchij shag:".format(pbar(1)),
            reply_markup=kb_next_mod(2),
            parse_mode="HTML",
        )

    elif stage == S_MOD2_SHOWN:
        lead_set(u.id, stage=S_MOD2_DONE, mod2_at=now, stuck_notified=0)
        await grp_b(ctx,
            "<b>Modul 2 sdan</b>\n"
            "User: {}".format(utag(u.id, u.username, u.full_name))
        )
        await update.message.reply_text(
            "<b>Modul 2 prinyat!</b>\n\n"
            "Progress: {}\n\n"
            "Pochti finish! Poslednij modul:".format(pbar(2)),
            reply_markup=kb_next_mod(3),
            parse_mode="HTML",
        )

    elif stage == S_MOD3_SHOWN:
        lead_set(u.id, stage=S_MOD3_DONE, mod3_at=now, stuck_notified=0)
        await grp_b(ctx,
            "<b>Modul 3 sdan</b>\n"
            "User: {}\n"
            "Gotov k polucheniyu kontenta!".format(utag(u.id, u.username, u.full_name))
        )
        await grp_a(ctx,
            "<b>Obuchenie zaversheno!</b>\n"
            "User: {}\n"
            "Vydaj kontent i invite vruchnuyu\n"
            "Posle vydachi: /mark_content {}".format(
                utag(u.id, u.username, u.full_name), u.id
            )
        )
        await update.message.reply_text(
            "<b>Vse moduli projdeny!</b>\n\n"
            "Progress: {}\n\n"
            "Timlid skoro vydast kontent i dostup.\n"
            "Net otveta - napishi sam: {}".format(pbar(3), TEAMLEAD_USERNAME),
            parse_mode="HTML",
        )


# =============================================================
#  KOMANDY TIMLIDA
# =============================================================
async def cmd_help_tl(update, ctx):
    if not is_tl(update.effective_user.id):
        return
    await update.message.reply_text(
        "<b>Komandy timlida</b>\n\n"
        "/lead ID - kartochka lida\n"
        "/unlock ID - razblokirovat opytnogo\n"
        "/set_newbie ID - perevesti opytnogo v novichki\n"
        "/mark_content ID - otmetit vydachu kontenta\n\n"
        "/stats - nedelya + mesyac (tekushchie)\n"
        "/stats week N - nedelya N\n"
        "/stats month N - mesyac N (1-12)",
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
        await update.message.reply_text("ID dolzhen byt chislom")
        return
    lead = lead_get(tid)
    if not lead:
        await update.message.reply_text("Lid ne najden")
        return

    def f(k):
        v = lead.get(k)
        return v[:16] if v else "-"

    await update.message.reply_text(
        "<b>Lid {}</b>  @{}  {}\n"
        "----------\n"
        "Geo: {} | Age: {} | Device: {}\n"
        "Opyt: {} | Tip: {}\n"
        "Stadiya: <b>{}</b>\n"
        "----------\n"
        "Zashel:   {}\n"
        "Anketa:   {}\n"
        "Kvalif.:  {}\n"
        "M1: {}  M2: {}  M3: {}\n"
        "Kontent:  {}".format(
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
        await update.message.reply_text("ID dolzhen byt chislom")
        return
    if not lead_get(tid):
        await update.message.reply_text("Lid ne najden")
        return

    lead_set(tid, stage=S_MOD3_DONE)
    try:
        await ctx.bot.send_message(
            tid,
            "<b>Timlid otkryl tebe dostup!</b>\n\n"
            "Zhdi - skoro poluchish kontent i invite.\n{}".format(TEAMLEAD_USERNAME),
            parse_mode="HTML",
        )
    except Exception:
        await update.message.reply_text("Ne udalos napisat polzovatelyu (bot zablokirovan?)")
        return
    await update.message.reply_text("{} razblokirovan - zhdet vydachi kontenta".format(tid))


async def cmd_set_newbie(update, ctx):
    if not is_tl(update.effective_user.id):
        return
    if not ctx.args:
        await update.message.reply_text("/set_newbie USER_ID")
        return
    try:
        tid = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("ID dolzhen byt chislom")
        return
    if not lead_get(tid):
        await update.message.reply_text("Lid ne najden")
        return

    lead_set(tid, lead_type="newbie", stage=S_QUALIFIED,
             qualified_at=datetime.now().isoformat())
    try:
        await ctx.bot.send_message(
            tid,
            "Timlid predlagaet projti obuchenie s nulya.\n\n"
            "[USLOVIYA_NOVICHOK]\n\n"
            "Voprosy? {}".format(TEAMLEAD_USERNAME),
            reply_markup=KB_MOD1,
            parse_mode="HTML",
        )
    except Exception:
        await update.message.reply_text("Ne udalos napisat polzovatelyu")
        return
    await update.message.reply_text("{} perevedyon v novichki".format(tid))


async def cmd_mark_content(update, ctx):
    if not is_tl(update.effective_user.id):
        return
    if not ctx.args:
        await update.message.reply_text("/mark_content USER_ID")
        return
    try:
        tid = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("ID dolzhen byt chislom")
        return
    lead_set(tid, stage=S_CONTENT, content_at=datetime.now().isoformat())
    await update.message.reply_text("Kontent otmechen vydannym dlya {}".format(tid))


async def cmd_stats(update, ctx):
    if not is_tl(update.effective_user.id):
        return
    now  = datetime.now()
    args = ctx.args or []
    if len(args) >= 2 and args[0] == "week":
        w    = int(args[1])
        text = fmt_stats(get_stats(week=w, year=now.year), "Nedelya {}, {}".format(w, now.year))
    elif len(args) >= 2 and args[0] == "month":
        m    = int(args[1])
        text = fmt_stats(get_stats(month=m, year=now.year),
                         "{} {}".format(calendar.month_name[m], now.year))
    else:
        cw   = now.isocalendar()[1]
        text = (
            fmt_stats(get_stats(week=cw, year=now.year),
                      "Nedelya {} (tekushchaya)".format(cw))
            + "\n"
            + fmt_stats(get_stats(month=now.month, year=now.year),
                        now.strftime("%B %Y"))
        )
    await update.message.reply_text(text, parse_mode="HTML")


# =============================================================
#  JOB - zavsshie lidy
# =============================================================
STUCK_WATCH = {
    S_QUALIFIED:  ("mod1_at", "ne nachal Modul 1", "qualified_at"),
    S_MOD1_SHOWN: ("mod1_at", "zavis na Module 1", "qualified_at"),
    S_MOD1_DONE:  ("mod2_at", "ne nachal Modul 2", "mod1_at"),
    S_MOD2_SHOWN: ("mod2_at", "zavis na Module 2", "mod1_at"),
    S_MOD2_DONE:  ("mod3_at", "ne nachal Modul 3", "mod2_at"),
    S_MOD3_SHOWN: ("mod3_at", "zavis na Module 3", "mod2_at"),
}


async def job_stuck(ctx):
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
                await grp_b(ctx,
                    "<b>Zavis > {}h</b>\n"
                    "User: {}\n"
                    "Stadiya: {}\n"
                    "/lead {}".format(
                        STUCK_HOURS,
                        utag(uid, r.get("username"), r.get("full_name")),
                        label,
                        uid
                    )
                )
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
    app.add_handler(CallbackQueryHandler(cb_age,          pattern="^age_"))
    app.add_handler(CallbackQueryHandler(cb_device,       pattern="^dev_"))
    app.add_handler(CallbackQueryHandler(cb_experience,   pattern="^exp_"))
    app.add_handler(CallbackQueryHandler(cb_cant_write,   pattern="^cant_write$"))
    app.add_handler(CallbackQueryHandler(cb_mod_start,    pattern=r"^mod_[123]_start$"))

    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_report))

    app.job_queue.run_repeating(job_stuck, interval=CHECK_INTERVAL, first=60)

    log.info("Bot zapushchen")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
