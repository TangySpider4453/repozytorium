"""python -m trener <polecenie>: sync | historia | dzien RRRR-MM-DD | serwer | analiza [rano|tydzien] | plan | cykl | kod"""
import json
import logging
import sys


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("garminconnect").setLevel(logging.WARNING)
    a = sys.argv[1:] or ["sync"]
    if a[0] == "sync":
        from .sync import sync
        sync()
    elif a[0] == "historia":
        from .sync import historia
        historia(a[1] if len(a) > 1 else None)
    elif a[0] == "dzien":
        from . import baza
        print(json.dumps(baza.dzien(baza.polacz(), a[1]), ensure_ascii=False, indent=1))
    elif a[0] == "cykl":
        from .cykl import cykl
        cykl()
    elif a[0] == "analiza":
        from .analiza import analizuj
        print(analizuj(a[1] if len(a) > 1 else "rano", wymus=True))
    elif a[0] == "plan":
        from .plan import zaplanuj
        print(zaplanuj(powod=" ".join(a[1:]) or "ręcznie"))
    elif a[0] == "kod":
        from .web import nowy_kod
        print(nowy_kod())
    elif a[0] == "serwer":
        from .web import app
        app.run(host="127.0.0.1", port=8095, threaded=True)
    else:
        print(__doc__)


main()
