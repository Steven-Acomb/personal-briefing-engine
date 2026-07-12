"""Claude synthesis: normalized items + a briefing's synthesis_instruction ->
one written brief (the source of truth; audio is derived from it later).

This is the core value-add — a single cross-source pass, not per-source
summaries stapled together. The synthesizer only ever sees IngestedItems.
"""

from __future__ import annotations

from datetime import datetime

import anthropic

from core.models import Briefing, IngestedItem

MODEL = "claude-opus-4-8"

_SYSTEM = """You are the synthesis engine of a personal briefing tool. You are \
given a batch of normalized messages pulled from one or more sources (group \
chats, feeds) over a time window, plus a briefing instruction describing what \
the owner wants. Produce ONE cohesive briefing.

Core rules:
- Synthesize ACROSS sources. Connect related items; do not just summarize each \
source in isolation.
- Follow the briefing instruction for focus, tone, length, and what to ignore.
- Ground every statement in the provided messages. Do not invent facts, names, \
numbers, or links that are not present.
- Output only the briefing text itself — no preamble, no meta-commentary, no \
"here is your briefing" framing."""


def _render_items(
    items: list[IngestedItem], source_contexts: dict[str, str] | None = None
) -> str:
    """Render items grouped BY SOURCE, each block headed by the source and — when
    one is set — that source's interpretive context, so the model reads each
    source's messages through the right lens. The gloss sits with the content it
    explains, not in a global preamble. Within a block, messages are chronological.
    """
    source_contexts = source_contexts or {}
    groups: dict[str, list[IngestedItem]] = {}
    for it in sorted(items, key=lambda i: i.timestamp):
        groups.setdefault(it.source, []).append(it)

    blocks = []
    for source, group in groups.items():
        ctx = (source_contexts.get(source) or "").strip()
        header = f"Messages from {source}"
        if ctx:  # omit cleanly when this source has no context
            header += f" (context: {ctx})"
        lines = [header + ":"]
        for it in group:
            author = it.meta.get("author", "unknown")
            ts = it.timestamp.strftime("%Y-%m-%d %H:%M UTC")
            lines.append(f"({author}, {ts})\n{it.content}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def synthesize(
    briefing: Briefing,
    items: list[IngestedItem],
    period: tuple[datetime, datetime] | None = None,
    client: anthropic.Anthropic | None = None,
    source_contexts: dict[str, str] | None = None,
) -> str:
    """Generate the written brief for `briefing` from `items`. Returns markdown/
    script text. Raises if there are no items to synthesize."""
    if not items:
        raise ValueError("No items to synthesize.")

    client = client or anthropic.Anthropic()

    window = ""
    if period:
        start, end = period
        window = (
            f"Time window: {start.strftime('%Y-%m-%d %H:%M')} to "
            f"{end.strftime('%Y-%m-%d %H:%M')} UTC.\n"
        )

    user_prompt = (
        f"BRIEFING: {briefing.name}\n"
        f"{window}\n"
        f"BRIEFING INSTRUCTION:\n{briefing.synthesis_instruction}\n\n"
        f"MESSAGES ({len(items)}):\n{_render_items(items, source_contexts)}"
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        thinking={"type": "adaptive"},
        system=_SYSTEM,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return "".join(b.text for b in response.content if b.type == "text").strip()
