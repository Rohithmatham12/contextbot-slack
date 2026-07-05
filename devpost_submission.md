# ContextBot — Codebase Intelligence for Slack

## Tagline
Ask anything about any GitHub repo. 16 secrets stripped before the LLM sees them. Answers in under 3 seconds.

---

## What it does

ContextBot connects any public GitHub repo to Slack and lets your team ask questions about it in plain English. You get accurate, citation-backed answers drawn from real code — not hallucinations — and Slack tribal knowledge from your team's own message history.

**Run `/ctx connect https://github.com/owner/repo` and within 30 seconds you can ask:**
- "What does the secret redaction pipeline do and why does it matter?"
- "Which files should I read first to understand the auth flow?"
- "What are the hottest files in the last 30 days?"

Secrets (API keys, DB connection strings, JWT tokens, AWS credentials) are detected and stripped **at ingestion time** — before anything is stored, before any LLM call. They are structurally incapable of reaching the model. Connecting the ContextOS repo found **132 files, 16 secrets redacted** in under 30 seconds. Answers arrive in **under 3 seconds**.

---

## Challenge technologies used

### 1. Model Context Protocol (MCP)
ContextOS exposes an MCP server (`contextos serve --stdio <repo_path>`). ContextBot spawns this server per call, invokes `pack_context` to select the most relevant files for the question (ranked by keyword match and import centrality), and injects that context — already secret-redacted — into the LLM prompt. 35 files analyzed per typical answer, 0 secrets leaked.

### 2. Real-Time Search API
Every answer is enriched with relevant Slack messages via `client.search_messages()`. If your team already discussed this part of the codebase in a channel, that context surfaces in the answer. Code knowledge + team knowledge in one response.

### 3. Slack AI (thread summarization)
When ContextBot is @mentioned inside an existing thread, it summarizes the thread with Groq before reasoning — giving it full context of the conversation before answering. This is the "Slack AI" capability: using Slack's conversational layer as structured context for the agent.

---

## How we built it

- **Slack Bolt** (Python, Socket Mode) — no public URL required, instant local dev
- **ContextOS MCP** — open-source codebase intelligence library, installed from source
- **Groq llama-3.3-70b-versatile** — free-tier LLM, fast inference (~1.5s)
- **SQLite** — per-workspace repo registry, active repo selection, audit log
- **Docker + Render Background Worker** — $7/month, always-on, auto-deploys from GitHub

Multi-repo: each Slack workspace maintains its own repo registry. `/ctx use <name>` switches between connected repos. No state is shared across workspaces.

---

## Tour Mode — onboarding for new contributors

`/ctx tour` generates a plain-English onboarding walkthrough of any connected repo:
- What the repo does (no jargon)
- Major components and what they're for
- The 2-3 most important files to read first
- Non-obvious architecture facts and gotchas

Target user: bootcamp grads, junior developers, open-source contributors encountering an unfamiliar codebase without a senior engineer available to walk them through it. Onboarding a new engineer typically takes 1-3 days of senior-engineer time. Tour Mode does it in 15 seconds, from secret-redacted code context.

---

## Robustness

Every failure path produces a specific, human-readable Slack message — no raw stack traces, no silent hangs:
- Invalid URL → "Not a valid URL. Try: `https://github.com/owner/repo`"
- Non-GitHub URL → "Only GitHub repos are supported"
- Nonexistent / private repo → "Repo not found or private. Make sure it's public."
- Clone timeout → "Clone timed out (>120s). Repo may be too large."
- Concurrent connect → "Already indexing a repo. Wait for it to finish."
- Binary files and large files: ContextOS skips them at scan time via extension allowlist and file-size threshold. No crash.

---

## Numbers from real testing

| Metric | Value |
|---|---|
| Files indexed (ContextOS repo) | 132 |
| Secrets redacted at ingestion | 16 |
| Files analyzed per answer | 35 |
| Answer latency (p50) | ~3.0s |
| Clone + index time | ~28s |
| Deployment cost | $7/month |

---

## Side-prize statements

**Best UX:** ContextBot's App Home surfaces live repo stats and redaction counts with zero configuration — the first thing you see is proof the product works, not a settings screen.

**Most Innovative Slack Agent:** ContextBot is the first Slack code agent to treat secret redaction as an ingestion-time architectural guarantee rather than an access-control policy — secrets are structurally incapable of reaching the LLM or vector store, not just permissioned against it.

**Best Technological Implementation:** ContextBot fires all three challenge technologies — MCP, Slack AI, and Real-Time Search — in a single `/ctx ask` request, fusing code context and Slack tribal knowledge into one synthesized answer in 3.0 seconds.

---

## Submission note: dual-track consideration (Part 4)

Tour Mode was built for the "Slack Agent for Good" track framing. Before submitting to both tracks, check the Devpost Rules tab to confirm whether one project can be entered in multiple tracks, or whether a separate project entry is required. Do not submit twice without confirming this is permitted.

**"Slack Agent for Good" framing:**
Onboarding a new engineer, open-source contributor, or bootcamp graduate onto an unfamiliar codebase is one of the biggest silent costs in software — often taking days of a senior engineer's time to walk someone through "here's how this repo works." Tour Mode uses the same secure, redaction-first indexing pipeline to generate an instant, safe onboarding walkthrough — improving economic opportunity and accessibility for people entering the field without a mentor available to do that walkthrough manually.

---

## GitHub
https://github.com/Rohithmatham12/contextbot-slack

## Demo
[Add video link after recording]
