# Run sheet: 02-spadetrack-hook, part 1 (backend)

Script: `script-1-backend.txt`. Folder: `standard-logon/backend/`.

## Before you start

1. VS Code: set **Editor: Auto Closing Quotes** to **never** (File > Preferences > Settings). Otherwise it adds a stray `"` after a typed quote.
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
