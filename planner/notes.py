"""Notes assistant. The offline summariser is the default and needs no internet or API key.

An OPTIONAL AI summary (Anthropic API) is available only if the user installs the `anthropic`
package AND sets the ANTHROPIC_API_KEY environment variable AND clicks the AI button.
Nothing in the app requires it, and the notes are only sent when the user explicitly asks.
"""
from __future__ import annotations

import os
import re
from collections import Counter

from .validators import ValidationError

MAX_CHARS = 200_000
MIN_CHARS = 40
STOPWORDS = set("""a an the and or but if then else of to in on at by for with from as is are was were be been being it its this
that these those i you he she we they them his her their our your my me not no yes do does did done have has had will would can
could should may might must so than too very also into about over under again more most some such only own same other each any
both few all just which who whom what when where why how there here up down out off through during before after above below
between because while until against once""".split())


def read_uploaded_text(raw: bytes, filename: str = "notes.txt") -> str:
    """Decode an uploaded .txt/.md file safely."""
    if not filename.lower().endswith((".txt", ".md")):
        raise ValidationError("Please upload a plain text file (.txt or .md).")
    if len(raw) > 1_000_000:
        raise ValidationError("That file is larger than 1 MB. Please upload a shorter text file.")
    for enc in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeError:
            continue
    raise ValidationError("Could not read the file as text.")


def _sentences(text: str) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text.replace("\r", ""))
    parts = re.split(r"(?<=[.!?])\s+|\n{2,}|\n(?=[-*\u2022]|\d+[.)]\s)", text)
    return [p.strip(" \n-*\u2022") for p in parts if len(p.strip()) >= 15]


def _words(s: str) -> list[str]:
    return [w for w in re.findall(r"[A-Za-z][A-Za-z\-']+", s.lower()) if w not in STOPWORDS and len(w) > 2]


def summarize_offline(text: str, max_sentences: int = 5) -> dict:
    """Extractive summary: score sentences by keyword frequency, keep original order."""
    text = (text or "").strip()
    if len(text) < MIN_CHARS:
        raise ValidationError(f"Please paste at least {MIN_CHARS} characters of notes.")
    if len(text) > MAX_CHARS:
        raise ValidationError("Notes are too long (limit 200,000 characters). Please split them.")
    max_sentences = max(1, min(int(max_sentences), 15))
    sents = _sentences(text) or [text]
    freq = Counter(w for s in sents for w in _words(s))
    scored = []
    for i, s in enumerate(sents):
        ws = _words(s)
        if not ws:
            continue
        score = sum(freq[w] for w in ws) / (len(ws) ** 0.7)
        if i == 0:
            score *= 1.15
        scored.append((score, i, s))
    top = sorted(sorted(scored, reverse=True)[:max_sentences], key=lambda x: x[1])
    keywords = [w for w, _ in freq.most_common(10)]
    questions = []
    for s in sents:
        m = re.match(r"^(?:An?\s+|The\s+)?([A-Z][\w\- ]{2,40}?)\s+(is|are|means|refers to)\s+(.{10,})$", s)
        if m and len(questions) < 5:
            questions.append(f"{'What is' if m.group(2) == 'is' else 'What are' if m.group(2) == 'are' else 'Define'} {m.group(1).strip()}?")
    return {"summary": [t[2] for t in top], "keywords": keywords, "practice_questions": questions,
            "stats": {"characters": len(text), "sentences": len(sents), "mode": "offline (rule-based)"}}


def ai_available() -> tuple[bool, str]:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False, "Set the ANTHROPIC_API_KEY environment variable to enable this optional feature."
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False, "Run `pip install anthropic` to enable this optional feature."
    return True, "Optional AI summary is available."


def summarize_with_ai(text: str) -> str:
    """OPTIONAL. Sends the notes to the Anthropic API. Not used unless the user clicks the AI button.

    NOTE: this path needs an API key and internet and has not been exercised in this project's tests.
    """
    ok, msg = ai_available()
    if not ok:
        raise ValidationError(msg)
    if len(text.strip()) < MIN_CHARS or len(text) > 50_000:
        raise ValidationError("For the AI summary, notes must be between 40 and 50,000 characters.")
    import anthropic
    client = anthropic.Anthropic()                     # reads ANTHROPIC_API_KEY from the environment
    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
    try:
        reply = client.messages.create(model=model, max_tokens=800, messages=[{
            "role": "user",
            "content": "Summarise these student notes in 5 bullet points, then list 3 practice questions.\n\n" + text}])
    except Exception as exc:                           # network, auth, model-name errors
        raise ValidationError(f"The AI request failed ({type(exc).__name__}). The offline summary still works.")
    return "".join(b.text for b in reply.content if getattr(b, "type", "") == "text")
