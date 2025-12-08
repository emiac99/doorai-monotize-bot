import os
import sqlite3
import threading
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext,
)

# ------------------------------
# CONFIG
# ------------------------------

ADMIN_ID = 123456789  # <-- PUT YOUR TELEGRAM NUMERIC ID HERE

DB_FILE = "bot.db"
ADS = [
    "https://your-ad-link-1.com",
    "https://your-ad-link-2.com",
    "https://your-ad-link-3.com"
]

# ------------------------------
# DATABASE
# ------------------------------

def db_connect():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            clicks INTEGER DEFAULT 0,
            referrals INTEGER DEFAULT 0,
            referred_by INTEGER
        )
    """)
    conn.commit()
    return conn

conn = db_connect()
cursor = conn.cursor()

# ------------------------------
# CORE FUNCTIONS
# ------------------------------

def add_user(user_id, referred_by=None):
    cursor.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    if cursor.fetchone() is None:
        cursor.execute(
            "INSERT INTO users (user_id, clicks, referrals, referred_by) VALUES (?, 0, 0, ?)",
            (user_id, referred_by)
        )
        conn.commit()


def increase_click(user_id):
    cursor.execute("UPDATE users SET clicks = clicks + 1 WHERE user_id=?", (user_id,))
    conn.commit()


def get_clicks(user_id):
    cursor.execute("SELECT clicks FROM users WHERE user_id=?", (user_id,))
    data = cursor.fetchone()
    return data[0] if data else 0


def add_referral(referrer_id):
    cursor.execute("UPDATE users SET referrals = referrals + 1 WHERE user_id=?", (referrer_id,))
    conn.commit()


def reset_daily_clicks():
    cursor.execute("UPDATE users SET clicks = 0")
    conn.commit()


def get_qualified_users():
    cursor.execute("SELECT user_id FROM users WHERE clicks >= 20")
    return [row[0] for row in cursor.fetchall()]


def get_daily_summary():
    cursor.execute("SELECT user_id, clicks FROM users")
    rows = cursor.fetchall()
    summary = "📊 *Daily Click Summary*\n\n"
    for user_id, clicks in rows:
        summary += f"👤 `{user_id}` → {clicks} clicks\n"
    return summary

# ------------------------------
# DAILY RESET THREAD
# ------------------------------

def daily_reset_job(bot):
    while True:
        now = datetime.now()
        next_run = (now + timedelta(days=1)).replace(hour=0, minute=0, second=5)
        sleep_time = (next_run - now).total_seconds()

        threading.Event().wait(sleep_time)

        summary = get_daily_summary()
        bot.send_message(ADMIN_ID, summary, parse_mode="Markdown")

        reset_daily_clicks()


# ------------------------------
# HANDLERS
# ------------------------------

def start(update: Update, context: CallbackContext):
    user = update.effective_user
    args = context.args

    referred_by = None
    if args:
        try:
            ref_id = int(args[0])
            if ref_id != user.id:
                referred_by = ref_id
        except:
            pass

    add_user(user.id, referred_by)

    update.message.reply_text(
        "👋 *Welcome!*\n\n"
        "Click ads below to earn points.\n"
        "20 clicks qualify you for the giveaway.\n",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )


def main_menu():
    keyboard = [
        [InlineKeyboardButton("📢 View Ad", callback_data="view_ad")],
        [InlineKeyboardButton("👥 Referral Link", callback_data="ref_link")],
        [InlineKeyboardButton("📊 My Stats", callback_data="stats")]
    ]
    return InlineKeyboardMarkup(keyboard)


def button_click(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    query.answer()

    if query.data == "view_ad":
        ad_url = ADS[user_id % len(ADS)]
        increase_click(user_id)
        clicks = get_clicks(user_id)

        # reward referral only if user clicks >= 20
        cursor.execute("SELECT referred_by FROM users WHERE user_id=?", (user_id,))
        ref = cursor.fetchone()
        if ref and ref[0] and clicks == 20:
            add_referral(ref[0])

        query.edit_message_text(
            f"🎯 *Ad Clicked!*\n\n"
            f"You now have *{clicks} clicks*.\n\n"
            f"🔗 Ad: {ad_url}",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )

    elif query.data == "ref_link":
        link = f"https://t.me/{context.bot.username}?start={user_id}"
        query.edit_message_text(
            f"👥 *Your Referral Link:*\n{link}",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )

    elif query.data == "stats":
        cursor.execute("SELECT clicks, referrals FROM users WHERE user_id=?", (user_id,))
        clicks, referrals = cursor.fetchone()

        query.edit_message_text(
            f"📊 *Your Stats*\n\n"
            f"Clicks: *{clicks}*\n"
            f"Qualified Referrals: *{referrals}*",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )


# ------------------------------
# RUN BOT (POLLING)
# ------------------------------

def main():
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN environment variable missing.")

    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button_click))

    # Start daily reset thread
    threading.Thread(target=daily_reset_job, args=(updater.bot,), daemon=True).start()

    # Start bot (polling)
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
