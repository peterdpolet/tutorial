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

### Before filming

- Search YouTube for the "same login, three front ends" gap. Only the web was searched on 9 Nov.
- Confirm the JWT + TOTP mechanism against current allauth docs, and say on camera that it is an assembled pattern, not a library default.

### Open questions

Domain for HTTPS; where the front end is built; real email for resets; when to move to Postgres; filming order.
