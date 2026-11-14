"""LLM wrapper. Every phase calls the model ONLY through complete() / complete_json().

    from app.llm import complete, complete_json
    text = complete(system, user, kind="chat", lecture_id=lid)
    data = complete_json(system, user, schema_hint='{"topics": [...]}', kind="topics", lecture_id=lid)

LLM_PROVIDER=mock (default) needs no key. Mock output is built from the <material>, <topics>,
<message> and <highlight> tags in the prompt, so it looks realistic and follows the real data.
Every call (mock included) is written to the agent_logs table.
"""
import json
import os
import re
import time

from dotenv import load_dotenv

from app.db import execute

load_dotenv()

PROVIDER = os.getenv("LLM_PROVIDER", "mock").strip().lower() or "mock"
DEFAULT_MODELS = {"anthropic": "claude-sonnet-5-5", "openai": "gpt-4o-mini", "mock": "mock"}
MODEL = os.getenv("LLM_MODEL", "").strip() or DEFAULT_MODELS.get(PROVIDER, "mock")
MAX_TOKENS = 4096


class LLMError(RuntimeError):
    pass


# ------------------------------------------------------------------ public API

def complete(system: str, user: str, kind: str = "generic", lecture_id: int | None = None,
             max_tokens: int = MAX_TOKENS) -> str:
    start = time.time()
    try:
        if PROVIDER == "mock":
            out = _mock(kind, system, user)
        elif PROVIDER == "anthropic":
            out = _anthropic(system, user, max_tokens)
        elif PROVIDER == "openai":
            out = _openai(system, user, max_tokens)
        else:
            raise LLMError(f"Unknown LLM_PROVIDER '{PROVIDER}' (use mock, anthropic or openai)")
    except Exception as e:  # log failures too, they are evidence for debugging
        _log(kind, lecture_id, system, user, f"ERROR: {e}", start)
        raise
    _log(kind, lecture_id, system, user, out, start)
    return out


def complete_json(system: str, user: str, schema_hint: str = "", kind: str = "generic",
                  lecture_id: int | None = None, max_tokens: int = MAX_TOKENS) -> dict:
    sys2 = system + "\n\nRespond with a single valid JSON object only. No prose, no code fences."
    if schema_hint:
        sys2 += f"\nShape: {schema_hint}"
    raw = complete(sys2, user, kind=kind, lecture_id=lecture_id, max_tokens=max_tokens)
    try:
        return _parse_json(raw)
    except ValueError:
        # one repair attempt
        raw2 = complete("Fix this into valid JSON. Output only the JSON object.", raw,
                        kind=kind + "_repair", lecture_id=lecture_id, max_tokens=max_tokens)
        return _parse_json(raw2)


# ------------------------------------------------------------------ providers

def _anthropic(system: str, user: str, max_tokens: int) -> str:
    import anthropic
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    msg = client.messages.create(model=MODEL, max_tokens=max_tokens, system=system,
                                 messages=[{"role": "user", "content": user}])
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def _openai(system: str, user: str, max_tokens: int) -> str:
    from openai import OpenAI
    client = OpenAI()  # reads OPENAI_API_KEY (and OPENAI_BASE_URL for compatible servers)
    resp = client.chat.completions.create(
        model=MODEL, max_tokens=max_tokens,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    return resp.choices[0].message.content or ""


# ------------------------------------------------------------------ helpers

def _parse_json(raw: str) -> dict:
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", s, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    raise ValueError("LLM did not return valid JSON")


def _log(kind, lecture_id, system, user, response, start):
    try:
        execute("INSERT INTO agent_logs (kind, lecture_id, prompt, response, model, latency_ms) "
                "VALUES (?,?,?,?,?,?)",
                (kind, lecture_id, f"[SYSTEM]\n{system}\n\n[USER]\n{user}", response,
                 f"{PROVIDER}:{MODEL}", int((time.time() - start) * 1000)))
    except Exception:
        pass  # logging must never break the app


def _tag(text: str, tag: str) -> str:
    m = re.search(rf"<{tag}>\s*(.*?)\s*</{tag}>", text, re.S)
    return m.group(1) if m else ""


def _slides(material: str) -> list[tuple[str, list[str]]]:
    """Split material into (title, lines) per slide/page."""
    parts = re.split(r"^--- (?:Slide|Page) \d+ ---$", material, flags=re.M)
    out = []
    for p in parts:
        lines = [l.strip(" •-\t") for l in p.strip().splitlines()
                 if l.strip() and not re.fullmatch(r"\s*(Slide|Page)?\s*\d+\s*", l)]
        if lines:
            out.append((lines[0][:80], lines[1:]))
    return out


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-zà-ÿ]{4,}", s.lower())}


# ------------------------------------------------------------------ mock LLM

def _mock(kind: str, system: str, user: str) -> str:
    material = _tag(user, "material")
    slides = _slides(material) or [("Introduction", ["(no material text found)"])]

    if kind == "lecture":
        md = ["> *Mock lecture (LLM_PROVIDER=mock). Set a real provider in `.env` for the AI-written version.*\n",
              f"This lecture walks through {len(slides)} ideas from the lecturer's slides: "
              + ", ".join(t for t, _ in slides[:5]) + ".\n"]
        for title, lines in slides:
            md.append(f"## {title}\n")
            if lines:
                md.append(lines[0] + "\n")
                md += [f"- {l}" for l in lines[1:8]] + [""]
            md.append(f"**Why it matters:** understanding *{title.lower()}* is needed for the rest of the lecture.\n")
        md.append("## Key takeaways\n")
        md += [f"- {t}" for t, _ in slides[:6]]
        return "\n".join(md)

    if kind == "topics":
        picked = slides[:6] if len(slides) >= 3 else slides + [("Core concepts", []), ("Applications", [])]
        return json.dumps({"topics": [
            {"name": t[:48], "summary": (" ".join(l[:2]) or f"The idea of {t.lower()}.")[:200]}
            for t, l in picked[:6]]})

    if kind == "questions":
        topics = json.loads(_tag(user, "topics") or "[]")
        n = int((re.search(r"Write (\d+) questions", user) or [0, 6])[1])
        qs = []
        for i in range(n):
            t = topics[i % len(topics)] if topics else {"id": None, "name": "the lecture", "summary": "It is covered."}
            others = [o["summary"] for o in topics if o.get("id") != t.get("id")][:3]
            while len(others) < 3:
                others.append(f"It is unrelated to {t['name'].lower()}.")
            correct = (i * 7) % 4
            options = others[:]
            options.insert(correct, t.get("summary") or t["name"])
            qs.append({"topic_id": t.get("id"), "text": f"Which statement best describes \"{t['name']}\"?",
                       "options": options, "correct_index": correct,
                       "explanation": f"The lecture defines {t['name']} this way; the other options describe different topics."})
        return json.dumps({"questions": qs})

    if kind == "topic_tag":
        topics = json.loads(_tag(user, "topics") or "[]")
        msg = _words(_tag(user, "message") + " " + _tag(user, "highlight"))
        best = max(topics, key=lambda t: len(msg & _words(t["name"] + " " + t.get("summary", ""))), default=None)
        return json.dumps({"topic_id": best["id"] if best else None})

    if kind == "chat":
        msg = _tag(user, "message") or user[-300:]
        hl = _tag(user, "highlight")
        best = max(slides, key=lambda s: len(_words(msg + " " + hl) & _words(s[0] + " " + " ".join(s[1]))))
        quote = f" about \"{hl[:80]}\"" if hl else ""
        return (f"*(mock tutor)* Good question{quote}. The material covers this under **{best[0]}**: "
                f"{' '.join(best[1][:2]) or 'see the slides for this part.'}\n\n"
                f"Try putting it in your own words: how would you explain *{best[0].lower()}* to a classmate?")

    return f"(mock {kind} response)"
