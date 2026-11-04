from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.db.models.functions import Lower


class AccountManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields["role"] = "DEVELOPER"
        extra_fields["client"] = None
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    role = models.CharField(
        max_length=12,
        choices=[("CLIENT", "Cliente"), ("DEVELOPER", "Desarrollador")],
        default="CLIENT",
    )
    client = models.ForeignKey("clients.Client", null=True, blank=True, on_delete=models.PROTECT)
    email = models.EmailField()
    objects = AccountManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="unique_email_ci"),
            models.CheckConstraint(
                condition=models.Q(role="CLIENT", client__isnull=False)
                | models.Q(role="DEVELOPER", client__isnull=True),
                name="user_role_client",
            ),
        ]


class RegistrationAttemptBucket(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    attempts = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)
