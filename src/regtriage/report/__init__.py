"""Triage reports: JSON + escaped Markdown, optional Slack delivery."""

from regtriage.report.report import build_json_report, escape_markdown, render_markdown
from regtriage.report.slack import send_slack

__all__ = ["build_json_report", "escape_markdown", "render_markdown", "send_slack"]
