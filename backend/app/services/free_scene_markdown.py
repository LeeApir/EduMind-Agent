"""Code-aware inert Markdown data, never trusted HTML or executable source."""

import re
from html import escape
from typing import Any, Iterable

import mistune
from mistune.core import BlockState
from mistune.renderers.markdown import MarkdownRenderer

_PUNCTUATION = re.compile(r"([\\`*_{}\[\]()#+.!|~>\-])")
_ALLOWED = {
    "blank_line",
    "paragraph",
    "heading",
    "thematic_break",
    "block_quote",
    "list",
    "list_item",
    "block_text",
    "text",
    "emphasis",
    "strong",
    "codespan",
    "block_code",
    "softbreak",
    "linebreak",
    "link",
    "image",
    "inline_html",
    "block_html",
}


def _walk(tokens: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for token in tokens:
        if token["type"] not in _ALLOWED:
            raise ValueError("UNSUPPORTED_MARKDOWN_TOKEN")
        yield token
        yield from _walk(token.get("children", []))


def _literal(value: str) -> str:
    return _PUNCTUATION.sub(r"\\\1", escape(value, quote=False))


class _InertRenderer(MarkdownRenderer):
    def text(self, token: dict[str, Any], state: BlockState) -> str:
        return _literal(token["raw"])

    def inline_html(self, token: dict[str, Any], state: BlockState) -> str:
        return _literal(token["raw"])

    def block_html(self, token: dict[str, Any], state: BlockState) -> str:
        return _literal(token["raw"]) + "\n\n"

    def link(self, token: dict[str, Any], state: BlockState) -> str:
        # Keep labels/destinations visible, but never reconstruct an active link.
        return (
            _literal("[")
            + self.render_children(token, state)
            + _literal("] (" + token["attrs"]["url"] + ")")
        )

    def image(self, token: dict[str, Any], state: BlockState) -> str:
        return _literal("!") + self.link(token, state)

    def render_referrences(self, state: BlockState) -> Iterable[str]:
        # The default renderer would recreate reference-link definitions.
        return ()

    def block_code(self, token: dict[str, Any], state: BlockState) -> str:
        code = token["raw"]
        if token.get("style") == "indent":
            # Indented-code tokens omit the final newline; retain their own syntax
            # rather than adding a newline to the code payload via a fence.
            return "\n".join("    " + line for line in code.split("\n")) + "\n\n"
        # Canonical fences cannot be closed by any delimiter inside the code.
        longest = max((len(v) for v in re.findall(r"~+", code)), default=0)
        marker = "~" * max(3, longest + 1)
        info = token.get("attrs", {}).get("info", "")
        language = info.split(maxsplit=1)[0] if info.strip() else ""
        if not re.fullmatch(r"[A-Za-z0-9_+.-]{0,32}", language):
            language = ""
        if code and not code.endswith("\n"):
            code += "\n"
        return marker + language + "\n" + code + marker + "\n\n"


def clean_code_markdown(value: str) -> str:
    """Preserve parsed code exactly; disable links/images/HTML outside code.

    The consumer must still use text interpolation or a renderer with raw HTML,
    autolinking and plugins disabled. Code is displayed as text, never executed.
    """
    parser = mistune.create_markdown(renderer=None, plugins=[])
    tokens, state = parser.parse(value)
    if not isinstance(tokens, list):
        raise ValueError("MARKDOWN_AST_REQUIRED")
    flattened = list(_walk(tokens))
    code = [(t["type"], t["raw"]) for t in flattened if t["type"] in {"codespan", "block_code"}]
    if not code:
        # Byte-compatible legacy behavior for prose-only content and tutor users.
        from app.services.free_scene_validation import clean_markdown

        return clean_markdown(value)
    cleaned = _InertRenderer()(tokens, state)
    reparsed, _ = parser.parse(cleaned)
    if not isinstance(reparsed, list):
        raise ValueError("MARKDOWN_AST_REQUIRED")
    after = list(_walk(reparsed))
    if any(t["type"] in {"link", "image", "inline_html", "block_html"} for t in after):
        raise ValueError("ACTIVE_MARKDOWN_RECONSTRUCTION")
    if [(t["type"], t["raw"]) for t in after if t["type"] in {"codespan", "block_code"}] != code:
        raise ValueError("MARKDOWN_CODE_CHANGED")
    return cleaned
