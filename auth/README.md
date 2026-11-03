# Auth tutorial

A hand-built sign-up and login system, taught one process flow at a time.
Everything here is invented for the tutorial: no client code, no real data,
nothing tied to a live site.

Each episode runs the same four-step loop on one flow:

**Process Flow > Understand > Test > Fix**

| # | Episode | Status |
|---|---|---|
| 1 | Register | built (`episodes/01-register/`) |
| 2 | Verify email | built (`episodes/02-verify-email/`) |
| 3 | Login | built (`episodes/03-login/`) |
| 4 | Token refresh | built (`episodes/04-token-refresh/`) |
| 5 | Logout | built (`episodes/05-logout/`) |
| 6 | Password reset | built (`episodes/06-password-reset/`) |
| 7 | Two-factor (TOTP) | built (`episodes/07-two-factor/`) |
| 8 | Permissions | built (`episodes/08-permissions/`) |

## Skipping ahead (this is not the aim of the tutorial)

**Read this before you use it.** The point of this series is the loop: draw the
flow, trace it, test it, break it on purpose, fix it. Finished code teaches almost
none of that. Copying a working login you did not build leaves you holding code
you cannot debug, which is exactly where AI-built code goes wrong. Use the tags
below only if an episode defeats you and you need working code to carry on, or to
compare your own work against. Then go back and run the episode properly.

Each episode is one commit, and each has a tag:

| Tag | Code as it stands after |
|---|---|
| `episode-1-register` | 1 Register (with the Flow and Traces tools) |
| `episode-2-verify-email` | 2 Verify email |
| `episode-3-login` | 3 Login |
| `episode-4-token-refresh` | 4 Token refresh |
| `episode-5-logout` | 5 Logout |
| `episode-6-password-reset` | 6 Password reset |
| `episode-7-two-factor` | 7 Two-factor |
| `episode-8-permissions` | 8 Permissions: **everything**, the finished series |

To jump to one, put it on a new branch so your own work is never touched:

    git fetch --tags
    git switch -c skip-ahead episode-5-logout

Then start fresh, because each episode adds database tables and your old database
will not match:

    cd backend
    rm db.sqlite3
    python manage.py migrate
    cd ../frontend && npm install

To get back to your own work: `git switch main` (or whichever branch you were on).

## Layout

    backend/    Django (port 8200): accounts app, config, tracker (copied in)
    frontend/   Vue 3 + Vite (port 5273)
    episodes/   one folder per episode: notes, and the planted bug as a patch
    spadetrack.json   tells the code-map tool where things are

## First-time setup

1. Copy the tracker in (it is the general tool from the spadetrack repo, version
   with `dev_authorise`, i.e. commit 0f10a1b or later):

       cp -r /opt/websites/spadetrack/tracker backend/tracker

2. Backend:

       cd backend
       python -m venv .venv && source .venv/bin/activate
       pip install -r requirements.txt
       python manage.py migrate
       python manage.py runserver 8200

3. Frontend (second terminal):

       cd frontend
       npm install
       npm run dev        # http://localhost:5273

4. Tests: `cd backend && python manage.py test accounts`

## Seeing the flow and the trace

- Register at http://localhost:5273 with "Trace this request" ticked. The page
  shows a run id. In `backend/` run `python manage.py show_trace` to print the
  trace as a tree. The verification email appears in the Django terminal.
- Code map, then the flow in VS Code (see the next section).

## The process flow in the browser

With both servers running (`npm run dev` and `runserver 8200`), open
http://localhost:5273 and use the **Flow** and **Traces** tabs. They exist only
in development: a production build leaves them out.

Load the code map first (the two commands in the next section). Then register
with "Trace this request" ticked, open **Flow**, and pick that trace under
"Overlay trace": the boxes that ran light up. **Traces** shows the same request
as a call tree with the values at each decision.

## The process flow in VS Code

The map is built from the source, loaded into the tracker's database, then read
by the spadetrack VS Code extension. After any change to the code, run the two
commands again.

    # from the spadetrack folder
    python discover/discover.py --project-dir /home/websites/tutorial/auth
    # from tutorial/auth/backend (venv active)
    python manage.py load_graph ../.spadetrack/graph.json

In VS Code, open the `tutorial/auth` folder and set (Settings, search "spadetrack"):

| Setting | Value |
|---|---|
| spadetrack.baseUrl | `http://127.0.0.1:8200/api/tracker` |
| spadetrack.project | `auth-tutorial` |
| spadetrack.projectRoot | `/home/websites/tutorial/auth` |

Then run the command **Spadetrack: Open flow**. Register once with tracing on and
reopen it: the boxes that ran light up, and "Open in editor" jumps to the line.

## Rules for the code in this repo

- Traced functions sit at module level and take keyword-only arguments, so a
  trace shows every value by name.
- Only invented data: addresses at example.com, and the fake password
  `Tut0rial-Pass!`. Never screen-share a trace from a real person's account.
- Passwords, tokens and emails are redacted before anything is stored; every
  episode has a test that proves it.

## Development commands

Small commands in `backend/accounts/management/commands/`, run as
`python manage.py <name>` from `backend/`. Each one that changes data refuses
to run unless DEBUG is on, except `make_admin`, which is how a real server
gets its first admin.

| Command | What it is for |
|---|---|
| `show_trace [run id]` | print a saved trace as an indented story |
| `age_tokens --hours N` | make emailed links look older (episodes 2 and 6) |
| `expire_sessions` | expire every live refresh token (episode 4) |
| `clear_locks` | forget failed-login counts and locks (episode 3) |
| `show_code --email ...` | print the six digits an authenticator app would show (episode 7) |
| `forget_totp --email ...` | switch two-factor off for an account (episode 7) |
| `seed_demo` | put three demo accounts (an admin and two members) into a known state (episode 8) |
| `make_admin --email ...` | make an account an admin, or `--member` to undo it (episode 8) |

## Where the tests live

One file per episode, in `backend/accounts/`. (Django's default name `tests.py`
holds episode 1.) Run one file with `python manage.py test accounts.test_login`,
or everything with `python manage.py test accounts`; add `-v 2` to print every
test's name.

| File | Episode | Tests |
|---|---|---|
| `tests.py` | 1 Register | 19 |
| `test_verify.py` | 2 Verify email | 16 |
| `test_login.py` | 3 Login | 24 |
| `test_refresh.py` | 4 Token refresh | 20 |
| `test_logout.py` | 5 Logout | 21 |
| `test_reset.py` | 6 Password reset | 36 |
| `test_twofactor.py` | 7 Two-factor | 59 |
| `test_permissions.py` | 8 Permissions | 41 |

## Planted-bug patches belong to their episode

Each `planted_bug.patch` is written against the code as its own episode left it.
Later episodes change the same files (episode 7 changes `login.py`, for
instance), so an old patch may no longer apply to a later tree, and an old
episode's notes describe that episode's tests and trace, not today's. To follow
an episode, check out its tag (see "Skipping ahead" above); each episode is one commit.

## Known limits (read this before trusting any of it)

The aim of this series is a login you can fully understand, and a process for
building everything after it. It is not a finished, hardened product. In
particular it does not cover, or does only for development:

- **HTTPS.** Everything here runs over plain HTTP on your own machine. A real
  site must serve every request over HTTPS, or tokens and passwords can be read
  in transit.
- **Where the browser keeps tokens.** The tokens live in a page variable, so a
  reload logs you out. Keeping them in localStorage or a cookie each brings its
  own risks (script injection, cross-site requests). Pick deliberately.
- **Attacks from other sites or injected scripts** (cross-site request forgery
  and cross-site scripting) are not discussed in depth.
- **Limits by network address.** Lockout counts failures per email address
  typed. It does not limit how fast one machine can try many addresses.
- **Development-only settings**: a throw-away secret key, DEBUG on, SQLite,
  emails printed to the terminal, and a trace viewer that is open to this
  machine. The deployment episodes replace these step by step.

Each episode's notes call out the limits that matter to its own flow.
