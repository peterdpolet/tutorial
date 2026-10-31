# Episode 5: Logout

**Flow:** the person presses "Log out". The server ends their login, so the
refresh token can never make another access token. "Log out everywhere" ends
every login of the account.

## Opening line (what happens if you skip this)

Without a server-side logout, "log out" only throws away the tokens in the
browser. A copy of the refresh token (in a stolen laptop, a leaked log, an old
tab) would keep working for two weeks. Logout is how a person takes back
control, and "log out everywhere" is what they reach for after losing a phone.

## The process flow (the map, before any code)

    click "Log out" / "Log out everywhere"   (LoginView.vue)
      -> onLogout()                           Vue: sends the refresh token
        -> logOutOnServer()                   session.js
          -> logoutAccount()                  api/auth.js: POST /api/auth/logout/
            -> logout_view()                  views.py: read JSON, shape the reply
              -> logout()                     logout.py: the one entry point
                   1 find_logout_session      which login does this token belong to?
                   2 end_login                end THIS login (the whole family)
                     or end_all_logins        every login of the account

## Understand (about 8 minutes)

1. Open **Flow** and start from `button @click -> onLogout(false)`. Say what
   should happen before running anything.
2. Log in. Press **Log out**. The page keeps its tokens on purpose and shows a
   notice, so you can see what still works afterwards.
3. Read the trace (`python manage.py show_trace <id>`): `logout_lookup
   [found=True]`, then `login_ended [revoked_rows=1]`. One login, one live
   token ended.
4. Press **Who am I?**. It still answers. Logout cannot recall the access
   token: it is a signed note the server does not look up, so it works until its
   15 minutes are up. This is not a bug; it is the price of access tokens that
   need no database lookup, and the reason they are short. A test
   (`test_the_access_token_still_works_until_it_expires`) writes the limit down
   so nobody is surprised.
5. Press **Refresh now**. Refused: the refresh token is dead, and the page
   drops back to the login form.
6. Why the whole FAMILY (episode 4) and not just the token presented? A login's
   refresh token changes every time it is used. Ending only the token the page
   happened to send would leave its newest successor alive. The test
   `test_logout_ends_the_whole_family_not_just_the_token_presented` logs out
   with an OLD token and checks the newest one is dead too.

## Unhappy paths (and things that look like one but are not)

1. **Log out twice.** Press **Log out** again. It still says "Logged out." The
   trace stops after `logout_lookup [found=True]` then `login_ended
   [revoked_rows=0]`: nothing left to end, and that is fine.
2. **Unknown token.** A made-up token also gets a 200, and the trace stops
   after `logout_lookup [found=False]`. The answer must not tell a stranger
   which tokens exist, and a page that logs out twice should not see an error.
   This is the same choice real token-revocation endpoints make.
3. **Log out everywhere.** Log in on two browser tabs (a laptop and a phone).
   In one, press **Log out everywhere**. In the other press **Refresh now**:
   refused. The trace shows `all_logins_ended [revoked_rows=…]` counting every
   live login of the account. In a long-used development database the number
   includes old logins from earlier episodes, which never had a logout.

## Talking points

- **The refresh token is the proof.** Logout needs no password and no access
  token. Whoever holds the secret that would keep the login alive may end it.
- **Idempotent.** Doing it twice has the same result as once.
- **Only a real `true` means everywhere.** A string "true" does not; a test
  covers it, because "log out everywhere" is the wide, surprising action.
- **Known limit:** the access token outlives logout by up to 15 minutes (see
  above, and the series README, "Known limits"). If that is too long for a
  system, the fix is a short list of revoked tokens the server checks on every
  request, which brings back the database lookup we avoided.

## Test

`python manage.py test accounts` (100 tests now). New file `test_logout.py`,
21 tests. The two-people-two-logins setup is shared by the tests: they prove
logout ends the right login and nothing else.

## Fix: the planted bug

From the `auth/` folder:

    patch -p1 < episodes/05-logout/planted_bug.patch

It changes one filter in `end_login`: it ends every live token of the
**user** (`filter(user=row.user)`) instead of the tokens of this login's
**family**. Logging out on the laptop now logs the phone out too. On a quiet
day with one device you would never notice.

1. Open the app in two browser tabs and log in on both (a laptop and a phone).
   Do not reload either tab: the tokens live in the page.
2. In tab 1 press **Log out**.
3. In tab 2 press **Refresh now**. It should still work. With the bug it is
   refused and tab 2 drops back to the login form: logging out one device
   logged out the other.
4. Careful: tab 2's refusal looks like theft detection from episode 4
   (`replay_check [replayed=True]`). That is a red herring. Follow the LOGOUT
   trace instead (the id is in tab 1's log): `login_ended [revoked_rows=…]`
   says 1 when healthy and more than 1 with the bug (every live login of the
   account, so 2 in a clean database, more in an old one).
5. Run the tests. Three fail:
   `test_logging_out_one_login_leaves_the_persons_other_login_alone`,
   `test_only_a_real_true_means_everywhere` and
   `test_the_trace_counts_what_was_ended`.
6. Ask an AI for a fix and judge it against the trace. The fix that matches is
   to select this login's family again:
   `filter(family=row.family, revoked_at__isnull=True)`.
7. Put it back: `patch -R -p1 < episodes/05-logout/planted_bug.patch`, rerun
   the tests (all green) and repeat the two-tab path (tab 2 keeps working).

## Before filming

- [ ] Fresh database (`rm backend/db.sqlite3 && python manage.py migrate`), then
      register and confirm an account (so the revoked counts are small)
- [ ] Code map reloaded after the update (discover, then `load_graph`)
- [ ] Tests green with the patch removed; exactly three red with it applied
- [ ] Only invented data on screen
