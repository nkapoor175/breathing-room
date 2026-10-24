"""Officer and volunteer bot on Telegram (A05).

  /start  -> "Officer" or "Volunteer" -> zone. An officer's phone takes over a
             simulated officer in that zone; from then on plans reach that phone.
  Instructions to officers come with [On my way] [Arrived] buttons; each press
  publishes an OfficerStatus (the dashboard's officer list updates).
  Any text a registered person sends (English, Tamil or Hindi) goes to report
  fusion and becomes a Report on br/report. If the model can't tell the zone,
  the sender's own zone is used.
  /whoami -> what this phone is registered as.

Sign-ups are saved in act/telegram_registry.json (chat ids, git-ignored) so a
restart doesn't lose them.

The bot runs on its own thread with its own asyncio loop (start_in_thread), so
run_act's watchdog loop and planner threads are untouched. notify() can be called
from any thread.

Run alone (no watchdog/planner):  python -m act.telegram_bot
Normally it starts inside:        python -m act.run_act
"""
import asyncio, json, os, threading
from pathlib import Path
from typing import Callable, Optional

from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup as Keyboard, Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes,
                          MessageHandler, filters)

from common.contracts import OfficerStatus, Report, Venue
from common.timeutil import now_iso

REGISTRY_FILE = Path(__file__).parent / "telegram_registry.json"


class Registry:
    """chat id -> {"role": "officer"|"volunteer", "zone", "name", "officer_id"?}, saved to disk."""

    def __init__(self, path: Path = REGISTRY_FILE):
        self.path = path
        try:
            self.data = {int(k): v for k, v in json.loads(path.read_text(encoding="utf-8")).items()}
        except FileNotFoundError:
            self.data = {}
        self.lock = threading.Lock()

    def get(self, chat_id: int) -> Optional[dict]:
        with self.lock:
            return self.data.get(chat_id)

    def set(self, chat_id: int, entry: dict):
        with self.lock:
            self.data[chat_id] = entry
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")


class OfficerBot:
    """Telegram-free core: everything the handlers do, as plain methods (tested directly)."""

    def __init__(self, venue: Venue, officers, executor, publish: Callable[[str, object], None],
                 fuse: Callable[[str, int], Report], registry: Registry, log: Callable[[str], None] = print):
        self.zones = {z.id: z.name for z in venue.zones}
        self.officers = officers
        self.executor = executor
        self.publish = publish
        self.fuse = fuse                     # (text, chat_id) -> Report
        self.registry = registry
        self.log = log
        for chat_id, e in registry.data.items():          # restore officer phones after a restart
            if e["role"] == "officer":
                e["officer_id"] = officers.claim(e["zone"], chat_id, e["name"])["officer_id"]

    def zone_label(self, zid: str) -> str:
        return f"{self.zones.get(zid, zid)} (zone {zid})"

    def register(self, chat_id: int, name: str, role: str, zone: str) -> str:
        if role not in ("officer", "volunteer") or zone not in self.zones:
            return "Sorry, that didn't work. Send /start to try again."
        entry = {"role": role, "zone": zone, "name": name}
        if role == "officer":
            o = self.officers.claim(zone, chat_id, name)
            entry["officer_id"] = o["officer_id"]
            self.publish("br/officer", OfficerStatus(
                t=now_iso(), officer_id=o["officer_id"], name=name, zone=o["zone"],
                status=o.get("status", "idle"), task=None, simulated=False))
        self.registry.set(chat_id, entry)
        self.log(f"telegram: {name} registered as {role} in zone {zone}")
        if role == "officer":
            return (f"✅ You're registered as an officer in {self.zone_label(zone)}.\n"
                    f"Instructions will arrive here. Press the buttons under them so the control room "
                    f"knows where you are. You can also type what you see; it becomes a report.")
        return (f"✅ You're registered as a volunteer in {self.zone_label(zone)}.\n"
                f"Type what you see (English, தமிழ் or हिन्दी), e.g. \"people pushing near gate 2\". "
                f"It goes straight to the control room.")

    def whoami(self, chat_id: int) -> str:
        e = self.registry.get(chat_id)
        if not e:
            return "You're not registered yet. Send /start."
        return f"You're registered as {e['role']} {e['name']} in {self.zone_label(e['zone'])}."

    def pressed(self, chat_id: int, officer_id: str, status: str) -> tuple[bool, str]:
        """[On my way] / [Arrived]. Only the phone that holds this officer may press."""
        o = self.officers.by_id(officer_id)
        if not o or o.get("telegram_chat_id") != chat_id:
            return False, "This instruction isn't yours."
        self.executor.officer_pressed(officer_id, status)
        e = self.registry.get(chat_id)
        if status == "arrived" and e and e["zone"] != o["zone"]:   # remember where they are now
            self.registry.set(chat_id, {**e, "zone": o["zone"]})
        return True, ("👍 Thanks, the control room sees you're on your way." if status == "on_the_way"
                      else f"✅ Marked as arrived in {self.zone_label(o['zone'])}.")

    def report_text(self, chat_id: int, text: str) -> str:
        e = self.registry.get(chat_id)
        if not e:
            return "Please send /start first so we know your zone."
        r = self.fuse(text, chat_id)
        if r.zone is None:
            r = r.model_copy(update={"zone": e["zone"]})
        self.publish("br/report", r)
        self.log(f"telegram: report from {e['name']}: zone {r.zone} severity {r.severity}: {r.text}")
        return f"📨 Sent to the control room: {self.zone_label(r.zone)}, severity {r.severity}/5."


def status_buttons(officer_id: str, after: Optional[str] = None) -> Optional[Keyboard]:
    if after == "arrived":
        return None
    row = [] if after == "on_the_way" else [Button("🚶 On my way", callback_data=f"st:{officer_id}:on_the_way")]
    row.append(Button("✅ Arrived", callback_data=f"st:{officer_id}:arrived"))
    return Keyboard([row])


class TelegramBot:
    """Telegram glue around OfficerBot."""

    def __init__(self, token: str, core: OfficerBot):
        self.token = token
        self.core = core
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.app: Optional[Application] = None
        self.ready = threading.Event()

    # ---------- handlers ----------
    async def _start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Breathing Room crowd-safety team. Who are you?",
            reply_markup=Keyboard([[Button("👮 Officer", callback_data="role:officer"),
                                    Button("🙋 Volunteer", callback_data="role:volunteer")]]))

    async def _whoami(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(self.core.whoami(update.effective_chat.id))

    async def _button(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        chat_id = q.message.chat.id
        parts = (q.data or "").split(":")
        if parts[0] == "role" and len(parts) == 2:
            await q.answer()
            rows = [[Button(f"{name} ({zid})", callback_data=f"zone:{parts[1]}:{zid}")]
                    for zid, name in self.core.zones.items()]
            await q.edit_message_text("Which zone are you in?", reply_markup=Keyboard(rows))
        elif parts[0] == "zone" and len(parts) == 3:
            await q.answer()
            name = q.from_user.first_name or "Officer"
            await q.edit_message_text(self.core.register(chat_id, name, parts[1], parts[2]))
        elif parts[0] == "st" and len(parts) == 3:
            ok, reply = self.core.pressed(chat_id, parts[1], parts[2])
            await q.answer(reply)
            if ok:
                await q.edit_message_reply_markup(status_buttons(parts[1], after=parts[2]))
                await q.message.reply_text(reply)
        else:
            await q.answer()

    async def _text(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        try:
            reply = await asyncio.to_thread(self.core.report_text, chat_id, update.message.text)
        except Exception as e:
            self.core.log(f"telegram: report failed ({type(e).__name__}: {e})")
            reply = "Sorry, that didn't go through. Please try again or call the control room."
        await update.message.reply_text(reply)

    # ---------- sending from other threads ----------
    def notify(self, o: dict, text: str, ask_status: bool = False):
        """Executor hook: phone if the officer has one, else print."""
        chat_id = o.get("telegram_chat_id")
        if not chat_id or not self.ready.is_set():
            print(f"  -> {o['name']}: {text}")
            return
        coro = self.app.bot.send_message(
            chat_id, f"🚨 {text}",
            reply_markup=status_buttons(o["officer_id"]) if ask_status else None)
        fut = asyncio.run_coroutine_threadsafe(coro, self.loop)
        fut.add_done_callback(lambda f: f.exception() and self.core.log(
            f"telegram: could not message {o['name']} ({f.exception()})"))

    # ---------- running ----------
    async def _run(self):
        self.app = Application.builder().token(self.token).build()
        self.app.add_handler(CommandHandler("start", self._start))
        self.app.add_handler(CommandHandler("whoami", self._whoami))
        self.app.add_handler(CallbackQueryHandler(self._button))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._text))
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(drop_pending_updates=True)
        self.loop = asyncio.get_running_loop()
        self.ready.set()
        me = await self.app.bot.get_me()
        self.core.log(f"telegram: @{me.username} running; {len(self.core.registry.data)} phone(s) registered")
        await asyncio.Event().wait()          # run until the process ends

    def start_in_thread(self):
        threading.Thread(target=lambda: asyncio.run(self._run()), daemon=True, name="telegram").start()
        if not self.ready.wait(30):
            self.core.log("telegram: bot did not start within 30 s; instructions will be printed")

    def run_forever(self):
        asyncio.run(self._run())


def build(venue: Venue, officers, executor, publish, on_cost) -> Optional[TelegramBot]:
    """A TelegramBot wired to report fusion, or None if there is no token."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("telegram: TELEGRAM_BOT_TOKEN not set; instructions will be printed")
        return None
    from act.reports import ReportFusion, nemotron_ask
    fusion = ReportFusion([z.model_dump() for z in venue.zones], nemotron_ask(on_cost))
    core = OfficerBot(venue, officers, executor, publish,
                      lambda text, chat_id: fusion.fuse(text, "telegram", node=str(chat_id)), Registry())
    return TelegramBot(token, core)


def main():
    from act.executor import Executor, Officers
    from act.planner import load_venue
    from common.bus import make_client, publish

    venue = load_venue()
    mq = make_client("act-telegram")
    mq.loop_start()
    officers = Officers()
    executor = Executor(venue, officers, lambda t, m: publish(mq, t, m))
    bot = build(venue, officers, executor, lambda t, m: publish(mq, t, m), lambda c: publish(mq, "br/cost", c))
    if bot:
        executor.notify = bot.notify
        bot.run_forever()


if __name__ == "__main__":
    main()
