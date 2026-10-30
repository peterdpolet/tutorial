# Episode 2: Verify email

**Flow:** the person opens the link in the confirmation email and presses
"Confirm my email". If the link is genuine, unused and recent, the account is
switched on.

## Opening line (what happens if you skip this)

Without verification, anyone can register someone else's address, and every
account is active from the first second. Show the learner that the episode-1
account has `is_active=False`, then build the thing that changes it.

## The process flow (the map, before any code)

    click "Confirm my email" (VerifyView.vue)
      -> confirm()                             Vue: sends the token from the address bar
        -> verifyEmail()                       api/auth.js: POST /api/auth/verify/
          -> verify_view()                     views.py: read JSON, shape the reply
            -> verify_email()                  verify.py: the one entry point
                 1 find_token                  the token must exist
                 2 check_not_used              a link works once
                 3 check_not_expired           24 hours (EMAIL_TOKEN_LIFETIME_HOURS)
                 4 activate_and_consume        switch the account on, mark the link used

## Understand (about 5 minutes)

1. Open the Flow tab (or the flow in VS Code) and start from
   `button @click -> confirm (VerifyView.vue)`. Say what should happen before
   running anything.
2. Register `learner@example.com`, copy the link from the Django terminal and
   open it. The page waits: nothing is sent until the button is pressed.
3. Press the button with tracing on. Overlay the trace: all four steps light.
4. `python manage.py show_trace`. Read the checkpoints:
   `token_lookup [found=True]`, `used_check [used=False]`,
   `expiry_check [age_hours=0.0, limit_hours=24, expired=False]`,
   `link_claimed [claimed=1]`, `user_activated`.
5. Point at the redaction: the token is `[REDACTED]` in the trace even though it
   is the whole point of the request.
6. Why step 4 claims the link with ONE database update
   (`filter(used_at__isnull=True).update(...)`) instead of "check, then save":
   two clicks arriving together would both pass the check. Only one update can
   change the row.

## Unhappy paths

1. **Link used twice.** Press the button again. The trace stops at step 2
   (`used_check [used=True]`); steps 3 and 4 stay dark.
2. **Link expired.** `python manage.py age_tokens --hours 50` (development only,
   it refuses to run unless DEBUG is on) and press the button. The trace stops at
   step 3: `expiry_check [age_hours=50.0, limit_hours=24, expired=True]`.
   Step 4 stays dark and the account stays off.
3. (Bonus) A made-up token stops at step 1: `token_lookup [found=False]`.

## Test

Run `python manage.py test accounts` (35 tests now). The names read as rules;
the expiry tests include "just inside the limit still works" and "just past the
limit is refused". A boundary test on each side is what makes a time rule
trustworthy.

## Fix: the planted bug

NOTE: the episode map planned "expiry compared in the wrong time zone". That bug
would not show for a viewer in the UK in winter (local time equals UTC), so it
could not be demonstrated reliably. This one shows everywhere.

From the `auth/` folder:

    patch -p1 < episodes/02-verify-email/planted_bug.patch

It changes `age.total_seconds()` to `age.seconds` in `check_not_expired`. Both
look like "the age in seconds". They are not: `.seconds` is only the seconds
*part* of the difference (0 to 86399), so a 50-hour-old link counts as about 2
hours old. With a 24-hour limit, links NEVER expire.

1. Register, then `python manage.py age_tokens --hours 50`, then press Confirm.
   It succeeds. Wrong.
2. Overlay the trace. The path is the healthy path, all four steps lit. Read
   the checkpoint: `age_hours=50.0 ... expired=False`. The trace contradicts
   itself: 50 hours old and not expired. That is the clue, and it points at the
   line that computes `expired`.
3. Run the tests. Four fail, all in the expiry rules:
   `test_a_link_just_past_the_limit_is_refused`,
   `test_a_link_two_days_and_an_hour_old_is_refused`,
   `test_an_expired_link_leaves_the_account_off_and_the_link_unused` and
   `test_the_expiry_decision_is_visible_with_its_numbers`.
4. Ask an AI for a fix and judge it against the flow. A change to the limit
   (for example, compare against `limit_hours * 3600 - 1`) hides the symptom; the
   fix that matches the trace is `total_seconds()`.
5. Put it back: `patch -R -p1 < episodes/02-verify-email/planted_bug.patch`,
   rerun the tests (all green) and the aged-link click (now refused).

## Before filming

- [ ] Fresh database (`rm backend/db.sqlite3 && python manage.py migrate`)
- [ ] Code map reloaded after the update (discover, then `load_graph`)
- [ ] Tests green with the patch removed; exactly four red with it applied
- [ ] Only invented data on screen
