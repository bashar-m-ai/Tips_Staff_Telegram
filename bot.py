import math
import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)
from staff import StaffMember
from tip_pool import TipPool

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

(
    MAIN_MENU, ASK_TOTAL, ASK_DEPT_ORDER, ASK_NAME, ASK_HOURS, ASK_SHARE,
    EDIT_MENU, EDIT_PERSON, EDIT_TOTAL, EDIT_NAME, EDIT_HOURS,
) = range(11)

DEPT_EMOJI = {"Kitchen": "🍳", "Service": "🍽️"}

RESET_BTN = InlineKeyboardButton("🔄 Reset", callback_data="reset")
EDIT_BTN = InlineKeyboardButton("✏️ Edit", callback_data="edit")
RESET_ROW = [RESET_BTN]


# ── Keyboards ────────────────────────────────────────────────────────────────

def app_url():
    """Address of the web page, if it has one. Railway sets RAILWAY_PUBLIC_DOMAIN
    once the service has a public domain; APP_URL can override it."""
    if os.getenv("APP_URL"):
        return os.getenv("APP_URL")
    domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    return f"https://{domain}" if domain else None


def main_menu_kb(update=None):
    rows = [[InlineKeyboardButton("💰 New Tip Split", callback_data="new_split")]]
    # Telegram only allows "open inside Telegram" buttons in private chats.
    chat = update.effective_chat if update else None
    url = app_url()
    if url and chat is not None and chat.type == "private":
        rows.append([InlineKeyboardButton("📱 Open the app", web_app=WebAppInfo(url=url))])
    return InlineKeyboardMarkup(rows)


def reset_kb():
    return InlineKeyboardMarkup([RESET_ROW])


def dept_kb():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🍳 Kitchen", callback_data="dept_kitchen"),
            InlineKeyboardButton("🍽️ Service", callback_data="dept_service"),
        ],
        RESET_ROW,
    ])


def share_kb():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Full Share", callback_data="share_full"),
            InlineKeyboardButton("Half Share", callback_data="share_half"),
        ],
        RESET_ROW,
    ])


def done_kb(dept):
    emoji = DEPT_EMOJI[dept]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✅ Done with {emoji} {dept}", callback_data="done_dept")],
        [EDIT_BTN, RESET_BTN],
    ])


def result_kb():
    # Shown under a finished split: fix a mistake or start a new one.
    return InlineKeyboardMarkup([
        [EDIT_BTN],
        [InlineKeyboardButton("💰 New Tip Split", callback_data="new_split")],
    ])


def edit_menu_kb(pool):
    # One button for the total, then one button per person.
    rows = [[InlineKeyboardButton(f"💰 Total · €{pool.total_tips:.2f}", callback_data="edit_total")]]
    for i, m in enumerate(pool.members):
        rows.append([InlineKeyboardButton(
            f"{DEPT_EMOJI[m.department]} {m.name} · {m.hours}h · {share_label(m)}",
            callback_data=f"edit_p_{i}",
        )])
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="edit_back")])
    return InlineKeyboardMarkup(rows)


def edit_person_kb(member):
    switch_to = "½ share" if member.multiplier == 1.0 else "full share"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ Name", callback_data="ep_name"),
            InlineKeyboardButton("⏱️ Hours", callback_data="ep_hours"),
        ],
        [InlineKeyboardButton(f"🔁 Switch to {switch_to}", callback_data="ep_share")],
        [InlineKeyboardButton("🗑️ Remove", callback_data="ep_remove")],
        [InlineKeyboardButton("⬅️ Back", callback_data="edit")],
    ])


def back_to_edit_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="edit")]])


# ── Text helpers ──────────────────────────────────────────────────────────────

def share_label(member):
    return "full" if member.multiplier == 1.0 else "½"


def parse_positive(text):
    """Turn '7,5' or '7.5' into 7.5. Returns None if it is not a positive number."""
    try:
        value = float(text.replace(",", "."))
    except ValueError:
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return value


def roster_text(members):
    if not members:
        return ""
    lines = ["📋 *Staff so far:*"]
    for m in members:
        lines.append(f"  {DEPT_EMOJI[m.department]} {m.name} · {m.hours}h · {share_label(m)}")
    return "\n".join(lines)


def result_text(pool):
    kitchen = [m for m in pool.members if m.department == "Kitchen"]
    service = [m for m in pool.members if m.department == "Service"]
    lines = [f"💰 *€{pool.total_tips:.2f} split*\n"]
    lines.append("🍳 *Kitchen*")
    for m in kitchen:
        share = " ½" if m.multiplier != 1.0 else ""
        lines.append(f"  {m.name} {m.hours}h{share} → *€{m.tips:.2f}*")
    lines.append("\n🍽️ *Service*")
    for m in service:
        share = " ½" if m.multiplier != 1.0 else ""
        lines.append(f"  {m.name} {m.hours}h{share} → *€{m.tips:.2f}*")
    lines.append(f"\n✅ Total: *€{sum(m.tips for m in pool.members):.2f}*")
    return "\n".join(lines)


MENU_TEXT = "👋 *Tip Split Bot*\n\nReady when you are!"


# ── Handlers ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        MENU_TEXT, parse_mode="Markdown", reply_markup=main_menu_kb(update)
    )
    return MAIN_MENU


async def reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🔄 Reset!")
    context.user_data.clear()
    await query.edit_message_text(
        MENU_TEXT, parse_mode="Markdown", reply_markup=main_menu_kb(update)
    )
    return MAIN_MENU


async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text(
        "💰 *New Tip Split*\n\nEnter total tips today (€):",
        parse_mode="Markdown",
        reply_markup=reset_kb(),
    )
    return ASK_TOTAL


async def got_total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = parse_positive(update.message.text)
    if total is None:
        await update.message.reply_text(
            "⚠️ Enter a positive number, e.g. `350`",
            parse_mode="Markdown", reply_markup=reset_kb(),
        )
        return ASK_TOTAL

    context.user_data["pool"] = TipPool(total)
    await update.message.reply_text(
        f"✅ *€{total:.2f}* set!\n\nWhich department goes first?",
        parse_mode="Markdown",
        reply_markup=dept_kb(),
    )
    return ASK_DEPT_ORDER


async def got_dept_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    dept = "Kitchen" if query.data == "dept_kitchen" else "Service"
    other = "Service" if dept == "Kitchen" else "Kitchen"
    context.user_data.update(current_dept=dept, other_dept=other, switched=False)
    emoji = DEPT_EMOJI[dept]
    await query.edit_message_text(
        f"{emoji} *{dept} crew*\n\nEnter first name:",
        parse_mode="Markdown",
        reply_markup=done_kb(dept),
    )
    return ASK_NAME


async def got_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    context.user_data["name"] = name
    await update.message.reply_text(
        f"👤 *{name}*\n\n⏱️ Hours worked?",
        parse_mode="Markdown",
        reply_markup=reset_kb(),
    )
    return ASK_HOURS


async def done_dept_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    pool = context.user_data.get("pool")
    if pool is None:
        await query.answer("Session expired — starting over.")
        await query.edit_message_text(
            MENU_TEXT, parse_mode="Markdown", reply_markup=main_menu_kb(update)
        )
        return MAIN_MENU

    current_dept = context.user_data["current_dept"]
    other_dept = context.user_data["other_dept"]
    switched = context.user_data["switched"]

    if not any(m.department == current_dept for m in pool.members):
        await query.answer(
            f"⚠️ Add at least one person to {current_dept} first!",
            show_alert=True,
        )
        return ASK_NAME

    await query.answer()

    if not switched:
        context.user_data.update(current_dept=other_dept, other_dept=current_dept, switched=True)
        emoji = DEPT_EMOJI[other_dept]
        await query.edit_message_text(
            f"{emoji} *{other_dept} crew*\n\nEnter first name:",
            parse_mode="Markdown",
            reply_markup=done_kb(other_dept),
        )
        return ASK_NAME

    pool.split()
    context.user_data["finished"] = True
    await query.edit_message_text(
        result_text(pool),
        parse_mode="Markdown",
        reply_markup=result_kb(),
    )
    return MAIN_MENU


async def got_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hours = parse_positive(update.message.text)
    if hours is None:
        await update.message.reply_text(
            "⚠️ Enter a positive number, e.g. `7.5`",
            parse_mode="Markdown", reply_markup=reset_kb(),
        )
        return ASK_HOURS

    context.user_data["hours"] = hours
    name = context.user_data["name"]
    await update.message.reply_text(
        f"👤 *{name}* · {hours}h\n\nShare type?",
        parse_mode="Markdown",
        reply_markup=share_kb(),
    )
    return ASK_SHARE


async def got_share(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    pool = context.user_data.get("pool")
    if pool is None:
        await query.answer("Session expired — starting over.")
        await query.edit_message_text(
            MENU_TEXT, parse_mode="Markdown", reply_markup=main_menu_kb(update)
        )
        return MAIN_MENU

    await query.answer()
    multiplier = 1.0 if query.data == "share_full" else 0.5
    member = StaffMember(
        context.user_data["name"],
        context.user_data["hours"],
        context.user_data["current_dept"],
        multiplier,
    )
    pool.add_member(member)
    current_dept = context.user_data["current_dept"]
    roster = roster_text(pool.members)
    await query.edit_message_text(
        f"✅ *{member.name}* added\n\n{roster}\n\n{DEPT_EMOJI[current_dept]} Enter next {current_dept} name:",
        parse_mode="Markdown",
        reply_markup=done_kb(current_dept),
    )
    return ASK_NAME


# ── Edit flow ─────────────────────────────────────────────────────────────────
#
# ✏️ Edit  →  pick 💰 Total or a person  →  change it  →  back where you were.
# "Where you were" is either the finished result (recalculated) or the
# "enter next name" step, depending on context.user_data["finished"].

def current_view(context, note=""):
    """Text, keyboard and state for the screen the user came from."""
    pool = context.user_data["pool"]
    prefix = f"{note}\n\n" if note else ""

    if context.user_data.get("finished"):
        pool.split()
        return prefix + result_text(pool), result_kb(), MAIN_MENU

    dept = context.user_data["current_dept"]
    roster = roster_text(pool.members)
    if roster:
        prefix += roster + "\n\n"
    text = f"{prefix}{DEPT_EMOJI[dept]} Enter next {dept} name:"
    return text, done_kb(dept), ASK_NAME


def edit_target(context):
    """The person currently being edited, or None if they no longer exist."""
    pool = context.user_data.get("pool")
    idx = context.user_data.get("edit_idx")
    if pool is None or idx is None or not 0 <= idx < len(pool.members):
        return None
    return pool.members[idx]


def person_text(member):
    return (
        f"👤 *{member.name}*\n"
        f"{DEPT_EMOJI[member.department]} {member.department} · "
        f"{member.hours}h · {share_label(member)} share\n\n"
        "What do you want to change?"
    )


async def edit_open(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    pool = context.user_data.get("pool")
    if pool is None:
        await query.answer("Nothing to edit — start a new split.", show_alert=True)
        return MAIN_MENU

    await query.answer()
    await query.edit_message_text(
        "✏️ *Edit*\n\nWhat do you want to change?",
        parse_mode="Markdown",
        reply_markup=edit_menu_kb(pool),
    )
    return EDIT_MENU


async def edit_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    pool = context.user_data.get("pool")
    if pool is None:
        await query.answer("Nothing to edit — start a new split.", show_alert=True)
        return MAIN_MENU

    if query.data == "edit_back":
        await query.answer()
        text, kb, state = current_view(context)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
        return state

    if query.data == "edit_total":
        await query.answer()
        await query.edit_message_text(
            f"💰 *Edit total*\n\nNow: €{pool.total_tips:.2f}\nEnter the new total (€):",
            parse_mode="Markdown",
            reply_markup=back_to_edit_kb(),
        )
        return EDIT_TOTAL

    # edit_p_<number>: a person was picked
    context.user_data["edit_idx"] = int(query.data.rsplit("_", 1)[1])
    member = edit_target(context)
    if member is None:
        await query.answer("That list is out of date.", show_alert=True)
        await query.edit_message_text(
            "✏️ *Edit*\n\nWhat do you want to change?",
            parse_mode="Markdown",
            reply_markup=edit_menu_kb(pool),
        )
        return EDIT_MENU

    await query.answer()
    await query.edit_message_text(
        person_text(member), parse_mode="Markdown", reply_markup=edit_person_kb(member)
    )
    return EDIT_PERSON


async def edit_person_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    pool = context.user_data.get("pool")
    member = edit_target(context)
    if member is None:
        await query.answer("Nothing to edit — start a new split.", show_alert=True)
        return MAIN_MENU

    if query.data == "ep_name":
        await query.answer()
        await query.edit_message_text(
            f"✏️ *Edit name*\n\nNow: {member.name}\nEnter the new name:",
            parse_mode="Markdown",
            reply_markup=back_to_edit_kb(),
        )
        return EDIT_NAME

    if query.data == "ep_hours":
        await query.answer()
        await query.edit_message_text(
            f"⏱️ *Edit hours for {member.name}*\n\nNow: {member.hours}h\nEnter the new hours:",
            parse_mode="Markdown",
            reply_markup=back_to_edit_kb(),
        )
        return EDIT_HOURS

    if query.data == "ep_share":
        member.multiplier = 0.5 if member.multiplier == 1.0 else 1.0
        note = f"✅ *{member.name}* is now {share_label(member)} share"

    else:  # ep_remove
        same_dept = [m for m in pool.members if m.department == member.department]
        dept_is_closed = (
            context.user_data.get("finished")
            or member.department != context.user_data.get("current_dept")
        )
        if len(same_dept) == 1 and dept_is_closed:
            # Each department needs at least one person or the split cannot be calculated.
            await query.answer(
                f"⚠️ {member.name} is the only one in {member.department}. "
                "Change the name or hours instead.",
                show_alert=True,
            )
            return EDIT_PERSON
        pool.members.remove(member)
        note = f"🗑️ *{member.name}* removed"

    await query.answer()
    context.user_data.pop("edit_idx", None)
    text, kb, state = current_view(context, note)
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    return state


async def got_edit_total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pool = context.user_data.get("pool")
    total = parse_positive(update.message.text)
    if pool is None or total is None:
        await update.message.reply_text(
            "⚠️ Enter a positive number, e.g. `350`",
            parse_mode="Markdown", reply_markup=back_to_edit_kb(),
        )
        return EDIT_TOTAL

    pool.total_tips = total
    text, kb, state = current_view(context, f"✅ Total is now *€{total:.2f}*")
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    return state


async def got_edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = edit_target(context)
    if member is None:
        return await reset_command(update, context)

    old_name = member.name
    member.name = update.message.text.strip()
    context.user_data.pop("edit_idx", None)
    text, kb, state = current_view(context, f"✅ *{old_name}* is now *{member.name}*")
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    return state


async def got_edit_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = edit_target(context)
    if member is None:
        return await reset_command(update, context)

    hours = parse_positive(update.message.text)
    if hours is None:
        await update.message.reply_text(
            "⚠️ Enter a positive number, e.g. `7.5`",
            parse_mode="Markdown", reply_markup=back_to_edit_kb(),
        )
        return EDIT_HOURS

    member.hours = hours
    context.user_data.pop("edit_idx", None)
    text, kb, state = current_view(context, f"✅ *{member.name}* now has {hours}h")
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    return state


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled.", reply_markup=main_menu_kb(update))
    return MAIN_MENU


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        MENU_TEXT, parse_mode="Markdown", reply_markup=main_menu_kb(update)
    )
    return MAIN_MENU


# Matches the "🔄 Reset" text sent by the old persistent reply keyboard,
# or anyone typing "reset" manually.
RESET_TEXT_FILTER = filters.Regex(r"(?i)^(🔄 )?reset!?$")


async def stale_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Catches taps on buttons from old/expired messages so they don't spin forever
    query = update.callback_query
    await query.answer("This menu has expired — use /start", show_alert=True)


# ── App ───────────────────────────────────────────────────────────────────────

def register_handlers(app):
    reset_btn = CallbackQueryHandler(reset_callback, pattern="^reset$")
    edit_btn = CallbackQueryHandler(edit_open, pattern="^edit$")
    reset_text = MessageHandler(RESET_TEXT_FILTER, reset_command)
    reset_cmd = CommandHandler("reset", reset_command)

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            reset_btn,
            reset_text,
            reset_cmd,
        ],
        states={
            MAIN_MENU: [
                reset_btn, reset_text, reset_cmd, edit_btn,
                CallbackQueryHandler(main_menu_callback, pattern="^new_split$"),
            ],
            ASK_TOTAL: [
                reset_btn, reset_text, reset_cmd,
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_total),
            ],
            ASK_DEPT_ORDER: [
                reset_btn, reset_text, reset_cmd,
                CallbackQueryHandler(got_dept_order, pattern="^dept_(kitchen|service)$"),
            ],
            ASK_NAME: [
                reset_btn, reset_text, reset_cmd, edit_btn,
                CallbackQueryHandler(done_dept_callback, pattern="^done_dept$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_name),
            ],
            ASK_HOURS: [
                reset_btn, reset_text, reset_cmd,
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_hours),
            ],
            ASK_SHARE: [
                reset_btn, reset_text, reset_cmd,
                CallbackQueryHandler(got_share, pattern="^share_(full|half)$"),
            ],
            EDIT_MENU: [
                reset_btn, reset_text, reset_cmd, edit_btn,
                CallbackQueryHandler(edit_menu_callback, pattern=r"^(edit_total|edit_back|edit_p_\d+)$"),
            ],
            EDIT_PERSON: [
                reset_btn, reset_text, reset_cmd, edit_btn,
                CallbackQueryHandler(edit_person_callback, pattern="^ep_(name|hours|share|remove)$"),
            ],
            EDIT_TOTAL: [
                reset_btn, reset_text, reset_cmd, edit_btn,
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_edit_total),
            ],
            EDIT_NAME: [
                reset_btn, reset_text, reset_cmd, edit_btn,
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_edit_name),
            ],
            EDIT_HOURS: [
                reset_btn, reset_text, reset_cmd, edit_btn,
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_edit_hours),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            reset_cmd,
        ],
        allow_reentry=True,
    )

    app.add_handler(conv)
    # Any callback not consumed by the conversation gets answered here,
    # otherwise Telegram shows an endless loading spinner on the button.
    app.add_handler(CallbackQueryHandler(stale_button), group=1)


def main():
    # The web page is an extra. If it cannot start, the bot still runs.
    try:
        import web
        web.start_in_background()
    except Exception as error:
        print(f"Web app not started: {error}")

    app = Application.builder().token(TOKEN).build()
    register_handlers(app)
    print("Bot running")
    app.run_polling()


if __name__ == "__main__":
    main()
