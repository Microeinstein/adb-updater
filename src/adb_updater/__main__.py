
import sys, asyncio

from .updater import Updater


def main():
    err = asyncio.run(Updater().main(*sys.argv)) or 0
    sys.exit(err)

if __name__ == '__main__':
    main()
