"""Slack Block Kit formatters — numbers-driven copy throughout."""

FOOTER = "⚡ ContextOS MCP · github.com/Rohithmatham12/ContextOS"


def _hdr(text: str) -> dict:
    return {"type": "header", "text": {"type": "plain_text", "text": text, "emoji": True}}

def _md(text: str) -> dict:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text[:2900]}}

def _div() -> dict:
    return {"type": "divider"}

def _ctx(text: str) -> dict:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": text}]}


def ask_result(question: str, answer: str, file_count: int, elapsed: float = 0) -> list[dict]:
    timing = f" · answered in {elapsed}s" if elapsed else ""
    return [
        _hdr("🤖 ContextBot"),
        _md(f"*Question:* _{question}_"),
        _div(),
        _md(answer),
        _div(),
        _ctx(f"📂 {file_count} files analyzed · 🔒 secrets redacted before LLM{timing} · {FOOTER}"),
    ]


def files_result(task: str, result: str) -> list[dict]:
    return [
        _hdr("📁 Relevant Files"),
        _md(f"*Task:* _{task}_"),
        _div(),
        _md(f"```{result[:2700]}```"),
        _ctx(f"Ranked by keyword match + import centrality · 🔒 secrets redacted · {FOOTER}"),
    ]


def scan_result(name: str, result: str) -> list[dict]:
    return [
        _hdr(f"✅ Indexed: {name}"),
        _md(f"```{result[:2700]}```"),
        _ctx(FOOTER),
    ]


def churn_result(result: str) -> list[dict]:
    return [
        _hdr("🔥 Hottest Files (30 days)"),
        _md(f"```{result[:2700]}```"),
        _ctx(FOOTER),
    ]


def connect_result(name: str, url: str, scan: str, redactions: int) -> list[dict]:
    redact_line = (
        f"🔒 *{redactions} secrets redacted* before anything was stored or sent to an LLM"
        if redactions > 0
        else "🔒 No secrets found in this repo"
    )
    return [
        _hdr(f"✅ Connected: {name}"),
        _md(f"`{url}`\n\n```{scan[:1600]}```"),
        _div(),
        _md(redact_line),
        _ctx(f"Use `/ctx ask <question>` to start · `/ctx use {name}` to switch · {FOOTER}"),
    ]


def repos_list(repos: list[dict], active_url: str) -> list[dict]:
    if not repos:
        return [_md("No repos connected yet.\nUse `/ctx connect <github-url>` to add one.")]
    lines = []
    for r in repos:
        marker = "✅ " if r["github_url"] == active_url else "   "
        lines.append(
            f"{marker}*{r['name']}*\n"
            f"     {r['file_count']} files indexed · "
            f"{r['redaction_count']} secrets redacted at ingestion\n"
            f"     `{r['github_url']}`"
        )
    return [
        _hdr("📦 Connected Repos"),
        _md("\n\n".join(lines)),
        _ctx(f"✅ = active repo · `/ctx use <name>` to switch · {FOOTER}"),
    ]


def audit_result(logs: list[dict], total: int) -> list[dict]:
    header = (
        f"🔒 *{total} secrets caught before reaching an LLM* across all connected repos."
    )
    if not logs:
        return [_md(f"{header}\n\nNo per-file entries logged yet. "
                    f"Connect a repo with secrets to see them here.")]
    lines = [header, ""]
    for e in logs[:15]:
        lines.append(f"• `{e['pattern']}` in `{e['file_path']}` ({e['repo_name']})")
    return [
        _hdr("🔒 Secret Redaction Audit"),
        _md("\n".join(lines)),
        _ctx(FOOTER),
    ]


def home_view(repos: list[dict], active: dict | None, total_redactions: int,
              preseed_url: str, suggested_question: str) -> dict:
    blocks: list[dict] = [
        _hdr("ContextBot — Codebase Intelligence for Slack"),
        _md(
            "Ask anything about any GitHub repo. "
            "Code context (MCP) + Slack history (Real-Time Search) + "
            "thread understanding (Slack AI) — in one answer.\n\n"
            "*Secrets are stripped at ingestion. Nothing sensitive ever reaches an LLM.*"
        ),
        _div(),
    ]

    if active:
        blocks += [
            _md(
                f"*Active repo:* `{active['name']}`\n"
                f"• {active['file_count']} files indexed\n"
                f"• {active['redaction_count']} secrets redacted before storage\n"
                f"• Indexed: {active.get('indexed_at', 'recently')[:19]}"
            ),
        ]
    else:
        blocks += [
            _md(
                f"*No repo connected yet.*\n\n"
                f"Run `/ctx connect {preseed_url}` to index a repo and start asking questions."
            ),
        ]

    blocks += [
        _div(),
        _md(
            f"💡 *Try this first:*\n"
            f">`/ctx ask {suggested_question}`"
        ),
        _div(),
        _hdr("Commands"),
        _md(
            "• `/ctx connect <github-url>` — index any public GitHub repo (~30s)\n"
            "• `/ctx ask <question>` — AI answer from real code, not hallucinations\n"
            "• `/ctx files <task>` — ranked relevant files with dependency reasons\n"
            "• `/ctx repos` — list all connected repos\n"
            "• `/ctx use <name>` — switch active repo\n"
            "• `/ctx audit` — secret redaction log\n"
            "• `/ctx churn` — most actively changed files (30d)\n\n"
            "Or @mention me in any channel, or DM me directly."
        ),
    ]

    if repos:
        blocks += [
            _div(),
            _ctx(
                f"📦 {len(repos)} repo{'s' if len(repos) != 1 else ''} connected · "
                f"🔒 {total_redactions} secrets caught before LLM · {FOOTER}"
            ),
        ]
    else:
        blocks += [_div(), _ctx(FOOTER)]

    return {"type": "home", "blocks": blocks}


def error_block(msg: str) -> list[dict]:
    return [_md(f"❌ *Error:* {msg[:500]}")]


def help_blocks(suggested_question: str = "") -> list[dict]:
    tip = (f"\n\n💡 *Try:* `/ctx ask {suggested_question}`"
           if suggested_question else "")
    return [
        _hdr("ContextBot — Codebase Intelligence"),
        _md(
            "• `/ctx connect <github-url>` — index any public repo, secrets stripped\n"
            "• `/ctx ask <question>` — AI answer from real code context\n"
            "• `/ctx files <task>` — ranked relevant files\n"
            "• `/ctx repos` — connected repos\n"
            "• `/ctx use <name>` — switch active repo\n"
            "• `/ctx audit` — secret redaction log\n"
            "• `/ctx churn` — hottest files (30d)"
            f"{tip}"
        ),
        _ctx(FOOTER),
    ]
