"""
Make an existing account an admin (or a member again).

    python manage.py make_admin --email you@example.com
    python manage.py make_admin --email you@example.com --member

Someone has to be the FIRST admin, and the admin page cannot do it (you must
already be an admin to use it). So the first one is made here, on the machine,
by whoever runs the server. That is the usual answer: the first key is handed
over in person.
"""
from django.core.management.base import BaseCommand, CommandError

from django.contrib.auth import get_user_model

from accounts.models import AccountRole

User = get_user_model()


class Command(BaseCommand):
    help = "Give an account the admin role (or take it back with --member)."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--member", action="store_true", help="make them a plain member instead")

    def handle(self, *args, email, member, **options):
        user = User.objects.filter(username=email.strip().lower()).first()
        if user is None:
            raise CommandError("No account with that address.")
        role = "member" if member else "admin"
        AccountRole.objects.update_or_create(user=user, defaults={"role": role})
        self.stdout.write(f"{user.username} is now {role}.")
