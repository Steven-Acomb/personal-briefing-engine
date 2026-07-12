"""Flask app — localhost authoring UI (M1).

Reads config via `core.config` (the same loader the pipeline uses) and writes via
`core.config_edit` (comment-preserving, atomic, validated). No scheduler, no
run state here; the operational surface (Run Now / markers) lands in M2.
"""

from __future__ import annotations

import re

from flask import Flask, flash, redirect, render_template, request, url_for

from core import config as cfg
from core import config_edit as ce

_SOURCE_KEYS = ("id", "platform", "identifier", "display_name", "credentials_ref", "context")


def _source_to_dict(src) -> dict:
    return {
        "id": src.id,
        "platform": src.platform.value,
        "identifier": src.identifier,
        "display_name": src.display_name or "",
        "credentials_ref": src.credentials_ref or "",
        "context": src.context or "",
    }


def _briefing_to_dict(b) -> dict:
    return {
        "name": b.name,
        "schedule": b.schedule,
        "lookback_window": b.lookback_window,
        "output": [o.value for o in b.output],
        "delivery": [d.value for d in b.delivery],
        "synthesis_instruction": b.synthesis_instruction,
        "sources": [
            {"source_id": sc.source_id, "keyword_filter": ", ".join(sc.keyword_filter)}
            for sc in b.sources
        ],
    }


def _parse_briefing_form(f) -> tuple[dict, list[dict]]:
    fields = {
        "name": f.get("name", ""),
        "schedule": f.get("schedule", ""),
        "lookback_window": f.get("lookback_window", ""),
        "output": f.getlist("output"),
        "delivery": f.getlist("delivery"),
        "synthesis_instruction": f.get("synthesis_instruction", ""),
    }
    rows: list[dict] = []
    for sid, kw in zip(f.getlist("src_source_id"), f.getlist("src_keyword_filter")):
        if not sid.strip():
            continue
        kws = [k.strip() for k in re.split(r"[,\n]", kw) if k.strip()]
        rows.append({"source_id": sid.strip(), "keyword_filter": kws})
    return fields, rows


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = "briefing-engine-localhost"  # localhost-only; flash needs a key

    # ---------------------------------------------------------------- dashboard
    @app.get("/")
    def dashboard():
        return render_template(
            "dashboard.html",
            briefings=cfg.load_briefings(),
            sources=cfg.load_sources(),
        )

    # ------------------------------------------------------------------ sources
    @app.get("/sources/new")
    def source_new():
        blank = {k: "" for k in _SOURCE_KEYS}
        return render_template(
            "source_form.html", source=blank, original_id="",
            platforms=ce.VALID_PLATFORMS,
        )

    @app.get("/sources/<sid>/edit")
    def source_edit(sid):
        src = cfg.load_sources().get(sid)
        if src is None:
            flash(f"Source {sid!r} not found.", "error")
            return redirect(url_for("dashboard"))
        return render_template(
            "source_form.html", source=_source_to_dict(src), original_id=sid,
            platforms=ce.VALID_PLATFORMS,
        )

    @app.post("/sources/save")
    def source_save():
        f = request.form
        original_id = f.get("original_id") or None
        fields = {k: f.get(k, "") for k in _SOURCE_KEYS}
        try:
            ce.upsert_source(fields, original_id=original_id)
            flash(f"Saved source {fields['id']!r}.", "ok")
            return redirect(url_for("dashboard"))
        except ce.ConfigError as e:
            flash(str(e), "error")
            return render_template(
                "source_form.html", source=fields, original_id=original_id or "",
                platforms=ce.VALID_PLATFORMS,
            ), 400

    @app.post("/sources/<sid>/delete")
    def source_delete(sid):
        try:
            ce.delete_source(sid)
            flash(f"Deleted source {sid!r}.", "ok")
        except ce.ConfigError as e:
            flash(str(e), "error")
        return redirect(url_for("dashboard"))

    # ---------------------------------------------------------------- briefings
    @app.get("/briefings/new")
    def briefing_new():
        blank = {
            "name": "", "schedule": "", "lookback_window": "",
            "output": ["text"], "delivery": ["local"],
            "synthesis_instruction": "", "sources": [],
        }
        return render_template(
            "briefing_form.html", briefing=blank, original_name="",
            all_sources=cfg.load_sources(),
            outputs=ce.VALID_OUTPUTS, deliveries=ce.VALID_DELIVERY,
        )

    @app.get("/briefings/<name>/edit")
    def briefing_edit(name):
        match = [b for b in cfg.load_briefings() if b.name == name]
        if not match:
            flash(f"Briefing {name!r} not found.", "error")
            return redirect(url_for("dashboard"))
        return render_template(
            "briefing_form.html", briefing=_briefing_to_dict(match[0]),
            original_name=name, all_sources=cfg.load_sources(),
            outputs=ce.VALID_OUTPUTS, deliveries=ce.VALID_DELIVERY,
        )

    @app.post("/briefings/save")
    def briefing_save():
        original_name = request.form.get("original_name") or None
        fields, rows = _parse_briefing_form(request.form)
        try:
            ce.upsert_briefing(fields, rows, original_name=original_name)
            flash(f"Saved briefing {fields['name']!r}.", "ok")
            return redirect(url_for("dashboard"))
        except ce.ConfigError as e:
            flash(str(e), "error")
            refill = dict(fields)
            refill["sources"] = [
                {"source_id": r["source_id"], "keyword_filter": ", ".join(r["keyword_filter"])}
                for r in rows
            ]
            return render_template(
                "briefing_form.html", briefing=refill,
                original_name=original_name or "", all_sources=cfg.load_sources(),
                outputs=ce.VALID_OUTPUTS, deliveries=ce.VALID_DELIVERY,
            ), 400

    @app.post("/briefings/<name>/delete")
    def briefing_delete(name):
        try:
            ce.delete_briefing(name)
            flash(f"Deleted briefing {name!r}.", "ok")
        except ce.ConfigError as e:
            flash(str(e), "error")
        return redirect(url_for("dashboard"))

    return app
