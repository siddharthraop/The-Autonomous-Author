"""Find the new sentences in a draft, from the added lines of each changed page."""
import difflib
import re

PLACEHOLDER = re.compile(r"\[NEEDS INPUT:\s*([^\]]+)\]")


def norm(s):
    s = re.sub(r"\s+", " ", s).strip()
    return s.strip("|").strip()


def added_lines(old, new):
    """Line numbers (1-based) and text of lines added in `new`."""
    sm = difflib.SequenceMatcher(a=(old or "").splitlines(), b=new.splitlines(), autojunk=False)
    out = []
    for op, _, _, j1, j2 in sm.get_opcodes():
        if op in ("replace", "insert"):
            out += [(j, new.splitlines()[j - 1]) for j in range(j1 + 1, j2 + 1)]
    return out


def split(old, new):
    """Return [(first_line, sentence)] for the added text of one page."""
    in_fence = False
    fence_lines = set()
    for n, line in enumerate(new.splitlines(), 1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            fence_lines.add(n)
        elif in_fence:
            fence_lines.add(-n)  # code line
    out, para, start, prev = [], [], 0, None

    def flush():
        nonlocal para
        if para:
            text = " ".join(para)
            held = PLACEHOLDER.findall(text)
            text = PLACEHOLDER.sub("\x00", text)
            parts = re.split(r"(?<=[.!?\]])\s+(?=[A-Z\x00`{])", text)
            for part in parts:
                while "\x00" in part:
                    part = part.replace("\x00", f"[NEEDS INPUT: {held.pop(0)}]", 1)
                if part.strip():
                    out.append((start, part.strip()))
            para = []

    for n, line in added_lines(old, new):
        s = line.strip()
        if prev is not None and n != prev + 1:
            flush()
        prev = n
        if not s or n in fence_lines:
            flush()
            continue
        if -n in fence_lines or s.startswith("|") or s.startswith("#"):
            flush()
            if not re.fullmatch(r"\|?[\s:|-]+\|?", s):
                out.append((n, s.lstrip("#").strip()))
            continue
        s = re.sub(r"^([-*+]|\d+\.)\s+", "", s)
        if not para:
            start = n
        para.append(s)
    flush()
    return out


LIT = [r"`([^`]+)`", r"(--[a-z0-9][a-z0-9-]*)", r"\b([a-z]+[A-Z][A-Za-z0-9]*)\b", r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])"]


def literals(sentence):
    s = re.sub(r"\{\{\s*[\w-]+\s*\}\}", " ", sentence)
    found = []
    for rx in LIT:
        for m in re.finditer(rx, s):
            v = m.group(1)
            if v not in found and not any(v in f for f in found):
                found.append(v)
    return found


def contains(pool, literal):
    """Whole-token match, so 1 does not match 120."""
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(literal.lower())}(?![A-Za-z0-9_])", pool) is not None
