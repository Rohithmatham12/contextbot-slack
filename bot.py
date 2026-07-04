"""ContextBot for Slack — codebase intelligence powered by ContextOS MCP.

Technologies used:
  1. MCP server integration — ContextOS MCP serves repo intelligence
  2. Real-Time Search API  — Slack search enriches answers with team context
  3. Slack AI capabilities — thread summarization before reasoning
"""
import logging
import os
import re
import shutil
import subprocess

from dotenv import load_dotenv

load_dotenv()  # must run before project imports (they read env at import time)

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

import ai_client
import formatters
import mcp_client
import slack_search
import storage
import thread_context

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("contextbot")

app = App(token=os.environ["SLACK_BOT_TOKEN"])
storage.init()


# ── helpers ────────────────────────────────────────────────────────────────────

def _active_repo_path(workspace_id: str) -> str | None:
    repo = storage.get_active_repo(workspace_id)
    return repo["local_path"] if repo else None


def _active_repo(workspace_id: str) -> dict | None:
    return storage.get_active_repo(workspace_id)


def _require_repo(workspace_id: str, respond) -> str | None:
    """Return local_path or send error and return None."""
    path = _active_repo_path(workspace_id)
    if not path or not os.path.isdir(path):
        respond({
            "response_type": "ephemeral",
            "text": "No repo connected. Use `/ctx connect <github-url>` first.",
        })
        return None
    return path


def _clone_and_index(github_url: str, workspace_id: str) -> dict:
    """Clone repo, scan with ContextOS MCP, return stats dict."""
    name = github_url.rstrip("/").split("/")[-1].replace(".git", "")
    local_path = f"/tmp/repos/{workspace_id}/{name}"

    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    if os.path.exists(local_path):
        shutil.rmtree(local_path)

    subprocess.run(
        ["git", "clone", github_url, local_path, "--depth=1"],
        check=True, capture_output=True, timeout=120,
    )

    scan_result = mcp_client.scan_repo(repo_path=local_path)

    # Parse file count from scan output
    file_count = 0
    for line in scan_result.splitlines():
        if "Scanned" in line and "files" in line:
            parts = line.split()
            for i, p in enumerate(parts):
                if p == "files" and i > 0:
                    try:
                        file_count = int(parts[i - 1])
                    except ValueError:
                        pass

    # Count secrets redacted — ContextOS logs [REDACTED_*] tokens
    # Run a quick pack to surface redaction count
    redaction_count = 0
    try:
        sample = mcp_client.pack_context("security secrets api keys", budget=16000,
                                         repo_path=local_path)
        redaction_count = sample.count("[REDACTED_")
    except Exception:
        pass

    storage.upsert_repo(workspace_id, github_url, local_path, name,
                        file_count=file_count, redaction_count=redaction_count)

    return {
        "name": name, "local_path": local_path,
        "file_count": file_count, "redaction_count": redaction_count,
        "scan_result": scan_result,
    }


# ── /ctx command ───────────────────────────────────────────────────────────────

@app.command("/ctx")
def handle_ctx(ack, command, respond, client):
    ack()
    workspace_id = command["team_id"]
    channel_id = command.get("channel_id", "")
    raw = (command.get("text") or "").strip()
    parts = raw.split(None, 1)
    sub = parts[0].lower() if parts else "help"
    arg = parts[1].strip() if len(parts) > 1 else ""

    # ── connect ────────────────────────────────────────────────────────────────
    if sub == "connect":
        if not arg:
            respond({"response_type": "ephemeral",
                     "text": "Usage: `/ctx connect <github-url>`"})
            return
        respond({"response_type": "in_channel",
                 "text": f"⏳ Cloning and indexing `{arg}`... (may take ~30s)"})
        try:
            stats = _clone_and_index(arg, workspace_id)
            respond({
                "response_type": "in_channel",
                "blocks": formatters.connect_result(
                    stats["name"], arg, stats["scan_result"],
                    stats["redaction_count"]
                ),
            })
        except subprocess.CalledProcessError:
            respond({"response_type": "ephemeral",
                     "text": f"❌ Could not clone `{arg}`. Check the URL and try again."})
        except Exception as exc:
            log.exception("connect failed")
            respond({"response_type": "ephemeral",
                     "blocks": formatters.error_block(str(exc))})

    # ── use ────────────────────────────────────────────────────────────────────
    elif sub == "use":
        if not arg:
            respond({"response_type": "ephemeral", "text": "Usage: `/ctx use <repo-name>`"})
            return
        repos = storage.get_repos(workspace_id)
        match = next((r for r in repos if r["name"].lower() == arg.lower()), None)
        if not match:
            names = ", ".join(r["name"] for r in repos) or "none"
            respond({"response_type": "ephemeral",
                     "text": f"Repo `{arg}` not found. Connected: {names}"})
            return
        storage.set_active(workspace_id, match["github_url"])
        respond({"response_type": "in_channel",
                 "text": f"✅ Active repo set to *{match['name']}*"})

    # ── repos ──────────────────────────────────────────────────────────────────
    elif sub == "repos":
        repos = storage.get_repos(workspace_id)
        active = _active_repo(workspace_id)
        active_url = active["github_url"] if active else ""
        respond({
            "response_type": "in_channel",
            "blocks": formatters.repos_list(repos, active_url),
        })

    # ── audit ──────────────────────────────────────────────────────────────────
    elif sub == "audit":
        logs = storage.get_audit_log(workspace_id)
        total = storage.total_redactions(workspace_id)
        respond({
            "response_type": "in_channel",
            "blocks": formatters.audit_result(logs, total),
        })

    # ── ask ────────────────────────────────────────────────────────────────────
    elif sub == "ask":
        if not arg:
            respond({"response_type": "ephemeral",
                     "text": "Usage: `/ctx ask <question>`"})
            return
        path = _require_repo(workspace_id, respond)
        if not path:
            return
        repo = _active_repo(workspace_id)
        respond({"response_type": "in_channel",
                 "text": f"_Searching *{repo['name']}* for:_ *{arg}*..."})
        try:
            context = mcp_client.pack_context(arg, repo_path=path)
            file_count = context.count("\n### ")

            # Slack AI capability: enrich with thread context if in a thread
            thread_summary = ""

            # Real-Time Search API: pull relevant Slack messages
            enriched = slack_search.enrich_answer(client, arg,
                                                  ai_client.answer(arg, context,
                                                                   thread_summary))
            respond({
                "response_type": "in_channel",
                "blocks": formatters.ask_result(arg, enriched, file_count),
            })
        except Exception as exc:
            log.exception("ask failed")
            respond({"response_type": "ephemeral",
                     "blocks": formatters.error_block(str(exc))})

    # ── files ──────────────────────────────────────────────────────────────────
    elif sub == "files":
        if not arg:
            respond({"response_type": "ephemeral",
                     "text": "Usage: `/ctx files <task>`"})
            return
        path = _require_repo(workspace_id, respond)
        if not path:
            return
        respond({"response_type": "in_channel",
                 "text": f"_Finding files for:_ *{arg}*..."})
        try:
            result = mcp_client.list_files(arg, repo_path=path)
            respond({
                "response_type": "in_channel",
                "blocks": formatters.files_result(arg, result),
            })
        except Exception as exc:
            log.exception("files failed")
            respond({"response_type": "ephemeral",
                     "blocks": formatters.error_block(str(exc))})

    # ── scan ───────────────────────────────────────────────────────────────────
    elif sub == "scan":
        path = _require_repo(workspace_id, respond)
        if not path:
            return
        repo = _active_repo(workspace_id)
        respond({"response_type": "in_channel", "text": "_Indexing repository..._"})
        try:
            result = mcp_client.scan_repo(repo_path=path)
            respond({
                "response_type": "in_channel",
                "blocks": formatters.scan_result(repo["name"], result),
            })
        except Exception as exc:
            log.exception("scan failed")
            respond({"response_type": "ephemeral",
                     "blocks": formatters.error_block(str(exc))})

    # ── churn ──────────────────────────────────────────────────────────────────
    elif sub == "churn":
        path = _require_repo(workspace_id, respond)
        if not path:
            return
        respond({"response_type": "in_channel", "text": "_Checking git history..._"})
        try:
            result = mcp_client.churn_report(repo_path=path)
            respond({
                "response_type": "in_channel",
                "blocks": formatters.churn_result(result),
            })
        except Exception as exc:
            log.exception("churn failed")
            respond({"response_type": "ephemeral",
                     "blocks": formatters.error_block(str(exc))})

    else:
        respond({"blocks": formatters.help_blocks()})


# ── App Home ───────────────────────────────────────────────────────────────────

@app.event("app_home_opened")
def handle_home(event, client):
    workspace_id = event.get("view", {}).get("team_id") or ""
    # Fallback: extract from user lookup
    try:
        user_info = client.users_info(user=event["user"])
        workspace_id = workspace_id or ""
    except Exception:
        pass

    # Get workspace from bot token context — use team from auth
    try:
        auth = client.auth_test()
        workspace_id = auth["team_id"]
    except Exception:
        pass

    repos = storage.get_repos(workspace_id)
    active = storage.get_active_repo(workspace_id)
    total = storage.total_redactions(workspace_id)

    client.views_publish(
        user_id=event["user"],
        view=formatters.home_view(repos, active, total),
    )


# ── @mention handler (Slack AI capability: thread summarization) ───────────────

@app.event("app_mention")
def handle_mention(event, say, client):
    question = re.sub(r"<@[A-Z0-9]+>", "", event["text"]).strip()
    if not question:
        say(blocks=formatters.help_blocks())
        return

    workspace_id = event.get("team", "")
    channel = event.get("channel", "")
    thread_ts = event.get("thread_ts") or event.get("ts", "")

    path = _active_repo_path(workspace_id)
    if not path:
        say(
            text="No repo connected. Use `/ctx connect <github-url>` first.",
            thread_ts=thread_ts,
        )
        return

    repo = _active_repo(workspace_id)
    say(text=f"_Searching *{repo['name']}* for:_ *{question}*...",
        thread_ts=thread_ts)

    try:
        # Slack AI capability: summarize thread context before reasoning
        thread_summary = ""
        if event.get("thread_ts"):
            thread_summary = thread_context.get_thread_summary(
                client, channel, event["thread_ts"]
            )

        context = mcp_client.pack_context(question, repo_path=path)
        file_count = context.count("\n### ")
        answer = ai_client.answer(question, context, thread_summary)

        # Real-Time Search API: enrich with Slack team knowledge
        enriched = slack_search.enrich_answer(client, question, answer)

        say(
            blocks=formatters.ask_result(question, enriched, file_count),
            thread_ts=thread_ts,
        )
    except Exception as exc:
        log.exception("mention failed")
        say(blocks=formatters.error_block(str(exc)), thread_ts=thread_ts)


# ── DM handler ─────────────────────────────────────────────────────────────────

@app.event("message")
def handle_dm(event, say, client):
    if event.get("channel_type") != "im":
        return
    if event.get("subtype"):
        return

    question = (event.get("text") or "").strip()
    if not question:
        say(blocks=formatters.help_blocks())
        return

    workspace_id = event.get("team", "")
    path = _active_repo_path(workspace_id)
    if not path:
        say("No repo connected. Use `/ctx connect <github-url>` first.")
        return

    repo = _active_repo(workspace_id)
    say(f"_Searching *{repo['name']}*..._")
    try:
        context = mcp_client.pack_context(question, repo_path=path)
        file_count = context.count("\n### ")
        answer = ai_client.answer(question, context)
        enriched = slack_search.enrich_answer(client, question, answer)
        say(blocks=formatters.ask_result(question, enriched, file_count))
    except Exception as exc:
        log.exception("dm failed")
        say(blocks=formatters.error_block(str(exc)))


# ── entrypoint ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info("ContextBot starting | default_repo=%s", mcp_client.DEFAULT_REPO)
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
