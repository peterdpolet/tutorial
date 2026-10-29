# Episode 1: Register

**Flow:** the person fills in the form and presses Register. An account is
created that cannot log in yet, and an email with a confirmation link is sent.

## Opening line (what happens if you skip this)

Without an inactive-until-verified account, anyone can register
`someone-else@their-company.com` and use it. Show the learner that error
first, then build the thing that prevents it.

## The process flow (the map, before any code)

    click Register (RegisterView.vue: form submit)
      -> submit()                              Vue: collects the form
        -> registerAccount()                   api/auth.js: POST /api/auth/register/
          -> register_view()                   views.py: read JSON, shape the reply
            -> register()                      services.py: the one entry point
                 1 clean_email                 tidy the address
                 2 check_email_free            refuse a duplicate
                 3 check_password              refuse a weak password
                 4 create_inactive_user        save; is_active = False
                 5 issue_verification_token    secret for the emailed link
                 6 send_verification_email     printed to the Django terminal

## Understand (about 5 minutes)

0. Open the flow in VS Code first (see the top-level README), before any trace.
   This is the map: click, form handler, API call, URL, view, the six steps.
   Say what should happen. Then register with tracing on and reopen the flow:
   the boxes that ran light up. For an unhappy path, the boxes after the
   refusal stay dark. That is the whole idea of the series in one picture.
1. Register `learner@example.com` / `Tut0rial-Pass!` with tracing on.
2. `python manage.py show_trace`. Read it top to bottom beside `services.py`.
3. Say what each `.` line (checkpoint) means:
   - `duplicate_check [taken=False]`: the decision at step 2
   - `password_accepted`: step 3
   - `user_created [user_id=1, is_active=False]`: the user exists but cannot log in
   - `token_issued`, `email_sent [to_domain='example.com']`
4. Point at the `[REDACTED]` markers. The trace never contains the password,
   the email address or the token. Say why: a trace is something you show on
   screen, paste into an AI chat, and send to a colleague.
5. Why the default tracing rule would have refused this request (nobody is
   logged in) and what `dev_authorise` allows instead (DEBUG on, this machine,
   `/api/auth/` only).

## Unhappy paths

1. **Email already registered.** Register the same address twice. The trace
   leaves the map at step 2: `duplicate_check [taken=True]`, then a 400.
2. **Password too weak.** Try `password123`. The trace stops at step 3
   (`password_refused`); nothing is saved and no email is sent.

Design note to mention, not to solve: telling someone "already registered"
reveals which addresses have accounts. Password reset (episode 6) takes the
opposite choice. Ask the learner which is right for their product.

## Test

Run `python manage.py test accounts`. Read the names as a list of rules; each
says which step of the map it protects. Happy path first, then one test per
unhappy path.

## Fix: the planted bug

From the `auth/` folder:

    patch -p1 < episodes/01-register/planted_bug.patch

This removes one word: `.lower()` in `clean_email`. Everything still works, the
happy-path tests pass, and it looks like harmless tidying. Then:

1. Register `Bob@example.com`, then `bob@example.com`. Both succeed. Two
   accounts, one person. Trace both: step 2 said `taken=False` both times.
2. Run the tests. Exactly one fails:
   `test_same_email_in_other_capitals_is_also_refused`.
3. Open the flow for the second registration: step 2 lights up and the rest looks
   normal. Nothing is dark, which is why this bug is hard to see.
4. The failing test name points at step 2, but the cause is in step 1: the
   tidy step no longer produces one canonical spelling, so step 2 compares
   different strings. This is the moment to show how a trace shows where the
   behaviour leaves the map, and how a fix has to be checked against the flow.
5. Ask an AI for a fix. Judge each proposal against the map. A fix in step 2
   (case-insensitive lookup) hides the problem and leaves mixed-case addresses
   stored; the fix that matches the flow is to restore `.lower()` in step 1.
6. Put it back: `patch -R -p1 < episodes/01-register/planted_bug.patch`, then
   rerun the tests (all green) and the double registration (second is refused).

## Before filming

- [ ] Fresh database (`rm backend/db.sqlite3 && python manage.py migrate`)
- [ ] Tracker copied in at version 0f10a1b or later
- [ ] Tests green with the patch removed; exactly one red with it applied
- [ ] Only invented data on screen
