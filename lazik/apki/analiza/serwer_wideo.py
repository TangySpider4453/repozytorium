#!/usr/bin/env python3
"""Strona do przesyłania filmów na Pi 5 (port 8080) i przeglądania raportów z telefonu, komputera lub tabletu.

Dostęp tylko z kodem: adres z kodem (?t=...) jest w kodzie QR w aplikacji „Łazik: analiza wideo”; po pierwszym
wejściu przeglądarka zapamiętuje go w ciasteczku. Plik idzie strumieniem prosto na kartę (bez /tmp w RAM-ie).
Usługa systemd: lazik-wideo.service.
"""

import html
import json
import os
import re
import secrets
import sys
import time

from flask import Flask, Response, abort, jsonify, make_response, redirect, request, send_from_directory

KATALOG = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KATALOG)
FILMY = os.path.join(KATALOG, "filmy")
RAPORTY = os.path.join(KATALOG, "raporty")
PLIK_KODU = os.path.join(KATALOG, "kod_dostepu.txt")
ROZSZERZENIA = (".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".3gp")
PORT = 8080


def kod_dostepu():
    if not os.path.exists(PLIK_KODU):
        with open(PLIK_KODU, "w") as f:
            f.write(secrets.token_urlsafe(8))
        os.chmod(PLIK_KODU, 0o600)
    return open(PLIK_KODU).read().strip()


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = None


def dozwolony():
    kod = kod_dostepu()
    return request.args.get("t") == kod or request.cookies.get("lazik_kod") == kod


@app.before_request
def sprawdz_kod():
    if not dozwolony():
        return Response("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
                        "<body style='font:18px system-ui;background:#0d1114;color:#e6ebee;padding:24px'>"
                        "<h2>Łazik: analiza wideo</h2><p>Zeskanuj kod QR z aplikacji na Pi, żeby wejść.</p>",
                        status=403, mimetype="text/html")


@app.after_request
def zapamietaj(resp):
    if request.args.get("t") == kod_dostepu():
        resp.set_cookie("lazik_kod", kod_dostepu(), max_age=365 * 24 * 3600, samesite="Lax")
    return resp


def bezpieczna_nazwa(n):
    n = os.path.basename(n).replace(" ", "_")
    n = re.sub(r"[^A-Za-z0-9._ąćęłńóśźżĄĆĘŁŃÓŚŹŻ-]", "", n)
    rdzen, rozsz = os.path.splitext(n)
    return (rdzen[:60] or "film") + rozsz.lower()


@app.put("/wyslij")
def wyslij():
    nazwa = bezpieczna_nazwa(request.args.get("nazwa", "film.mp4"))
    if not nazwa.lower().endswith(ROZSZERZENIA):
        abort(415, "To nie wygląda na film (mp4, mov, avi, mkv, webm, 3gp).")
    os.makedirs(FILMY, exist_ok=True)
    cel = os.path.join(FILMY, time.strftime("%Y-%m-%d_%H%M%S_") + nazwa)
    tymczasowy = os.path.join(FILMY, "." + os.path.basename(cel) + ".czesc")
    rozmiar = 0
    try:
        with open(tymczasowy, "wb") as f:
            while True:
                kawalek = request.stream.read(1 << 20)
                if not kawalek:
                    break
                f.write(kawalek)
                rozmiar += len(kawalek)
    except Exception:
        if os.path.exists(tymczasowy):
            os.remove(tymczasowy)
        raise
    if rozmiar == 0:
        os.remove(tymczasowy)
        abort(400, "Pusty plik.")
    os.rename(tymczasowy, cel)  # aplikacja widzi film dopiero, gdy jest cały
    return jsonify(ok=True, plik=os.path.basename(cel), mb=round(rozmiar / 1e6, 1))


@app.get("/raporty/<path:sciezka>")
def raporty(sciezka):
    return send_from_directory(RAPORTY, sciezka)


@app.get("/api/filmy")
def api_filmy():
    import analiza_wideo as A
    return jsonify([dict(nazwa=f["nazwa"], zrodlo=f["zrodlo"], mb=round(f["rozmiar_mb"], 1),
                         raport=os.path.relpath(os.path.join(f["raport"], "raport.html"), RAPORTY) if f["ma_raport"] else None)
                    for f in A.lista_filmow()])


@app.get("/")
def strona():
    return Response(STRONA, mimetype="text/html")


STRONA = """<!doctype html><html lang="pl" translate="no"><head><meta charset="utf-8">
<meta name="google" content="notranslate"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Łazik: wyślij film</title><style>
:root{--tlo:#0d1114;--panel:#161c21;--tekst:#e6ebee;--szary:#8b979f;--akcent:#e0a640;--ok:#3fbf6a;--linia:#232b31}
body{margin:0;background:var(--tlo);color:var(--tekst);font:17px/1.45 system-ui,"Segoe UI",sans-serif}
main{max-width:640px;margin:0 auto;padding:20px max(16px,env(safe-area-inset-left)) 40px;display:flex;flex-direction:column;gap:18px}
h1{font-size:24px;margin:0} p{margin:0} .szary{color:var(--szary);font-size:15px}
.wybor{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;background:var(--panel);border:2px dashed #3a4650;
border-radius:14px;padding:28px 16px;text-align:center;cursor:pointer;font-size:19px;font-weight:600}
.wybor input{display:none} .wybor small{font-weight:400;color:var(--szary);font-size:14px}
.plik{background:var(--panel);border:1px solid var(--linia);border-radius:12px;padding:12px 14px;display:flex;flex-direction:column;gap:6px}
.pasek{height:10px;background:#2a333a;border-radius:5px;overflow:hidden} .pasek i{display:block;height:100%;width:0;background:var(--akcent)}
.ok .pasek i{background:var(--ok)} .blad{color:#e5534b}
ul{list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:8px}
li{background:var(--panel);border:1px solid var(--linia);border-radius:10px;padding:10px 14px;display:flex;justify-content:space-between;gap:10px;align-items:center}
li span{min-width:0;overflow-wrap:anywhere} a{color:var(--akcent);font-weight:600;white-space:nowrap}
</style></head><body><main>
<h1>Łazik: wyślij film do analizy</h1>
<p class="szary">Film trafi na Pi 5. Analizę uruchamiasz w aplikacji „Łazik: analiza wideo”, a gotowy raport pojawi się niżej.</p>
<label class="wybor">Wybierz film albo nagraj nowy<small>mp4, mov, avi, mkv, webm · można kilka naraz</small>
<input id="pliki" type="file" accept="video/*" multiple></label>
<div id="kolejka" style="display:flex;flex-direction:column;gap:10px"></div>
<h2 style="font-size:19px;margin:6px 0 0">Filmy na Pi</h2><ul id="lista"><li class="szary">Wczytuję…</li></ul>
</main><script>
const kolejka = document.getElementById('kolejka');
document.getElementById('pliki').addEventListener('change', async e => {
  for (const plik of e.target.files) await wyslij(plik);
  e.target.value = ''; odswiez();
});
function wyslij(plik) {
  return new Promise(gotowe => {
    const el = document.createElement('div'); el.className = 'plik';
    el.innerHTML = `<b></b><div class="pasek"><i></i></div><span class="szary">Wysyłam…</span>`;
    el.querySelector('b').textContent = plik.name; kolejka.prepend(el);
    const pasek = el.querySelector('i'), opis = el.querySelector('span');
    const x = new XMLHttpRequest();
    x.open('PUT', '/wyslij?nazwa=' + encodeURIComponent(plik.name));
    const t0 = Date.now();
    x.upload.onprogress = ev => { if (!ev.lengthComputable) return;
      const p = ev.loaded / ev.total, mbs = ev.loaded / 1e6 / Math.max(0.1, (Date.now() - t0) / 1000);
      pasek.style.width = (100 * p).toFixed(1) + '%';
      opis.textContent = `${(ev.loaded / 1e6).toFixed(0)} z ${(ev.total / 1e6).toFixed(0)} MB · ${mbs.toFixed(1)} MB/s`; };
    x.onload = () => { if (x.status === 200) { el.classList.add('ok'); pasek.style.width = '100%';
        opis.textContent = 'Wysłane. Uruchom analizę w aplikacji na Pi.'; }
      else { opis.className = 'blad'; opis.textContent = 'Nie wysłano: ' + (x.responseText.replace(/<[^>]+>/g, ' ').trim().slice(0, 160) || x.status); }
      gotowe(); };
    x.onerror = () => { opis.className = 'blad'; opis.textContent = 'Przerwane połączenie: spróbuj jeszcze raz.'; gotowe(); };
    x.send(plik);
  });
}
async function odswiez() {
  const l = document.getElementById('lista');
  try {
    const filmy = await (await fetch('/api/filmy')).json();
    l.innerHTML = '';
    if (!filmy.length) { l.innerHTML = '<li class="szary">Jeszcze nic tu nie ma.</li>'; return; }
    for (const f of filmy) {
      const li = document.createElement('li'); const s = document.createElement('span');
      s.textContent = `${f.nazwa} · ${f.mb} MB · ${f.zrodlo}`; li.append(s);
      if (f.raport) { const a = document.createElement('a'); a.href = '/raporty/' + f.raport; a.textContent = 'Raport'; li.append(a); }
      else { const z = document.createElement('span'); z.className = 'szary'; z.textContent = 'bez raportu'; li.append(z); }
      l.append(li);
    }
  } catch (_) { l.innerHTML = '<li class="blad">Nie udało się pobrać listy.</li>'; }
}
odswiez(); setInterval(odswiez, 15000);
</script></body></html>"""


if __name__ == "__main__":
    kod_dostepu()
    app.run(host="0.0.0.0", port=PORT, threaded=True)
