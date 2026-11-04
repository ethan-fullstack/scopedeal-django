from datetime import datetime
from datetime import timezone as datetime_timezone

from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac

from apps.accounts.models import RegistrationAttemptBucket


@transaction.atomic
def registration_allowed(remote_address):
    now = timezone.now()
    window = int(now.timestamp()) // 300
    key = salted_hmac("registration", f"{remote_address}:{window}", algorithm="sha256").hexdigest()
    RegistrationAttemptBucket.objects.filter(expires_at__lt=now).delete()
    bucket, _ = RegistrationAttemptBucket.objects.select_for_update().get_or_create(
        key=key,
        defaults={
            "expires_at": datetime.fromtimestamp((window + 1) * 300, tz=datetime_timezone.utc)
        },
    )
    if bucket.attempts >= 10:
        return False
    bucket.attempts += 1
    bucket.save(update_fields=["attempts"])
    return True
