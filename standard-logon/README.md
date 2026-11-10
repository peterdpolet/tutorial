# Standard logon

A tutorial series on logging in with standard tools, built on one shared
template: Django 5.2 (LTS) on the back end, Vue 3 with Vite on the front end.

The hand-built series in `../auth/` shows how login works underneath. This
series uses the standard libraries instead.

## Status

Chunk 1, the template, is done: a main menu, stub pages, a service layer and
a health check that proves the front end and back end are connected. Login
episodes come next. See `LOG.md` for the running log of decisions.

## Run it

You need Python 3.12 and Node 24 (what the series is recorded on).

Back end:

    python3 -m venv .venv
    .venv/bin/pip install -r backend/requirements.txt
    cp backend/.env.example backend/.env
    cd backend
    ../.venv/bin/python manage.py migrate
    ../.venv/bin/python manage.py runserver 8201

Front end, in a second terminal:

    cd frontend
    npm install
    npm run dev

Open http://localhost:5274 and click Health. It should say `ok` for the status
and the database.

Tests:

    cd backend
    ../.venv/bin/python manage.py test -v 2

## Ports

| What | Port | Notes |
| --- | --- | --- |
| Vue dev server (Vite) | 5274 | `strictPort`: fails rather than moving to another port |
| Django dev server | 8201 | Vite forwards `/api` here, so there is no CORS to set up |

## Layout

    backend/
      config/            settings (read from the environment), urls, wsgi, asgi
      core/
        services/        the rules: plain Python, no HTTP
        views.py         thin: call a service, turn the result into a response
        tests/
    frontend/
      src/
        router.js        the one list of pages; the main menu is built from it
        views/           HomeView, HealthView, and StubView for pages not built yet
        api/client.js    axios, with /api as its base URL

## The architecture rule

Business logic lives in `core/services/`. Views, whether JSON today or HTMX
later, call a service and hold no rules of their own. A second front end then
needs new views and templates only, with no new back-end rules.

## Settings and secrets

`backend/config/settings.py` reads everything that differs between machines
from the environment, or from `backend/.env` while developing. The defaults
are secure: `DEBUG` is off unless `DJANGO_DEBUG=1`, and without
`DJANGO_SECRET_KEY` Django refuses to start (except in debug mode). `.env` is
ignored by git; `.env.example` is committed. See `backend/.env.example` for
every variable.
