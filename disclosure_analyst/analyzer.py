"""Analyze extracted disclosure content via Claude API."""
from __future__ import annotations

import os
from typing import Callable

import anthropic

from .extractor import ExtractionResult


SYSTEM_PROMPT = """You are a real estate disclosure analyst. You will be given the extracted contents of a ZIP archive containing home purchase disclosure documents (PDFs, Word docs, spreadsheets, images, text files, etc.).

Analyze every file and produce a single structured report titled "Disclosure Package Summary" with these eight sections, in this exact order:

1. Key Inspection Findings — all material defects, issues, or concerns noted
2. Repairs Performed — completed repairs with descriptions, dates, contractor, and cost when available
3. Repairs Pending — outstanding repairs, EACH with a specific cost estimate (use a bid figure if one exists in the documents; otherwise give a typical Bay Area / regional planning range and label it as such)
4. Appliance Conditions — condition AND age of every appliance mentioned
5. Roof Condition — covering type, age, repairs performed, repairs still needed, warranty notes
6. Foundation — foundation type and any issues or concerns
7. Termite / Pest Inspection — firm, inspector, date, Section 1 / Section 2 / Further Inspection findings, treatments performed, clearance status
8. HOA Details — whether an HOA exists, fees (current and recent history), what dues cover, reserves, special assessments, litigation, insurance

Required output format — follow this EXACTLY so the PDF renderer produces a polished document:

- Begin the document with a single H1 line: `# Disclosure Package Summary`
- Immediately after the title, write a one-line subtitle in italics with the property address, county, APN if known.
- Then a property-summary key/value table (markdown table with two columns: field name | value). Include rows like Sellers, Listing Agent, Package Date, Property Type, Year Built, Documents Reviewed.
- Then an italic "Scope note." paragraph explaining the basis for cost estimates and that ambiguities are flagged.
- Use `## 1. Key Inspection Findings`, `## 2. Repairs Performed`, etc. — each section heading MUST be `##` followed by the number, period, space, and title.
- Inside each section, use `### Sub-heading:` for grouped lists (e.g., `### Open (Action Recommended) items from home inspection:`).
- Use markdown bullets (`- ` at start of line) for lists. Start each bullet with a **bold lead-in label** followed by a period and the explanation, e.g. `- **3.4 Eaves (roof sheathing, rafters, fascia).** Weather damage observed at SW corner...`
- For any tabular data — Repairs Pending cost tables, Appliance Conditions, Roof attributes, Foundation attributes, Termite report metadata, HOA assessment history — use proper markdown tables with a header row and a separator row (`| --- | --- |`). Two-column key/value tables are preferred for attribute lists; three-column `Item | Cost Estimate | Source` tables for cost lists.
- Use short italic callout paragraphs starting with words like "Scope note.", "Flags.", "Caveats.", "Ambiguity flagged.", "Warranty limitations.", "Document-availability flags.", or "Clearance ambiguity flagged." to highlight cross-document conflicts, missing data, or important caveats.
- Cross-reference information across documents. Explicitly call out conflicts (e.g., TDS says one thing, inspection report says another).
- Cite source documents by filename in parentheses or in the Source column of tables.
- End the report with an `## Appendix — Document Index & Processing Notes` section: a markdown table listing every file processed with a brief note about its content and any extraction issues. If any files were unreadable, list them here in a final paragraph.

Be thorough, precise, and professional. Prefer concrete numbers, dates, license numbers, and named parties over vague summaries."""


def _build_user_content(extraction: ExtractionResult) -> list[dict]:
    content: list[dict] = []

    # Combine text files into one block
    text_parts = []
    for f in extraction.text_files:
        if not f.text.strip():
            continue
        text_parts.append(f"\n\n========== FILE: {f.path} ==========\n{f.text}")

    if extraction.unreadable_files:
        text_parts.append("\n\n========== UNREADABLE FILES ==========")
        for f in extraction.unreadable_files:
            text_parts.append(f"- {f.path}: {f.error}")

    if not text_parts and not extraction.image_files:
        text_parts.append("(No readable content found in the archive.)")

    # Images first (Claude vision recommendation)
    for f in extraction.image_files:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": f.image_media_type,
                "data": f.image_b64,
            },
        })
        content.append({"type": "text", "text": f"(Image above: {f.path})"})

    intro = ("Below are the extracted contents of all documents in the disclosure ZIP archive. "
             "Analyze them and produce the structured report as specified.\n")
    content.append({"type": "text", "text": intro + "".join(text_parts)})

    return content


def analyze(extraction: ExtractionResult,
            api_key: str | None = None,
            progress: Callable[[str], None] | None = None) -> str:
    """Run Claude analysis. Returns the markdown report text."""
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Configure it in the app settings.")

    client = anthropic.Anthropic(api_key=api_key)
    user_content = _build_user_content(extraction)

    if progress:
        progress("Sending documents to Claude for analysis...")

    # Use streaming for large inputs
    with client.messages.stream(
        model="claude-opus-4-7",
        max_tokens=32000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    ) as stream:
        for _ in stream.text_stream:
            if progress:
                progress("Receiving analysis...")
        final = stream.get_final_message()

    parts = [b.text for b in final.content if b.type == "text"]
    return "\n".join(parts)
