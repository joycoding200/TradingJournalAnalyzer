"""Sanitize AI-generated content before saving to DB or rendering.

Covers issue P1-14: LLM output may contain <script> tags, event handlers,
or other XSS vectors that would execute if the frontend renders the report
as raw HTML. The sanitizer strips these — it's a defence-in-depth layer
that keeps the DB clean even if the frontend Markdown renderer has gaps.
"""
import re

# Match <script> blocks (case-insensitive, multiline)
_SCRIPT_RE = re.compile(r"<script[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
_ON_EVENT_RE = re.compile(r"\s+on\w+\s*=\s*[\"'][^\"']*[\"']", re.IGNORECASE)
_JAVASCRIPT_URL_RE = re.compile(r"""href\s*=\s*['"]\s*javascript\s*:""", re.IGNORECASE)


def sanitize_report(content: str) -> str:
    """Strip dangerous HTML from AI-generated report content.

    Handles the three most common XSS vectors in Markdown-to-HTML contexts:
      - <script> blocks
      - inline event handlers (onclick, onerror, onload, …)
      - javascript: pseudo-URLs in links

    Returns the cleaned string. Is a last-resort safety net — the frontend
    must still use a safe Markdown renderer.
    """
    content = _SCRIPT_RE.sub("", content)
    content = _ON_EVENT_RE.sub("", content)
    content = _JAVASCRIPT_URL_RE.sub('href="', content)
    return content
