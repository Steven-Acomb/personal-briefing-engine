"""Localhost web UI for the briefing engine — authoring (edit sources/briefings)
and a thin operational surface (render failure markers/log, Run Now).

Deliberately NOT the scheduler: the schedule lives in OS-cron running
`scheduler.py once`; this server is a viewer + trigger over the durable config
files and run artifacts. It binds to 127.0.0.1 only. See ROADMAP for scope.
"""
