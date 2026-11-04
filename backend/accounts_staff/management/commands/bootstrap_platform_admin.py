import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts_staff.models import PlatformRole, StaffAccount, StaffRoleAssignment
from accounts_staff.normalization import normalize_staff_email
from accounts_staff.services import provision_totp_device


class Command(BaseCommand):
    help = "Create the initial Joybuy platform administrator and provision TOTP."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--display-name", required=True)
        parser.add_argument("--password")

    def handle(self, *args, **options):
        email = normalize_staff_email(options["email"])
        if StaffAccount.objects.filter(email=email).exists():
            raise CommandError("A staff account with this email already exists.")

        password = options.get("password") or getpass.getpass("Password: ")
        validate_password(password)

        try:
            admin_role = PlatformRole.objects.get(code="platform_admin")
        except PlatformRole.DoesNotExist as exc:
            raise CommandError(
                "Run migrations before bootstrapping a platform administrator."
            ) from exc

        with transaction.atomic():
            staff = StaffAccount(email=email, display_name=options["display_name"])
            staff.set_password(password)
            staff.save()
            StaffRoleAssignment.objects.create(staff=staff, role=admin_role)
            _, secret, uri = provision_totp_device(staff)

        self.stdout.write(self.style.SUCCESS(f"Created platform administrator {email}."))
        self.stdout.write("Add this secret to the administrator's authenticator now:")
        self.stdout.write(secret)
        self.stdout.write(uri)
        self.stdout.write("The secret will not be displayed again by this command.")
