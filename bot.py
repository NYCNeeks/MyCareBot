"""
Care Bot — main Telegram entry point.
Vitamins · Skincare · Nutrition · Running Coach · Task AI · Daily Check-in · Memory
"""
import os
import re
import logging
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
from dotenv import load_dotenv

from notion_manager import NotionManager
import ai_assistant as ai

load_dotenv()

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID        = os.getenv("TELEGRAM_CHAT_ID")

notion = NotionManager()

CATEGORY_EMOJI = {
    "Health": "💊", "Skincare": "✨", "Nutrition": "🥗",
    "Exercise": "💪", "Running": "🏃", "Task": "📋",
    "General": "🔔", "Vitamins": "💊", "Meal": "🍽️", "Water": "💧",
}
PRIORITY_EMOJI = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}
STATUS_EMOJI   = {"To Do": "📌", "In Progress": "⚡", "Done": "✅", "Blocked": "🚫"}

# Track who's in the middle of a check-in response
AWAITING_CHECKIN = set()


# ─────────────────────────────────────────────────────────────
# SCHEDULED JOBS
# ─────────────────────────────────────────────────────────────

async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Every minute: send any Notion reminders that match now."""
    profile = notion.get_user_profile()
    due = notion.get_due_reminders()
    for reminder in due:
        props = reminder.get("properties", {})
        name     = NotionManager.prop_text(props, "Name")
        message  = NotionManager.prop_text(props, "Message")
        category = NotionManager.prop_select(props, "Category")
        emoji    = CATEGORY_EMOJI.get(category, "🔔")
        text = f"{emoji} *{name}*"
        if message:
            text += f"\n{message}"
        try:
            await context.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown")
            logger.info(f"Sent reminder: {name}")
        except Exception as e:
            logger.error(f"Failed to send reminder '{name}': {e}")


async def send_morning_message(context: ContextTypes.DEFAULT_TYPE):
    """Every day at the user's morning time (set in profile)."""
    profile  = notion.get_user_profile(use_cache=False)
    logs     = notion.get_health_logs(14)
    message  = ai.morning_message(profile, logs)
    try:
        await context.bot.send_message(chat_id=CHAT_ID, text=message, parse_mode="Markdown")
        logger.info("Sent morning message")
    except Exception as e:
        logger.error(f"Morning message error: {e}")


async def send_daily_checkin(context: ContextTypes.DEFAULT_TYPE):
    """Daily evening check-in — 'what good have you done for yourself today?'"""
    global AWAITING_CHECKIN
    profile  = notion.get_user_profile(use_cache=False)
    question = ai.daily_checkin_question(profile)
    AWAITING_CHECKIN.add(CHAT_ID)
    try:
        await context.bot.send_message(chat_id=CHAT_ID, text=question, parse_mode="Markdown")
        logger.info("Sent daily check-in")
    except Exception as e:
        logger.error(f"Check-in error: {e}")


# ─────────────────────────────────────────────────────────────
# /start
# ─────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile  = notion.get_user_profile()
    name     = profile.get("name", "")
    greeting = f"Hey {name}! 👋" if name else "Hey there! 👋"
    keyboard = [
        [
            InlineKeyboardButton("📋 Tasks",         callback_data="tasks"),
            InlineKeyboardButton("🔔 Reminders",     callback_data="reminders"),
        ],
        [
            InlineKeyboardButton("💊 Health Check",  callback_data="health"),
            InlineKeyboardButton("🥗 Nutrition",     callback_data="nutrition"),
        ],
        [
            InlineKeyboardButton("🏃 Running",       callback_data="running"),
            InlineKeyboardButton("✨ Check-in",      callback_data="checkin"),
        ],
        [InlineKeyboardButton("➕ Add Task (AI)",    callback_data="add_task_prompt")],
    ]
    await update.message.reply_text(
        f"{greeting}\n\n"
        "I'm your personal *Care Bot* — I remember you, coach you, and cheer for you. 💛\n\n"
        "• 💊 Vitamins, skincare & health reminders\n"
        "• 🏃 Running coach with your personal plan\n"
        "• 🥗 Nutritionist in your pocket\n"
        "• 📋 AI task breakdown → Notion Kanban\n"
        "• ✨ Daily check-in + praise (you are exceptional)\n\n"
        "What would you like to do?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ─────────────────────────────────────────────────────────────
# /help
# ─────────────────────────────────────────────────────────────

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    await target.reply_text(
        "*Care Bot Commands* 🤖\n\n"
        "*Daily Care:*\n"
        "/checkin — Your daily check-in & praise moment\n"
        "/health — Health summary & coaching\n"
        "/log \\[type\\] \\[notes\\] — Log vitamins, skincare, meal, exercise\n\n"
        "*Running Coach:*\n"
        "/run \\[question or update\\] — Talk to your running coach\n"
        "/logrun \\[km\\] \\[min\\] \\[notes\\] — Log a run\n"
        "/runstats — Your running stats & progress\n"
        "/runplan \\[fitness level\\] — Get a 4-week training plan\n\n"
        "*Nutrition:*\n"
        "/nutrition \\[question\\] — Ask your nutritionist\n\n"
        "*Tasks:*\n"
        "/tasks — View your Kanban board\n"
        "/addtask \\[description\\] — AI breaks it into steps\n\n"
        "*Info:*\n"
        "/reminders — List active reminders\n"
        "/me — Your saved profile & memory\n"
        "/start — Main menu",
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────────────────────────
# /checkin — manual trigger of the daily check-in
# ─────────────────────────────────────────────────────────────

async def checkin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global AWAITING_CHECKIN
    profile  = notion.get_user_profile()
    question = ai.daily_checkin_question(profile)
    AWAITING_CHECKIN.add(str(update.effective_chat.id))
    await update.message.reply_text(question, parse_mode="Markdown")


# ─────────────────────────────────────────────────────────────
# /me — show user profile stored in Notion
# ─────────────────────────────────────────────────────────────

async def me_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = notion.get_user_profile(use_cache=False)
    if not profile or not any(profile.values()):
        await update.message.reply_text(
            "📝 I don't have your profile yet!\n\n"
            "Open your *Notion Profile* database and fill in your details — "
            "that's how I remember you, your goals, your vitamins and more. 💛",
            parse_mode="Markdown",
        )
        return

    text = "*👤 Your Profile (my memory of you)*\n\n"
    fields = {
        "name":          ("📛 Name",           ""),
        "running_goal":  ("🏃 Running Goal",   ""),
        "vitamins":      ("💊 Vitamins",        ""),
        "skin_routine":  ("✨ Skin Routine",    ""),
        "diet_notes":    ("🥗 Diet Notes",      ""),
        "health_notes":  ("📋 Health Notes",    ""),
        "checkin_time":  ("🌙 Check-in Time",   ""),
        "morning_time":  ("🌅 Morning Message", ""),
    }
    for key, (label, _) in fields.items():
        val = profile.get(key, "")
        if val:
            text += f"{label}: {val}\n"

    text += "\n_Update any of this in your Notion Profile database and I'll remember it instantly._"
    await update.message.reply_text(text, parse_mode="Markdown")


# ─────────────────────────────────────────────────────────────
# /health
# ─────────────────────────────────────────────────────────────

async def health_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    proc   = await target.reply_text("💊 Checking in on you…")
    profile = notion.get_user_profile()
    logs    = notion.get_health_logs(20)
    advice  = ai.health_advice(logs, user_profile=profile)
    keyboard = [[
        InlineKeyboardButton("💊 Vitamins ✓",  callback_data="log_Vitamins"),
        InlineKeyboardButton("✨ Skincare ✓",  callback_data="log_Skincare"),
    ], [
        InlineKeyboardButton("🥗 Meal ✓",      callback_data="log_Meal"),
        InlineKeyboardButton("💪 Exercise ✓",  callback_data="log_Exercise"),
    ]]
    await proc.edit_text(
        f"*💊 Health Check-in*\n\n{advice}\n\n_Quick log:_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ─────────────────────────────────────────────────────────────
# /log
# ─────────────────────────────────────────────────────────────

TYPE_MAP = {"vitamins": "Vitamins", "skincare": "Skincare", "meal": "Meal",
            "exercise": "Exercise", "water": "Water", "run": "Running"}

async def log_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "📝 `/log [type] [optional notes]`\n\n"
            "Types: `vitamins` · `skincare` · `meal` · `exercise` · `water`",
            parse_mode="Markdown",
        )
        return
    raw_type    = context.args[0].lower()
    notes       = " ".join(context.args[1:])
    notion_type = TYPE_MAP.get(raw_type)
    if not notion_type:
        await update.message.reply_text(
            f"❓ Unknown type `{raw_type}`.\nUse: vitamins · skincare · meal · exercise · water",
            parse_mode="Markdown",
        )
        return
    ok    = notion.log_health(notion_type, notes)
    emoji = CATEGORY_EMOJI.get(notion_type, "✅")
    if ok:
        msg = f"{emoji} *{notion_type} logged!*"
        if notes:
            msg += f"\n_{notes}_"
        msg += "\n\nThat's you taking care of yourself. Keep going! 🌟"
        await update.message.reply_text(msg, parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Couldn't log — check your Notion connection.")


# ─────────────────────────────────────────────────────────────
# RUNNING COMMANDS
# ─────────────────────────────────────────────────────────────

async def run_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Talk to your running coach."""
    target = update.message or update.callback_query.message
    if not context.args:
        profile = notion.get_user_profile()
        goal    = profile.get("running_goal", "not set yet")
        stats   = notion.get_run_stats()
        text = (
            f"🏃 *Your Running Coach*\n\n"
            f"Goal: _{goal}_\n"
        )
        if stats:
            text += (
                f"\n📊 Your stats:\n"
                f"  🗓 Runs logged: {stats.get('total_runs', 0)}\n"
                f"  📏 Total: {stats.get('total_km', 0)} km\n"
                f"  ⚡ Avg pace: {stats.get('avg_pace', 0)} min/km\n"
                f"  🏆 Longest: {stats.get('longest_km', 0)} km\n"
            )
        text += "\nAsk me anything or tell me about a run!\nOr use /logrun to log one."
        await target.reply_text(text, parse_mode="Markdown")
        return

    question  = " ".join(context.args)
    proc      = await target.reply_text("🏃 Checking with your coach…")
    profile   = notion.get_user_profile()
    run_hist  = notion.get_run_history(10)
    advice    = ai.running_coach(question, run_hist, profile)
    await proc.edit_text(f"*🏃 Running Coach*\n\n{advice}", parse_mode="Markdown")


async def logrun_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/logrun [km] [min] [optional notes]"""
    if len(context.args) < 2:
        await update.message.reply_text(
            "🏃 `/logrun [km] [minutes] [optional notes]`\n\n"
            "Example: `/logrun 5 28 felt great today`",
            parse_mode="Markdown",
        )
        return
    try:
        km  = float(context.args[0])
        min = int(context.args[1])
        notes = " ".join(context.args[2:])
    except ValueError:
        await update.message.reply_text("❌ Format: `/logrun 5.2 30 notes`", parse_mode="Markdown")
        return

    proc    = await update.message.reply_text("🏃 Logging your run…")
    ok      = notion.log_run(km, min, notes)
    profile = notion.get_user_profile()
    pace    = round(min / km, 2) if km > 0 else 0

    if ok:
        praise = ai.running_coach(
            f"I just ran {km} km in {min} minutes (pace {pace} min/km). {notes}",
            notion.get_run_history(10),
            profile,
        )
        await proc.edit_text(
            f"🏃 *Run Logged!*\n\n"
            f"📏 Distance: {km} km\n"
            f"⏱ Duration: {min} min\n"
            f"⚡ Pace: {pace} min/km\n"
            + (f"📝 {notes}\n" if notes else "")
            + f"\n{praise}",
            parse_mode="Markdown",
        )
    else:
        await proc.edit_text("❌ Couldn't log run — check Notion connection.")


async def runstats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    proc    = await update.message.reply_text("📊 Pulling your stats…")
    stats   = notion.get_run_stats()
    profile = notion.get_user_profile()
    goal    = profile.get("running_goal", "")

    if not stats:
        await proc.edit_text(
            "🏃 No runs logged yet! Use `/logrun [km] [min]` to log your first one.",
            parse_mode="Markdown",
        )
        return

    await proc.edit_text(
        f"*🏃 Your Running Stats*\n\n"
        f"🎯 Goal: _{goal}_\n\n"
        f"🗓 Runs logged: {stats['total_runs']}\n"
        f"📏 Total distance: {stats['total_km']} km\n"
        f"⏱ Total time: {stats['total_duration']} min\n"
        f"⚡ Avg pace: {stats['avg_pace']} min/km\n"
        f"🏆 Longest run: {stats['longest_km']} km ({stats['longest_date']})\n\n"
        f"_Every km is a win. You are exceptional._ 🌟",
        parse_mode="Markdown",
    )


async def runplan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/runplan [fitness level] [optional: goal race]"""
    if not context.args:
        await update.message.reply_text(
            "🏃 `/runplan [fitness level] [optional goal]`\n\n"
            "Fitness levels: `beginner` · `intermediate` · `advanced`\n\n"
            "Examples:\n"
            "`/runplan beginner`\n"
            "`/runplan intermediate 10k race`",
            parse_mode="Markdown",
        )
        return

    fitness   = context.args[0]
    goal_race = " ".join(context.args[1:]) if len(context.args) > 1 else None
    proc      = await update.message.reply_text("🏃 Building your personal training plan…")
    profile   = notion.get_user_profile()
    plan      = ai.generate_training_plan(fitness, profile, goal_race)
    await proc.edit_text(f"*🏃 Your 4-Week Training Plan*\n\n{plan}", parse_mode="Markdown")


# ─────────────────────────────────────────────────────────────
# /nutrition
# ─────────────────────────────────────────────────────────────

async def nutrition_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    if not context.args:
        await target.reply_text(
            "🥗 *Your Nutritionist*\n\nAsk me anything!\n\n"
            "Examples:\n"
            "`/nutrition What should I eat before a morning run?`\n"
            "`/nutrition I'm low on energy — what's missing?`",
            parse_mode="Markdown",
        )
        return
    question = " ".join(context.args)
    proc     = await target.reply_text("🥗 Consulting your nutritionist…")
    profile  = notion.get_user_profile()
    advice   = ai.nutrition_advice(question, profile)
    await proc.edit_text(f"*🥗 Nutrition Advice*\n\n{advice}", parse_mode="Markdown")


# ─────────────────────────────────────────────────────────────
# /tasks & /addtask
# ─────────────────────────────────────────────────────────────

async def tasks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    tasks  = notion.get_tasks()
    if not tasks:
        await target.reply_text(
            "📋 No tasks yet!\n\nAdd one with `/addtask [description]`",
            parse_mode="Markdown",
        )
        return
    groups: dict = {"To Do": [], "In Progress": [], "Done": [], "Blocked": []}
    for task in tasks:
        props    = task.get("properties", {})
        name     = NotionManager.prop_text(props, "Task Name") or "Unnamed"
        status   = NotionManager.prop_select(props, "Status") or "To Do"
        priority = NotionManager.prop_select(props, "Priority") or "Medium"
        groups.setdefault(status, []).append(f"{PRIORITY_EMOJI.get(priority,'⚪')} {name}")

    text = "*📋 Your Kanban Board*\n"
    for status, items in groups.items():
        if items:
            text += f"\n{STATUS_EMOJI.get(status,'📋')} *{status}*\n"
            text += "\n".join(f"  • {i}" for i in items) + "\n"
    await target.reply_text(text, parse_mode="Markdown")


async def addtask_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "📋 `/addtask [describe your task]`\n\n"
            "Example: `/addtask Redesign my portfolio website`",
            parse_mode="Markdown",
        )
        return
    description = " ".join(context.args)
    proc        = await update.message.reply_text("🤔 Breaking your task down with AI…")
    breakdown   = ai.break_down_task(description)
    if not breakdown:
        await proc.edit_text("❌ Couldn't process that — try again.")
        return

    steps     = breakdown.get("steps", [])
    steps_txt = "\n".join(
        f"{i+1}. {s['step']} *({s.get('duration','?')})*"
        for i, s in enumerate(steps)
    )
    due = (datetime.now() + timedelta(days=breakdown.get("estimated_days", 7))).strftime("%Y-%m-%d")
    notion.add_task(
        name      = breakdown.get("task_name", description),
        steps     = "\n".join(f"{i+1}. {s['step']} ({s.get('duration','?')})" for i, s in enumerate(steps)),
        priority  = breakdown.get("priority", "Medium"),
        due_date  = due,
    )
    p_emoji = PRIORITY_EMOJI.get(breakdown.get("priority", "Medium"), "🟡")
    await proc.edit_text(
        f"✅ *Added to Notion!*\n\n"
        f"📋 *{breakdown.get('task_name')}*\n"
        f"{p_emoji} {breakdown.get('priority')} · ⏱ ~{breakdown.get('estimated_days')} days\n\n"
        f"*Steps:*\n{steps_txt}",
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────────────────────────
# /reminders
# ─────────────────────────────────────────────────────────────

async def reminders_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target    = update.message or update.callback_query.message
    reminders = notion.get_all_reminders()
    if not reminders:
        await target.reply_text(
            "🔔 No active reminders.\n\nAdd them in your *Notion Reminders* database.",
            parse_mode="Markdown",
        )
        return
    text = "*🔔 Active Reminders*\n\n"
    for r in reminders:
        props    = r.get("properties", {})
        name     = NotionManager.prop_text(props, "Name")
        time     = NotionManager.prop_text(props, "Time") or "--:--"
        days     = NotionManager.prop_multiselect(props, "Days")
        category = NotionManager.prop_select(props, "Category")
        emoji    = CATEGORY_EMOJI.get(category, "🔔")
        days_str = ", ".join(d[:3] for d in days) if days else "Every day"
        text    += f"{emoji} *{name}*\n   ⏰ {time}  |  📅 {days_str}\n\n"
    await target.reply_text(text, parse_mode="Markdown")


# ─────────────────────────────────────────────────────────────
# INLINE BUTTON HANDLER
# ─────────────────────────────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data

    if   data == "tasks":         await tasks_cmd(update, context)
    elif data == "reminders":     await reminders_cmd(update, context)
    elif data == "health":        await health_cmd(update, context)
    elif data == "running":
        context.args = []
        await run_cmd(update, context)
    elif data == "checkin":       await checkin_cmd(update, context)
    elif data == "nutrition":
        context.args = []
        await nutrition_cmd(update, context)
    elif data == "add_task_prompt":
        await query.message.reply_text(
            "📋 `/addtask [describe your task]`",
            parse_mode="Markdown",
        )
    elif data.startswith("log_"):
        notion_type = data[4:]
        ok    = notion.log_health(notion_type)
        emoji = CATEGORY_EMOJI.get(notion_type, "✅")
        if ok:
            await query.message.reply_text(
                f"{emoji} *{notion_type} logged!* Every act of self-care counts. 🌟",
                parse_mode="Markdown",
            )
        else:
            await query.message.reply_text("❌ Couldn't log — check Notion connection.")


# ─────────────────────────────────────────────────────────────
# FREE-TEXT MESSAGE HANDLER — smart routing + check-in interception
# ─────────────────────────────────────────────────────────────

NUTRITION_KW = {"eat", "food", "diet", "meal", "protein", "carb", "calorie", "nutrition", "weight", "macro", "recipe"}
HEALTH_KW    = {"vitamin", "skin", "sleep", "tired", "energy", "supplement", "skincare", "routine"}
RUNNING_KW   = {"run", "ran", "running", "jog", "pace", "km", "marathon", "5k", "10k", "sprint", "training"}
TASK_KW      = {"task", "todo", "project", "work", "finish", "complete", "deadline", "build", "create"}


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global AWAITING_CHECKIN
    text    = update.message.text
    chat_id = str(update.effective_chat.id)
    words   = set(text.lower().split())

    # Check-in response interception
    if chat_id in AWAITING_CHECKIN:
        AWAITING_CHECKIN.discard(chat_id)
        proc    = await update.message.reply_text("💛 Reading what you shared…")
        profile = notion.get_user_profile()
        logs    = notion.get_health_logs(10)
        praise  = ai.praise_checkin_response(text, profile, logs)
        await proc.edit_text(praise)
        return

    # Smart routing
    if words & RUNNING_KW:
        proc    = await update.message.reply_text("🏃 Checking with your coach…")
        profile = notion.get_user_profile()
        history = notion.get_run_history(10)
        advice  = ai.running_coach(text, history, profile)
        await proc.edit_text(f"*🏃 Running Coach*\n\n{advice}", parse_mode="Markdown")
    elif words & NUTRITION_KW:
        proc    = await update.message.reply_text("🥗 Consulting your nutritionist…")
        profile = notion.get_user_profile()
        advice  = ai.nutrition_advice(text, profile)
        await proc.edit_text(f"*🥗 Nutrition*\n\n{advice}", parse_mode="Markdown")
    elif words & HEALTH_KW:
        proc    = await update.message.reply_text("💊 Checking on you…")
        profile = notion.get_user_profile()
        logs    = notion.get_health_logs(14)
        advice  = ai.health_advice(logs, text, profile)
        await proc.edit_text(f"*💊 Health*\n\n{advice}", parse_mode="Markdown")
    elif words & TASK_KW:
        proc      = await update.message.reply_text("🤔 Breaking this down…")
        breakdown = ai.break_down_task(text)
        if breakdown:
            steps = "\n".join(f"{i+1}. {s['step']}" for i, s in enumerate(breakdown.get("steps", [])))
            await proc.edit_text(
                f"📋 *Task Breakdown*\n\n*{breakdown.get('task_name')}*\n\n{steps}\n\n"
                "_Use /addtask to save to Notion!_",
                parse_mode="Markdown",
            )
        else:
            await proc.edit_text("Try `/addtask [description]` for best results!")
    else:
        profile = notion.get_user_profile()
        reply   = ai.chat(text, profile)
        await update.message.reply_text(reply)


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN not set in .env")
    if not CHAT_ID:
        raise ValueError("TELEGRAM_CHAT_ID not set in .env")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start",      start))
    app.add_handler(CommandHandler("help",       help_cmd))
    app.add_handler(CommandHandler("checkin",    checkin_cmd))
    app.add_handler(CommandHandler("me",         me_cmd))
    app.add_handler(CommandHandler("health",     health_cmd))
    app.add_handler(CommandHandler("log",        log_cmd))
    app.add_handler(CommandHandler("run",        run_cmd))
    app.add_handler(CommandHandler("logrun",     logrun_cmd))
    app.add_handler(CommandHandler("runstats",   runstats_cmd))
    app.add_handler(CommandHandler("runplan",    runplan_cmd))
    app.add_handler(CommandHandler("nutrition",  nutrition_cmd))
    app.add_handler(CommandHandler("tasks",      tasks_cmd))
    app.add_handler(CommandHandler("addtask",    addtask_cmd))
    app.add_handler(CommandHandler("reminders",  reminders_cmd))

    # Buttons & free text
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # ── Scheduled Jobs ──────────────────────────────────────
    # Reminder check every 60 seconds
    app.job_queue.run_repeating(check_reminders, interval=60, first=10)
    # Morning message — daily at 07:30 UTC (adjust to your timezone offset)
    app.job_queue.run_daily(send_morning_message,  time=datetime.strptime("07:30", "%H:%M").time())
    # Evening check-in — daily at 20:00 UTC
    app.job_queue.run_daily(send_daily_checkin,    time=datetime.strptime("20:00", "%H:%M").time())

    logger.info("🤖 Care Bot is running!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
