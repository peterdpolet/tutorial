# tracker: runtime tracing for Django

Record the journey of ONE real request through your code (which functions ran, in what
order, what decisions they made and the values behind them) and read it back as a tree in
the browser. Built for the Spadework tutorials; usable in any Django project.

Tracing is **off by default**, switched on **per request**, and only for **authorised
users**. What is recorded passes through a **redaction policy** first.

## What is in this folder

| File | Job |
|---|---|
| `tracker.py` | The capture mechanism. No Django import. `@traced`, `checkpoint()`, `start_trace()`. |
| `redaction.py` | What may be recorded. Names and value shapes that are hidden before storage. |
| `models.py` | `RuntimeEvent`, `TraceRun` (traces) and `CodeEntity`, `CodeRelation` (code map). |
| `persistence.py`, `persistence_django.py` | Flatten a trace into rows and bulk-insert it. |
| `middleware.py` | Decides whether a request is traced, ends the trace, saves it once. |
| `trigger.py` | The "arm my next request" one-shot (superuser) and its state. |
| `policy.py` | The default authorise rule: logged-in staff. |
| `persist.py` | Saves a finished trace; rebuilds one as a nested tree. |
| `views.py`, `urls.py` | Read API: `runs/` and `runs/<id>/`. |
| `arm_views.py` | The arm endpoint view. **Not wired into `urls.py` yet.** |
| `management/commands/prune_traces.py` | Retention: delete old traces. |
| `graph.py`, `management/commands/load_graph.py` | The static code map: load, flow, route matching. |
| `tests.py` | Tests for everything Django-side. |

## Mark the code you want to see

```python
from tracker.tracker import traced, checkpoint

class Quote(models.Model):
    @traced("Quote.convert_to_po")           # this function becomes a node in the tree
    def convert_to_po(self):
        ...
        checkpoint("approval_check", total=total, threshold=limit, needs_approval=needed)
```

* `@traced("Name")` records the call: inputs, return value (or the error), timing, and who
  it called. The first positional argument (`self`/`cls`) is left out.
* **Module-level traced functions should take keyword-only arguments** (`def f(*, a, b)`),
  otherwise the first argument is skipped as if it were `self`.
* `checkpoint("label", name=value, ...)` records the values behind a DECISION, inside a
  traced function. Only what you mark is recorded; nothing is captured automatically.
* Untraced requests pay almost nothing: one context-variable read per call.

## Install in a Django project

1. Add `"tracker"` to `INSTALLED_APPS`, run `python manage.py migrate`.
2. Add `"tracker.middleware.TrackerMiddleware"` to `MIDDLEWARE`, **after** the
   authentication middleware.
3. Add `path("api/tracker/", include("tracker.urls"))` to your URLs.
4. Set `TRACKER_ENABLED = True` (it is False unless you say so).

## When is a request traced?

All of these must hold:

1. `TRACKER_ENABLED` is True.
2. `TRACKER_AUTHORISE(request)` is True. Default: a logged-in staff user. If the function
   raises, the answer is "no".
3. The request ASKS, either by sending the header `X-Tracker: 1`, or because its user
   **armed** their next request (`trigger.py`, superuser only, one-shot, expires after 5
   minutes).

A traced response carries `X-Tracker-Run: <id>`. A request where no traced code ran saves
nothing. A failure while saving is logged and never breaks the request.

| Setting | Default | Meaning |
|---|---|---|
| `TRACKER_ENABLED` | `False` | Master switch. |
| `TRACKER_AUTHORISE` | `"tracker.policy.default_authorise"` | Dotted path to `f(request) -> bool`. Used for tracing AND for reading traces. |

The sample project sets `TRACKER_AUTHORISE` to an allow-everyone function because it has no
logins. **Never do that in a real project.**

## Read API

* `GET runs/` : the 50 most recent runs (summaries).
* `GET runs/<uuid>/` : one run as a nested tree: `calls[]`, each with `name`, `args`,
  `returned`, `exception`, `elapsed_ms`, `checkpoints[]` and `children[]`.

Both answer 403 when `TRACKER_AUTHORISE` says no.

## What is stored, and what is not

A trace holds real values from a live request, so it is treated as sensitive.

* Everything is passed through `redaction.py` **before** it is stored: values under
  sensitive names (password, token, secret, api key, email, card number, bank details,
  certificate numbers ...), values that LOOK sensitive (emails, card numbers, NI numbers,
  phone numbers), sensitive keys inside dicts, and the same inside free text such as
  exception messages.
* Redaction applies to what is **recorded** only. The real data and the real exceptions
  your code sees are never altered.
* Booleans and None are always shown, even under a sensitive-sounding name, because a flag
  such as `has_token=False` is exactly what a trace is for.
* Django model instances are recorded as `<Class pk=N>`, never as a field dump.
* Only the id of the user who asked is stored, never a name or email.

**Known gaps, stated plainly:**

* Human names and street addresses are NOT detected.
* A list of pairs such as `[("api_key", "...")]` is not scrubbed by key.
* Long reference numbers such as `PO-2026-000123` can be over-redacted as phone numbers.
* Very large values are fully `repr()`'d before being truncated (about 300 ms per million
  items), so do not pass huge collections to `checkpoint()`.

## Retention

Traces should not live forever:

    python manage.py prune_traces --days 7

Run it on a schedule.

## Try it: the sample

Three terminals, from `/opt/websites/spadetrack`:

    # 1. backend (port 8100: emillar's dev containers already use 8000)
    cd sample && python manage.py migrate && python manage.py reset_demo
    python manage.py runserver 8100

    # 2. front end
    cd sample/frontend && npm install && npm run dev      # http://localhost:5173

Open http://localhost:5173, tick **Trace this action**, convert a quote, then **View
trace**. `python manage.py reset_demo` puts the demo data back.

## Tests

    cd sample && python manage.py test tracker procurement     # Django side + sample
    cd .. && python -m unittest discover tests                 # capture + redaction, no Django

## Known limitations and next steps

* The armed state in `trigger.py` is held by a stand-in (`FakeRedis`) that lives inside one
  process. It is fine for `runserver`; with several worker processes it must be replaced
  by a shared store (Redis or the Django cache).
* `arm_views.py` (the endpoint a superuser calls to arm) is preserved but not yet wired in
  or tested.
* The capture is opt-in per decision point (`checkpoint()`); automatic branch tracking is
  deliberately not built.
## The code map (static graph)

The tracer shows what ONE request did. The code map shows what the code COULD do. Both are
kept in this app's tables so they can be joined.

    python discover/discover.py --project-dir sample        # see discover/README.md
    python manage.py load_graph sample/.spadetrack/graph.json

Tables `code_entities` and `code_relations`, replaced per project on every load. Read API
(same authorise rule as traces, 403 otherwise):

* `GET graph/` : projects loaded.
* `GET graph/<project>/` : every entity and relation.
* `GET graph/<project>/flow/?start=<entity id>` : everything reachable from one entity.
* `GET graph/<project>/match/?method=POST&path=/api/quotes/1/convert/` : which route and
  view method handles a recorded request. The mount prefix (`/api`) is ignored.

The sample screen's **Flow** tab draws this map and lays a stored trace over it. The join is
by name: a node's `traced_name` equals the call name in the trace, and the recorded
method + path is matched to a route with `match/`. Dim boxes were not run, or are not
marked `@traced`, so the trace cannot see them (the Vue side is dim until the browser is
traced too).

## Tracing requests nobody is logged in for (development only)

Register, login and password reset are used by people who are not logged in, so
the default rule (logged-in staff only) never traces them. For development you
can open a narrow door:

    # settings.py  (development settings only)
    TRACKER_AUTHORISE = "tracker.policy.dev_authorise"
    TRACKER_DEV_ANON_PREFIXES = ["/api/auth/"]   # only these paths; default: none
    TRACKER_DEV_LOOPBACK_ONLY = True             # default; set False for Docker dev

`dev_authorise` lets an anonymous request through only when ALL of these hold:
`DEBUG` is True; the caller is this machine (loopback); the path starts with a
prefix you listed. The trace viewer's own URLs are never opened, so anonymous
visitors can still not read traces. Logged-in staff are allowed as before, and
`TRACKER_ENABLED` plus the `X-Tracker: 1` header are still required.

### Reading traces before login exists

The trace viewer (the Flow tab and the VS Code extension) reads `/api/tracker/...`,
which the default rule keeps for logged-in staff. In a project with no login yet,
open that door too, for reading only:

    TRACKER_DEV_ALLOW_VIEWER = True     # default False

It needs the same two conditions (`DEBUG` on, caller is this machine) and answers
GET/HEAD/OPTIONS only. Remove it once the project has logins.

Redaction still applies: passwords, tokens and emails are blanked before
anything is stored, including secrets carried in link query strings
(`?token=...`, `?t=...`), which are found by the parameter name.
