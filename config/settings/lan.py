from .base import *  # noqa: F403
from .base import ALLOWED_HOSTS as BASE_ALLOWED_HOSTS

ALLOWED_HOSTS = [
    *BASE_ALLOWED_HOSTS,
    *(f"192.168.1.{host}" for host in range(1, 255)),
]
