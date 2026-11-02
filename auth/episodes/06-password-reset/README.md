# Episode 6: Password reset

**Flow:** the person forgot their password. They type their email, we email a
link, they open it and choose a new password. The new password works, the old
one does not, and every login that existed before is ended.

## Opening line (what happens if you skip this)

A site with no way back in loses its users, so every site ships a reset. It is
also the weakest door in the building: it lets someone who does NOT know the
password get one set, and the only proof it asks for is "can read this email".
Every choice in this episode is about keeping that door from being used by the
wrong person, or being used to learn something about the right one.

## The process flow (the map, before any code)

Two requests, because two different things happen.

    A. ask for a link
    click "Send me a link"                    (ForgotView.vue)
      -> submit()                              Vue: sends the email
        -> forgotPassword()                    api/auth.js: POST /api/auth/forgot/
          -> forgot_view()                     views.py: read JSON, ALWAYS the same reply
            -> request_reset()                 reset.py: the one entry point
                 1 normalise_email             tidy the address (login.py, shared)
                 2 find_account                a confirmed account for it?
                 3 check_cooldown              was a link emailed a moment ago?
                 4 issue_reset_token           new secret; retire any older link
                 5 send_reset_email            prints the email (console)

    B. use the link
    open /reset?token=...  then  click "Change my password"   (ResetView.vue)
      -> submit()                              Vue: sends token + new password
        -> resetPassword()                     api/auth.js: POST /api/auth/reset/
          -> reset_view()                      views.py: read JSON, shape the reply
            -> reset_password()                reset.py: the one entry point
                 1 find_reset                  the link must exist
                 2 check_reset_not_used        a link works once
                 3 check_reset_not_expired     a link works 60 minutes
                 4 check_new_password          same rules as Register
                 5 apply_reset                 ONE transaction:
                                                 use up the link, set the password,
                                                 end_all_logins (episode 5),
                                                 reset_failures (episode 3)

Notice how much is reused. `normalise_email`, `end_all_logins` and
`reset_failures` are the same traced steps from episodes 3 and 5. A new flow
built from steps you already trust is how a series like this stays small.

## Before you start

Re-run the code map so the Flow tab knows about the new files:

    python ../../../spadetrack/discover/discover.py   (as in earlier episodes)
    python manage.py load_graph ../.spadetrack/graph.json

and run `python manage.py migrate` (migration `0004` adds the reset-link table).
You need a confirmed account to reset: register one and open its confirmation
link first (the dev database from earlier episodes is fine).

## Understand (about 10 minutes)

1. Open **Flow** and start from the **Forgot password** form's submit. Say what
   should happen before running anything.
2. On **Log in**, log in. This login is the one the reset should end. Leave the
   page open.
3. Open **Forgot password** in a second browser tab, type the account's email
   and press **Send me a link**. The page answers "If that address has an
   account, we have emailed a link...". Look at the backend terminal: the email
   is printed there, with a link ending `/reset?token=...`.
4. Read the trace (`python manage.py show_trace <id>`): `account_lookup
   [found=True]`, `cooldown_check [too_soon=False]`, `reset_issued
   [older_links_retired=0]`, `email_sent`.
5. Copy the link from the terminal into the browser. Type a weak password
   (`short`). It is refused with reasons, and the link is NOT used up.
6. Type a good password. "Password changed." Read its trace:
   `reset_lookup`, `used_check`, `expiry_check`, `password_accepted`,
   `link_claimed [claimed=1]`, `password_changed`, `all_logins_ended
   [revoked_rows=…]`, `failures_reset`. (In a long-used development database
   `revoked_rows` includes old logins from earlier episodes.)
7. Go back to the first tab and press **Refresh now**. Refused: the login that
   existed before the reset is gone. That is the whole point of the step.
8. Try to log in with the OLD password (refused) and the NEW one (works).

## Unhappy paths (and things that look like one but are not)

1. **An address with no account.** In the Forgot form type
   `nobody@example.com`. The page gives the SAME sentence. The trace stops
   after `account_lookup [found=False]`, and the backend terminal shows no
   email. If the page said "no such account", the form would be a free way to
   find out who has one. (A test compares the two replies word for word.)
2. **An unconfirmed account.** It gets the same reply and no email: it should
   use its confirmation link first.
3. **Asking twice in a minute.** The second request gets the same words but no
   second email: `cooldown_check [too_soon=True]`. Without this, the form is a
   way to flood someone's inbox. After a minute a new link is sent, and the new
   link retires the old one (`older_links_retired=1`).
4. **A weak password.** Refused with the reasons, and the link survives
   (`password_refused`, and no `link_claimed`). The order matters: check the
   password BEFORE using up the link, or one typo burns the link.
5. **Using a link twice.** The second use says "already used" and changes
   nothing. Like episode 2, the link is claimed in one database step
   (`link_claimed [claimed=1]`), so two requests arriving together cannot both
   win.
6. **An expired link.** Request a link, then run
   `python manage.py age_tokens --hours 2` and open it: "has expired". (The
   same command ages confirmation links; it now covers both kinds.)
7. **A made-up link.** "Not valid", and the trace stops after
   `reset_lookup [found=False]`.

## The planted bug (Fix)

`episodes/06-password-reset/planted_bug.patch` removes one line in
`apply_reset`: the call to `end_all_logins`. The reset still works, the new
password works, the old one stops working. Everything looks right.

1. From the `auth/` folder: `patch -p1 < episodes/06-password-reset/planted_bug.patch`
2. Repeat the Understand steps: log in, ask for a link, reset the password.
3. Press **Refresh now** in the first tab. It SUCCEEDS. A login that existed
   before the reset is still alive. Someone who stole the old password and
   logged in has just survived the reset, which is the one thing a reset is for.
4. Read the reset trace: `password_changed` is followed straight by
   `failures_reset`. There is no `all_logins_ended`. The map said there should
   be one; the trace shows it missing.
5. Run `python manage.py test accounts.test_reset -v 2`. Three tests go red:
   `test_reset_ends_every_login_of_the_person`,
   `test_using_the_link_shows_every_step`,
   `test_the_trace_counts_the_logins_that_were_ended`. Nothing about the
   happy path (new password works) fails, which is why this bug survives
   manual testing: you only see it if you ask the unhappy question, "what
   about the logins that were already there?"
6. Fix: `patch -R -p1 < episodes/06-password-reset/planted_bug.patch`, run the
   tests again, and `git status` is clean.

## Talking points

- **The email is the only proof.** Whoever can read the inbox can take the
  account. That is why the link is short-lived (60 minutes), used once, stored
  only as a hash, and why the reset ends every login.
- **Same words for every address.** The Forgot form answers identically for
  known, unknown and unconfirmed addresses. Episode 1's Register form does
  NOT: it says "already registered", which tells a stranger an address has an
  account. The two forms take opposite choices on purpose, and the trade-off is
  real: a register form that hides this is harder to use, because a person who
  mistypes cannot be told why. A real site decides which it values more. The
  tutorial leaves episode 1 as it is, and says so here.
- **Check first, spend last.** The new password is checked before the link is
  used up, and the link, the password and the logins change in ONE
  transaction, so a failure part-way cannot leave a changed password with
  logins still alive.
- **Reset does not log you in.** After a reset the person logs in normally. An
  automatic login would turn a stolen link into a stolen session.

## Known limits (this episode)

- **Timing.** A known address does more work than an unknown one (it writes a
  row and sends an email), so a very careful attacker could measure the
  difference. A real site sends the email from a background job so both paths
  take the same time.
- **No limit by network address.** The cooldown is per account. Someone could
  still ask for links for thousands of different accounts from one machine.
- **Email is trusted.** If the inbox is compromised, so is the account. Episode
  7 (two-factor) is what protects against that.

## Test

`python manage.py test accounts` (136 tests now). New file `test_reset.py`,
36 tests: asking for a link (happy and unhappy), using the link (happy and
unhappy), bad requests, and the trace. Run it with
`python manage.py test accounts.test_reset -v 2` to see every name.
