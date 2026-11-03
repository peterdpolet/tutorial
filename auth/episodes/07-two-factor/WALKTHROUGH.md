# Episode 7: the walkthrough card

One page to keep beside you while you run it. Do one step, check the result,
then go on. The full explanation is in `README.md`; this is only the order and
what you should see.

You need two things open: the browser (http://localhost:5273) and a terminal in
`backend/` with the virtual environment on. Tick **Trace these requests** on
every form.

To start from a known state at any point: `python manage.py forget_totp --email you@example.com`
(removes the secret and the recovery codes), and `python manage.py clear_locks`.
(From episode 8 on, `python manage.py seed_demo` resets three demo accounts in
one go.)

## 1. Turn it on

| Do | You should see |
|---|---|
| Log in with the password. | "Logged in". No code asked: it is off. |
| Press **Set up two-factor**. | A 32-character secret, shown once. |
| Terminal: `python manage.py show_code --email you@example.com` | Six digits, and "changes in N seconds". |
| Type the digits. Press **Switch it on**. | "Two-factor is on" and **8 recovery codes**. Copy them now: they are never shown again. |
| Trace the setup and the confirm. | The secret and the codes are `[REDACTED]`. `recovery_issued [count=8]`. |

## 2. Log in with a code (the normal path)

| Do | You should see |
|---|---|
| **Forget the session.** Log in with the password only. | The page changes to **Enter your code**. |
| Trace the login. | `second_step_check [required=True]`, `second_step_started`. No `failures_reset`, no `tokens_issued`. |
| Run `show_code`. If it is the code you just used, wait for the next one. Type it. | Logged in. |
| Trace the code step. | `totp_check [matched=True, replayed=False, claimed=1]`, then `failures_reset`, `tokens_issued`. |

## 3. The unhappy paths, one at a time

**A wrong code.** Type `000000`. "That code is not right." The trace ends at
`failure_recorded [failures=1]`. No tokens.

**The same code twice.** Easiest with no timing: in a Django shell, submit one
fresh code twice (the first call returns True, the second False). In the
browser: log in, copy a code, use it, log out, log in again, paste the SAME
digits. Refused. The trace says `matched=True, replayed=True, claimed=0`.
If it says `matched=False`, the digits had gone stale (a code lasts about 60 to
90 seconds), not a bug.

**A recovery code.** At **Enter your code**, type one instead of six digits
(`xxxxx-xxxxx`). Logged in. Trace: `recovery_check [used=True, codes_left=7]`.
Log out, log in, type the SAME one again: refused, `used=False`, and it counts
as a failure. Each use takes one off: `codes_left` counts the ones still unused.

**The lock.** At **Enter your code**, type a wrong code until the page says
"Too many failed attempts. Try again in 15 minute(s)." (five failures in all,
counting any earlier ones). Trace: `lock_check [locked=True, failures=0]` and
nothing after it. Now log in with the RIGHT password: the same 429, and the
trace stops at `lock_check`. (`failures=0` is correct: when the fifth failure
sets the lock, the count restarts, and the lock is judged by the clock.)
Clear it: `python manage.py clear_locks`.

**Taking too long.** Optional: set `MFA_TOKEN_SECONDS = 10` in `settings.py`,
log in with the password, wait, type the code: "That took too long." Put it back.

## 4. The planted bug

1. From `auth/`: `patch -p1 < episodes/07-two-factor/planted_bug.patch`
2. Five times: log in with the password, type a WRONG code, press **Start again**.
3. Log in with the password a sixth time. You get the code form. It should have
   locked.
4. Trace that password step: `failures_reset` now sits BEFORE `second_step_check`.
5. From `backend/`: `python manage.py test accounts -v 2`. Four red:
   `test_logging_in_again_with_the_password_does_not_reset_the_count`,
   `test_a_good_code_wipes_the_failure_count`,
   `test_the_password_step_stops_before_wiping_the_failure_count`,
   and episode 3's `test_the_trace_shows_the_steps_and_decisions`.
6. From `auth/`: `patch -R -p1 < episodes/07-two-factor/planted_bug.patch`
   (if it says "Unreversed patch detected", it is already reversed: answer `n`
   and delete any `.rej` and `.orig` file it made). Run the tests: all green.
   `git status` clean.

Stop the two servers when you finish (Ctrl-C in each terminal).
