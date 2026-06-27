# obsidian-copilot-sync

Convert your GitHub Copilot Chat conversations into a searchable, linked knowledge base in Obsidian. Zero external dependencies — pure Python, reads exported JSON files from VS Code.

---

## What it does

- Reads exported Copilot Chat JSON files from a folder you point it at
- Converts each session to a markdown note organized by project and date
- Classifies by project using keyword scoring (title 3×, body 1×) — no API calls
- Incremental: only new or changed exports are written on each run
- Optional selective sync — only save sessions you tag with `#vault`

---

## Quick start

### 1. Export from VS Code

In VS Code, open the Copilot Chat panel → click `...` → **Export Chat...** → save as `.json` to a folder (e.g. `~/copilot-exports`).

Do this for each session you want to sync.

### 2. Clone

```bash
git clone https://github.com/arya51-ai/obsidian-copilot-sync.git
cd obsidian-copilot-sync
```

### 3. Configure

Edit the top of `sync.py`:

```python
VAULT              = Path.home() / "MyVault"        # your Obsidian vault
COPILOT_EXPORT_DIR = Path.home() / "copilot-exports" # folder of exported .json files
```

### 4. Set up your projects

```python
PROJECTS = [
    {"label": "My App", "hub": None, "tag": "myapp",
     "kw": ["my app", "backend", "auth"]},
    {"label": "Work", "hub": None, "tag": "work",
     "kw": ["standup", "sprint", "ticket"]},
]
```

- `label` — display name in the vault
- `hub` — optional memory note to link to (filename without `.md`), or `None`
- `tag` — Obsidian tag for filtering
- `kw` — keywords for auto-classification (title match = 3×, body = 1×)

### 5. Run

```bash
python3 sync.py
```

```
Vault: /Users/you/MyVault
Copilot: 12 exports scanned | 3 new/updated
Total notes: 12
```

---

## Auto-sync

Drop new exports into `COPILOT_EXPORT_DIR` and run sync — or put it on a cron/launchd schedule to pick up new files automatically.

### macOS (launchd)

```bash
cat > ~/Library/LaunchAgents/com.obsidian.copilot-sync.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.obsidian.copilot-sync</string>
    <key>ProgramArguments</key>
    <array>
        <string>python3</string>
        <string>/path/to/obsidian-copilot-sync/sync.py</string>
    </array>
    <key>StartInterval</key>
    <integer>1800</integer>
    <key>StandardErrorPath</key>
    <string>/tmp/copilot-vault-sync.err</string>
</dict>
</plist>
EOF
launchctl load ~/Library/LaunchAgents/com.obsidian.copilot-sync.plist
```

### Linux / cron

```bash
*/30 * * * * python3 /path/to/obsidian-copilot-sync/sync.py >> ~/.copilot-vault-sync.log 2>&1
```

---

## Selective sync

Only want to keep sessions worth saving? Include `#vault` anywhere in a conversation:

```python
# sync.py
SELECTIVE_MODE = True
VAULT_TAG      = "#vault"
```

Exports without the tag are tracked (so they aren't re-checked) but no note is written.

---

## Supported export formats

The reader handles two formats VS Code produces:

**Format 1 — VS Code Chat export** (`requests` array):
```json
{
  "sessionId": "abc123",
  "title": "Fix auth bug",
  "requests": [
    {
      "message": {"text": "why is my JWT expiring early?"},
      "response": [{"value": "The issue is likely..."}]
    }
  ]
}
```

**Format 2 — raw message array** (`role`/`content` pairs):
```json
[
  {"role": "user", "content": "why is my JWT expiring early?"},
  {"role": "assistant", "content": "The issue is likely..."}
]
```

If your export looks different, open an issue with a redacted sample.

---

## Vault structure

```
MyVault/
├── Home.md
├── Conversations/
│   ├── _Index.md
│   ├── 2025-06/
│   │   └── 2025-06-15 - Fix auth bug.md
│   └── 2025-07/
│       └── 2025-07-01 - Refactor API layer.md
└── .sync/
    └── manifest.json
```

---

## Troubleshooting

**"No .json files in COPILOT_EXPORT_DIR"**
Make sure you exported from VS Code as `.json` (not markdown). The export button is in the `...` menu at the top of the Copilot Chat panel.

**"Unrecognized format"**
Open an issue and paste a redacted sample of the JSON. The reader handles two known formats — if Copilot changed theirs, we'll add support.

---

## FAQ

**Does it sync to Copilot, or only from Copilot?**
One-way only: Copilot → Obsidian.

**Does it work with Copilot in JetBrains / other IDEs?**
Not yet — the export format varies. If you can share a sample export from JetBrains, open an issue.

**Can I use this alongside obsidian-vault-sync (Claude)?**
Yes. Point both at the same Obsidian vault. Sessions get tagged separately (`claude/conversation` vs `copilot/conversation`) so they don't conflict.

---

## License

MIT
