# Running log: Standard logon

Decisions and commands, in order, so work can be picked up after a pause.

## 10 Nov 2026: chunk 1, the template

### Decisions

1. New work lives in `standard-logon/`. `auth/` and its eight episode tags are untouched.
2. Fresh environment-driven `settings.py`; nothing copied from `auth/accounts`.
3. Django 5.2 LTS, pinned exactly in `backend/requirements.txt` (`pip freeze`). The old series only said `Django>=5.2`.
4. One virtualenv at `standard-logon/.venv`, ignored by git.
5. Ports 5274 (Vite) and 8201 (Django), so this project can run beside `auth/` (5273 and 8200).
6. Secure by default: `DEBUG` off, no built-in secret key. Postgres is chosen by setting `DB_NAME`. HTTPS-only cookies sit behind their own `DJANGO_HTTPS` switch.
7. Business logic in `core/services/`; views are thin. Proved with the health check.
8. Menu driven by the route list in `router.js`; one `StubView` for pages not built yet.
9. `vue-router` added (the old series switched views by hand).
10. Work in small chunks: finish, tag, script and record each one before starting the next.
11. Positioning: lead with security and the end-to-end path (secure logon to secure server in one series), not with "deploy Django on DigitalOcean", which is crowded. See the deployment search below.
12. Deployment sequence: manual to the server over SSH (episode 3), then deploy via GitHub (episode 4), then deploy via GitHub with Docker (episode 5). Whether episode 5 builds images on the server or in GitHub Actions is decided when we get there.
13. Launch plan: release the Django + Vue logon series with the three deployment episodes, watch uptake, and say that HTMX and React versions will follow. HTMX can be promised more firmly (after checking spadetrack can trace HTMX requests); React stays conditional on interest, as it needs learning first.

### Commits

| Commit | What |
| --- | --- |
| `e495dfa` | Django 5.2 LTS skeleton, environment-driven settings, pinned requirements |
| `8860af7` | `core` app: health service, thin view, `/api/health/`, 6 tests |
| `21fb065` | Vue 3 template: menu from the route list, stubs, Health page |

### Checked

- `manage.py check` clean; `migrate` applied the built-in apps to SQLite.
- 6 tests, all passing:
  - `HealthServiceTests`: `test_reports_ok_when_the_database_answers`, `test_reports_degraded_when_the_database_is_down`
  - `HealthViewTests`: `test_returns_200_and_the_service_result`, `test_returns_503_when_the_service_reports_degraded`, `test_calls_the_service_exactly_once`, `test_rejects_post`
- Browser: http://localhost:5274 shows the menu; Health shows `ok` / `ok` through the Vite proxy to Django.

### Still to do for this chunk

- Optional tracker (spadetrack) in the template. Check how `auth/backend/tracker` is copied in and what `auth/spadetrack.json` does.
- Style the in-page links (they use the browser default; the menu links are styled).

### YouTube gap search (10 Nov 2026)

Seven searches, restricted to youtube.com, via a web search tool (not YouTube's own search). Titles and descriptions only: no view counts, no transcripts, so absence from the results is not proof of absence.

- Nothing found that combines a Django back end, all three front ends (Vue, HTMX, React) and login. The nearest are generic "HTMX vs React vs Vue" opinion videos with no shared back end or login, and a DjangoCon 2022 talk on migrating one product from React to htmx.
- Django + React JWT login is crowded: several full series, mostly 700 to 1500+ days old. Django + Vue auth has a few (one session-based "no tokens, no DRF", one Djoser JWT). Django + HTMX + allauth has a couple of starter-style videos.
- 2FA/TOTP results were mostly django-two-factor and the Django admin, 755 to 2741 days old. Nothing found on allauth.mfa, TOTP behind a SPA, or JWT + TOTP.
- Session vs JWT comparisons exist but are generic, not Django-specific.
- Reading: the gap is strongest at (a) TOTP/MFA with the current standard tools and (b) the same login across front ends with one shared back end. The React slot is the most crowded, which supports deciding on release 3 only after the Vue release.
- To do by hand before relying on it: search YouTube itself sorted by upload date, and note view counts for the top Django + Vue and Django + React auth videos.

### YouTube deployment and security search (10 Nov 2026)

Four more youtube.com searches, same method and same limits (titles only, no view counts). This tested the idea that "dev to deploy with security as the focus, in one place" is less well covered.

- Deploying Django to a DigitalOcean droplet with Nginx, Gunicorn and HTTPS is crowded, including recent videos and a long free course covering server creation through Let's Encrypt.
- Bundled deployment with CI/CD exists, including recent Django + React videos (about 135 to 280 days old).
- The security pieces exist separately: `check --deploy` checklists (mostly 4 to 6 years old), a generic Linux hardening checklist (about 4 months old), and stand-alone videos on Docker bypassing UFW.
- Not found: one series that follows a single app from login through deployment with security as the thread, on Vue. Docker/UFW appears only as stand-alone "fix it" videos, not as part of a deployment series.
- Reading: the opening is the integrated, security-led path, not deployment on its own. Titles and the series introduction should lead with security and the end-to-end angle.

### Before filming

- Confirm the JWT + TOTP mechanism against current allauth docs, and say on camera that it is an assembled pattern, not a library default.

### Open questions

Domain for HTTPS; where the front end is built; real email for resets; when to move to Postgres; filming order.

## 17 to 22 Nov 2026: the spadetrack hook and the first EPC (in progress)

Next chunk: spadetrack hook, then the first EPC diagram (the health-check flow, Vue to Django to service to database). The hook, the code map, the Vue Flow view, the EPC and both typer scripts are done and pushed to `main`. Still to do: a last dry run in the real recording setup, then tag and push the tag.

### Decisions

1. **The repo folder moved** from `/home/websites/tutorial` to `/home/websites/tutorial_final`. Same GitHub repo and `origin`. Steps: stop Django and Vite, `mv -T tutorial tutorial_final`, delete and rebuild `standard-logon/.venv` (its scripts hardcode the old path), then `manage.py check` and the tests. `git grep "websites/tutorial"` found only two lines, both in `auth/README.md` (lines 114 and 124). Left alone: `auth/` is finished and tagged.
2. **The tracker is taken from `auth/backend/tracker`, not from `/opt/websites/spadetrack/tracker`.** `diff -rq` showed one difference, `redaction.py`. The `auth` copy (2 Nov) also redacts `"otp"` and `"recovery"`; the stand-alone copy (29 Oct) does not. The TOTP chunk needs that. Parked: back-port those two names to the stand-alone `spadetrack`.
3. **`policy.py` needed no change.** It is generic and is configured entirely by settings. The tracker reads exactly five settings: `TRACKER_ENABLED`, `TRACKER_AUTHORISE`, `TRACKER_DEV_ANON_PREFIXES`, `TRACKER_DEV_ALLOW_VIEWER`, `TRACKER_DEV_LOOPBACK_ONLY`. `TRACKER_AUTHORISE` takes a dotted-path string (copied from the working `auth` settings).
4. **Tracker settings in `standard-logon`:**
   - `TRACKER_ENABLED` comes from the environment and is off by default (the old series tied it to `DEBUG`). `.env.example` and the local `.env` set `TRACKER_ENABLED=1` for development.
   - `TRACKER_AUTHORISE = "tracker.policy.dev_authorise"`. With `DEBUG` off it behaves like the staff-only default, so it is safe to name on every server.
   - `TRACKER_DEV_ANON_PREFIXES = ["/api/health/"]`: nobody logs in at this stage.
   - `TRACKER_DEV_ALLOW_VIEWER = DEBUG and "test" not in sys.argv`. Held shut while tests run: three of the tracker's own tests expect the viewer to be closed unless a test opens it, and failed when `.env` had `DEBUG` on. Same pattern as the fast password hasher in `settings.py`.
5. **Marking the health check.** `@traced("Check health")` on `check_health` with a `checkpoint("database_checked", database=...)`; `@traced("Health view")` on `health_view` with a `checkpoint("http_status_chosen", status=..., status_code=...)`. `@require_GET` stays outermost. The architecture rule holds: rules in the service, a thin view.
6. **Showing a change on camera.** Lines starting `#-` or `//-` show red (Highlight extension, `.vscode/settings.json` in the repo root, ignored by git). The change is two `[[overwrite]]` blocks: first the old line typed back as `#- ...` over the selected line, then the new line typed over the red one. `#-` (like the minus on a removed line in a git diff) was chosen over a bare `#` because every ordinary comment, including narration and the comments already in files like `settings.py`, would otherwise turn red. The first form, `# DEL`, still works.
7. **The code map describes the project in `standard-logon/spadetrack.json`:** project `standard-logon`, backend `backend`, apps `["core"]`, frontend `frontend`, API client `client`. `discover.py init` guessed these; `discover.py` then writes `.spadetrack/graph.json` (9 entities, 4 relations) and `manage.py load_graph` loads it into the database.
8. **`.spadetrack/` is git-ignored** (`standard-logon/.gitignore`), because `discover.py` rebuilds it.
9. **The Flow view** is the sample's `FlowView.vue` unchanged, plus `api/graph.js` and `api/traces.js`, a `/flow` route labelled Flow, and `@dagrejs/dagre`. `api/client.js` now exports `toError()`, which keeps the status, the server's detail and the `X-Tracker-Run` id. It draws the code map and overlays a stored trace, so a traced health check lights up the Health view and Check health boxes.
10. **The first EPC** (health check): events are hexagons, functions are rounded boxes, XOR is an oval. Drawn on a Whiteboard, with the real code names (`health_view`, `check_health`) as a second line. Proposed home in the repo: a plain `.svg` beside the typer script in `standard-logon/episodes/NN-name/` (not decided).
11. **Typer scripts live in `standard-logon/episodes/02-spadetrack-hook/`:** `script-1-backend.txt` (12 blocks: tracker settings, middleware, URLs, `.env.example`, and the traced marks on the health service and view), `script-2-frontend.txt` (6 blocks: `spadetrack.json` typed into a new file, the `client.js` change with a red-line replacement, the `FlowView` import and `/flow` route) and `RUNSHEET.md` (where to put the cursor for each block, the terminal steps between them, and the check command). The new Vue files are copied from `/opt/websites/spadetrack/sample/frontend/src`, with the import in `graph.js` and `traces.js` changed to `@/api/client.js` by `sed`. `package.json` changes through `npm install @dagrejs/dagre@^1.1.8`.
12. **Pin the dagre version.** Plain `npm install @dagrejs/dagre` now fetches version 3, and `FlowView.vue` is written for 1.x. The rehearsal showed `package.json` differing from the commit.
13. **The EPC is `epc-health-check.svg`** in the same episode folder: a plain file, with the layout of the Whiteboard drawing. Events are hexagons, functions are rounded boxes, XOR is an oval.

### Commits

| Commit | What |
| --- | --- |
| `a4af601` | Add the spadetrack tracker and mark the health check for tracing |
| `db56ecc` | Update LOG.md for the spadetrack hook |
| `25248f4` | Add code map and Flow view for the health check |
| `2655d22` | Ignore the generated spadetrack code map |
| `2ac9a2f` | Update LOG.md for the code map, Flow view and first EPC |
| `2db6452` | Add the typer script for the backend half of the spadetrack hook |
| `f604bc0` | Add the typer script for the front half of the spadetrack hook |
| `0fbfbb2` | Add the health-check EPC as an SVG |

`main` was pushed at `2db6452` and `f604bc0` (22 Nov). Not tagged yet.

### Checked

- `manage.py check` clean after adding the app, middleware and URLs.
- `showmigrations tracker`: `0001_initial` and `0002_code_graph` were unapplied; `migrate` applied both (the built-in apps were already migrated).
- 64 tests, all passing: 6 core health tests (as above) and 58 tracker tests:
  - `AnonymousRegisterTraceTests` (7), `ArmedTriggerTests` (6), `DevAuthorisePolicyTests` (13), `GraphApiTests` (4), `GraphLoadTests` (7), `GraphQueryTests` (6), `MiddlewareTests` (9), `PolicyTests` (1), `PruneTests` (1), `ReadApiTests` (4).
- First run had 3 failures, all "the viewer should be closed": `test_viewer_is_closed_unless_switched_on`, `test_never_opens_the_trace_viewer_itself`, `test_anonymous_cannot_read_traces`. Cause: our settings turned the viewer door on whenever `.env` had `DEBUG` on. Fixed as in decision 4.
- A traced request: `curl` with `X-Tracker: 1` against `/api/health/` returned the `X-Tracker-Run` header, and the stored trace showed Health view > Check health with both checkpoint values.
- The Flow page in the browser: the code map renders, and the dropdown overlay of the stored trace lights up the traced boxes.
- Both typer scripts, rehearsed in a clean `git worktree` of `standard-logon-1-template`: every typed file was identical to the committed one (`diff` printed nothing). Part 1: `settings.py`, `urls.py`, `.env.example`, `health.py`, `views.py`. Part 2: `spadetrack.json`, `client.js`, `router.js`, `graph.js`, `traces.js`, `FlowView.vue`, `package.json`.
- `diff -rq` between the two tracker copies after copying: identical apart from `__pycache__` (deliberately removed from the copy).

### Commands, in order

1. `diff -rq auth/backend/tracker /opt/websites/spadetrack/tracker -x __pycache__ -x '*.pyc'`, then `diff -u` on `redaction.py`.
2. Stop Django and Vite; `git status --short`; `cd /home/websites && mv -T tutorial tutorial_final`.
3. In `standard-logon`: `rm -rf .venv && python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt`.
4. In `backend`: `manage.py check` and `manage.py test -v 2`.
5. `git grep -n "websites/tutorial"`.
6. `cp -r auth/backend/tracker standard-logon/backend/tracker`, then remove `__pycache__` from the copy; `diff -rq` to compare.
7. `grep -rho "TRACKER_[A-Z_]*" ... | sort | uniq -c` to list the settings the tracker reads.
8. Drop-in `settings.py` and `urls.py`, then `.env.example`, `health.py`, `views.py` (each moved from `~/Downloads`, then checked with `grep`).
9. `manage.py showmigrations tracker`, then `manage.py migrate`.
10. `printf '\nTRACKER_ENABLED=1\n' >> .env` (local only).
11. `git add standard-logon`, `git commit -F ~/Downloads/commit-msg-tracker.txt`.
12. `runserver`, then `curl -i -H "X-Tracker: 1" .../api/health/` and a read of `/api/tracker/runs/<id>/`.
13. `discover.py init`, then `discover.py`, then `manage.py load_graph`.
14. In `frontend`: `npm install @dagrejs/dagre`; drop-in `client.js`, `graph.js`, `traces.js`, `router.js`, `FlowView.vue`; `npm run dev`.
15. Commits `25248f4` (`git add` with the eight files named, then `git commit -F commit-msg-flow.txt`) and `2655d22` (`.gitignore`, using `git commit -m` with `--trailer` for the attribution lines).

### Tooling notes (VS Code and typer)

- **Red lines.** The Highlight extension matches the pattern against the whole document, so `^` and `$` only match at the start and end of the file. The patterns avoid them and use a lookbehind for "start of a line": `(?<![^\n])[ \t]*(?:#|//)-[^\n]*` for `#-` and `//-` (19 Nov), and `(?<![^\n])[ \t]*(?:#|//|<!--)[ \t]*DEL\b[^\n]*` for the earlier `# DEL` form. Both use `isWholeLine`, so they work on any line. The `DEL` pattern ignores case. A background colour was tried and dropped: red text only.
- **Typer: `[[overwrite]]` did not replace a selection** unless it was the very first block of the run. Typer sent Escape, Enter and Shift+Home before every line except the first of the run. Escape cancels a selection in VS Code. Fix in `/home/utilities/typer/typer.py`, line 608 (the `type_block` call): `is_first_block=not first_type_done or block["tag"] == "overwrite"` and `add_separator=args.block_separator and block["tag"] != "overwrite"`. Backups: `typer.py.bak` (before the separator edit) and `typer.py.bak2` (before the second edit). The `test_*.py` files in the typer folder are sample input scripts, not automated tests.
- **Script rules.** A blank line ends a block; use `[[break]]` for a blank line inside one. `[[narrate]]` text is typed into the file, so never put instructions to the presenter in a script.
- **Presenter gotchas.** Tab Moves Focus mode (Ctrl+M toggles it; the status bar shows it). Caps Lock inverts typed case. A screenshot between selecting and tapping clears the selection. If the hash key gives a backslash, typer left its layout switched: `pkill -INT -f typer.py` restores `gb`.

### Typer scripts for changing existing files (how it works)

- **Method.** Turn each run of `+` lines in `git diff <tag> HEAD -- <files>` into one `[[code]]` block. Each block has an anchor line: put the cursor at the end of it and tap Right Ctrl; typer opens a new line below and types the block there. A leading `[[break]]` leaves a blank line before the text; a blank line inside a block is also `[[break]]`. A changed line is the red-line pair of `[[overwrite]]` blocks (`#-` or `//-`). No `[[narrate]]` blocks in a script that is checked, because they are typed into the file.
- **Run with `--no-block-separator`.** Without it typer adds a blank line before every block.
- **First block is special.** Typer opens the new line and clears the auto-indent for every block except the first, so for the first block press Enter then Backspace by hand (not needed in an empty new file).
- **VS Code settings:** Editor: Auto Closing Quotes and Auto Closing Brackets both set to `never`. The quotes setting fixed a stray `"` at the end of one line.
- **Focus.** Typer types into whichever window has focus. Click into the editor before every tap, and touch nothing until the terminal prints `done`. Clicking the Claude chat mid-block sent half the text there; run typer in a separate terminal window, not VS Code's own.
- **Saving.** Typing does not save: Ctrl+S on each file before running the check.
- **Rehearsal.** `git worktree add ../rehearsal <tag>`, type into that, then `diff` each file against the committed one; remove it with `git worktree remove --force ../rehearsal`. The worktree has no `.vscode/settings.json` (git-ignored), so the red lines do not show there; they will in the real folder.
- **Git pager.** `git diff` opened `less`, which ignores Ctrl+C. Fixed with `git config --global core.pager cat`.
- **Downloads.** Files sometimes take a moment to arrive: `ls -lt ~/Downloads | head` shows the newest.

### Still to do for this chunk

- A last dry run of both scripts in the real recording folder (for the red `//-` line), then tag `standard-logon-2-spadetrack` and push the tag.
- Check that spadetrack can trace HTMX requests before promising it on camera.
- Optional: a "trace this action" toggle on the Health page so the Vue boxes light up.
- Style the in-page links (carried over from chunk 1).
- Parked: back-port the `otp` / `recovery` redaction to `/opt/websites/spadetrack`; add a one-line note to `auth/README.md` about the moved path if wanted.
