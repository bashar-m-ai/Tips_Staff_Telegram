"""Chat simulations for the tip bot.

These tests run the real handlers from bot.py, but swap the internet
connection to Telegram for a fake one that just records what the bot
tried to send. Nothing here talks to the real bot or needs a token.

Run with:  python -m pytest -q
"""
import asyncio
import json

import pytest
from telegram import Update
from telegram.ext import Application
from telegram.request import BaseRequest

import bot

USER = {"id": 5, "is_bot": False, "first_name": "Tester"}
CHAT = {"id": 5, "type": "private"}


class FakeTelegram(BaseRequest):
    """Pretends to be Telegram's servers and remembers every call."""

    def __init__(self):
        self.calls = []
        self.next_message_id = 1000

    async def initialize(self):
        pass

    async def shutdown(self):
        pass

    async def do_request(self, url, method, request_data=None, *args, **kwargs):
        endpoint = url.rsplit("/", 1)[1]
        params = dict(request_data.parameters) if request_data else {}
        self.calls.append((endpoint, params))

        if endpoint == "getMe":
            result = {"id": 1, "is_bot": True, "first_name": "Tip", "username": "tip_test_bot"}
        elif endpoint in ("sendMessage", "editMessageText"):
            self.next_message_id += 1
            result = {
                "message_id": params.get("message_id", self.next_message_id),
                "date": 0,
                "chat": CHAT,
                "text": params.get("text", ""),
            }
        else:
            result = True
        return 200, json.dumps({"ok": True, "result": result}).encode()


class Chat:
    """One simulated private chat with the bot."""

    def __init__(self):
        self.telegram = FakeTelegram()
        self.app = Application.builder().token("1:TEST").request(self.telegram).updater(None).build()
        bot.register_handlers(self.app)
        self.loop = asyncio.new_event_loop()
        self.loop.run_until_complete(self.app.initialize())
        self.update_id = 0

    def close(self):
        self.loop.run_until_complete(self.app.shutdown())
        self.loop.close()

    def _process(self, payload):
        self.update_id += 1
        payload["update_id"] = self.update_id
        self.telegram.calls.clear()
        update = Update.de_json(payload, self.app.bot)
        self.loop.run_until_complete(self.app.process_update(update))

    def say(self, text):
        message = {"message_id": self.update_id + 1, "date": 0, "chat": CHAT, "from": USER, "text": text}
        if text.startswith("/"):
            message["entities"] = [{"type": "bot_command", "offset": 0, "length": len(text)}]
        self._process({"message": message})

    def press(self, data):
        self._process({"callback_query": {
            "id": str(self.update_id + 1),
            "from": USER,
            "chat_instance": "c",
            "data": data,
            "message": {"message_id": 1, "date": 0, "chat": CHAT, "text": "previous message"},
        }})

    # What the bot did in response to the last say()/press()

    def _last_screen(self):
        screens = [p for name, p in self.telegram.calls if name in ("sendMessage", "editMessageText")]
        return screens[-1] if screens else None

    @property
    def text(self):
        screen = self._last_screen()
        return screen["text"] if screen else None

    @property
    def buttons(self):
        screen = self._last_screen()
        if not screen or "reply_markup" not in screen:
            return []
        markup = screen["reply_markup"]
        if isinstance(markup, str):
            markup = json.loads(markup)
        return [
            b.get("callback_data") or b["web_app"]["url"]
            for row in markup["inline_keyboard"] for b in row
        ]

    @property
    def alert(self):
        """Text of the first pop-up answer (the one the user actually sees)."""
        for name, params in self.telegram.calls:
            if name == "answerCallbackQuery":
                return params.get("text")
        return None

    # Shortcuts

    def add(self, name, hours, share="full"):
        self.say(name)
        self.say(str(hours))
        self.press(f"share_{share}")

    def finished_split(self, total="100", kitchen=(("Anna", 8),), service=(("Ben", 8),)):
        self.say("/start")
        self.press("new_split")
        self.say(total)
        self.press("dept_kitchen")
        for name, hours in kitchen:
            self.add(name, hours)
        self.press("done_dept")
        for name, hours in service:
            self.add(name, hours)
        self.press("done_dept")


@pytest.fixture
def chat():
    c = Chat()
    yield c
    c.close()


# ── The flow that already existed ────────────────────────────────────────────

def test_normal_split_still_works(chat):
    chat.finished_split()
    assert "€100.00 split" in chat.text
    assert chat.text.count("→ *€50.00*") == 2
    assert chat.buttons == ["edit", "new_split"]


def test_new_split_after_result_starts_clean(chat):
    chat.finished_split()
    chat.press("new_split")
    assert "Enter total tips today" in chat.text
    chat.say("60")
    chat.press("dept_service")
    assert "Service crew" in chat.text
    assert "edit" in chat.buttons


# ── Edit after the result ────────────────────────────────────────────────────

def test_edit_menu_lists_total_and_every_person(chat):
    chat.finished_split()
    chat.press("edit")
    assert "What do you want to change?" in chat.text
    assert chat.buttons == ["edit_total", "edit_p_0", "edit_p_1", "edit_back"]


def test_edit_total_recalculates_result(chat):
    chat.finished_split()
    chat.press("edit")
    chat.press("edit_total")
    assert "Now: €100.00" in chat.text
    chat.say("200")
    assert "Total is now *€200.00*" in chat.text
    assert chat.text.count("→ *€100.00*") == 2
    assert chat.buttons == ["edit", "new_split"]


def test_edit_hours_recalculates_result(chat):
    chat.finished_split(total="120", kitchen=(("Anna", 8), ("Cem", 8)))
    assert chat.text.count("→ *€30.00*") == 2          # kitchen: 60 split evenly
    chat.press("edit")
    chat.press("edit_p_1")
    assert "*Cem*" in chat.text and "8.0h" in chat.text
    chat.press("ep_hours")
    chat.say("4")
    assert "*Cem* now has 4.0h" in chat.text
    assert "Anna 8.0h → *€40.00*" in chat.text
    assert "Cem 4.0h → *€20.00*" in chat.text


def test_edit_name(chat):
    chat.finished_split()
    chat.press("edit")
    chat.press("edit_p_0")
    chat.press("ep_name")
    chat.say("Annika")
    assert "*Anna* is now *Annika*" in chat.text
    assert "Annika 8.0h" in chat.text
    assert "Anna 8.0h" not in chat.text


def test_switch_share(chat):
    chat.finished_split(total="120", kitchen=(("Anna", 8), ("Cem", 8)))
    chat.press("edit")
    chat.press("edit_p_1")
    chat.press("ep_share")
    assert "*Cem* is now ½ share" in chat.text
    assert "Anna 8.0h → *€40.00*" in chat.text
    assert "Cem 8.0h ½ → *€20.00*" in chat.text


def test_remove_person(chat):
    chat.finished_split(total="120", kitchen=(("Anna", 8), ("Cem", 8)))
    chat.press("edit")
    chat.press("edit_p_1")
    chat.press("ep_remove")
    assert "*Cem* removed" in chat.text
    assert "Cem 8.0h" not in chat.text
    assert "Anna 8.0h → *€60.00*" in chat.text


def test_cannot_remove_last_person_of_a_department(chat):
    chat.finished_split()
    chat.press("edit")
    chat.press("edit_p_0")
    chat.press("ep_remove")
    assert "only one in Kitchen" in chat.alert
    assert chat.text is None                     # screen unchanged
    chat.press("ep_hours")                       # still on the person screen
    assert "Edit hours for Anna" in chat.text


def test_back_from_edit_menu_shows_same_result(chat):
    chat.finished_split()
    chat.press("edit")
    chat.press("edit_back")
    assert chat.text.count("→ *€50.00*") == 2
    assert chat.buttons == ["edit", "new_split"]


def test_back_from_person_screen_returns_to_edit_menu(chat):
    chat.finished_split()
    chat.press("edit")
    chat.press("edit_p_0")
    chat.press("edit")
    assert chat.buttons == ["edit_total", "edit_p_0", "edit_p_1", "edit_back"]


# ── Wrong input while editing ────────────────────────────────────────────────

@pytest.mark.parametrize("bad", ["abc", "-5", "0", "nan", "inf"])
def test_bad_total_is_rejected_and_can_be_retried(chat, bad):
    chat.finished_split()
    chat.press("edit")
    chat.press("edit_total")
    chat.say(bad)
    assert "Enter a positive number" in chat.text
    chat.say("80,50")                            # comma works like a dot
    assert "Total is now *€80.50*" in chat.text


def test_bad_hours_is_rejected_and_can_be_retried(chat):
    chat.finished_split()
    chat.press("edit")
    chat.press("edit_p_0")
    chat.press("ep_hours")
    chat.say("lots")
    assert "Enter a positive number" in chat.text
    chat.say("6,5")
    assert "*Anna* now has 6.5h" in chat.text


# ── Edit in the middle of entering staff ─────────────────────────────────────

def test_edit_total_mid_entry_then_continue(chat):
    chat.say("/start")
    chat.press("new_split")
    chat.say("100")
    chat.press("dept_kitchen")
    chat.add("Anna", 8)
    chat.press("edit")
    chat.press("edit_total")
    chat.say("300")
    assert "Total is now *€300.00*" in chat.text
    assert "Anna" in chat.text and "Enter next Kitchen name" in chat.text
    chat.press("done_dept")
    chat.add("Ben", 8)
    chat.press("done_dept")
    assert chat.text.count("→ *€150.00*") == 2


def test_fix_hours_mid_entry_then_continue(chat):
    chat.say("/start")
    chat.press("new_split")
    chat.say("100")
    chat.press("dept_kitchen")
    chat.add("Anna", 75)                         # typo: meant 7.5
    chat.press("edit")
    chat.press("edit_p_0")
    chat.press("ep_hours")
    chat.say("7.5")
    assert "Anna · 7.5h" in chat.text
    chat.add("Cem", 7.5)
    chat.press("done_dept")
    chat.add("Ben", 8)
    chat.press("done_dept")
    assert chat.text.count("→ *€25.00*") == 2    # kitchen 50 split evenly


def test_remove_only_person_mid_entry_then_done_is_blocked(chat):
    chat.say("/start")
    chat.press("new_split")
    chat.say("100")
    chat.press("dept_kitchen")
    chat.add("Anna", 8)
    chat.press("edit")
    chat.press("edit_p_0")
    chat.press("ep_remove")                      # allowed: Kitchen is still open
    assert "*Anna* removed" in chat.text
    chat.press("done_dept")
    assert "Add at least one person to Kitchen" in chat.alert


def test_cannot_empty_finished_department_from_second_department(chat):
    chat.say("/start")
    chat.press("new_split")
    chat.say("100")
    chat.press("dept_kitchen")
    chat.add("Anna", 8)
    chat.press("done_dept")                      # now entering Service
    chat.press("edit")
    chat.press("edit_p_0")
    chat.press("ep_remove")
    assert "only one in Kitchen" in chat.alert


# ── Old buttons and resets ───────────────────────────────────────────────────

def test_edit_button_after_reset_does_nothing_harmful(chat):
    chat.finished_split()
    chat.press("reset")
    chat.press("edit")
    assert "Nothing to edit" in chat.alert
    chat.press("new_split")
    assert "Enter total tips today" in chat.text


def test_reset_works_from_inside_edit(chat):
    chat.finished_split()
    chat.press("edit")
    chat.press("edit_total")
    chat.say("reset")
    assert "Ready when you are" in chat.text


# ── "Open the app" button ────────────────────────────────────────────────────

def test_no_app_button_until_the_page_has_an_address(chat, monkeypatch):
    monkeypatch.delenv("APP_URL", raising=False)
    monkeypatch.delenv("RAILWAY_PUBLIC_DOMAIN", raising=False)
    chat.say("/start")
    assert chat.buttons == ["new_split"]


def test_app_button_appears_once_railway_gives_a_domain(chat, monkeypatch):
    monkeypatch.delenv("APP_URL", raising=False)
    monkeypatch.setenv("RAILWAY_PUBLIC_DOMAIN", "tips-example.up.railway.app")
    chat.say("/start")
    assert chat.buttons == ["new_split", "https://tips-example.up.railway.app"]
    chat.press("new_split")                      # the normal flow is untouched
    assert "Enter total tips today" in chat.text


def test_no_app_button_in_group_chats(chat, monkeypatch):
    # Telegram rejects open-inside-Telegram buttons outside private chats.
    monkeypatch.setenv("RAILWAY_PUBLIC_DOMAIN", "tips-example.up.railway.app")
    monkeypatch.setitem(CHAT, "type", "group")
    chat.say("/start")
    assert chat.buttons == ["new_split"]


# ── Number parsing ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected", [
    ("350", 350.0), ("7,5", 7.5), ("7.5", 7.5), (" 12 ", 12.0),
    ("abc", None), ("", None), ("0", None), ("-3", None), ("nan", None), ("inf", None),
])
def test_parse_positive(text, expected):
    assert bot.parse_positive(text) == expected
