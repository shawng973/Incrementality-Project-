"""
PDF report renderer.

Renders the analysis result + test metadata into an A4 PDF using
Jinja2 for HTML templating and WeasyPrint for PDF conversion.

Usage:
    pdf_bytes = render_report(test=test, result=result, narrative=narrative_text)
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATE_DIR = Path(__file__).parent.parent.parent / "templates"

_CHANNEL_LABELS: dict[str, str] = {
    "ctv": "CTV",
    "paid_search": "Paid Search",
    "paid_social": "Paid Social",
    "display": "Display",
    "audio": "Audio",
    "ooh": "OOH",
}


def render_report(
    *,
    test,
    result,
    job_id: str,
    narrative: Optional[str] = None,
) -> bytes:
    """
    Render a PDF report for the given test and analysis result.

    Args:
        test:       ORM Test instance (or any object with the same attributes).
        result:     ORM AnalysisResult instance.
        job_id:     String UUID of the AnalysisJob (used in the header).
        narrative:  Optional plain-text narrative from the LLM; inserted as-is.

    Returns:
        Raw PDF bytes suitable for streaming in a FastAPI Response.
    """
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.globals["fmt_dollars"] = _fmt_dollars

    template = env.get_template("report.html.jinja2")

    html_str = template.render(
        test=test,
        result=result,
        job_id=str(job_id),
        narrative=narrative,
        channel_label=_CHANNEL_LABELS.get(test.channel or "", test.channel or ""),
        generated_at=datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC"),
    )

    from weasyprint import HTML  # deferred — requires native libs (pango/gobject)
    return HTML(string=html_str, base_url=str(_TEMPLATE_DIR)).write_pdf()


def _fmt_dollars(value: Optional[float]) -> str:
    """Format a float as a dollar amount (e.g. 1234567.8 → '$1,234,568')."""
    if value is None:
        return "—"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:,.1f}M"
    if abs(value) >= 1_000:
        return f"${value:,.0f}"
    return f"${value:.2f}"
