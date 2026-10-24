#!/usr/bin/env node
/* Sprawdzenie strony nauki przed pokazaniem jej właścicielowi (używa go Claude w bocie):
     node /home/tonyg/bot/sprawdz_strone.js <folder>
   - sprawdziany.json: poprawny JSON, wpis z id = folder, data RRRR-MM-DD albo null
   - index.html: składnia skryptów, data-nauka, klucz wyniku quizu, ../postep.js, link powrotu, zakładka „Najważniejsze”,
     tablice T, FC, Q (poprawna odpowiedź na indeksie 0, 4 odpowiedzi), OQ
   - licz-zadania.js (jeśli jest): każdy typ zadania losowany 300 razy, odpowiedzi: liczby skończone, teksty albo ich listy
   - strona odpowiada 200 w portalu
   Kod wyjścia 0 = wszystko w porządku. */
const fs = require("fs"), vm = require("vm"), http = require("http"), path = require("path");
const NAUKA = "/home/tonyg/portal/sites/nauka";
const folder = process.argv[2] || "";
const bledy = [], uwagi = [];
const blad = t => bledy.push("❌ " + t), ok = t => uwagi.push("✅ " + t);

if (!/^[a-z0-9_-]+$/.test(folder)) { console.log("Użycie: node sprawdz_strone.js <folder>"); process.exit(2); }
const dir = path.join(NAUKA, folder);

try {
  const spis = JSON.parse(fs.readFileSync(path.join(NAUKA, "sprawdziany.json"), "utf8"));
  const w = spis.find(x => x.id === folder);
  if (!w) blad(`brak wpisu z id "${folder}" w sprawdziany.json`);
  else {
    for (const k of ["id", "folder", "przedmiot", "typ", "tytul", "opis", "dodano", "zawiera"]) if (!(k in w)) blad(`wpis: brak pola ${k}`);
    if (w.folder !== folder) blad("wpis: folder różny od id");
    if (!["sprawdzian", "kartkówka"].includes(w.typ)) blad("wpis: typ musi być „sprawdzian” albo „kartkówka”");
    if (w.data !== null && !/^\d{4}-\d{2}-\d{2}$/.test(w.data || "")) blad("wpis: data RRRR-MM-DD albo null");
    if (bledy.length === 0) ok(`sprawdziany.json: wpis „${w.tytul}” (${w.data})`);
  }
  const ids = spis.map(x => x.id);
  if (new Set(ids).size !== ids.length) blad("sprawdziany.json: powtórzone id");
} catch (e) { blad("sprawdziany.json: " + e.message); }

let html = "";
try { html = fs.readFileSync(path.join(dir, "index.html"), "utf8"); } catch (e) { blad("brak " + dir + "/index.html"); }
if (html) {
  const wym = [[`data-nauka="${folder}"`, "atrybut data-nauka"], [`nauka:${folder}:best_`, "klucz wyniku quizu nauka:<id>:best_"],
               ['src="../postep.js"', "skrypt ../postep.js"], ["Wszystkie notatki", "link powrotu „← Wszystkie notatki”"],
               ["Najważniejsze", "zakładka „Najważniejsze”"]];
  for (const [s, n] of wym) html.includes(s) ? ok(n) : blad("brak: " + n);
  const skrypty = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
  skrypty.forEach((k, i) => { try { new vm.Script(k); } catch (e) { blad(`skrypt nr ${i + 1}: błąd składni: ${e.message}`); } });
  const kod = skrypty.join("\n");
  const tab = nazwa => { const m = kod.match(new RegExp(`(?:const|let|var)\\s+${nazwa}\\s*=\\s*`)); if (!m) return null;
    let i = m.index + m[0].length, gl = 0, j = i;
    for (; j < kod.length; j++) { const c = kod[j]; if ("[{(".includes(c)) gl++; else if ("]})".includes(c)) { gl--; if (gl === 0) { j++; break; } }
      else if (c === '"' || c === "'" || c === "`") { const q = c; j++; while (j < kod.length && kod[j] !== q) { if (kod[j] === "\\") j++; j++; } } }
    try { return vm.runInNewContext("(" + kod.slice(i, j) + ")"); } catch (e) { blad(`${nazwa}: nie da się odczytać (${e.message})`); return null; } };
  const T = tab("T"), FC = tab("FC"), Q = tab("Q"), OQ = tab("OQ");
  if (T) ok(`tematy: ${Object.keys(T).length}`); else blad("brak T (nazwy tematów)");
  if (FC) { const zle = FC.filter(c => !Array.isArray(c) || c.length < 3 || !c[1] || !c[2]); zle.length ? blad(`FC: ${zle.length} złych fiszek`) : ok(`fiszki: ${FC.length}`);
    const kl = FC.map(c => c[0] + "|" + c[1]); if (new Set(kl).size !== kl.length) blad("FC: powtórzone fiszki (ten sam temat i przód)"); }
  else blad("brak FC (fiszki)");
  if (Q) { const zle = Q.filter(q => !Array.isArray(q) || !q[1] || !Array.isArray(q[2]) || q[2].length !== 4 || q[3] !== 0 || new Set(q[2]).size !== 4);
    zle.length ? blad(`Q: ${zle.length} złych pytań (4 różne odpowiedzi, poprawna na indeksie 0, czwarte pole 0); pierwsze: ${JSON.stringify(zle[0]).slice(0, 120)}`) : ok(`pytania quizu: ${Q.length}`); }
  else blad("brak Q (quiz)");
  if (OQ) ok(`pytania otwarte: ${OQ.length}`);
  if (T && FC && Q) { const tem = new Set(Object.keys(T).map(String)); const poza = [...FC, ...Q].filter(x => !tem.has(String(x[0])));
    if (poza.length) blad(`${poza.length} fiszek/pytań ma numer tematu spoza T`); }
}

const lz = path.join(dir, "licz-zadania.js");
if (fs.existsSync(lz)) {
  let typy = null;
  const ctx = {console, Math, document: {getElementById: () => ({}), createElement: () => ({})}, C: () => "#888"};
  ctx.window = ctx;
  try {
    vm.runInNewContext(fs.readFileSync(path.join(NAUKA, "licz.js"), "utf8"), ctx);
    ctx.Licz.init = o => { typy = o.typy; };
    vm.runInNewContext(fs.readFileSync(lz, "utf8"), ctx);
  } catch (e) { blad("licz-zadania.js: " + e.message); }
  if (typy) {
    for (const t of typy) {
      let zle = 0, przyk = "";
      for (let i = 0; i < 300; i++) {
        try { const z = t.gen.call(t);
          const okZ = typeof z.tresc === "string" && Array.isArray(z.pola) && z.pola.length && Array.isArray(z.rozw) &&
            z.pola.every(p => (Array.isArray(p.odp) ? p.odp.length > 0 && p.odp : [p.odp])
              .every(v => typeof v === "string" ? v.length > 0 : Number.isFinite(v)));
          if (!okZ) { zle++; przyk = przyk || JSON.stringify(z).slice(0, 150); }
        } catch (e) { zle++; przyk = przyk || e.message; }
      }
      zle ? blad(`Licz „${t.nazwa}”: ${zle}/300 złych losowań (${przyk})`) : ok(`Licz „${t.nazwa}”: 300 losowań OK`);
    }
    if (!html.includes('src="licz-zadania.js"') || !html.includes('src="../licz.js"')) blad("index.html nie ładuje ../licz.js i licz-zadania.js");
  }
}

http.get(`http://127.0.0.1/strony/nauka/${folder}/`, r => {
  r.statusCode === 200 ? ok("strona działa w portalu (200)") : blad(`portal zwraca ${r.statusCode}`);
  r.resume(); koniec();
}).on("error", e => { blad("portal: " + e.message); koniec(); });

function koniec() {
  console.log([...uwagi, ...bledy].join("\n"));
  console.log(bledy.length ? `\nBŁĘDY: ${bledy.length}. Popraw i sprawdź jeszcze raz.` : "\nWSZYSTKO OK");
  process.exit(bledy.length ? 1 : 0);
}
