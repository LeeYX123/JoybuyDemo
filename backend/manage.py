#!/usr/bin/env python
import os
import sys
from pathlib import Path


def main() -> None:
    os.chdir(Path(__file__).resolve().parent)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    if "test" in sys.argv:
        # Tests must be hermetic: a developer/prod .env may set MEDIA_BACKEND=s3,
        # and unit tests must never upload objects to the real bucket. S3-mode
        # tests opt back in via override_settings(MEDIA_BACKEND="s3").
        os.environ["MEDIA_BACKEND"] = "local"
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django is not installed. Install backend/requirements/dev.txt first."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
