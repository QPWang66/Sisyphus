import sys


def cli():
    if "--check" in sys.argv:
        from .check import check
        check()
    else:
        from .app import main
        main()


if __name__ == "__main__":
    cli()
