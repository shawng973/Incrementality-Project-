"""
Narrative generation service.

Builds a marketer-readable interpretation of geo split-test analysis results
using an LLM via OpenRouter. Output is structured Markdown suitable for
rendering in the results dashboard or exporting to PDF.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.llm.client import LLMResponse, OpenRouterClient

# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


@dataclass
class NarrativeOutput:
    headline: str           # One-sentence summary (extracted from LLM)
    body_markdown: str      # Full Markdown narrative
    model: str              # Which model was used (for provenance)
    prompt_tokens: int
    completion_tokens: int


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a senior marketing analytics strategist. Your job is to interpret
geo-split incrementality test results for a non-technical marketing executive.

Write in plain business English — no statistical jargon unless you define it.
Be direct and confident about what the data shows. Flag any concerns clearly.

Format your response as Markdown with the following sections:
## Headline
One bold sentence summarising the key finding.

## What We Measured
Brief description of the test design and metric.

## Results
- TWFE lift estimate and significance
- Confidence intervals (mention the range without technical notation)
- Simple DiD cross-check alignment

## Incrementality
- Best estimate of incremental revenue
- ROAS range (conservative to optimistic)

## Data Quality Notes
- Parallel trends validity
- Whether the result is causally clean
- Power / sample-size adequacy

## Recommendation
One clear action or next step based on the results.
"""


def build_prompt(result: dict[str, Any]) -> list[dict[str, str]]:
    """
    Construct the chat messages list for the narrative generation call.

    Args:
        result: Dict containing analysis result fields (same shape as
                AnalysisResultResponse / analysis_results DB row).
    """
    # Format key numbers into the user message
    twfe_effect = result.get("twfe_treatment_effect")
    twfe_pct = f"{twfe_effect * 100:.1f}%" if twfe_effect is not None else "N/A"
    twfe_dollars = result.get("twfe_treatment_effect_dollars")
    twfe_p = result.get("twfe_p_value")
    ci_95 = result.get("twfe_ci_95") or {}
    ci_lo = ci_95.get("lower")
    ci_hi = ci_95.get("upper")
    ci_str = (
        f"{ci_lo * 100:.1f}%–{ci_hi * 100:.1f}%"
        if ci_lo is not None and ci_hi is not None
        else "N/A"
    )

    simple_est = result.get("simple_did_estimate")
    simple_pct = f"{simple_est * 100:.1f}%" if simple_est is not None else "N/A"

    incr_mid = result.get("incremental_revenue_midpoint")
    incr_wtd = result.get("incremental_revenue_weighted")

    roas_low = result.get("roas_low")
    roas_mid = result.get("roas_mid")
    roas_high = result.get("roas_high")
    roas_str = (
        f"{roas_low:.2f}x – {roas_mid:.2f}x – {roas_high:.2f}x (conservative / mid / optimistic)"
        if all(v is not None for v in [roas_low, roas_mid, roas_high])
        else "Not computed (no spend provided)"
    )
    total_spend = result.get("total_spend")

    pt_passes = result.get("parallel_trends_passes")
    pt_flag = result.get("parallel_trends_flag") or ""
    causally_clean = result.get("is_causally_clean")

    power_json = result.get("power_analysis_json") or {}
    power_val = power_json.get("power")
    powered = power_json.get("is_adequately_powered")
    power_warning = power_json.get("warning_message") or ""

    # Pre-format values that need conditional formatting
    twfe_p_str = f"{twfe_p:.4f}" if twfe_p is not None else "N/A"
    twfe_dollars_str = f"${twfe_dollars:,.0f}" if twfe_dollars is not None else "N/A"
    incr_mid_str = f"${incr_mid:,.0f}" if incr_mid is not None else "N/A"
    incr_wtd_str = f"${incr_wtd:,.0f}" if incr_wtd is not None else "N/A"
    total_spend_str = f"${total_spend:,.0f}" if total_spend is not None else "N/A"
    power_str = f"{power_val:.0%}" if power_val is not None else "N/A"
    power_status = "adequate" if powered else "UNDERPOWERED"
    pt_status = "PASSED ✓" if pt_passes else "FAILED ✗"
    pt_suffix = f" — {pt_flag}" if pt_flag else ""
    causally_clean_str = str(causally_clean) if causally_clean is not None else "N/A"
    power_warning_line = f"⚠ {power_warning}" if power_warning else ""

    user_content = f"""
Here are the analysis results for a geo split incrementality test:

**TWFE Treatment Effect:** {twfe_pct} lift ({twfe_dollars_str})
**TWFE p-value:** {twfe_p_str}
**95% CI (lift):** {ci_str}
**Simple DiD cross-check:** {simple_pct}

**Incremental Revenue — Midpoint:** {incr_mid_str}
**Incremental Revenue — Variance-Weighted:** {incr_wtd_str}
**Total Spend:** {total_spend_str}
**ROAS:** {roas_str}

**Parallel Trends Test:** {pt_status}{pt_suffix}
**Causally Clean (pre-trend adjusted):** {causally_clean_str}
**Statistical Power:** {power_str} ({power_status})
{power_warning_line}

Write the analysis narrative following the format in your instructions.
""".strip()

    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


async def generate_narrative(
    result: dict[str, Any],
    client: OpenRouterClient,
) -> NarrativeOutput:
    """
    Generate a Markdown narrative for the given analysis result.

    Args:
        result: Analysis result fields dict.
        client: Configured OpenRouterClient instance.

    Returns:
        NarrativeOutput with headline extracted and full Markdown body.
    """
    messages = build_prompt(result)
    response: LLMResponse = await client.chat(messages, temperature=0.3, max_tokens=1024)

    headline = _extract_headline(response.content)

    return NarrativeOutput(
        headline=headline,
        body_markdown=response.content,
        model=response.model,
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
    )


def _extract_headline(markdown: str) -> str:
    """
    Pull the first non-empty line after '## Headline' as the headline.
    Falls back to the first non-empty line of the response.
    """
    lines = markdown.splitlines()
    in_headline = False
    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith("## headline"):
            in_headline = True
            continue
        if in_headline and stripped:
            # Strip leading markdown bold markers
            return stripped.strip("*").strip()
        if in_headline and not stripped:
            continue
        # Once we hit the next section header, stop
        if in_headline and stripped.startswith("##"):
            break

    # Fallback: first non-empty line
    for line in lines:
        if line.strip():
            return line.strip().strip("*").strip()
    return "Analysis complete."
