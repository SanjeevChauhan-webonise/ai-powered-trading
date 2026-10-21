import re
from dataclasses import dataclass

MAX_CHARS = 800
OVERLAP_CHARS = 120

_HEADING = re.compile(r"^(#{1,4})\s+(.*\S)\s*$")


@dataclass(frozen=True)
class Chunk:
    text: str
    heading: str  # e.g. "Risk management > Stop loss (`risk.stop_loss_pct`)"


def _sections(markdown: str) -> list[tuple[str, str]]:
    """Split on headings; each section carries its heading path."""
    path: list[tuple[int, str]] = []
    sections: list[tuple[str, list[str]]] = [("", [])]
    in_code = False
    for line in markdown.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
        m = None if in_code else _HEADING.match(line)
        if m:
            level, title = len(m.group(1)), m.group(2)
            path = [(lv, t) for lv, t in path if lv < level] + [(level, title)]
            sections.append((" > ".join(t for _, t in path), []))
        else:
            sections[-1][1].append(line)
    return [(h, "\n".join(lines).strip()) for h, lines in sections if "\n".join(lines).strip()]


def _split_long(text: str, max_chars: int, overlap: int) -> list[str]:
    """Split on paragraph boundaries, falling back to sentence/hard cuts; carry a small overlap between pieces."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces: list[str] = []
    for p in paras:
        while len(p) > max_chars:
            cut = max(p.rfind(". ", 0, max_chars), p.rfind("\n", 0, max_chars))
            cut = cut + 1 if cut > max_chars // 2 else max_chars
            pieces.append(p[:cut].strip())
            p = p[cut:].strip()
        if p:
            pieces.append(p)
    chunks: list[str] = []
    cur = ""
    for piece in pieces:
        if cur and len(cur) + len(piece) + 2 > max_chars:
            chunks.append(cur)
            tail = cur[-overlap:].split(" ", 1)[-1] if overlap else ""  # start the next chunk on a word boundary
            cur = f"{tail}\n\n{piece}" if tail and len(tail) + len(piece) + 2 <= max_chars else piece
        else:
            cur = f"{cur}\n\n{piece}" if cur else piece
    if cur:
        chunks.append(cur)
    return chunks


def chunk_markdown(markdown: str, max_chars: int = MAX_CHARS, overlap: int = OVERLAP_CHARS) -> list[Chunk]:
    out: list[Chunk] = []
    for heading, body in _sections(markdown):
        if len(body) <= max_chars:
            out.append(Chunk(body, heading))
        else:
            out.extend(Chunk(t, heading) for t in _split_long(body, max_chars, overlap))
    return out
