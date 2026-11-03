# Episode 8: Permissions (who is allowed to do what)

**Flow:** logging in answers "who are you?". This episode answers a different
question: "are you allowed to do THIS?". Two roles (member, admin), one rule in
one place, and two admin-only actions that use it: see the list of accounts,
and change someone's role.

## Opening line (what happens if you skip this)

Every page you built so far asks the first question: is this a real, logged-in
person? A page that asks only that is open to every person who has an account.
The classic hole is exactly this: the admin page checks you are logged in and
forgets to check you are an admin, so any member who finds the address can use
it. It is one forgotten line, nothing crashes, every test of the happy path
still passes, and the only symptom is someone doing what they should not. This
episode is that line, and the tests that notice when it goes missing.

## The process flow (the map, before any code)

Two flows. Both start the same way: prove who you are (episode 3's access
token), then ask whether that person may do this.

    A. see the list of accounts
    click "Load accounts"                       (AdminView.vue)
      -> load() -> listAccounts()                 Vue, api/session.js
        -> adminUsers()                           api/auth.js: GET /api/auth/admin/users/
          -> admin_users_view()                   views.py
               authenticate_access               who are you?        (401 if not logged in)
            -> list_users()                       permissions.py
                 1 check_role                     are you an admin?   (403 if not)
                 2 build the list                 id, address, role, active

    B. change someone's role
    click "Make admin" (or "Send")               (AdminView.vue)
      -> setRole() -> changeRole()                Vue, api/session.js
        -> adminSetRole()                         api/auth.js: POST /api/auth/admin/role/
          -> admin_role_view()                    views.py
               authenticate_access               who are you?        (401)
            -> change_role()                      permissions.py
                 1 check_role                     are you an admin?   (403)  FIRST, before anything else
                 2 check_role_input               is it a real id and a real role?   (400)
                 3 find_target                    does that account exist?   (404)
                 4 check_not_last_admin           would it leave no admin?   (409)
                 5 apply_role                     write it down

## The ideas to hold on to (read `accounts/permissions.py`: about 120 lines)

- **Two questions, two answers.** 401 means "I do not know who you are". 403
  means "I know who you are, and the answer is no". Mixing them up makes both
  harder to debug, and the screen shows the difference
  ("Not logged in (401)" and "Refused (403)").
- **One rule, in one place.** `check_role` is the only code that decides.
  Every protected action calls it as its FIRST step. A rule written out again
  in each view is a rule that one view will forget, and that is the planted bug.
- **The role is not in the access token.** The token is still just "user 7"
  (`test_the_access_token_carries_no_role`). The role is read from the database
  on every request. The cost is one small query per request. The gain: when an
  admin is demoted, their very next request is refused, instead of working until
  their 15-minute token runs out
  (`test_a_demoted_admin_loses_the_power_on_the_very_next_request`). A token that
  carried the role would have to be revoked, and a stateless token cannot be.
- **The permission is checked before the request is looked at.** A member who
  asks about an account that does not exist gets 403, not 404
  (`test_a_member_asking_about_a_missing_account_still_gets_403_not_404`).
  If the server said 404 to members and 403 for accounts that exist, the admin
  page would be a free way to find out which accounts exist.
- **Hiding a button is a courtesy, not security.** The Admin page shows the table
  only to someone it loaded for, but a script has no use for the table. The page
  has a "Send the request yourself" form to make that real: it sends exactly what
  a script would. The server's answer is the rule.
- **Someone has to be the first admin, and not through the page** (you would need
  to be an admin to use it). The first key is handed over on the machine:
  `python manage.py make_admin --email you@example.com`.
- **The last admin cannot be removed**, by anyone, including themselves
  (409). A system with no admin is a system nobody can fix.

## Before you start

Re-run the code map, then migrate and set up three demo accounts:

    cd auth
    /opt/websites/spadetrack/.venv/bin/python /opt/websites/spadetrack/discover/discover.py
    cd backend
    python manage.py load_graph ../.spadetrack/graph.json
    python manage.py migrate                    (migration 0006)
    python manage.py seed_demo

`seed_demo` makes `admin@example.com` (an admin), `member@example.com` and
`member2@example.com`, all with the password `demo-password-55`, and prints each
account's id. Run it again at any time to put everything back as it was (it also
clears locks and two-factor). It refuses to run unless DEBUG is on.

## Understand (about 10 minutes)

1. Open **Flow** and start from the **Load accounts** button. Say what should
   happen before running anything.
2. **Log in** as `admin@example.com`. Press **Who am I?**: the page now says
   `Logged in as admin@example.com (admin).` (`/me` returns the role.)
3. Open the **Admin** tab and press **Load accounts**. Every account in your
   database appears (the three demo ones are at the bottom, with the highest ids).
   Run the trace: `access_check`, then `role_check [needed='admin', has='admin',
   allowed=True]`, then `users_listed [count=N]`, where N is the number of rows. The addresses are `[REDACTED]`.
4. Press **Make admin** beside `member2@example.com`. The table refreshes. Read
   that trace: `access_check`, `role_check`, `role_input_check`, `target_lookup`,
   `last_admin_check [would_leave_none=False]`, `role_changed`. Five questions
   asked in a fixed order, then the one write.

## Unhappy paths (and things that look like one but are not)

1. **Not logged in.** Press **Forget the session** on the Log in tab, then Load
   accounts. The page says to log in first. The server's answer is 401.
2. **A member.** Log in as `member@example.com`, open Admin, press Load accounts:
   "Refused (403): you are logged in, but you are not an admin." Read the trace:
   it stops after `role_check [needed='admin', has='member', allowed=False]`.
   Nothing was listed.
3. **A member, with no buttons.** As the member, use **Send the request
   yourself**: give your own id (printed by `seed_demo`) and the role `admin`.
   Still 403, and the trace shows only `access_check` and `role_check`. The
   buttons were never the protection.
4. **An admin asking for nonsense.** Account id `99999`: 404. Role `wizard`: 400
   ("The role must be one of: member, admin."). Nothing changes either time.
5. **The last admin.** With `admin@example.com` as the only admin, ask to make
   it a member: 409, "That would leave no admin." Make `member2@example.com` an
   admin first and it works. The trace says why: `last_admin_check
   [would_leave_none=True]`.
6. **A role changed while someone is logged in.** Use two browser tabs. Tab A:
   log in as `member2@example.com`, Admin, Load accounts: 403. Tab B: log in as
   the admin and make member2 an admin. Back in Tab A, **without logging in
   again**, press Load accounts: it works. Reverse it (demote member2 in Tab B)
   and press Load accounts in Tab A once more: 403 again, on the same login.
7. **Things that are NOT permission failures:** an admin who has been switched
   off is "not logged in" (401), not "not allowed"
   (`test_an_admin_who_has_been_switched_off_is_not_logged_in`); and changing a
   role does not log the person out (`test_changing_a_role_does_not_log_the_person_out`).

## The planted bug (Fix)

`episodes/08-permissions/planted_bug.patch` deletes ONE line from `change_role`:
the call to `check_role`. The admin page still loads for admins. Every button
still works for admins. The list is still protected, because it has its own
`check_role`. Only the dangerous action lost its guard.

1. From the `auth/` folder: `patch -p1 < episodes/08-permissions/planted_bug.patch`
2. Run `python manage.py seed_demo` (backend folder) so you start from a known state.
3. Log in as `member@example.com`. Open Admin. Press **Load accounts**: still
   "Refused (403)". The list is fine. Looks safe.
4. Under **Send the request yourself**, enter the member's own id and the role
   `admin`, and press **Send**. It says the account **is now admin**. Press
   **Load accounts** again: the table appears. A plain member has just made
   themselves an admin, using the same login.
5. Read the trace of the Send: `access_check`, then straight to
   `role_input_check`. There is **no `role_check`**. In the healthy trace it is
   the second line.
6. Run `python manage.py test accounts -v 2`. Seven tests go red:
   `test_a_member_cannot_change_someone_elses_role`,
   `test_a_member_cannot_make_themselves_an_admin`,
   `test_a_member_cannot_remove_an_admin`,
   `test_a_member_asking_about_a_missing_account_still_gets_403_not_404`,
   `test_a_member_sending_nonsense_still_gets_403`,
   `test_changing_a_role_shows_every_step`, and
   `test_the_permission_is_checked_before_the_request_is_looked_at`.
7. Fix: `patch -R -p1 < episodes/08-permissions/planted_bug.patch`, run the
   tests, remove any `.orig` or `.rej` file `patch` left, `git status` is clean.
   Run `seed_demo` once more to undo the damage to the demo accounts.

## Talking points

- **Test the refusals.** A happy-path test cannot see this bug: an admin who
  changes a role works with or without the check. Only a test that says "a
  member must be refused" can. Every protected action needs one of those, and
  writing it is the habit that matters most in this episode.
- **Why an AI-assisted build gets this wrong.** Ask for "an admin page" and you
  will usually get one that works for admins. Whether it refuses everyone else
  is a separate requirement, and it is only true if somebody wrote it down and
  tested it.
- **The server decides.** Whatever the page hides, shows or disables is for the
  person's convenience. If the answer to "what stops a script?" is "the page
  does not show the button", nothing stops it.

## Known limits (this episode)

- **Two roles only.** Real systems grow more, and then a list of permissions
  (can_edit_prices, can_refund) is clearer than a ladder of roles.
- **Nothing about individual records.** "Can this member edit THIS order?" is a
  different question (per-object permission) and needs its own check.
- **No record of who changed a role, or when.** A real system keeps an audit log
  of every change. That is the first thing to add.
- **No second check for a sensitive change.** Real sites ask for the password
  (or a code) again before making someone an admin.
- **Changing a role does not end their logins.** The role is read live, so it is
  not needed for permissions, but a security-conscious site may also want to
  end a demoted admin's sessions (episode 5's "log out everywhere").

## Test

`python manage.py test accounts` (236 tests now). New file `test_permissions.py`,
41 tests, run with `python manage.py test accounts.test_permissions -v 2` to see
every name. Episodes 3, 4 and 7 each had one test updated, because `/me` now also
returns the role.
