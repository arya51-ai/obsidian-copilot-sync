#!/usr/bin/env python3
"""
obsidian-copilot-sync — Convert GitHub Copilot Chat conversations to Obsidian notes

Reads exported Copilot Chat JSON files and converts them to linked markdown
notes in your Obsidian vault, classified by project.

How to export from VS Code:
    1. Open the Copilot Chat panel (Ctrl+Alt+I / Cmd+Shift+I)
    2. Click the "..." menu at the top of the panel
    3. Select "Export Chat..."
    4. Save as .json to your COPILOT_EXPORT_DIR

Usage:
    python3 sync.py

Configuration:
    Edit VAULT and COPILOT_EXPORT_DIR below to match your setup.
    Edit PROJECTS to match your work.

Output structure:
    Vault/
    ├── Home.md
    ├── Conversations/
    │   ├── _Index.md
    │   └── YYYY-MM/
    │       └── YYYY-MM-DD - Title.md
    └── .sync/
        └── manifest.json
"""
import json, os, re, sys, glob
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# ---- paths ----------------------------------------------------------------
HOME              = Path.home()
VAULT             = HOME / "CopilotVault"       # change to your Obsidian vault path
COPILOT_EXPORT_DIR = HOME / "copilot-exports"   # folder of exported .json files

CONV_DIR = VAULT / "Conversations"
MANIFEST = VAULT / ".sync" / "manifest.json"
FORMAT   = 1

# ---- selective sync -------------------------------------------------------
SELECTIVE_MODE = False
VAULT_TAG      = "#vault"

# ---- project taxonomy -----------------------------------------------------
PROJECTS = [
    {"label": "Example Project", "hub": None, "tag": "example",
     "kw": ["example", "test"]},
]
MISC = {"label": "Misc", "hub": None, "tag": "misc", "kw": []}

def classify(title, body):
    tl, bl = (title or "").lower(), (body or "").lower()
    best, best_score = None, 0
    for proj in PROJECTS:
        score = sum((3 if k in tl else 0) + (1 if k in bl else 0) for k in proj["kw"])
        if score > best_score:
            best, best_score = proj, score
    return best or MISC

# ---- helpers --------------------------------------------------------------

def load_manifest():
    try:    return json.loads(MANIFEST.read_text())
    except Exception: return {}

def save_manifest(m):
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(m))

def sanitize(name, maxlen=70):
    name = re.sub(r'[\\/:\*\?"<>\|\n\r\t]', ' ', name or '')
    name = name.replace('[', '(').replace(']', ')')
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:maxlen].strip() or "Untitled"

def short(s, n=200):
    if not isinstance(s, str): s = json.dumps(s, ensure_ascii=False)
    s = re.sub(r'\s+', ' ', s).strip()
    return s[:n] + ('...' if len(s) > n else '')

def parse_ts(ts):
    if not ts: return None
    try:
        if isinstance(ts, (int, float)):
            ts = ts / 1000 if ts > 1e10 else ts
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        return datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
    except Exception:
        return None

# ---- copilot reader -------------------------------------------------------

def _extract_text(val):
    """Pull a plain string out of various content shapes."""
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, list):
        parts = []
        for item in val:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(item.get("value") or item.get("text") or
                             item.get("content") or "")
        return "\n\n".join(p for p in parts if p).strip()
    if isinstance(val, dict):
        return (val.get("value") or val.get("text") or val.get("content") or "").strip()
    return ""


def parse_copilot_file(path):
    """
    Parse one exported Copilot Chat JSON file.
    Returns (session_id, title, turns, first_ts) or None on failure.

    Handles two formats:
      1. VS Code Chat export: {"sessionId": "...", "requests": [...]}
      2. Raw message array:   [{"role": "user"|"assistant", "content": "..."}]
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            data = json.load(fh)
    except Exception as e:
        print(f"  ! {Path(path).name}: JSON parse error: {e}", file=sys.stderr)
        return None

    turns    = []
    first_ts = None

    # Format 1: VS Code Chat export
    if isinstance(data, dict) and "requests" in data:
        sid   = data.get("sessionId") or Path(path).stem
        title = data.get("title") or None

        for req in data.get("requests", []):
            # user turn
            msg = req.get("message") or req.get("prompt") or {}
            if isinstance(msg, str):
                user_text = msg
            else:
                user_text = _extract_text(msg.get("text") or msg.get("parts") or msg)
            if user_text:
                turns.append(("user", user_text))

            # timestamp
            if not first_ts:
                first_ts = parse_ts(req.get("timestamp") or req.get("time"))

            # assistant turn
            resp = req.get("response") or req.get("result") or ""
            resp_text = _extract_text(resp)
            if resp_text:
                turns.append(("asst", resp_text))

        return sid, title, turns, first_ts

    # Format 2: raw message array
    if isinstance(data, list) and data and isinstance(data[0], dict) and "role" in data[0]:
        sid = Path(path).stem
        for msg in data:
            role    = (msg.get("role") or "").lower()
            content = _extract_text(msg.get("content") or msg.get("text") or "")
            if not content:
                continue
            if not first_ts:
                first_ts = parse_ts(msg.get("timestamp") or msg.get("time"))
            if role == "user":
                turns.append(("user", content))
            elif role in ("assistant", "copilot", "model"):
                turns.append(("asst", content))
        return sid, None, turns, first_ts

    print(f"  ! {Path(path).name}: unrecognized format — open an issue with a redacted sample",
          file=sys.stderr)
    return None

# ---- write note -----------------------------------------------------------

def convert(path, manifest):
    """Convert one exported JSON file to a markdown note."""
    sid   = f"copilot_{Path(path).stem}"
    mtime = os.path.getmtime(path)
    rec   = manifest.get(sid)
    if rec and abs(rec.get("mtime", 0) - mtime) < 1:
        out = rec.get("out", "")
        if out == "" or Path(out).exists():
            return None

    parsed = parse_copilot_file(path)
    if not parsed:
        manifest[sid] = {"mtime": mtime, "out": ""}
        return None
    _, title, turns, first_ts = parsed

    if not turns:
        manifest[sid] = {"mtime": mtime, "out": ""}
        return None

    if SELECTIVE_MODE:
        all_text = " ".join(md for _, md in turns)
        if VAULT_TAG not in all_text:
            manifest[sid] = {"mtime": mtime, "out": "", "skipped": True}
            return None

    dt   = first_ts or datetime.fromtimestamp(mtime, tz=timezone.utc)
    date = dt.strftime("%Y-%m-%d")
    ym   = dt.strftime("%Y-%m")
    if not title:
        seed  = next((md for kind, md in turns if kind == "user"), turns[0][1])
        title = short(seed, 55)

    first_human = next((md for kind, md in turns if kind == "user"), "")
    proj = classify(title, first_human[:500])
    hub  = proj["hub"]

    outdir = CONV_DIR / ym
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"{date} - {sanitize(title)}.md"
    if out.exists() and (not rec or rec.get("out") != str(out)):
        out = outdir / f"{date} - {sanitize(title, 60)} ({sid[-8:]}).md"

    fm = ["---",
          f'title: "{title.replace(chr(34), chr(39))}"',
          f"date: {date}",
          f"project: {proj['label']}",
          "source: copilot"]
    if hub: fm.append(f'hub: "[[{hub}]]"')
    fm += [f"session: {sid}", f"turns: {len(turns)}",
           f"tags: [copilot/conversation, project/{proj['tag']}]", "---", ""]

    L = fm + [f"# {title}", "",
              f"**Project:** " + (f"[[{hub}]]" if hub else proj["label"]) +
              f"  ·  *{date}*  ·  *{len(turns)} turns*", ""]
    last = None
    for kind, md in turns:
        if kind == "user":
            if last != "user": L += ["", "## 👤 User", ""]
            L += [md, ""]; last = "user"
        elif kind == "asst":
            if last != "asst": L += ["", "## 🤖 Copilot", ""]
            L += [md, ""]; last = "asst"
    out.write_text("\n".join(L), encoding="utf-8")

    old = (rec or {}).get("out")
    if old and old != str(out) and Path(old).exists():
        try: Path(old).unlink()
        except Exception: pass
    manifest[sid] = {"mtime": mtime, "out": str(out),
                     "date": date, "project": proj["label"], "hub": hub}
    return out

# ---- vault setup ----------------------------------------------------------

def ensure_home():
    home = VAULT / "Home.md"
    if home.exists(): return
    home.write_text(
        "---\ntitle: Copilot Vault\ntags: [copilot/home]\n---\n\n"
        "# 🏠 Copilot Vault\n\n"
        "Your GitHub Copilot Chat conversations in Obsidian.\n\n"
        "- 💬 [[Conversations/_Index|Conversations index]]\n\n"
        "## Export & Refresh\n\n"
        "1. In VS Code: Copilot Chat panel → **...** → **Export Chat...** → save to "
        f"`{COPILOT_EXPORT_DIR}`\n"
        "2. Run: `python3 sync.py`\n",
        encoding="utf-8")

def build_index(manifest):
    groups = defaultdict(list)
    for sid, rec in manifest.items():
        if sid == "_format": continue
        out = rec.get("out")
        if not out or not Path(out).exists(): continue
        groups[rec.get("project", "Misc")].append(
            (rec.get("date", ""), Path(out).stem, rec.get("hub")))
    order = [p["label"] for p in PROJECTS] + ["Misc"]
    total = sum(len(v) for v in groups.values())
    L = ["---", "title: Conversations Index", "tags: [copilot/index]", "---", "",
         f"# 💬 Conversations ({total})", ""]
    for label in order:
        items = groups.get(label)
        if not items: continue
        hub = next((h for _, _, h in items if h), None)
        head = f"\n## {label} ({len(items)})"
        if hub: head += f"  ·  [[{hub}]]"
        L.append(head); L.append("")
        for _, stem, _ in sorted(items, reverse=True):
            L.append(f"- [[{stem}]]")
    (CONV_DIR / "_Index.md").write_text("\n".join(L), encoding="utf-8")

# ---- main -----------------------------------------------------------------

def main():
    export_dir = Path(COPILOT_EXPORT_DIR)
    if not export_dir.exists():
        print(f"COPILOT_EXPORT_DIR not found: {export_dir}", file=sys.stderr)
        print("Create it and export sessions from VS Code: Copilot Chat → ... → Export Chat",
              file=sys.stderr)
        sys.exit(1)

    CONV_DIR.mkdir(parents=True, exist_ok=True)
    ensure_home()
    manifest = load_manifest()
    if manifest.get("_format") != FORMAT:
        for m in CONV_DIR.rglob("*.md"):
            if m.name != "_Index.md":
                try: m.unlink()
                except Exception: pass
        manifest = {"_format": FORMAT}

    files = sorted(glob.glob(str(export_dir / "*.json")))
    if not files:
        print(f"No .json files in {export_dir}. Export from VS Code first.", file=sys.stderr)
        sys.exit(0)

    new = 0
    for p in files:
        try:
            if convert(p, manifest): new += 1
        except Exception as e:
            print(f"  ! {Path(p).name}: {e}", file=sys.stderr)

    save_manifest(manifest)
    build_index(manifest)

    total = len([m for m in CONV_DIR.rglob("*.md") if not m.name.startswith("_")])
    print(f"\nVault: {VAULT}")
    mode  = f" [selective: {VAULT_TAG}]" if SELECTIVE_MODE else ""
    print(f"Copilot: {len(files)} exports scanned | {new} new/updated{mode}")
    print(f"Total notes: {total}")

if __name__ == "__main__":
    main()
