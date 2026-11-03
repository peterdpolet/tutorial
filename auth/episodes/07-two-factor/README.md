# Episode 7: Two-factor (a code from an authenticator app)

**Flow:** the person turns two-factor on once. From then on, a correct
password is not enough: they must also type the six digits their phone shows
right now (or a recovery code). The login finishes only when both are right.

## Opening line (what happens if you skip this)

Passwords leak: reused on another site, typed into a fake page, read from a
sticky note. A second factor means a stolen password alone is not a login. The
price is a second step that has to be built carefully, because it creates new
ways to be wrong: the person locks themselves out, or an attacker who already
has the password gets unlimited guesses at the code. This episode is those
choices.

## The process flow (the map, before any code)

Two flows. The first turns it on; the second changes how every later login ends.

    A. turn it on  (the person is logged in)
    click "Set up two-factor"                  (TwoFactorPanel.vue)
      -> start()                                Vue
        -> twoFactorSetup()                     api/auth.js: POST /api/auth/2fa/setup/
          -> two_factor_setup_view()            views.py
            -> start_setup()                    twofactor.py: make a secret, show it ONCE
    type the code, click "Switch it on"
      -> confirm() -> twoFactorConfirm()        POST /api/auth/2fa/confirm/
          -> two_factor_confirm_view()          views.py
            -> confirm_two_factor()             twofactor.py
                 1 find_pending_device          a setup must be waiting
                 2 check_setup_code             the code must match the secret
                 3 switch_on                    only now does login ask for a code
                 4 issue_recovery_codes         8 one-use codes, shown ONCE

    B. log in with a code
    click "Log in"                             (LoginView.vue)
      -> login()                                login.py, as in episode 3, up to:
           check_second_step                    does this account use two-factor?
           start_second_step                    yes: an mfa_token, NOT tokens
    type the code, click "Log in"
      -> onCode() -> finishLogin() -> twoFactorLogin()    POST /api/auth/2fa/login/
          -> two_factor_login_view()            views.py
            -> complete_login()                 twofactor.py
                 1 read_mfa_token               the "password was right" note: genuine, fresh, whose?
                 2 check_not_locked             the SAME lock as the password step
                 3 check_second_factor          six digits or a recovery code
                      use_totp_code             must match AND be newer than the last one used
                      use_recovery_code         must exist and be unused
                      (miss: record_failure     the SAME failure count)
                 4 reset_failures               only now is the count wiped
                 5 issue_tokens                 the access and refresh tokens

## How a six-digit code works (read `accounts/totp.py`: about 70 lines, no library)

The phone and the server both know a **secret** (20 random bytes, shown to you
as 32 letters and digits) and both know the **time**. Every 30 seconds the
clock moves to a new "step". The code is a scrambled version of
`HMAC-SHA1(secret, step)` cut down to six digits. Same secret, same step, same
six digits, on both sides, and nothing travels between them. `test_the_standard_test_values`
checks our recipe against the published test values in the standard (RFC 6238),
so "it is the same thing your phone computes" is a test, not a claim.

Three consequences you will see in the trace and the tests:

- **The secret is stored as it is, not hashed.** A password is stored as a
  hash because the server only ever has to check one. Here the server has to
  recompute the code, so it needs the secret itself. A real system encrypts it
  at rest (see Known limits). Recovery codes, by contrast, ARE stored as hashes.
- **Clocks drift**, so the server also accepts the step before and after
  (`test_the_step_before_this_one_and_after_it_are_accepted`), and nothing further away.
- **A code works once.** Each accepted step is remembered (`last_used_step`),
  and anything at or before it is refused, even inside its 30 seconds. The step
  is claimed in ONE database update, as episodes 2 and 6 claim a link.

## Before you start

Re-run the code map, then migrate:

    python ../../../spadetrack/discover/discover.py      (from auth/)
    python manage.py load_graph ../.spadetrack/graph.json
    python manage.py migrate                             (migration 0005)

You need a confirmed account. You do NOT need a phone: the development command
`python manage.py show_code --email you@example.com` prints the code an app
would show. (If you do have an authenticator app, use it: choose "enter a setup
key" and type the secret.)

## Understand (about 12 minutes)

1. Open **Flow** and start from the **Set up two-factor** button. Say what
   should happen before running anything.
2. Log in (no code asked yet: two-factor is off). Press **Set up two-factor**.
   The page shows a secret, once.
3. In a terminal: `python manage.py show_code --email you@example.com`. Type the
   code into the page and press **Switch it on**. Recovery codes appear, once.
4. Read the trace: `access_check`, `pending_lookup`, `code_check [matched=True]`,
   `two_factor_on`, `recovery_issued [count=8]`. Notice the secret and the
   codes show as `[REDACTED]`.
5. Press **Forget the session**, then log in again with just the password. The
   form changes to **Enter your code**. Read the login trace:
   `second_step_check [required=True]`, `second_step_started`. There is **no
   `failures_reset` and no `tokens_issued`**: a correct password is not yet a
   login. The reply held a short-lived note (`mfa_token`), not tokens.
6. Run `show_code` again. If less than 30 seconds have passed since step 3 it
   prints the same code you used there ("changes in N seconds"). That code is
   spent, so wait for the next one. Type it. You are logged in.
7. Read that trace: `mfa_token_check [valid=True]`, `lock_check`, `totp_check
   [matched=True, replayed=False, claimed=1]`, `failures_reset`, `tokens_issued`.

To run the demo again: `python manage.py forget_totp --email you@example.com`.

## Unhappy paths (and things that look like one but are not)

1. **A wrong code.** "That code is not right." The trace stops after
   `totp_check [matched=False, replayed=False, claimed=0]` and `failure_recorded`.
   No tokens exist.
2. **The same code twice.** Log in with a good code; log out; log in again and
   type the SAME code. Refused with the same words as any wrong code
   (`totp_check [matched=True, replayed=True, claimed=0]`: the digits are right for
   a recent step, but that step was already used). Someone who read the code over your shoulder gets nothing.
3. **A recovery code.** Type one instead of six digits. It works once; the
   trace shows `recovery_check [used=True, codes_left=7]`. Type it again: refused.
4. **Five wrong codes.** The address locks, exactly as five wrong passwords
   do (the SAME count), and then even the RIGHT code is refused with "Too many
   failed attempts", and so is the password step.
5. **Taking too long.** The note after the password lasts 5 minutes
   (`MFA_TOKEN_SECONDS`). To see it expire, set that to `10` in `settings.py`,
   wait, then type the code: "That took too long. Log in again." Put it back.
6. **Things that are NOT two-factor failures:** an account that never turned it
   on logs in with the password alone, and a setup that is started but never
   confirmed does nothing (`test_setup_alone_does_not_switch_it_on`). Switching
   on only after a code works means a typo copying the secret cannot lock you
   out of your own account.

## The planted bug (Fix)

`episodes/07-two-factor/planted_bug.patch` moves ONE line in `login()`: the call
to `reset_failures` goes from after the second-step check to before it. Login
still works. Two-factor still works. Everything you did above still passes.

1. From the `auth/` folder: `patch -p1 < episodes/07-two-factor/planted_bug.patch`
2. Do this five times: log in with the password, type a WRONG code, press
   **Start again**.
3. Log in with the password a sixth time. You get the code form again. It
   should have said "Too many failed attempts": five wrong codes are meant to
   lock the address. Someone who already knows the password can keep guessing
   six-digit codes forever, because every fresh password step wipes the count
   (a million possible codes, 30 seconds each, nobody watching).
4. Read the password-step trace: `active_check`, then `failures_reset`, then
   `second_step_check`. In the healthy trace `failures_reset` is not there at all.
5. Run `python manage.py test accounts -v 2`. Four tests go red:
   `test_logging_in_again_with_the_password_does_not_reset_the_count`,
   `test_a_good_code_wipes_the_failure_count`,
   `test_the_password_step_stops_before_wiping_the_failure_count`, and
   (episode 3's) `test_the_trace_shows_the_steps_and_decisions`.
6. Fix: `patch -R -p1 < episodes/07-two-factor/planted_bug.patch`, run the
   tests, `git status` is clean.

## Talking points

- **A correct password is not a login any more.** `login()` can now return
  "keep going" instead of tokens, and the note it hands back opens nothing but
  the code check. It is signed with its own salt, so an access token is not
  accepted in its place and it is not accepted as an access token
  (`test_an_access_token_is_not_accepted_as_the_note`, `test_the_note_is_not_a_login`).
- **One failure count for both steps.** A second, separate counter for codes
  would be a second thing to get wrong. Reusing the same lock is why the planted
  bug is so quiet: the two steps interact through one number.
- **Same words for every wrong code.** Wrong, replayed, expired and made-up
  recovery codes all say "That code is not right."
- **Password reset (episode 6) does not switch two-factor off.** A reset proves
  you can read the email; it must not also remove the second factor, or the
  second factor protects nothing against someone with the inbox.
- **The redaction lesson.** The tracker hides values by the NAME they travel
  under. Two things nearly slipped through: the name `code` is not on its list
  (so this episode names the argument `otp_code` and adds `otp` and `recovery`
  to the tracker's list), and a function that returns a bare list of recovery
  codes has no name at all. The audit test caught the second one: the codes now
  come back under the key `recovery_codes`. (Port the two new fragments to the
  master spadetrack copy.)

## Known limits (this episode)

- **The secret is stored unencrypted.** The server must be able to read it; a
  real system encrypts it with a key kept outside the database.
- **No QR code, no "turn it off", no "get new recovery codes".** The tutorial
  types the key by hand and removes it with a development command. A real "turn
  it off" asks for the password and a code.
- **Setting it up needs only a login.** Someone holding a stolen session could
  register THEIR app. Real sites ask for the password again first.
- **Codes can be phished in real time.** A fake site can ask for your code and
  pass it straight on within the 30 seconds. Hardware keys and passkeys (WebAuthn)
  are the answer; they are outside this series.
- **Lose the phone AND the recovery codes and the account is gone** (a real site
  has a support process; this one does not).

## Test

`python manage.py test accounts` (195 tests now). New file `test_twofactor.py`,
59 tests, run with `python manage.py test accounts.test_twofactor -v 2` to see
every name. They fix the clock (`self.step`, `self.tick()`), so none of them
waits 30 seconds or fails if a step boundary passes during a run.
Episode 3's trace test was updated: `login` now has one more step
(`check_second_step`, label `second_step_check`).
