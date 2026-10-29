# Auth tutorial

A hand-built sign-up and login system, taught one process flow at a time.
Everything here is invented for the tutorial: no client code, no real data,
nothing tied to a live site.

Each episode runs the same four-step loop on one flow:

**Process Flow > Understand > Test > Fix**

| # | Episode | Status |
|---|---|---|
| 1 | Register | built (`episodes/01-register/`) |
| 2 | Verify email | next |
| 3 | Login | |
| 4 | Token refresh | |
| 5 | Logout | |
| 6 | Password reset | |
| 7 | Two-factor (TOTP) | |
| 8 | Permissions | |

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
- Code map (from the spadetrack folder):

      python discover/discover.py --project-dir /path/to/tutorial/auth
      cd /path/to/tutorial/auth/backend
      python manage.py load_graph ../.spadetrack/graph.json

## Rules for the code in this repo

- Traced functions sit at module level and take keyword-only arguments, so a
  trace shows every value by name.
- Only invented data: addresses at example.com, and the fake password
  `Tut0rial-Pass!`. Never screen-share a trace from a real person's account.
- Passwords, tokens and emails are redacted before anything is stored; every
  episode has a test that proves it.
