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
import threading
import time

from dotenv import load_dotenv

load_dotenv()

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

import ai_client
import formatters
import mcp_client
import slack_search
import storage
import thread_context
import tour as tour_module

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("contextbot")

app = App(token=os.environ["SLACK_BOT_TOKEN"])
storage.init()

# Track in-progress indexing jobs to prevent duplicate connects
_indexing_lock: dict[str, bool] = {}
_indexing_lock_mutex = threading.Lock()

PRESEED_REPO = os.getenv("PRESEED_REPO", "https://github.com/Rohithmatham12/ContextOS")
SUGGESTED_QUESTION = "What does the secret redaction pipeline do and why does it matter?"

# ── URL validation ─────────────────────────────────────────────────────────────

_GITHUB_PATTERN = re.compile(
    r"^https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(\.git)?/?$"
)


def _validate_github_url(url: str) -> str | None:
    """Return an error string if invalid, None if ok."""
    if not url.startswith(("http://", "https://")):
        return "Not a valid URL. Try: `https://github.com/owner/repo`"
    if "github.com" not in url:
        return "Only GitHub repos are supported. URL must contain `github.com`"
    if not _GITHUB_PATTERN.match(url):
        return "Invalid GitHub URL format. Try: `https://github.com/owner/repo`"
    return None


# ── helpers ────────────────────────────────────────────────────────────────────

def _active_repo(workspace_id: str) -> dict | None:
    return storage.get_active_repo(workspace_id)


def _active_repo_path(workspace_id: str) -> str | None:
    repo = _active_repo(workspace_id)
    if not repo:
        return None
    path = repo["local_path"]
    return path if os.path.isdir(path) else None


def _require_repo(workspace_id: str, respond) -> str | None:
    path = _active_repo_path(workspace_id)
    if not path:
        respond({
            "response_type": "ephemeral",
            "text": "No repo connected. Use `/ctx connect <github-url>` first.\n"
                    f"Try: `/ctx connect {PRESEED_REPO}`",
        })
        return None
    return path


def _clone_and_index(github_url: str, workspace_id: str) -> dict:
    """Clone repo, run ContextOS MCP scan, return stats. Raises on failure."""
    name = github_url.rstrip("/").split("/")[-1].replace(".git", "")
    local_path = f"/tmp/repos/{workspace_id}/{name}"

    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    if os.path.exists(local_path):
        shutil.rmtree(local_path)

    result = subprocess.run(
        ["git", "clone", github_url, local_path, "--depth=1"],
        capture_output=True, timeout=120,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").lower()
        # Docker has no credential helper — "could not read Username" means
        # repo doesn't exist or is private (git can't prompt for creds)
        if any(phrase in stderr for phrase in [
            "not found", "repository", "authentication",
            "could not read username", "access denied", "does not exist",
        ]):
            raise PermissionError(
                f"Repo not found or private. Make sure `{github_url}` is a public repo."
            )
        raise RuntimeError(
            f"git clone failed: {result.stderr.decode(errors='replace')[:200]}"
        )

    scan_result = mcp_client.scan_repo(repo_path=local_path)

    file_count = 0
    for line in scan_result.splitlines():
        if "Scanned" in line and "files" in line:
            for i, p in enumerate(line.split()):
                if p == "files" and i > 0:
                    try:
                        file_count = int(line.split()[i - 1])
                    except ValueError:
                        pass

    # Count secrets redacted by sampling pack output + log per-file to audit table
    redaction_count = 0
    try:
        sample = mcp_client.pack_context(
            "security secrets api keys passwords tokens", budget=16000, repo_path=local_path
        )
        redaction_count = sample.count("[REDACTED_")
        _log_redactions_from_pack(sample, workspace_id, name)
    except Exception:
        pass

    storage.upsert_repo(
        workspace_id, github_url, local_path, name,
        file_count=file_count, redaction_count=redaction_count,
    )
    return {
        "name": name, "local_path": local_path,
        "file_count": file_count, "redaction_count": redaction_count,
        "scan_result": scan_result,
    }


def _log_redactions_from_pack(pack_output: str, workspace_id: str, repo_name: str):
    """Parse pack output for [REDACTED_TYPE] tokens; log unique (file, pattern) pairs."""
    current_file = "unknown"
    logged: set[tuple[str, str]] = set()
    for line in pack_output.splitlines():
        if line.startswith("### "):
            current_file = line[4:].split()[0]
        else:
            for match in re.finditer(r'\[REDACTED_([A-Z_0-9]+)\]', line):
                key = (current_file, match.group(1))
                if key not in logged:
                    logged.add(key)
                    try:
                        storage.log_redaction(workspace_id, repo_name,
                                              match.group(1), current_file)
                    except Exception:
                        pass


def _preseed_if_empty(workspace_id: str):
    """Auto-index the preseed repo if workspace has no repos (background)."""
    if storage.get_repos(workspace_id):
        return
    with _indexing_lock_mutex:
        if _indexing_lock.get(workspace_id):
            return
        _indexing_lock[workspace_id] = True
    try:
        _clone_and_index(PRESEED_REPO, workspace_id)
        log.info("Preseeded %s for workspace %s", PRESEED_REPO, workspace_id)
    except Exception as exc:
        log.warning("Preseed failed: %s", exc)
    finally:
        with _indexing_lock_mutex:
            _indexing_lock[workspace_id] = False


# ── /ctx command ───────────────────────────────────────────────────────────────

@app.command("/ctx")
def handle_ctx(ack, command, respond, client):
    ack()
    workspace_id = command["team_id"]
    raw = (command.get("text") or "").strip()
    parts = raw.split(None, 1)
    sub = parts[0].lower() if parts else "help"
    arg = parts[1].strip() if len(parts) > 1 else ""

    # ── connect ────────────────────────────────────────────────────────────────
    if sub == "connect":
        if not arg:
            respond({"response_type": "ephemeral",
                     "text": f"Usage: `/ctx connect <github-url>`\n"
                             f"Example: `/ctx connect {PRESEED_REPO}`"})
            return

        err = _validate_github_url(arg)
        if err:
            respond({"response_type": "ephemeral", "text": f"❌ {err}"})
            return

        with _indexing_lock_mutex:
            if _indexing_lock.get(workspace_id):
                respond({"response_type": "ephemeral",
                         "text": "⏳ Already indexing a repo. Wait for it to finish."})
                return
            _indexing_lock[workspace_id] = True

        respond({"response_type": "in_channel",
                 "text": f"⏳ Cloning and indexing `{arg}`... (~30s)"})
        try:
            stats = _clone_and_index(arg, workspace_id)
            respond({
                "response_type": "in_channel",
                "blocks": formatters.connect_result(
                    stats["name"], arg, stats["scan_result"],
                    stats["redaction_count"]
                ),
            })
        except PermissionError as exc:
            respond({"response_type": "ephemeral", "text": f"❌ {exc}"})
        except subprocess.TimeoutExpired:
            respond({"response_type": "ephemeral",
                     "text": "❌ Clone timed out (>120s). Repo may be too large. Try a smaller one."})
        except Exception as exc:
            log.exception("connect failed")
            respond({"response_type": "ephemeral",
                     "text": f"❌ Failed to connect repo: {str(exc)[:200]}"})
        finally:
            with _indexing_lock_mutex:
                _indexing_lock[workspace_id] = False

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
                 "text": f"✅ Active repo → *{match['name']}* "
                         f"({match['file_count']} files · "
                         f"{match['redaction_count']} secrets redacted)"})

    # ── repos ──────────────────────────────────────────────────────────────────
    elif sub == "repos":
        repos = storage.get_repos(workspace_id)
        active = _active_repo(workspace_id)
        active_url = active["github_url"] if active else ""
        respond({"response_type": "in_channel",
                 "blocks": formatters.repos_list(repos, active_url)})

    # ── audit ──────────────────────────────────────────────────────────────────
    elif sub == "audit":
        logs = storage.get_audit_log(workspace_id)
        total = storage.total_redactions(workspace_id)
        respond({"response_type": "in_channel",
                 "blocks": formatters.audit_result(logs, total)})

    # ── ask ────────────────────────────────────────────────────────────────────
    elif sub == "ask":
        if not arg:
            respond({"response_type": "ephemeral",
                     "text": f"Usage: `/ctx ask <question>`\n"
                             f"Example: `/ctx ask {SUGGESTED_QUESTION}`"})
            return
        path = _require_repo(workspace_id, respond)
        if not path:
            return
        repo = _active_repo(workspace_id)
        respond({"response_type": "in_channel",
                 "text": f"_Searching *{repo['name']}* for:_ *{arg}*..."})
        try:
            t0 = time.time()
            context = mcp_client.pack_context(arg, repo_path=path)
            file_count = context.count("\n### ")
            answer = ai_client.answer(arg, context)
            elapsed = round(time.time() - t0, 1)
            enriched = slack_search.enrich_answer(client, arg, answer)
            respond({
                "response_type": "in_channel",
                "blocks": formatters.ask_result(arg, enriched, file_count, elapsed),
            })
        except Exception as exc:
            log.exception("ask failed")
            respond({"response_type": "ephemeral",
                     "text": f"❌ Could not answer: {str(exc)[:200]}"})

    # ── files ──────────────────────────────────────────────────────────────────
    elif sub == "files":
        if not arg:
            respond({"response_type": "ephemeral", "text": "Usage: `/ctx files <task>`"})
            return
        path = _require_repo(workspace_id, respond)
        if not path:
            return
        respond({"response_type": "in_channel",
                 "text": f"_Finding files for:_ *{arg}*..."})
        try:
            result = mcp_client.list_files(arg, repo_path=path)
            respond({"response_type": "in_channel",
                     "blocks": formatters.files_result(arg, result)})
        except Exception as exc:
            log.exception("files failed")
            respond({"response_type": "ephemeral",
                     "text": f"❌ Could not list files: {str(exc)[:200]}"})

    # ── scan ───────────────────────────────────────────────────────────────────
    elif sub == "scan":
        path = _require_repo(workspace_id, respond)
        if not path:
            return
        repo = _active_repo(workspace_id)
        respond({"response_type": "in_channel", "text": "_Re-indexing repository..._"})
        try:
            result = mcp_client.scan_repo(repo_path=path)
            respond({"response_type": "in_channel",
                     "blocks": formatters.scan_result(repo["name"], result)})
        except Exception as exc:
            log.exception("scan failed")
            respond({"response_type": "ephemeral",
                     "text": f"❌ Scan failed: {str(exc)[:200]}"})

    # ── churn ──────────────────────────────────────────────────────────────────
    elif sub == "churn":
        path = _require_repo(workspace_id, respond)
        if not path:
            return
        respond({"response_type": "in_channel", "text": "_Checking git history..._"})
        try:
            result = mcp_client.churn_report(repo_path=path)
            respond({"response_type": "in_channel",
                     "blocks": formatters.churn_result(result)})
        except Exception as exc:
            log.exception("churn failed")
            respond({"response_type": "ephemeral",
                     "text": f"❌ Churn report failed: {str(exc)[:200]}"})

    # ── tour ───────────────────────────────────────────────────────────────────
    elif sub == "tour":
        path = _require_repo(workspace_id, respond)
        if not path:
            return
        repo = _active_repo(workspace_id)
        respond({"response_type": "in_channel",
                 "text": f"_Generating onboarding tour of *{repo['name']}*... (~15s)_"})
        try:
            context = mcp_client.pack_context(
                "architecture overview entry point main components readme",
                budget=20000, repo_path=path
            )
            file_list = mcp_client.list_files(
                "main entry points architecture overview", top_n=20, repo_path=path
            )
            walkthrough = tour_module.generate_tour(repo["name"], context, file_list)
            respond({"response_type": "in_channel",
                     "blocks": formatters.tour_result(repo["name"], walkthrough)})
        except Exception as exc:
            log.exception("tour failed")
            respond({"response_type": "ephemeral",
                     "text": f"❌ Tour failed: {str(exc)[:200]}"})

    else:
        respond({"blocks": formatters.help_blocks(SUGGESTED_QUESTION)})


# ── App Home ───────────────────────────────────────────────────────────────────

@app.event("app_home_opened")
def handle_home(event, client):
    try:
        auth = client.auth_test()
        workspace_id = auth["team_id"]
    except Exception:
        workspace_id = ""

    # Auto-preseed in background so first-time judges see a demo repo
    threading.Thread(
        target=_preseed_if_empty, args=(workspace_id,), daemon=True
    ).start()

    repos = storage.get_repos(workspace_id)
    active = storage.get_active_repo(workspace_id)
    total = storage.total_redactions(workspace_id)

    try:
        client.views_publish(
            user_id=event["user"],
            view=formatters.home_view(repos, active, total,
                                      PRESEED_REPO, SUGGESTED_QUESTION),
        )
    except Exception as exc:
        log.exception("home view failed: %s", exc)


# ── @mention (Slack AI: thread summarization) ──────────────────────────────────

@app.event("app_mention")
def handle_mention(event, say, client):
    question = re.sub(r"<@[A-Z0-9]+>", "", event["text"]).strip()
    if not question:
        say(blocks=formatters.help_blocks(SUGGESTED_QUESTION))
        return

    workspace_id = event.get("team", "")
    channel = event.get("channel", "")
    thread_ts = event.get("thread_ts") or event.get("ts", "")

    path = _active_repo_path(workspace_id)
    if not path:
        say(text=f"No repo connected. Use `/ctx connect {PRESEED_REPO}` first.",
            thread_ts=thread_ts)
        return

    repo = _active_repo(workspace_id)
    say(text=f"_Searching *{repo['name']}*..._", thread_ts=thread_ts)
    try:
        # Slack AI capability: summarize existing thread context before reasoning
        thread_summary = ""
        if event.get("thread_ts"):
            thread_summary = thread_context.get_thread_summary(
                client, channel, event["thread_ts"]
            )

        t0 = time.time()
        context = mcp_client.pack_context(question, repo_path=path)
        file_count = context.count("\n### ")
        answer = ai_client.answer(question, context, thread_summary)
        elapsed = round(time.time() - t0, 1)

        # Real-Time Search API: pull relevant Slack discussions
        enriched = slack_search.enrich_answer(client, question, answer)

        say(blocks=formatters.ask_result(question, enriched, file_count, elapsed),
            thread_ts=thread_ts)
    except Exception as exc:
        log.exception("mention failed")
        say(text=f"❌ {str(exc)[:200]}", thread_ts=thread_ts)


# ── DM handler ─────────────────────────────────────────────────────────────────

@app.event("message")
def handle_dm(event, say, client):
    if event.get("channel_type") != "im":
        return
    if event.get("subtype"):
        return

    question = (event.get("text") or "").strip()
    if not question:
        say(blocks=formatters.help_blocks(SUGGESTED_QUESTION))
        return

    workspace_id = event.get("team", "")
    path = _active_repo_path(workspace_id)
    if not path:
        say(f"No repo connected. Use `/ctx connect {PRESEED_REPO}` first.")
        return

    repo = _active_repo(workspace_id)
    say(f"_Searching *{repo['name']}*..._")
    try:
        t0 = time.time()
        context = mcp_client.pack_context(question, repo_path=path)
        file_count = context.count("\n### ")
        answer = ai_client.answer(question, context)
        elapsed = round(time.time() - t0, 1)
        enriched = slack_search.enrich_answer(client, question, answer)
        say(blocks=formatters.ask_result(question, enriched, file_count, elapsed))
    except Exception as exc:
        log.exception("dm failed")
        say(f"❌ {str(exc)[:200]}")


# ── entrypoint ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info("ContextBot starting | preseed=%s", PRESEED_REPO)
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
