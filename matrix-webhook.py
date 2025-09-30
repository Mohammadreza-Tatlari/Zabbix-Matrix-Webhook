import os
import threading
from dotenv import load_dotenv
import simplematrixbotlib as botlib
import uuid
import html
import time
from flask import Flask, request, jsonify
import requests



# Load environment variables
load_dotenv()

# Configuration
PREFIX = "!"
PORT = int(os.getenv("PORT", 5001))
DEBUG = os.getenv("DEBUG", "False").lower() == "true"


DEFAULT_ROOM = os.getenv("MATRIX_ROOM_ID")
MATRIX_HOMESERVER = os.getenv('MATRIX_HOMESERVER') 
MATRIX_USER = os.getenv('MATRIX_USER')
MATRIX_PASSWORD = os.getenv('MATRIX_PASSWORD') 


# Flask app
app = Flask(__name__)


class MatrixZabbixBot:
    def __init__(self):
        self.creds = botlib.Creds(MATRIX_HOMESERVER, MATRIX_USER, MATRIX_PASSWORD)
        self.bot = botlib.Bot(self.creds)
        self.notifications_enabled = True
        self.notification_history = []
        self.MAX_HISTORY = 50
        self._setup_handlers()

    def _setup_handlers(self):
        @self.bot.listener.on_message_event
        async def handle_command(room, message):
            match = botlib.MessageMatch(room, message, self.bot, "!")
            if not match.is_not_from_this_bot() or not match.prefix():
                return

            cmd = match.command()
            if cmd == "enable_zabbix":
                await self.bot.api.send_text_message(room.room_id, "Zabbix notifications enabled.")
                self.notifications_enabled = True
            elif cmd == "disable_zabbix":
                await self.bot.api.send_text_message(room.room_id, "Zabbix notifications disabled.")
                self.notifications_enabled = False
            elif cmd == "zabbix_status":
                await self.bot.api.send_text_message(
                    room.room_id,
                    f"Notifications are {'enabled' if self.notifications_enabled else 'disabled'}. "
                    f"History size: {len(self.notification_history)}"
                )
            elif cmd == "zabbix_history":
                if not self.notification_history:
                    await self.bot.api.send_text_message(room.room_id, "No history.")
                    return
                text = "Recent notifications:\n\n"
                for i, n in enumerate(self.notification_history[-10:], 1):
                    text += f"{i}. {n.get('subject','No subject')} — {n.get('severity','?')}\n"
                await self.bot.api.send_text_message(room.room_id, text)

    def add_history(self, data):
        if len(self.notification_history) >= self.MAX_HISTORY:
            self.notification_history.pop(0)
        self.notification_history.append(data)

    def send_via_rest(self, room_id: str, subject: str, message: str, severity: str):
        """
        Synchronous send using Matrix client-server API and the bot's access token.
        Returns (ok: bool, details: dict)
        """
        # try to get access token from the simplematrixbotlib async client
        async_client = getattr(self.bot.api, "async_client", None)
        token = None
        if async_client is not None:
            token = getattr(async_client, "access_token", None)

        if not token:
            return False, {"error": "bot_not_ready", "reason": "access token not available yet"}

        txn_id = str(uuid.uuid4())
        url = f"{MATRIX_HOMESERVER}/_matrix/client/v3/rooms/{room_id}/send/m.room.message/{txn_id}"

        # build html safe formatted body
        subject_esc = html.escape(subject)
        message_esc = html.escape(message).replace("\n", "<br/>")
        severity_esc = html.escape(severity)
        formatted_body = f"<strong>{subject_esc}</strong><br/><br/>{message_esc}<br/><br/><em>Severity: {severity_esc}</em>"

        # plain text body
        plain_body = f"{subject}\n\n{message}\n\nSeverity: {severity}"

        payload = {
            "msgtype": "m.text",
            "format": "org.matrix.custom.html",
            "body": plain_body,
            "formatted_body": formatted_body,
        }

        headers = {
            "Authorization": f"Bearer {token}"
        }

        try:
            # PUT is required for the /send endpoint (transactional)
            r = requests.put(url, json=payload, headers=headers, timeout=10)
        except Exception as e:
            return False, {"error": "request_failed", "exception": str(e)}

        if 200 <= r.status_code < 300:
            return True, {"matrix_response": r.json() if r.content else {}}
        else:
            # pass server response back for debugging
            try:
                resp = r.json()
            except Exception:
                resp = r.text
            return False, {"status_code": r.status_code, "response": resp}


matrix_bot = MatrixZabbixBot()


# Flask routes
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json or {}
    # store raw payload into history
    matrix_bot.add_history(data)

    if not matrix_bot.notifications_enabled:
        return jsonify({"status": "ignored", "reason": "notifications disabled"})

    room_id = data.get("room_id") or DEFAULT_ROOM
    if not room_id:
        return jsonify({"status": "error", "reason": "no room_id provided (and no DEFAULT_ROOM set)"}), 400

    subject = data.get("subject", "No subject")
    message = data.get("message", "No message")
    severity = data.get("severity", "Unknown")

    # basic macro handling like your original code
    if "{" in subject:
        subject = "Unknown/default Subject Field From Zabbix"
    if "{" in message:
        message = "Unknown/default Message Field From Zabbix"
    if "{" in severity:
        severity = "Disaster (default for Unknown or empty data Macros)"

    ok, details = matrix_bot.send_via_rest(room_id, subject, message, severity)
    if ok:
        return jsonify({"status": "success", "matrix": details})
    else:
        return jsonify({"status": "error", "details": details}), 502


@app.route("/enable_zabbix", methods=["GET"])
def api_enable():
    matrix_bot.notifications_enabled = True
    return jsonify({"status": "success", "notifications": "enabled"})


@app.route("/disable_zabbix", methods=["GET"])
def api_disable():
    matrix_bot.notifications_enabled = False
    return jsonify({"status": "success", "notifications": "disabled"})


@app.route("/zabbix_status", methods=["GET"])
def api_status():
    async_client = getattr(matrix_bot.bot.api, "async_client", None)
    token_present = bool(getattr(async_client, "access_token", None)) if async_client else False
    return jsonify({
        "status": "success",
        "notifications_enabled": matrix_bot.notifications_enabled,
        "history_count": len(matrix_bot.notification_history),
        "bot_logged_in": token_present
    })


def run_flask():
    app.run(host="172.24.5.35", port=PORT, debug=DEBUG)


def run_bot():
    # This blocks until the bot stops; run it in a separate thread.
    matrix_bot.bot.run()


if __name__ == "__main__":
    # Start the bot in a background thread (so it can login and listen)
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # Give the bot a moment to start and log in (optional)
    # You can remove or increase the sleep if needed in your env.
    time.sleep(1)

    # Start the Flask webhook server (main thread)
    run_flask()