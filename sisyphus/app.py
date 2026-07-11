"""Platform dispatch for the desktop window."""
import sys


def main():
    if sys.platform == "darwin":
        from .app_mac import main as run
    else:
        from .app_win import main as run
    run()
