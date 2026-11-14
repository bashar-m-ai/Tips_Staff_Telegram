"""The tip splitter as a small web page.

It runs next to the Telegram bot, in the same process, and uses the same
split logic (tip_pool.py and staff.py). Nothing is stored: the page sends the
shift, this file answers with the result.

Try it on your own computer:   python web.py   then open http://localhost:8080
"""
import hashlib
import json
import math
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from staff import StaffMember
from tip_pool import TipPool

HERE = Path(__file__).parent

# The only files this server hands out: address -> (file, type)
FILES = {
    "/": ("app.html", "text/html; charset=utf-8"),
    "/logo.png": ("logo.png", "image/png"),
}

def page_version():
    """A short fingerprint of app.html. It changes whenever the page changes,
    so an open page can notice that a newer one has been deployed."""
    return hashlib.sha256((HERE / "app.html").read_bytes()).hexdigest()[:12]


MAX_BODY_BYTES = 20_000
MAX_PEOPLE = 60
MAX_NAME_LENGTH = 40
MAX_HOURS = 24
MAX_TOTAL = 1_000_000


class BadInput(ValueError):
    """The page sent something we cannot calculate. The message is shown to the user."""


def _positive_number(value, what, maximum):
    # bool is a kind of int in Python, so rule it out first
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BadInput(f"{what} must be a number.")
    if not math.isfinite(value) or value <= 0:
        raise BadInput(f"{what} must be more than zero.")
    if value > maximum:
        raise BadInput(f"{what} is too high.")
    return float(value)


def calculate(data):
    """Check the shift the page sent and split the tips with the bot's own logic."""
    if not isinstance(data, dict):
        raise BadInput("Could not read the request.")

    total = _positive_number(data.get("total"), "The total", MAX_TOTAL)

    people = data.get("people")
    if not isinstance(people, list) or not people:
        raise BadInput("Add at least one person.")
    if len(people) > MAX_PEOPLE:
        raise BadInput("Too many people.")

    pool = TipPool(total)
    for person in people:
        if not isinstance(person, dict):
            raise BadInput("Could not read one of the people.")
        name = person.get("name")
        if not isinstance(name, str) or not name.strip():
            raise BadInput("Every person needs a name.")
        name = name.strip()[:MAX_NAME_LENGTH]
        hours = _positive_number(person.get("hours"), f"Hours for {name}", MAX_HOURS)
        if person.get("dept") not in ("Kitchen", "Service"):
            raise BadInput(f"{name} needs a department.")
        multiplier = 0.5 if person.get("share") == "half" else 1.0
        pool.add_member(StaffMember(name, hours, person["dept"], multiplier))

    for dept in ("Kitchen", "Service"):
        if not any(m.department == dept for m in pool.members):
            raise BadInput(f"Add at least one person to {dept}.")

    pool.split()
    return {"total": round(total, 2), "people": [m.to_dict() for m in pool.members]}


class Handler(BaseHTTPRequestHandler):
    timeout = 15  # seconds; drops connections that just hang
    server_version = "TipSplit"

    def _send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, status, payload):
        self._send(status, json.dumps(payload).encode(), "application/json")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            return self._send(200, b"ok", "text/plain")
        if path == "/version":
            return self._send(200, page_version().encode(), "text/plain")
        if path not in FILES:
            return self._send(404, b"Not found", "text/plain")
        filename, content_type = FILES[path]
        self._send(200, (HERE / filename).read_bytes(), content_type)

    do_HEAD = do_GET

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/api/split":
            return self._send(404, b"Not found", "text/plain")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if not 0 < length <= MAX_BODY_BYTES:
            return self._send_json(400, {"error": "Could not read the request."})
        try:
            data = json.loads(self.rfile.read(length))
            result = calculate(data)
        except BadInput as problem:
            return self._send_json(400, {"error": str(problem)})
        except (ValueError, UnicodeDecodeError):
            return self._send_json(400, {"error": "Could not read the request."})
        self._send_json(200, result)

    def log_message(self, format, *args):
        pass  # keep Railway's log for the bot


def make_server(port=None):
    if port is None:
        port = int(os.getenv("PORT", "8080"))  # Railway tells us the port through PORT
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.daemon_threads = True
    return server


def start_in_background(port=None):
    """Start the page without blocking, so the bot can keep running in the main thread."""
    server = make_server(port)
    threading.Thread(target=server.serve_forever, daemon=True, name="web").start()
    print(f"Web app running on port {server.server_address[1]}")
    return server


if __name__ == "__main__":
    server = make_server()
    print(f"Open http://localhost:{server.server_address[1]}")
    server.serve_forever()
