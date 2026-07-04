"""Real-Time Search API — pull relevant Slack messages to enrich answers."""
import logging

log = logging.getLogger("contextbot.search")


def search_relevant_messages(client, query: str, limit: int = 5) -> str:
    """Search Slack for messages related to the query. Returns formatted context."""
    try:
        resp = client.search_messages(query=query, count=limit, highlight=False)
        matches = resp.get("messages", {}).get("matches", [])
        if not matches:
            return ""

        lines = ["*Relevant Slack discussions:*"]
        for m in matches[:limit]:
            user = m.get("username", "teammate")
            text = m.get("text", "")[:200].replace("\n", " ")
            channel = m.get("channel", {}).get("name", "")
            ts = m.get("ts", "")
            lines.append(f"• @{user} in #{channel}: {text}")

        return "\n".join(lines)

    except Exception as exc:
        # search:read scope may not be available — degrade gracefully
        log.debug("Real-Time Search unavailable: %s", exc)
        return ""


def enrich_answer(client, question: str, ai_answer: str) -> str:
    """Append relevant Slack context below the AI answer if found."""
    slack_context = search_relevant_messages(client, question)
    if not slack_context:
        return ai_answer
    return f"{ai_answer}\n\n{slack_context}"
