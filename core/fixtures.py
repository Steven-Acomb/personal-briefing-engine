"""Hand-crafted fake IngestedItems for validating the consumption experience
before any real ingestion exists (build-sequence step 2).

Two sources matching the daily-morning briefing: discord/chip-design and
telegram/ee-group. Content is deliberately realistic — a mix of signal
(tapeouts, PDK issues, papers, tool bugs) and noise (logistics, banter) so the
synthesis_instruction's filtering can actually be judged.

Timestamps are relative to a fixed reference so the batch is internally
consistent; the runner shifts the whole batch to land inside a recent lookback
window without depending on the wall clock here.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.models import IngestedItem

# Fixed reference "now" for reproducible fixtures.
_REF = datetime(2026, 7, 2, 6, 0, tzinfo=timezone.utc)


def _t(hours_ago: float) -> datetime:
    return _REF - timedelta(hours=hours_ago)


FAKE_ITEMS: list[IngestedItem] = [
    # --- discord/chip-design -------------------------------------------------
    IngestedItem(
        source="discord/chip-design",
        content="Heads up: TSMC pushed a new N3 PDK revision (v1.2). The old "
        "antenna rules were way too conservative; new deck relaxes them for "
        "the top two metals. If you're mid-layout, re-run DRC before you commit.",
        timestamp=_t(3),
        meta={"author": "mira_v", "link_back": "discord://chip-design/9912"},
    ),
    IngestedItem(
        source="discord/chip-design",
        content="Anyone else seeing Innovus 22.1 segfault on ECO route when the "
        "def has >2M placed instances? Downgrading to 21.3 fixed it for us. "
        "Cadence case is open, no ETA.",
        timestamp=_t(5),
        meta={"author": "d_park", "link_back": "discord://chip-design/9908"},
    ),
    IngestedItem(
        source="discord/chip-design",
        content="We taped out the RISC-V test chip this morning 🎉 28nm, "
        "shuttle slot confirmed for August. Thanks everyone who caught the "
        "clock-gating bug in the last review.",
        timestamp=_t(6),
        meta={"author": "s_okafor", "link_back": "discord://chip-design/9901"},
    ),
    IngestedItem(
        source="discord/chip-design",
        content="lunch? 🍜",
        timestamp=_t(6.5),
        meta={"author": "d_park"},
    ),
    IngestedItem(
        source="discord/chip-design",
        content="Reminder the weekly PD sync moved to Thursdays 10am now.",
        timestamp=_t(9),
        meta={"author": "mira_v"},
    ),
    IngestedItem(
        source="discord/chip-design",
        content="Interesting paper making rounds: a learned placement approach "
        "that beats simulated annealing on congestion for mixed-size blocks. "
        "Results look real, not just cherry-picked. Link in thread.",
        timestamp=_t(12),
        meta={"author": "j_liang", "link_back": "discord://chip-design/9880"},
    ),
    # --- telegram/ee-group ---------------------------------------------------
    IngestedItem(
        source="telegram/ee-group",
        content="Verification war story: found a metastability bug that only "
        "showed up in gate-level sim with SDF back-annotation. RTL sim was "
        "totally clean. Lesson: your CDC checker won't catch it if the "
        "synchronizer is inferred, not instantiated.",
        timestamp=_t(4),
        meta={"author": "elena_t", "link_back": "tg://ee-group/4521"},
    ),
    IngestedItem(
        source="telegram/ee-group",
        content="Does anyone have a good reference for extracting parasitic "
        "inductance on wire-bond packages? The usual RLCK flow assumes "
        "flip-chip and my numbers are garbage.",
        timestamp=_t(7),
        meta={"author": "raymond_k", "link_back": "tg://ee-group/4510"},
    ),
    IngestedItem(
        source="telegram/ee-group",
        content="PDK tangent: got burned by a mismatched corner in the "
        "liberty files — the ss_0p72v corner was regenerated but the noise "
        "views weren't. If your tapeout signoff uses noise analysis, diff the "
        ".lib timestamps.",
        timestamp=_t(10),
        meta={"author": "elena_t", "link_back": "tg://ee-group/4498"},
    ),
    IngestedItem(
        source="telegram/ee-group",
        content="anyone going to the conference next month",
        timestamp=_t(11),
        meta={"author": "raymond_k"},
    ),
    IngestedItem(
        source="telegram/ee-group",
        content="New open-source RTL linter dropped that actually understands "
        "SystemVerilog interfaces and modports properly. Caught three real "
        "width-mismatch bugs in our codebase that Verilator missed.",
        timestamp=_t(14),
        meta={"author": "priya_n", "link_back": "tg://ee-group/4470"},
    ),
]
