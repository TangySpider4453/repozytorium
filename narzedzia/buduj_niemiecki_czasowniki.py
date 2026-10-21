# Buduje strona/niemiecki-czasowniki-nieregularne-1-23/ (kartkówka 2026-10-28) z tabeli w podręczniku, s. 130, poz. 1–23.
# Do nauki: Infinitiv, Partizip Perfekt (z haben/sein) i znaczenie, BEZ Präteritum (tak chciał użytkownik).
# Baza: szablon strony z fizyki sprzed podłączenia postępów (git b3e42a8); potem dodaj_postep.py i dodaj_licz.py.
# Użycie (z katalogu repo): python3 narzedzia/buduj_niemiecki_czasowniki.py <plik_bazowy.html>
import json, os, random, re, sys

ID = "niemiecki-czasowniki-nieregularne-1-23"
random.seed(130)

# nr, Infinitiv, Partizip, posiłkowy, znaczenie, grupa (1 ge-…-en, 2 bez ge-, 3 mieszane ge-…-t)
V = [
 (1, "backen", "gebacken", "h", "piec", 1),
 (2, "befehlen", "befohlen", "h", "rozkazywać", 2),
 (3, "beginnen", "begonnen", "h", "zaczynać", 2),
 (4, "beißen", "gebissen", "h", "gryźć", 1),
 (5, "besitzen", "besessen", "h", "posiadać", 2),
 (6, "betrügen", "betrogen", "h", "oszukiwać", 2),
 (7, "biegen", "gebogen", "h", "giąć", 1),
 (7, "biegen", "gebogen", "s", "skręcać (w kierunku)", 1),
 (8, "bieten", "geboten", "h", "ofiarowywać, oferować", 1),
 (9, "binden", "gebunden", "h", "wiązać", 1),
 (10, "bitten", "gebeten", "h", "prosić", 1),
 (11, "bleiben", "geblieben", "s", "zostawać", 1),
 (12, "braten", "gebraten", "h", "smażyć", 1),
 (13, "brechen", "gebrochen", "h", "łamać", 1),
 (14, "brennen", "gebrannt", "h", "palić się, płonąć", 3),
 (15, "bringen", "gebracht", "h", "przynosić", 3),
 (16, "denken", "gedacht", "h", "myśleć", 3),
 (17, "dürfen", "gedurft", "h", "móc, mieć pozwolenie", 3),
 (18, "empfangen", "empfangen", "h", "przyjmować", 2),
 (19, "empfehlen", "empfohlen", "h", "polecać", 2),
 (20, "empfinden", "empfunden", "h", "czuć, odczuwać", 2),
 (21, "erschrecken", "erschrocken", "s", "przestraszyć się", 2),
 (22, "essen", "gegessen", "h", "jeść", 1),
 (23, "fahren", "gefahren", "s", "jechać", 1),
 (23, "fahren", "gefahren", "h", "wieźć", 1),
]
T = {1: "ge- … -en", 2: "bez ge- (be-, emp-, er-)", 3: "mieszane: ge- … -t"}
COL = {1: 6, 2: 3, 3: 4}
AUX = {"h": "hat", "s": "ist"}
ZLE = {  # wiarygodne błędne formy Partizip
 "backen": ["gebackt", "gebucken", "backen"], "befehlen": ["gebefohlen", "befehlt", "befahlen"],
 "beginnen": ["gebeginnt", "gebegonnen", "begann"], "beißen": ["gebeißt", "gebeißen", "gebisst"],
 "besitzen": ["gebesessen", "besitzt", "gesessen"], "betrügen": ["gebetrogen", "betrügt", "betrugen"],
 "biegen": ["gebiegt", "gebiegen", "gebogt"], "bieten": ["gebietet", "gebieten", "gebotet"],
 "binden": ["gebindet", "gebinden", "gebandet"], "bitten": ["gebittet", "gebitten", "gebatten"],
 "bleiben": ["gebleibt", "gebleiben", "geblibt"], "braten": ["gebratet", "gebrieten", "gebrotten"],
 "brechen": ["gebrecht", "gebrechen", "gebracht"], "brennen": ["gebrennt", "gebrannen", "gebronnen"],
 "bringen": ["gebringt", "gebrungen", "gebrangen"], "denken": ["gedenkt", "gedachen", "gedunken"],
 "dürfen": ["gedürft", "gedurfen", "gedarft"], "empfangen": ["geempfangen", "empfangt", "empfingen"],
 "empfehlen": ["geempfohlen", "empfehlt", "empfahlen"], "empfinden": ["geempfunden", "empfindet", "empfanden"],
 "erschrecken": ["geerschrocken", "erschrecken", "erschracken"], "essen": ["geessen", "gegesst", "gessen"],
 "fahren": ["gefahrt", "gefuhren", "gefohren"],
}
WZOR = {  # krótka podpowiedź do zapamiętania
 "backen": "a zostaje: backen → gebacken", "befehlen": "e → o, bez ge- (be-)", "beginnen": "i → o, bez ge- (be-)",
 "beißen": "ei → i, ß → ss (krótkie i)", "besitzen": "i → e, bez ge- (be-)", "betrügen": "ü → o, bez ge- (be-)",
 "biegen": "ie → o", "bieten": "ie → o", "binden": "i → u", "bitten": "i → e", "bleiben": "ei → ie, z sein",
 "braten": "a zostaje", "brechen": "e → o", "brennen": "mieszany: e → a, końcówka -t", "bringen": "mieszany: zupełnie inny rdzeń (brach-)",
 "denken": "mieszany: dach-, końcówka -t", "dürfen": "mieszany: bez umlautu, -t", "empfangen": "Partizip = bezokolicznik (emp-, bez ge-)",
 "empfehlen": "e → o, bez ge- (emp-)", "empfinden": "i → u, bez ge- (emp-)", "erschrecken": "e → o, bez ge- (er-), z sein",
 "essen": "uwaga: ge-g-essen (dodatkowe g!)", "fahren": "a zostaje; jechać = ist, wieźć = hat",
}

def js(x):
    return json.dumps(x, ensure_ascii=False)

def verbs():  # unikalne bezokoliczniki
    seen = {}
    for v in V:
        seen.setdefault(v[1], []).append(v)
    return seen

VS = verbs()
def de_back(inf):
    rows = VS[inf]
    return " · ".join(f"{AUX[r[3]]} {r[2]} – {r[4]}" for r in rows)

# ---------- fiszki ----------
FC = []
for inf, rows in VS.items():
    FC.append([rows[0][5], inf, de_back(inf)])
for r in V:
    FC.append([r[5], r[4], f"{r[1]} – {AUX[r[3]]} {r[2]}"])

# ---------- quiz ----------
Q = []
for inf, rows in VS.items():
    r = rows[0]
    Q.append([r[5], f"Partizip Perfekt od „{inf}” to:", [r[2]] + ZLE[inf], 0, f"{inf} → {r[2]}. {WZOR[inf]}."])
meanings = [r[4] for r in V]
for inf, rows in VS.items():
    good = " / ".join(r[4] for r in rows)
    pool = [m for m in meanings if m not in [r[4] for r in rows]]
    Q.append([rows[0][5], f"Co znaczy „{inf}”?", [good] + random.sample(pool, 3), 0, f"{inf} – {good}."])
for r in V:
    pool = [x for x in VS if x != r[1]]
    Q.append([r[5], f"Jak po niemiecku „{r[4]}”?", [r[1]] + random.sample(pool, 3), 0, f"{r[4]} – {r[1]}, Partizip: {AUX[r[3]]} {r[2]}."])
ZDANIA = [
 (1, "Ich ___ zu Hause geblieben.", ["bin", "habe", "ist", "hat"], "bleiben łączy się z sein: ich bin geblieben."),
 (1, "Wir ___ mit dem Bus nach Krakau gefahren.", ["sind", "haben", "seid", "habt"], "fahren = jechać → sein: wir sind gefahren."),
 (1, "Er ___ seine Freundin nach Hause gefahren.", ["hat", "ist", "habt", "sind"], "fahren = wieźć kogoś → haben: er hat … gefahren."),
 (2, "Sie ___ sehr erschrocken.", ["ist", "hat", "sind", "haben"], "erschrecken (przestraszyć się) → sein: sie ist erschrocken."),
 (1, "Das Auto ___ um die Ecke gebogen.", ["ist", "hat", "sind", "haben"], "biegen = skręcać → sein."),
 (1, "Der Mechaniker ___ das Rohr gebogen.", ["hat", "ist", "haben", "sind"], "biegen = giąć coś → haben."),
 (1, "Wir ___ Pizza gegessen.", ["haben", "sind", "hat", "ist"], "essen → haben: wir haben gegessen."),
 (2, "Der Film ___ um acht Uhr begonnen.", ["hat", "ist", "haben", "sind"], "beginnen → haben (mimo że to „zaczynać się”)."),
 (1, "Ich ___ einen Kuchen gebacken.", ["habe", "bin", "hat", "ist"], "backen → haben."),
 (3, "Du ___ mir Blumen gebracht.", ["hast", "bist", "hat", "ist"], "bringen → haben: du hast gebracht."),
]
for n, zd, opts, ex in ZDANIA:
    Q.append([n, f"Uzupełnij (haben czy sein?): {zd}", opts, 0, ex])

# ---------- pytania otwarte ----------
OQ = [
 [2, "Wymień czasowniki z tej listy, które w Partizip Perfekt NIE mają ge-. Dlaczego?",
  ["befehlen → befohlen, beginnen → begonnen, besitzen → besessen, betrügen → betrogen",
   "empfangen → empfangen, empfehlen → empfohlen, empfinden → empfunden, erschrecken → erschrocken",
   "Mają nieakcentowany przedrostek <b>be-, emp-, er-</b>. Takie czasowniki nigdy nie dostają ge-."]],
 [1, "Które czasowniki z listy tworzą Perfekt z <b>sein</b>?",
  ["<b>bleiben</b> → ist geblieben", "<b>erschrecken</b> (przestraszyć się) → ist erschrocken",
   "<b>fahren</b> (jechać) → ist gefahren, ale wieźć kogoś → hat gefahren",
   "<b>biegen</b> (skręcać) → ist gebogen, ale giąć coś → hat gebogen", "Wszystkie pozostałe: <b>haben</b>."]],
 [3, "Które czasowniki są „mieszane” (ge- … -t, ale ze zmianą rdzenia)?",
  ["brennen → gebrannt", "bringen → gebracht", "denken → gedacht", "dürfen → gedurft"]],
 [1, "Podaj Partizip Perfekt i znaczenie: bitten, bieten, binden, beißen.",
  ["bitten → gebeten (prosić)", "bieten → geboten (oferować)", "binden → gebunden (wiązać)", "beißen → gebissen (gryźć)",
   "Uważaj, żeby ich nie pomylić: bitten/bieten, gebeten/geboten."]],
 [1, "Podaj Partizip Perfekt: essen, brechen, braten, backen.",
  ["essen → <b>gegessen</b> (z dodatkowym g!)", "brechen → gebrochen", "braten → gebraten", "backen → gebacken"]],
 [2, "Przetłumacz i podaj Partizip: polecać, przyjmować, czuć, posiadać.",
  ["polecać – empfehlen – hat empfohlen", "przyjmować – empfangen – hat empfangen",
   "czuć – empfinden – hat empfunden", "posiadać – besitzen – hat besessen"]],
]

# ---------- zakładka Najważniejsze ----------
def li(xs): return "".join(f"<li>{x}</li>" for x in xs)
NAJ = f'''<!-- ============ NAJWAŻNIEJSZE ============ -->
<section class="tab" id="najwazniejsze">
  <p class="intro">Kartkówka 28 października: podręcznik s. 130, czasowniki 1–23. Uczysz się <b>bezokolicznika, Partizip Perfekt (z haben/sein) i znaczenia</b>. Präteritum nie obowiązuje.</p>
  <div class="top3"><h2>Jeśli zapamiętasz tylko tyle</h2><ol>{li([
   "Zwykle: <b>ge- + zmieniony rdzeń + -en</b>: binden → gebunden, bitten → gebeten, brechen → gebrochen.",
   "Przedrostek <b>be-, emp-, er-</b> → <b>bez ge-</b>: begonnen, empfohlen, erschrocken (empfangen = empfangen).",
   "Z <b>sein</b>: bleiben, erschrecken, fahren (jechać), biegen (skręcać). Reszta z <b>haben</b>."])}</ol></div>
  <div class="key" style="--c:var(--t6)"><h2>1. ge- … -en</h2><ol>{li([
   "a zostaje: backen → gebacken, braten → gebraten, fahren → gefahren",
   "ie → o: biegen → gebogen, bieten → geboten; e → o: brechen → gebrochen",
   "i → u: binden → gebunden; i → e: bitten → gebeten; ei → ie: bleiben → geblieben",
   "ei → i: beißen → gebi<b>ss</b>en (po krótkim i piszemy ss)",
   "<b>essen → gegessen</b> – dodatkowe g w środku!"])}</ol></div>
  <div class="key" style="--c:var(--t3)"><h2>2. bez ge- (be-, emp-, er-)</h2><ol>{li([
   "befehlen → befohlen, empfehlen → empfohlen (e → o)", "beginnen → begonnen (i → o)", "besitzen → besessen (i → e)",
   "betrügen → betrogen (ü → o)", "empfinden → empfunden (i → u), empfangen → empfangen (bez zmian)",
   "erschrecken → <b>ist</b> erschrocken (przestraszyć się)"])}</ol></div>
  <div class="key" style="--c:var(--t4)"><h2>3. mieszane: ge- … -t</h2><ol>{li([
   "brennen → gebrannt (palić się)", "bringen → gebracht (przynosić)", "denken → gedacht (myśleć)", "dürfen → gedurft (móc)",
   "Końcówka -t jak w regularnych, ale rdzeń się zmienia."])}</ol></div>
  <div class="key" style="--c:var(--nav)"><h2>Uważaj na pary</h2><ol>{li([
   "<b>bitten</b> (prosić) → gebeten ≠ <b>bieten</b> (oferować) → geboten",
   "<b>brechen</b> (łamać) → gebrochen ≠ <b>bringen</b> (przynosić) → gebracht",
   "<b>fahren</b>: ich <b>bin</b> nach Berlin gefahren (jechałem), ich <b>habe</b> sie gefahren (wiozłem ją)",
   "<b>biegen</b>: das Auto <b>ist</b> um die Ecke gebogen (skręciło), er <b>hat</b> das Rohr gebogen (wygiął)"])}</ol></div>
</section>
'''
rows = "".join(
    f'<tr><td>{r[0]}.</td><td class="c-inf"><span>{r[1]}</span></td><td class="c-pp"><span>{AUX[r[3]]} {r[2]}</span></td><td class="c-pl"><span>{r[4]}</span></td></tr>'
    for r in V)
TAB = f'''<!-- ============ TABELA ============ -->
<section class="tab" id="tabela" hidden>
  <p class="intro">Zasłoń kolumnę i odpowiadaj z pamięci. Dotknięcie zasłoniętej komórki ją odsłania. „ist” = Perfekt z sein, „hat” = z haben.</p>
  <div class="row" style="margin-bottom:10px"><button class="btn" data-hide="c-inf">Zasłoń bezokolicznik</button><button class="btn" data-hide="c-pp">Zasłoń Partizip</button><button class="btn" data-hide="c-pl">Zasłoń znaczenie</button><button class="btn" data-hide="">Pokaż wszystko</button></div>
  <div class="tablewrap"><table class="czas"><tr><th>nr</th><th>Infinitiv</th><th>Partizip Perfekt</th><th>znaczenie</th></tr>{rows}</table></div>
</section>
'''
TAB_CSS = """
/* tabela czasowników */
table.czas{min-width:0}
table.czas td.c-inf,table.czas td.c-pp{font-weight:700}
table.czas td.zakryte span{visibility:hidden}
table.czas td.zakryte{background:var(--soft);cursor:pointer}
"""
TAB_JS = """
/* ---------- tabela: zasłanianie kolumn ---------- */
document.querySelectorAll("[data-hide]").forEach(b=>b.addEventListener("click",()=>{
  document.querySelectorAll("table.czas td").forEach(td=>td.classList.toggle("zakryte",!!b.dataset.hide&&td.classList.contains(b.dataset.hide)));
}));
document.querySelector("table.czas").addEventListener("click",e=>{const td=e.target.closest("td.zakryte");if(td)td.classList.remove("zakryte")});
"""
NAV = '''<nav class="tabs" aria-label="Sekcje"><div class="wrap" role="tablist">
  <button role="tab" aria-selected="true" data-tab="najwazniejsze">Najważniejsze</button>
  <button role="tab" aria-selected="false" data-tab="tabela">Tabela</button>
  <button role="tab" aria-selected="false" data-tab="fiszki">Fiszki</button>
  <button role="tab" aria-selected="false" data-tab="quiz">Quiz</button>
  <button role="tab" aria-selected="false" data-tab="otwarte">Pytania</button>
</div></nav>'''

def main(base):
    s = open(base, encoding="utf-8").read()
    def cut(a, b, new):
        nonlocal s
        i, j = s.index(a), s.index(b)
        assert i < j, (a, b)
        s = s[:i] + new + s[j:]
    def rep(a, b):
        nonlocal s
        assert s.count(a) == 1, a[:60]
        s = s.replace(a, b)
    s = re.sub(r"<title>.*?</title>", "<title>Niemiecki – czasowniki nieregularne 1–23</title>", s, count=1)
    s = re.sub(r"<h1>.*?</h1>", "<h1>Czasowniki nieregularne 1–23</h1>", s, count=1)
    s = re.sub(r"(<h1>.*?</h1>\s*<p>).*?(</p>)", r"\1Niemiecki, kartkówka śr. 28 października. Podręcznik s. 130: Infinitiv, Partizip Perfekt, znaczenie\2", s, count=1, flags=re.S)
    cut('<nav class="tabs"', "</div></nav>", NAV[:-len("</div></nav>")])
    cut("<!-- ============ NAJWAŻNIEJSZE ============ -->", "<!-- ============ FISZKI ============ -->", NAJ + "\n" + TAB + "\n")
    rep("</style>", TAB_CSS + "</style>")
    rep('<p class="intro">Pytania teoretyczne i zadania rachunkowe w stylu kartkówki. Najpierw rozwiąż sam(a), potem rozwiń rozwiązanie.</p>',
        '<p class="intro">Pytania podsumowujące. Najpierw odpowiedz sam(a), potem rozwiń odpowiedź.</p>')
    s = re.sub(r"const T = \{[^}]*\};", "const T = " + js({str(k): v for k, v in T.items()}) + ";", s, count=1)
    s = re.sub(r"const COL = \{[^}]*\};", "const COL = " + js({str(k): v for k, v in COL.items()}) + ";", s, count=1)
    cut("const FC=[", "let deck=", "const FC=" + js(FC).replace("],[", "],\n [") + ";\n")
    cut("const Q=[", "let qs=", "const Q=" + js(Q).replace("],[", "],\n [") + ";\n")
    cut("const OQ=[", 'document.getElementById("oqList")', "const OQ=" + js(OQ).replace("],[", "],\n [") + ";\n")
    s = s.replace("nauka:fizyka-pole-elektryczne:best_", f"nauka:{ID}:best_")
    s = s.replace("jesteś gotowy(-a) na sprawdzian", "jesteś gotowy(-a) na kartkówkę")
    i = s.rfind("</script>")
    s = s[:i] + TAB_JS + s[i:]
    os.makedirs(f"strona/{ID}", exist_ok=True)
    open(f"strona/{ID}/index.html", "w", encoding="utf-8").write(s)
    print("ok", ID, "fiszki", len(FC), "quiz", len(Q), "pytania", len(OQ))

if __name__ == "__main__":
    main(sys.argv[1])
