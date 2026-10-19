# Dodaje zakładkę "Najważniejsze" (pierwsza, domyślnie otwarta) do stron w strona/<id>/index.html
import re, sys, json
BASE = "/home/user/repozytorium/strona/"
CSS = """
/* najważniejsze */
.key{background:var(--surface);border:1px solid var(--line);border-left:8px solid var(--c);border-radius:14px;padding:12px 16px 10px;margin:0 0 14px}
.key h2{font-size:21px;color:var(--c);margin-bottom:4px}
.key ol{margin:4px 0;padding-left:22px}
.key li{margin:5px 0}
.key li::marker{color:var(--c);font-weight:700}
.top3{background:var(--nav);color:var(--navInk);border-radius:14px;padding:14px 16px;margin:0 0 18px}
.top3 h2{font-size:21px;margin-bottom:6px}
.top3 ol{margin:0;padding-left:22px}
.top3 li{margin:5px 0}
"""
def build(page):
    d = json.load(open(sys.argv[1], encoding="utf-8"))[page]
    p = BASE + page + "/index.html"
    s = open(p, encoding="utf-8").read()
    if 'id="najwazniejsze"' in s:
        print(page, "już ma"); return
    m = re.search(r'const COL = \{([^}]*)\}', s)
    col = {int(k): int(v) for k, v in (x.split(":") for x in m.group(1).split(","))} if m else None
    c = lambda n: f"var(--t{col[n] if col else n})"
    h = '<!-- ============ NAJWAŻNIEJSZE ============ -->\n<section class="tab" id="najwazniejsze">\n'
    h += f'  <p class="intro">{d["intro"]}</p>\n'
    h += '  <div class="top3"><h2>Jeśli zapamiętasz tylko tyle</h2><ol>' + "".join(f"<li>{x}</li>" for x in d["top"]) + "</ol></div>\n"
    for n, title, pts in d["topics"]:
        h += f'  <div class="key" style="--c:{c(n)}"><h2>{n}. {title}</h2><ol>' + "".join(f"<li>{x}</li>" for x in pts) + "</ol></div>\n"
    h += "</section>\n\n"
    R = [
        ("</style>", CSS + "</style>"),
        ('<button role="tab" aria-selected="true" data-tab="notatka">Notatka</button>',
         '<button role="tab" aria-selected="true" data-tab="najwazniejsze">Najważniejsze</button>\n  <button role="tab" aria-selected="false" data-tab="notatka">Notatka</button>'),
        ('<section class="tab" id="notatka">', '<section class="tab" id="notatka" hidden>'),
        ("<!-- ============ NOTATKA ============ -->", h + "<!-- ============ NOTATKA ============ -->"),
    ]
    for a, b in R:
        assert s.count(a) == 1, (page, a); s = s.replace(a, b)
    open(p, "w", encoding="utf-8").write(s); print(page, "ok")
for page in sys.argv[2:]: build(page)
