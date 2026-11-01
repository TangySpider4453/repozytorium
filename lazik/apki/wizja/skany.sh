#!/bin/bash
# Lista skanów 3D (ikona „Łazik: skany 3D”): buduje skany/index.html i otwiera go w Chromium.
cd "$(dirname "$0")"
mkdir -p skany
python3 - <<'PY'
import glob, html, json, os
wiersze = []
for info in sorted(glob.glob("skany/*/info.json"), reverse=True):
    d = json.load(open(info, encoding="utf-8"))
    n = os.path.basename(os.path.dirname(info))
    opis = html.escape(d.get("opis", "")).replace("\n", "<br>")
    wiersze.append(
                   f'<a class="skan" href="{n}/skan.html"><b>{html.escape(n)}</b>'
                   f'<span>{d.get("czas","")} · {d.get("punkty",0)} punktów · obrót {d.get("obrot_stopnie",0)}°</span>'
                   f'<small>{opis}</small></a>')
pusto = '<p class="pusto">Brak skanów. W aplikacji „Łazik: wizja” przełącz tryb na Przestrzeń, zrób skan i zapisz go.</p>'
open("skany/index.html", "w", encoding="utf-8").write(f"""<!doctype html><html lang="pl" translate="no"><head><meta charset="utf-8"><meta name="google" content="notranslate">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Łazik: skany 3D</title><style>
body{{margin:0;background:#0d1114;color:#e6ebee;font:16px/1.45 system-ui,sans-serif}}
main{{max-width:900px;margin:0 auto;padding:24px max(16px,env(safe-area-inset-left))}}
h1{{font-size:26px;margin:0 0 4px}} p{{color:#8b979f;margin:0 0 18px}}
.skan{{display:flex;flex-direction:column;gap:2px;background:#161c21;border-radius:10px;padding:14px 16px;margin-bottom:10px;
color:inherit;text-decoration:none;border:1px solid #232b31}} .skan:active,.skan:hover{{border-color:#e0a640}}
.skan span{{color:#8b979f;font-size:14px}} .skan small{{color:#b5c0c7;font-size:13px}}
.pusto{{padding:30px 0}} button{{position:fixed;right:12px;top:12px;width:52px;height:52px;border-radius:26px;border:0;
background:#2a333a;color:#e6ebee;font-size:24px;cursor:pointer}}
</style></head><body><button onclick="window.close()" title="Zamknij">✕</button><main><h1>Skany 3D</h1>
<p>Dotknij skanu, żeby po nim chodzić. Na komputerze skopiuj folder skanu i otwórz skan.html w przeglądarce.</p>
{''.join(wiersze) or pusto}</main></body></html>""")
PY
# pulpit Pi 5 to Wayland; bez tej flagi Chromium uruchomiony spoza sesji próbuje X11 i się nie otwiera
FLAGI=()
[ -n "$WAYLAND_DISPLAY" ] && FLAGI+=(--ozone-platform=wayland)
if command -v chromium >/dev/null; then
  exec chromium "${FLAGI[@]}" --app="file://$PWD/skany/index.html" --start-maximized >skany.log 2>&1
fi
exec firefox "file://$PWD/skany/index.html" >skany.log 2>&1
