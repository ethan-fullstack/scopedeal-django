import os
import sys
from pathlib import Path

from django.core.management import execute_from_command_line
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

execute_from_command_line(sys.argv)
