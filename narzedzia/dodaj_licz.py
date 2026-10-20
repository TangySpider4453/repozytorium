# Dodaje zakładkę „Licz” (zadania rachunkowe z losowymi liczbami) do strony sprawdzianu.
# Generatory: narzedzia/licz/<id>.js -> kopiowane do strona/<id>/licz-zadania.js; silnik: strona/licz.js.
# Użycie: python3 narzedzia/dodaj_licz.py <id> [<id> ...]   (z katalogu repozytorium; strona musi mieć już postep.js)
import shutil, sys

CSS = """
/* zakładka Licz */
.lz-tresc{font-size:17.5px;line-height:1.5;margin:4px 0 12px}
.lz-pole{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:8px 0;font-weight:700}
.lz-pole input{font:inherit;font-weight:400;font-size:18px;width:min(220px,60vw);padding:8px 10px;border:2px solid var(--line);border-radius:10px;background:var(--bg);color:var(--ink)}
.lz-pole input:focus{border-color:var(--c);outline:none}
.lz-pole.lz-ok input{border-color:var(--ok);background:color-mix(in srgb,var(--ok) 12%,var(--surface))}
.lz-pole.lz-zle input{border-color:var(--bad);background:color-mix(in srgb,var(--bad) 10%,var(--surface))}
.lz-j{font-weight:400;color:var(--muted)}
.lz-kroki{margin:8px 0 0;padding-left:20px}
.lz-kroki li{margin:5px 0}
.lz-pasek{display:flex;justify-content:space-between;font-size:15px;color:var(--muted);margin:0 0 10px}
.lz-pasek b{color:var(--ink)}
.lz-wybor{margin:0 0 12px}
.lz-wybor summary{cursor:pointer;font-size:15.5px;padding:8px 12px;border:1px solid var(--line);border-radius:10px;background:var(--surface);list-style:none}
.lz-wybor summary::-webkit-details-marker{display:none}
.lz-wybor summary span{color:var(--muted)}
.lz-wybor[open] summary{margin-bottom:10px}
"""

def add(pid):
    p = f"strona/{pid}/index.html"
    s = open(p, encoding="utf-8").read()
    shutil.copy(f"narzedzia/licz/{pid}.js", f"strona/{pid}/licz-zadania.js")
    if 'id="licz"' in s:
        print(pid, "zakładka już jest, odświeżono generatory"); return
    assert "postep.js" in s, "najpierw narzedzia/dodaj_postep.py"
    def rep(a, b):
        nonlocal s
        assert s.count(a) == 1, (pid, a[:60], s.count(a))
        s = s.replace(a, b)
    rep("</style>", CSS + "</style>")
    rep('<script src="../postep.js"></script>', '<script src="../postep.js"></script>\n<script src="../licz.js"></script>')
    rep('data-tab="wzory">Wzory</button>', 'data-tab="wzory">Wzory</button>\n  <button role="tab" aria-selected="false" data-tab="licz">Licz</button>')
    rep("<!-- ============ FISZKI ============ -->",
        '<!-- ============ LICZ ============ -->\n<section class="tab" id="licz" hidden><div id="liczBox"></div></section>\n\n<!-- ============ FISZKI ============ -->')
    rep("</body>", '<script src="licz-zadania.js"></script>\n</body>')
    open(p, "w", encoding="utf-8").write(s)
    print(pid, "ok")

for pid in sys.argv[1:]:
    add(pid)
