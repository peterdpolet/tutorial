"""
Put three demo accounts into a known state, so a walkthrough always starts the same.

    python manage.py seed_demo

  admin@example.com     an admin
  member@example.com    a member
  member2@example.com   a member

All three are active, share the password below, have no two-factor and no lock.
Run it again at any time to put things back: it is safe to repeat. It is for
filming and for following an episode; it never touches any other account.

Development only: it refuses to run unless DEBUG is on, because it sets known
passwords.
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from accounts.models import AccountRole, LoginLock, RecoveryCode, RefreshToken, TotpDevice

User = get_user_model()

PASSWORD = "demo-password-55"
PEOPLE = [
    ("admin@example.com", "admin"),
    ("member@example.com", "member"),
    ("member2@example.com", "member"),
]


class Command(BaseCommand):
    help = "Create or reset three demo accounts (development only)."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs while DEBUG is on.")
        for email, role in PEOPLE:
            user, _ = User.objects.get_or_create(username=email, defaults={"email": email})
            user.email = email
            user.is_active = True
            user.set_password(PASSWORD)
            user.save()
            AccountRole.objects.update_or_create(user=user, defaults={"role": role})
            TotpDevice.objects.filter(user=user).delete()
            RecoveryCode.objects.filter(user=user).delete()
            RefreshToken.objects.filter(user=user).delete()
            LoginLock.objects.filter(email=email).delete()
            self.stdout.write(f"id {user.pk:<4} {email:22} {role}")
        self.stdout.write(f"Password for all three: {PASSWORD}")
