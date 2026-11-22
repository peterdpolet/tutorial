# Run sheet: 02-spadetrack-hook

Two scripts: part 1 (`script-1-backend.txt`, in `standard-logon/backend/`) and part 2 (`script-2-frontend.txt`, further down). The setup and the way a block lands are the same for both.

# Part 1: backend

## Before you start

1. VS Code: set **Editor: Auto Closing Quotes** to **never** (File > Preferences > Settings). Otherwise it adds a stray `"` after a typed quote. For part 2 also set **Editor: Auto Closing Brackets** to **never**, or `{ }` and `[ ]` over several lines get a duplicate closer.
2. VS Code: turn Caps Lock off, and leave Tab Moves Focus off (Ctrl+M toggles it).
3. Start typer from this folder with the separator switched off. Without the flag it adds a blank line before every block:

```
python3 /home/utilities/typer/typer.py --no-block-separator script-1-backend.txt
```

4. Save each file with Ctrl+S as you finish with it. Typing does not save.

## How it works

How a block lands: put the cursor at the END of the anchor line (click the line, press End), then tap Right Ctrl. Typer opens a new line below and types the block there. A block that starts with a blank line (`[[break]]`) leaves one empty line before its text.

The very first block is the one exception: press Enter once yourself, then Backspace once (to remove VS Code's auto-indent), then tap. Typer only opens the new line, and clears the auto-indent, for every block after the first.

| # | File | Anchor line (end of) | Types |
| --- | --- | --- | --- |
| 1 | `config/settings.py` | `"core",     # the shared service layer ...` | the `"tracker",` app (press Enter first) |
| 2 | `config/settings.py` | `"django.contrib.auth.middleware.AuthenticationMiddleware",` | comment and `TrackerMiddleware` |
| 3 | `config/settings.py` | `FRONTEND_URL = env(...)` | the whole tracker settings section |
| 4 | `config/urls.py` | `path("api/", include("core.urls")),` | the `api/tracker/` route |
| 5 | `.env.example` | `# DJANGO_HTTPS=1` | `TRACKER_ENABLED=1` with its comment |
| 6 | `core/services/health.py` | the empty line straight after `from django.db import ...` | the tracker import |
| 7 | `core/services/health.py` | the empty line straight above `def check_health():` | `@traced("Check health")` |
| 8 | `core/services/health.py` | `rather than raising, so the caller decides how to present that.` | the docstring paragraph |
| 9 | `core/services/health.py` | `database = "unavailable"` | the `checkpoint(...)` line |
| 10 | `core/views.py` | `from core.services import health` | the tracker import |
| 11 | `core/views.py` | `@require_GET` | `@traced("Health view")` |
| 12 | `core/views.py` | `status_code = 200 if result["status"] == "ok" else 503` | the `checkpoint(...)` line |

Reset: put the files back as at tag `standard-logon-1-template` (or rehearse in a clean copy).
After: save the five files, then check them against the committed versions. Only `finished` means a perfect run:

```
for f in config/settings.py config/urls.py .env.example core/services/health.py core/views.py; do diff /home/websites/rehearsal/standard-logon/backend/$f /home/websites/tutorial_final/standard-logon/backend/$f; done; echo finished
```

(Rehearsal copy: `git worktree add ../rehearsal standard-logon-1-template`. Remove it afterwards with `git worktree remove --force ../rehearsal`.)

# Part 2: front end and the code map

Script: `script-2-frontend.txt` (6 blocks). Folder: `standard-logon/` (the project root, one level above `backend` and `frontend`).

Start typer the same way, from this folder:

```
python3 /home/utilities/typer/typer.py --no-block-separator script-2-frontend.txt
```

Order of play. Steps marked TERMINAL are typed by you in a terminal, not by typer; typer simply waits for the next tap.

| Step | Where | What |
| --- | --- | --- |
| 1 | `standard-logon/spadetrack.json` | Create an EMPTY new file here and leave the cursor in it. Tap for block 1 (the JSON). No Enter or Backspace first: the file is empty. Save. |
| 2 | `frontend/src/api/client.js` | Click the line `export default axios.create({ baseURL: '/api' })`, press Home then Shift+End to select it. Tap: block 2 types the old line back in red (`//- ...`). |
| 3 | same line | Select it again (Home, Shift+End). Do not press Escape or take a screenshot in between. Tap: block 3 types `const client = ...` over it. |
| 4 | `frontend/src/api/client.js` | The cursor is at the end of `const client = ...`. Tap: block 4 adds `toError()` and the new `export default client`. Save. |
| 5 | TERMINAL, in `standard-logon/frontend` | `S=/opt/websites/spadetrack/sample/frontend/src` |
| 6 | TERMINAL | `cp $S/api/graph.js $S/api/traces.js src/api/ && cp $S/FlowView.vue src/views/FlowView.vue` |
| 7 | TERMINAL | `sed -i "s#@/api/axios#@/api/client.js#" src/api/graph.js src/api/traces.js` (the sample imports its client under another name) |
| 8 | `frontend/src/router.js` | Click the end of `import HealthView from '@/views/HealthView.vue'`. Tap: block 5 adds the `FlowView` import. |
| 9 | `frontend/src/router.js` | Click the end of the `{ path: '/health', ... }` line. Tap: block 6 adds the `/flow` route. Save. |
| 10 | TERMINAL, in `standard-logon/frontend` | `npm install @dagrejs/dagre@^1.1.8` (the version number matters: plain `npm install @dagrejs/dagre` fetches version 3, and `FlowView.vue` is written for 1.x). In the rehearsal add `--package-lock-only`: it edits `package.json` and the lock file without downloading everything. |

Check after a rehearsal (paste as one line; only `finished` means a perfect run):

```
for f in spadetrack.json frontend/package.json frontend/src/api/client.js frontend/src/api/graph.js frontend/src/api/traces.js frontend/src/views/FlowView.vue frontend/src/router.js; do diff /home/websites/rehearsal/standard-logon/$f /home/websites/tutorial_final/standard-logon/$f; done; echo finished
```
