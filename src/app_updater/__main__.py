
import sys, asyncio

from .updater import Updater


err = asyncio.run(Updater().main(*sys.argv)) or 0
sys.exit(err)
