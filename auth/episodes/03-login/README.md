# Episode 3: Login

**Flow:** the person types their email and password. If the address is not
locked, the password matches and the account has been confirmed, the server
hands back two tokens: a short-lived **access token** and a long-lived
**refresh token**.

## Opening line (what happens if you skip this)

Registration and verification only create an account. Nothing yet proves, on a
later visit, that the person is the owner. Login is the first place where an
attacker is actively trying things (guessing passwords, probing which
addresses exist), so this is where the unhappy paths matter most.

## The process flow (the map, before any code)

    click "Log in" (LoginView.vue)
      -> submit()                              Vue: sends email + password
        -> loginAccount()                      api/auth.js: POST /api/auth/login/
          -> login_view()                      views.py: read JSON, shape the reply
            -> login()                         login.py: the one entry point
                 1 normalise_email             same tidy-up as Register
                 2 check_not_locked            5 failures lock the address for 15 minutes
                 3 check_credentials           user exists AND password matches
                     (miss -> record_failure)
                 4 check_active                right password, email never confirmed?
                 5 reset_failures              a good login wipes the failure count
                 6 issue_tokens                access token + refresh token
        -> fetchMe()                           api/auth.js: GET /api/auth/me/
          -> me_view() -> authenticate_access  proves the access token works

## Understand (about 8 minutes)

1. Open **Flow**, start from `form @submit -> submit (LoginView.vue)`. Say what
   should happen before running anything.
2. Register `learner@example.com`, confirm the email (episode 2), then log in
   with tracing on. Overlay the trace: all six steps light, then `me_view`.
3. `python manage.py show_trace` (run it for the login trace id shown on the
   page). Read the checkpoints: `lock_check [locked=False, failures=0]`,
   `credentials_check [user_found=True, password_ok=True]`,
   `active_check [active=True]`, `failures_reset`,
   `tokens_issued [access_valid_seconds=900, refresh_valid_days=14]`.
4. Point at the redaction. The email, the password and BOTH tokens are
   `[REDACTED]` in the trace, and the tokens are never printed on the page.
   The test `test_redaction_audit_no_secret_is_stored` fails if any of them
   ever reaches the stored trace.
5. Why two tokens? The access token is a signed note ("user 7, made at 10:02")
   the server can check without a database lookup, and it dies in 15 minutes,
   so a stolen one is short-lived. The refresh token is a random secret kept
   (hashed) in the database, so it can be revoked. Episode 4 spends it.

## Unhappy paths

1. **Wrong password.** Trace stops at step 3: `credentials_check
   [user_found=True, password_ok=False]` then `failure_recorded [failures=1,
   max_failures=5, locked=False]`. Steps 4 to 6 stay dark.
2. **Unknown email.** The page shows the SAME message and status as a wrong
   password. Only the trace differs (`user_found=False`). That sameness is the
   point: a login form that says "no such user" lets a stranger test which
   addresses have accounts.
3. **Right password, email not confirmed.** Register but do not use the link.
   Trace stops at step 4 (`active_check [active=False]`) with a 403 and "Confirm
   your email address first". It only says this once the password is right, so
   it tells a stranger nothing.
4. **Lockout.** Five wrong passwords in a row. The fifth is still answered
   "incorrect" (and the trace shows `locked=True`); from the sixth attempt the
   reply is 429 "Too many failed attempts", and even the RIGHT password is
   refused. The trace stops at step 2.
   `python manage.py clear_locks` (development only) lets you try again without
   waiting 15 minutes.

## Talking points

- **Locks are per address typed, not per account.** If only real accounts
  locked, the lock message would reveal which addresses exist. The table
  (`LoginLock`) is keyed by the email string for that reason.
- **Timing.** For an unknown email the code still checks the password against a
  dummy hash, so "no such user" is not noticeably faster than "wrong password".
- **A lock is also an attack.** Someone can lock YOUR address by failing five
  times on purpose. Real systems weigh this against guessing; here we accept it
  and say so.
- **Where the tokens live in the browser** is a decision of its own (memory,
  localStorage, a cookie). This tutorial keeps them in a variable, so a reload
  logs you out. Not a recommendation, just the simplest honest choice.
- The trace viewer door (`TRACKER_DEV_ALLOW_VIEWER` in `settings.py`) stays:
  the tracker only recognises Django staff logins, not these tokens. It goes
  when the tracker learns to read the token. Never on a real server.

## Test

`python manage.py test accounts` (59 tests now). New file `test_login.py`; the
names read as rules. Note the boundary pair: four failures do not lock, five do.

## Fix: the planted bug

From the `auth/` folder:

    patch -p1 < episodes/03-login/planted_bug.patch

It deletes the line that calls `reset_failures`. Everything still works on a
quiet day, which is why this kind of bug survives: **a failure counter that
never resets on success.** Failures add up across weeks, so a good user who
mistypes four times over a year is locked out on the fifth mistake, with a
correct password.

1. Register and confirm an account. Fail four times (wrong passwords), then log
   in correctly. It works. Now make ONE more mistake, then log in correctly.
   Locked out (429). Wrong: that is two mistakes since the last good login.
2. Look at the successful login's trace. The path is healthy except for one
   thing: the box for `reset_failures` is dark and there is no `failures_reset`
   checkpoint. Then open the trace of the next failed attempt:
   `lock_check [failures=4]`, straight after a successful login. The trace
   contradicts itself. That points at step 5.
3. Run the tests. Two fail: `test_a_good_login_wipes_earlier_failures` and
   `test_the_trace_shows_the_steps_and_decisions`.
4. Ask an AI for a fix and judge it against the flow. Raising
   `LOGIN_MAX_FAILURES` hides the symptom; so does a shorter lock. The fix that
   matches the trace is to call `reset_failures(email=email)` again after
   `check_active`.
5. Put it back: `patch -R -p1 < episodes/03-login/planted_bug.patch`, rerun the
   tests (all green) and repeat the click path (no lockout).

## Before filming

- [ ] Fresh database (`rm backend/db.sqlite3 && python manage.py migrate`)
- [ ] Code map reloaded after the update (discover, then `load_graph`)
- [ ] Tests green with the patch removed; exactly two red with it applied
- [ ] Only invented data on screen
