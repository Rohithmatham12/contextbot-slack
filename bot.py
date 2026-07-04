"""ContextBot for Slack — codebase intelligence powered by ContextOS MCP."""
import logging
import os
import re

from dotenv import load_dotenv

load_dotenv()  # must run before mcp_client is imported (it reads REPO_PATH at import time)

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

import ai_client
import formatters
import mcp_client

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("contextbot")

app = App(token=os.environ["SLACK_BOT_TOKEN"])


# ── /ctx command dispatcher ────────────────────────────────────────────────────

@app.command("/ctx")
def handle_ctx(ack, command, respond):
    ack()

    raw = (command.get("text") or "").strip()
    parts = raw.split(None, 1)
    sub = parts[0].lower() if parts else "help"
    arg = parts[1].strip() if len(parts) > 1 else ""

    if sub == "ask":
        if not arg:
            respond(":warning: Usage: `/ctx ask <question about the codebase>`")
            return
        respond({"response_type": "in_channel", "text": f"_Searching codebase for:_ *{arg}*..."})
        try:
            context = mcp_client.pack_context(arg)
            answer = ai_client.answer(arg, context)
            respond({
                "response_type": "in_channel",
                "blocks": formatters.ask_result(arg, answer, context),
            })
        except Exception as exc:
            log.exception("ask failed")
            respond({"response_type": "in_channel", "blocks": formatters.error_block(str(exc))})

    elif sub == "files":
        if not arg:
            respond(":warning: Usage: `/ctx files <task description>`")
            return
        respond({"response_type": "in_channel", "text": f"_Finding files for:_ *{arg}*..."})
        try:
            result = mcp_client.list_files(arg)
            respond({
                "response_type": "in_channel",
                "blocks": formatters.files_result(arg, result),
            })
        except Exception as exc:
            log.exception("files failed")
            respond({"response_type": "in_channel", "blocks": formatters.error_block(str(exc))})

    elif sub == "scan":
        respond({"response_type": "in_channel", "text": "_Indexing repository..._"})
        try:
            result = mcp_client.scan_repo()
            respond({
                "response_type": "in_channel",
                "blocks": formatters.scan_result(result),
            })
        except Exception as exc:
            log.exception("scan failed")
            respond({"response_type": "in_channel", "blocks": formatters.error_block(str(exc))})

    elif sub == "churn":
        respond({"response_type": "in_channel", "text": "_Checking git history..._"})
        try:
            result = mcp_client.churn_report()
            respond({
                "response_type": "in_channel",
                "blocks": formatters.churn_result(result),
            })
        except Exception as exc:
            log.exception("churn failed")
            respond({"response_type": "in_channel", "blocks": formatters.error_block(str(exc))})

    else:
        respond({"blocks": formatters.help_blocks()})


# ── @mention handler ───────────────────────────────────────────────────────────

@app.event("app_mention")
def handle_mention(event, say):
    question = re.sub(r"<@[A-Z0-9]+>", "", event["text"]).strip()
    if not question:
        say(blocks=formatters.help_blocks())
        return

    say(f"_Searching codebase for:_ *{question}*...")
    try:
        context = mcp_client.pack_context(question)
        answer = ai_client.answer(question, context)
        say(blocks=formatters.ask_result(question, answer, context))
    except Exception as exc:
        log.exception("mention failed")
        say(blocks=formatters.error_block(str(exc)))


# ── DM handler ─────────────────────────────────────────────────────────────────

@app.event("message")
def handle_dm(event, say):
    # Only respond in direct messages (channel_type im), not in channels
    if event.get("channel_type") != "im":
        return
    if event.get("subtype"):
        return  # ignore bot messages, edits, etc.

    question = (event.get("text") or "").strip()
    if not question:
        say(blocks=formatters.help_blocks())
        return

    say(f"_Searching codebase for:_ *{question}*...")
    try:
        context = mcp_client.pack_context(question)
        answer = ai_client.answer(question, context)
        say(blocks=formatters.ask_result(question, answer, context))
    except Exception as exc:
        log.exception("dm failed")
        say(blocks=formatters.error_block(str(exc)))


# ── entrypoint ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    repo = os.getenv("REPO_PATH", ".")
    log.info("ContextBot starting | repo=%s", repo)
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
