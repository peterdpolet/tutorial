# Episode 4: Token refresh

**Flow:** the access token has run out (15 minutes). Instead of asking for the
password again, the page hands the server its refresh token and gets a fresh
pair. The refresh token it sent is retired at that moment.

## Opening line (what happens if you skip this)

Without refresh there are only two bad choices: access tokens that last for
weeks (a stolen one is useful for weeks) or a password prompt every 15
minutes. Refresh gives short-lived access tokens AND a smooth session. The
price is a second secret, the refresh token, that is far more valuable than the
first. This episode is mostly about protecting it.

## The process flow (the map, before any code)

    "Who am I?" / any request            (LoginView.vue -> session.js)
      -> access token refused (401)?     whoAmI(): refresh once, then retry
        -> refreshNow()                  session.js: ONE refresh at a time
          -> refreshTokens()             api/auth.js: POST /api/auth/refresh/
            -> refresh_view()            views.py: read JSON, shape the reply
              -> refresh()               refresh.py: the one entry point
                   1 find_refresh_token         must be a token we issued
                   2 check_not_replayed         a RETIRED token = a copy exists
                       (hit -> revoke_family)
                   3 check_refresh_not_expired  14 days (REFRESH_TOKEN_DAYS)
                   4 check_user_active          the account must still be on
                   5 rotate_tokens              retire this token, issue the next pair

## Understand (about 10 minutes)

1. Open **Flow** and start from `form @submit -> onLogin (LoginView.vue)`, or
   from `refresh_view`. Say what should happen before running anything.
2. Log in (use an account confirmed in episode 2). The page now shows the
   session panel instead of the form.
3. Press **Break my access token**, then **Who am I?**. The page says the access
   token was refused, refreshed itself and tried again. Three traces were made:
   `/me (refused)`, `refresh`, `/me (retry)`. Read the refresh one with
   `python manage.py show_trace <id>`:
   `refresh_lookup [found=True]`, `replay_check [replayed=False]`,
   `refresh_expiry_check [days_left=14.0, expired=False]`,
   `user_active_check [active=True]`, `token_claimed [claimed=1]`,
   `tokens_rotated [access_valid_seconds=900]`.
4. Redaction: `refresh_token` is `[REDACTED]` in every trace. The test
   `test_redaction_audit_no_token_is_stored` fails if either token, old or new,
   ever reaches a stored trace.
5. **Family.** Every login starts a family of refresh tokens. Each refresh
   retires one token and issues the next in the same family. The database holds
   a chain, one live token at the end (`revoked_at` is set on the others).
6. **Why step 5 claims the token with ONE update** (`filter(pk=..,
   revoked_at__isnull=True).update(...)`): the same idea as episode 2's link.
   Two requests carrying the same token cannot both win.
7. **Why the page shares one refresh.** Rotation means a token can be spent
   once. If two requests hit a 401 together and BOTH refreshed, the second
   would send an already-retired token, and the server would read that as
   theft and end the login. `session.js` therefore keeps a single refresh in
   flight and every caller waits for it. (This is explained, not covered by an
   automated test here.)

## Unhappy paths

1. **Replay (the point of rotation).** Press **Refresh now** once (so there is a
   previous token), then **Replay the previous refresh token**. That plays a
   thief holding a stolen copy. The server refuses ("This session has ended")
   and the trace shows `replay_check [replayed=True]` then `family_revoked
   [revoked_rows=1]`: the owner's newest token was live, and has just been
   ended. Press **Refresh now** again: refused, and the page falls back to the
   login form with the reason. Both parties are out; only the owner can log back
   in with the password. Read that second trace too: it also says
   `family_revoked`, but with `revoked_rows=0`. That zero is correct, because
   the family was already ended and nothing was left to revoke. Only the FIRST
   replay should show `revoked_rows=1`. Remember the difference for the bug
   below.
   Do not reload the page between presses: the tokens live in the page, so a
   reload logs you out and you have to start the sequence again.
2. **Access token still works for up to 15 minutes after that.** After the
   replay, press **Who am I?**: it still answers. The access token is a signed
   note the server does not look up, so it cannot be recalled. That is exactly
   why access tokens are short.
3. **Expired session.** In a terminal run `python manage.py expire_sessions`
   (development only), then press **Break my access token** and **Who am I?**.
   The refresh is refused at step 3 (`refresh_expiry_check [days_left=-0.0,
   expired=True]`; the tiny negative is the one second the command backdates)
   and you are back at the login form. (Without breaking the access token first,
   `/me` would still succeed for a few minutes.) The command reports how many
   live tokens it expired. That is every login not yet ended, including old
   ones from earlier episodes, because logout does not exist until episode 5.
4. **Made-up token** stops at step 1 (`refresh_lookup [found=False]`), covered
   by tests.

## Talking points

- **Retired token versus stolen token.** The server cannot tell whether the
  second user of a token is a thief or the owner (a flaky connection can make a
  real page retry). It treats both the same and ends the login. Real systems
  often allow a few seconds of grace for retries; this tutorial does not, so
  the rule stays easy to see.
- **Only a hash is stored**, as with episode 3: a database copy cannot be used
  to log in.
- **Known limit:** the tokens still live in a page variable (see the series
  README, "Known limits").

## Test

`python manage.py test accounts` (79 tests now). New file `test_refresh.py`,
20 tests. Note the replay class: "a retired token is refused", "replaying it
ends the whole login", "another login by the same person is not affected",
"the same token cannot be spent twice". The access-token test deliberately does
not demand that two access tokens made in the same second differ: they are
identical, which is harmless.

## Fix: the planted bug

From the `auth/` folder:

    patch -p1 < episodes/04-token-refresh/planted_bug.patch

It changes one filter in `revoke_family`: it ends only the token that was
presented, `filter(pk=row.pk)`, instead of every token in the family. The
replayed token is already retired, so the filter matches nothing. The reply to
the thief is still a refusal, which is why nothing looks wrong on a quiet day.

1. Log in. Press **Refresh now**, then **Replay the previous refresh token**.
   Refused, as before. Now press **Refresh now** again. It SUCCEEDS. Wrong: a
   replay was detected, and the login should have been ended.
2. Read the FIRST replay trace. The path is the healthy one, but look at the
   number: `replay_check [replayed=True]` then `family_revoked [revoked_rows=0]`.
   A healthy server shows `revoked_rows=1` here, because the owner's newest
   token was still live. A step called "revoke the family" that revoked nothing
   points at `revoke_family`. (A zero on a LATER attempt would be normal; the
   family is already gone.)
3. Run the tests. Two fail: `test_replaying_a_retired_token_ends_the_whole_login`
   and `test_a_replay_shows_the_family_being_ended_with_a_count`.
4. Ask an AI for a fix and judge it against the flow. Adding a second check
   somewhere else would hide it; the fix that matches the trace is to select the
   whole family again: `filter(family=row.family, revoked_at__isnull=True)`.
5. Put it back: `patch -R -p1 < episodes/04-token-refresh/planted_bug.patch`,
   rerun the tests (all green) and repeat the click path (the second refresh is
   refused).

## Before filming

- [ ] Fresh database (`rm backend/db.sqlite3 && python manage.py migrate`), then
      register and confirm an account
- [ ] Code map reloaded after the update (discover, then `load_graph`)
- [ ] Tests green with the patch removed; exactly two red with it applied
- [ ] Only invented data on screen
