"""JSON and Markdown triage reports; all untrusted text is escaped."""

import re
from datetime import UTC, datetime
from typing import Any

from regtriage.agent import Diagnosis
from regtriage.signature import Cluster

_MD_SPECIAL_RE = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>])")


def escape_markdown(text: str) -> str:
    """Backslash-escape Markdown-significant characters so untrusted text
    renders literally and cannot inject headers, links, or code fences."""
    return _MD_SPECIAL_RE.sub(r"\\\1", text)


def build_json_report(
    clusters: list[Cluster],
    diagnoses: dict[str, Diagnosis],
    model_id: str,
) -> dict[str, Any]:
    """Build a JSON-serializable report; JSON encoding is the escaping."""
    cluster_rows: list[dict[str, Any]] = []
    for cluster in clusters:
        cluster_rows.append(
            {
                "cluster_id": cluster.cluster_id,
                "signature": cluster.signature,
                "members": [{"test": f.test, "message": f.message} for f in cluster.members],
            }
        )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "model_id": model_id,
        "cluster_count": len(clusters),
        "clusters": cluster_rows,
        "diagnoses": {key: value.model_dump(mode="json") for key, value in diagnoses.items()},
        "status_counts": _status_counts(diagnoses),
    }


def _status_counts(diagnoses: dict[str, Diagnosis]) -> dict[str, int]:
    """Count diagnoses by status without assuming the key set."""
    counts = {"verified": 0, "unverified": 0, "failed": 0}
    for diagnosis in diagnoses.values():
        counts[diagnosis.status] = counts.get(diagnosis.status, 0) + 1
    return counts


def render_markdown(report: dict[str, Any]) -> str:
    """Render the JSON report dict as Markdown with every free-text field
    escaped. Structure (headers, tables) is ours; content is escaped."""
    lines = [
        "# RegTriage report",
        "",
        f"Generated: {escape_markdown(str(report.get('generated_at', '')))}",
        f"Model: {escape_markdown(str(report.get('model_id', '')))}",
        f"Clusters: {int(report.get('cluster_count', 0))}",
        "",
    ]
    counts = report.get("status_counts", {})
    if isinstance(counts, dict):
        lines.append(
            "Verified: "
            f"{int(counts.get('verified', 0))}, Unverified: "
            f"{int(counts.get('unverified', 0))}, Failed: "
            f"{int(counts.get('failed', 0))}"
        )
        lines.append("")
    clusters = report.get("clusters", [])
    if isinstance(clusters, list):
        for cluster in clusters:
            if not isinstance(cluster, dict):
                continue
            lines.append(f"## {escape_markdown(str(cluster.get('cluster_id', '')))}")
            lines.append("")
            for member in cluster.get("members", []):
                if not isinstance(member, dict):
                    continue
                lines.append(
                    f"- {escape_markdown(str(member.get('test', '')))}: "
                    f"{escape_markdown(str(member.get('message', '')))}"
                )
            lines.append("")
    diagnoses = report.get("diagnoses", {})
    if isinstance(diagnoses, dict):
        for key, diagnosis in diagnoses.items():
            lines.append(f"## Diagnosis {escape_markdown(str(key))}")
            lines.append("")
            if isinstance(diagnosis, dict):
                lines.append(
                    f"Summary: {escape_markdown(str(diagnosis.get('root_cause_summary', '')))}"
                )
                lines.append(f"Status: {escape_markdown(str(diagnosis.get('status', '')))}")
                lines.append(f"Confidence: {escape_markdown(str(diagnosis.get('confidence', '')))}")
                for step in diagnosis.get("next_steps", []):
                    lines.append(f"- Next: {escape_markdown(str(step))}")
            lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"
