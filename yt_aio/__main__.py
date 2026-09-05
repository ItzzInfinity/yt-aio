"""Entry point for `python -m yt_aio`.

The preflight runs first and the shell is imported only after it passes. Importing the
shell reaches PyQt on the third line, so checking afterwards would mean the check never
runs on exactly the machine that needs it.
"""

from .preflight import run as preflight


def main() -> int:
    if preflight() != 0:
        return 1

    from .application.shell import main as run_application

    return run_application()


if __name__ == "__main__":
    raise SystemExit(main())
