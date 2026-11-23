"use strict";
const $ = (s, el = document) => el.querySelector(s);
const SKR = document.body;     // przewija się body, nie okno (iOS, patrz koniec pliku)
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
// numer nawigacji: odpowiedź, która przyszła po przejściu na inną zakładkę, nie może nadpisać ekranu
let nawNr = 0;
class Anulowano extends Error {}
// pamięć odpowiedzi: zakładki pokazują się od razu z pamięci, a świeże dane dociągają się w tle (i po cichu przerysowują
// ekran, gdy coś się zmieniło). Po każdej zmianie (POST) wpisy są „brudne”: przejście na zakładkę dalej pokazuje je
// od razu, ale przerysowanie po akcji (np. dodany produkt) czeka na świeże dane z sieci.
const PAMIEC = new Map(), W_LOCIE = new Map();
const bezPamieci = p => /^(zadanie|push|produkt|start|wersja)/.test(p);
let nawigacja = false, uzyte = new Set();
async function siec(p, opt) {
  const r = await fetch("/api/" + p, opt && { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(opt) });
  if (r.status === 401) { niezapamietane(); throw new Error("To urządzenie nie jest zapamiętane"); }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).blad || r.status + " " + p);
  return r.text();
}
function pobierzDoPamieci(p) {               // jedno zapytanie naraz o ten sam adres (wczytywanie z góry + ekran)
  if (!W_LOCIE.has(p)) W_LOCIE.set(p, siec(p).then(s => {
    const st = PAMIEC.get(p), zmiana = !st || st.s !== s;
    PAMIEC.set(p, { s, t: Date.now() });
    return [s, zmiana];
  }).finally(() => W_LOCIE.delete(p)));
  return W_LOCIE.get(p);
}
function odswiezWTle(p) {
  const nr = nawNr;
  pobierzDoPamieci(p).then(([, zmiana]) => { if (zmiana && nr === nawNr && uzyte.has(p)) przerysujPoCichu(); }).catch(() => {});
}
const api = async (p, opt) => {
  const nr = nawNr;
  if (opt) {
    const j = JSON.parse(await siec(p, opt));
    PAMIEC.forEach(w => w.brudne = true);
    wczytajZGory(2500);
    return j;
  }
  let s;
  if (bezPamieci(p)) s = await siec(p);
  else {
    uzyte.add(p);
    const w = PAMIEC.get(p);
    if (w && (nawigacja || !w.brudne)) {
      if (w.brudne || Date.now() - w.t > 20e3) odswiezWTle(p);
      s = w.s;
    } else s = (await pobierzDoPamieci(p))[0];
  }
  if (nr !== nawNr && !p.startsWith("zadanie/")) throw new Anulowano("anulowano");
  return JSON.parse(s);
};
const DNI = ["ndz", "pon", "wt", "śr", "czw", "pt", "sob"];
const SPORT_IKONA = { rower: "🚴", bieg: "🏃", silka: "🏋️", odpoczynek: "😴", inne: "⚡" };
const SPORT_SVG = { rower: '<circle cx="6" cy="16" r="4"/><circle cx="18" cy="16" r="4"/><path d="M6 16l4-8h5l3 8M10 8l3 8M9 5h3"/>',
  bieg: '<circle cx="14" cy="4" r="2"/><path d="M7 21l3-6 3 2 1 4M10 15l1-5 4 2 3-1M11 10l-3 1-2 3"/>',
  silka: '<path d="M6 8v8M18 8v8M3 10v4M21 10v4M6 12h12"/>', odpoczynek: '<path d="M20 14A8 8 0 0 1 10 4a8 8 0 1 0 10 10z"/>', inne: '<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>' };
const ikSport = s => `<svg class="sport-ik" viewBox="0 0 24 24">${SPORT_SVG[s] || SPORT_SVG.inne}</svg>`;
const kat = t => !t ? "inne" : /cycl|bik|ride/.test(t) ? "rower" : /run/.test(t) ? "bieg" : t === "strength_training" ? "silka" : "inne";
const dataPL = d => { const x = new Date(d + "T12:00"); return `${DNI[x.getDay()]} ${x.getDate()}.${String(x.getMonth() + 1).padStart(2, "0")}`; };
const widok = $("#widok");

async function czekaj(zid, co) {
  for (let i = 0; i < 400; i++) {
    await new Promise(r => setTimeout(r, i < 10 ? 1500 : 3000));
    const z = await api("zadanie/" + zid);
    if (z.stan !== "trwa") { if (z.stan === "blad") throw new Error(z.wynik); return z.wynik; }
    const pe = document.getElementById("postep"); if (pe) pe.textContent = z.postep || "";
    if (co) co(i);
  }
  throw new Error("za długo");
}

// Adres panelu serwera: ten sam host *.ts.net, port 8443 (portal przez Funnel). Lokalnie/LAN: portal na porcie 80.
const adresPanelu = () => location.protocol === "https:" ? `https://${location.hostname}:8443/` : `http://${location.hostname}/`;

function niezapamietane(cel = "trener") {
  const panel = cel === "panel";
  widok.innerHTML = `<div class="karta"><h3>🔐 Logowanie</h3>
    <div class="zakladki" role="tablist" style="margin-bottom:10px">
      <button type="button" role="tab" class="${panel ? "" : "akt"}" aria-selected="${!panel}" data-cel="trener">Trener</button>
      <button type="button" role="tab" class="${panel ? "akt" : ""}" aria-selected="${panel}" data-cel="panel">Zaloguj do panelu</button></div>
    <div class="szary">${panel ? "Panel serwera (stan Pi, Minecraft, NAS, zdrowie). To samo hasło, potem przełączasz się bez logowania."
      : "Apka wpuszcza z internetu tylko Ciebie. Hasło wpisujesz raz: urządzenie zostanie zapamiętane."}</div>
    <form id="log-form" autocomplete="on" style="margin-top:10px">
      <input type="text" name="username" value="serwerek" autocomplete="username" hidden>
      <div class="wiersz"><input id="haslo" name="password" type="password" placeholder="Hasło" autocomplete="current-password"
        autocapitalize="off" autocorrect="off" spellcheck="false" style="flex:1;min-width:0;font-size:18px" required>
      <button id="zaloguj" type="submit">Wejdź</button></div></form>
    <div id="log-info" class="szary" style="margin-top:6px"></div>
    <details style="margin-top:12px"><summary class="szary">Mam kod parowania</summary>
      <div class="wiersz" style="margin-top:8px"><input id="kod" type="text" placeholder="KOD" autocomplete="one-time-code" autocapitalize="characters"
        style="flex:1;min-width:0;font-size:18px;letter-spacing:.15em;text-transform:uppercase">
      <button id="paruj" class="drugi">Połącz</button></div><div id="paruj-info" class="szary" style="margin-top:6px"></div></details></div>`;
  widok.querySelectorAll("[data-cel]").forEach(b => b.onclick = () => niezapamietane(b.dataset.cel));
  $("#log-form").onsubmit = async e => {
    e.preventDefault();
    const info = $("#log-info"); info.textContent = "Sprawdzam…";
    const r = await fetch("/api/logowanie", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ haslo: $("#haslo").value }) });
    if (r.ok) { info.textContent = "✅ Zalogowano"; setTimeout(() => panel ? location.assign(adresPanelu()) : location.reload(), 400); }
    else { info.textContent = (await r.json().catch(() => ({}))).blad || "Błąd " + r.status; $("#haslo").select(); }
  };
  $("#paruj").onclick = async () => {
    const info = $("#paruj-info"); info.textContent = "Sprawdzam…";
    const r = await fetch("/api/paruj", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ kod: $("#kod").value }) });
    if (r.ok) { info.textContent = "✅ Zapamiętane"; setTimeout(() => location.reload(), 500); }
    else info.textContent = (await r.json().catch(() => ({}))).blad || "Błąd " + r.status;
  };
  $("#haslo").focus();
}

// ------------------------------------------------------------------ wykresy (SVG, mierzone do szerokości, z dotykiem)
// Każdy wykres to <div class="wyk" data-id> + specyfikacja w WYK; rysuj() buduje SVG po wstawieniu HTML.
const KOLOR = { niebieski: "#3987e5", morski: "#199e70", fiolet: "#9085e9", zolty: "#c98500" };
const SPORT_KOLOR = { rower: KOLOR.niebieski, bieg: KOLOR.morski, silka: KOLOR.fiolet, inne: KOLOR.zolty };
const MIES = ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"];
const WYK = new Map();
let wykNr = 0;
const wyk = spec => { const id = "w" + (++wykNr); WYK.set(id, spec); return `<div class="wyk${spec.typ === "spark" ? " spark" : ""}" data-id="${id}" style="height:${spec.h || (spec.typ === "spark" ? 30 : 180)}px"></div>`; };
const lb = (v, dz = 0) => v == null || isNaN(v) ? "–" : Number(v).toLocaleString("pl-PL", { minimumFractionDigits: dz, maximumFractionDigits: dz });
const hm = h => { if (h == null || isNaN(h)) return "–"; const m = Math.round(Math.abs(h) * 60); return `${h < 0 ? "-" : ""}${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}`; };  // 7,57 h → 7:34
const dataKr = d => { const x = new Date(d + "T12:00"); return `${x.getDate()} ${MIES[x.getMonth()]}`; };

function zaokr(lo, hi, n = 4, stalyKrok = null) {     // ładne podziałki osi Y
  if (lo === hi) { lo -= 1; hi += 1; }
  const krok0 = (hi - lo) / n, p = Math.pow(10, Math.floor(Math.log10(krok0)));
  const krok = stalyKrok ? [1, 2, 3, 4, 6].map(m => m * stalyKrok).find(k => k >= krok0) || 6 * stalyKrok : [1, 2, 2.5, 5, 10].map(m => m * p).find(k => k >= krok0) || 10 * p;
  const a = Math.floor(lo / krok) * krok, b = Math.ceil(hi / krok) * krok, t = [];
  for (let v = a; v <= b + krok / 2; v += krok) t.push(+v.toFixed(6));
  return t;
}
const zaokrRect = (x, y, w, h, r) => {   // słupek: zaokrąglona góra 4px, płaska podstawa
  r = Math.max(0, Math.min(r, h, w / 2));
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
};

function rysuj(root = document) {
  root.querySelectorAll(".wyk[data-id]").forEach(el => {
    const s = WYK.get(el.dataset.id); if (!s) return;
    const W = el.clientWidth; if (!W) return;
    el._w = W;
    ({ linia: rysujLinie, slupki: rysujSlupki, spark: rysujSpark }[s.typ])(el, s, W, el.clientHeight);
  });
}
let rozm;
window.addEventListener("resize", () => { clearTimeout(rozm); rozm = setTimeout(() => document.querySelectorAll(".wyk[data-id]").forEach(el => { if (el._w !== el.clientWidth) rysuj(el.parentNode); }), 150); });

function rysujSpark(el, s, W, H) {
  const y = s.y, ok = y.map((v, i) => [i, v]).filter(([, v]) => v != null);
  if (ok.length < 2) { el.innerHTML = ""; return; }
  const v = ok.map(p => p[1]), lo = Math.min(...v), hi = Math.max(...v);
  const X = i => 3 + (W - 8) * i / (y.length - 1), Y = q => 4 + (H - 8) * (1 - (q - lo) / ((hi - lo) || 1));
  const d = ok.map(([i, q], k) => (k ? "L" : "M") + X(i).toFixed(1) + "," + Y(q).toFixed(1)).join("");
  const [li, lv] = ok[ok.length - 1];
  el.innerHTML = `<svg width="${W}" height="${H}"><path d="${d}" fill="none" stroke="${s.kolor}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="${X(li)}" cy="${Y(lv)}" r="3.5" fill="${s.kolor}" stroke="var(--pierscien)" stroke-width="2"/></svg>`;
}

function rysujLinie(el, s, W, H) {
  const n = s.x.length, serie = s.serie;
  const prawe = serie.filter(q => q.os === "prawa");   // druga oś (np. mięśnie obok tłuszczu): każda seria na całą wysokość
  const wart = serie.filter(q => q.os !== "prawa").flatMap(q => q.y).concat(s.pasmo ? s.pasmo.flat() : []).concat(s.ref != null ? [s.ref] : []).concat((s.linie || []).map(l => l.y)).filter(v => v != null);
  if (wart.length < 2) { el.innerHTML = `<div class="pusto">za mało danych</div>`; return; }
  const fmt = s.fmt || (v => lb(v, s.dz || 0));
  const t = zaokr(s.min ?? Math.min(...wart), s.max ?? Math.max(...wart), 4, s.krokY);
  const lo = t[0], hi = t[t.length - 1];
  // prawa oś: tyle samo kresek co lewa, żeby siatka była wspólna
  let t2 = null;
  if (prawe.length) {
    const w2 = prawe.flatMap(q => q.y).filter(v => v != null), k = t.length - 1;
    let a2 = Math.min(...w2), b2 = Math.max(...w2); if (a2 === b2) { a2 -= 1; b2 += 1; }
    const p10 = Math.pow(10, Math.floor(Math.log10((b2 - a2) / k))), kroki = [1, 2, 5, 10, 20].map(m => m * p10);
    for (const kr of kroki) { const st = Math.floor(a2 / kr) * kr; if (st + kr * k >= b2 - 1e-9) { t2 = t.map((_, j) => +(st + kr * j).toFixed(6)); break; } }
    if (!t2) { const kr = (b2 - a2) / k; t2 = t.map((_, j) => +(a2 + kr * j).toFixed(6)); }
  }
  const dwie = !!t2, T = (s.znaczniki || []).length || dwie ? 24 : 10;
  const L = 6, R = 6, B = 22, osL = Math.max(...t.map(v => fmt(v).length)) * 6.5 + 8, osP = dwie ? Math.max(...t2.map(v => fmt(v).length)) * 6.5 + 8 : 0;
  const x0 = L + osL, x1 = W - R - osP - (s.etykietaKonca === false ? 0 : 30);
  const X = i => n === 1 ? (x0 + x1) / 2 : x0 + (x1 - x0) * i / (n - 1), Y = v => T + (H - T - B) * (1 - (v - lo) / (hi - lo));
  const Y2 = dwie ? v => T + (H - T - B) * (1 - (v - t2[0]) / (t2[t2.length - 1] - t2[0])) : Y;
  const Yq = q => q.os === "prawa" ? Y2 : Y;
  let g = t.map((v, j) => `<line x1="${x0}" x2="${W - R - osP}" y1="${Y(v)}" y2="${Y(v)}" class="siatka"/><text x="${x0 - 6}" y="${Y(v) + 3.5}" text-anchor="end">${fmt(v)}</text>`
    + (dwie ? `<text x="${W - R}" y="${Y(v) + 3.5}" text-anchor="end">${fmt(t2[j])}</text>` : "")).join("");
  if (dwie) {   // podpisy osi nad wykresem: kropka w kolorze serii + nazwa
    const lewa = serie.find(q => q.os !== "prawa");
    g += `<circle cx="${L + 4}" cy="${T - 13}" r="4" fill="${lewa.kolor}"/><text x="${L + 12}" y="${T - 9.5}">${esc(lewa.nazwa)}${s.jedn ? " " + esc(s.jedn) : ""}</text>`
      + `<text x="${W - R - 12}" y="${T - 9.5}" text-anchor="end">${esc(prawe[0].nazwa)}${s.jedn ? " " + esc(s.jedn) : ""}</text><circle cx="${W - R - 4}" cy="${T - 13}" r="4" fill="${prawe[0].kolor}"/>`;
  }
  // podpisy osi X: ~4 równo rozłożone
  const ileX = Math.min(n, W < 380 ? 3 : 5);
  for (let k = 0; k < ileX; k++) { const i = ileX === 1 ? 0 : Math.round((n - 1) * k / (ileX - 1)); g += `<text x="${X(i)}" y="${H - 6}" text-anchor="${k === 0 ? "start" : k === ileX - 1 ? "end" : "middle"}">${esc(s.etX ? s.etX(s.x[i]) : s.x[i])}</text>`; }
  if (s.pasmo) {   // np. norma HRV
    const p = s.pasmo.map((b, i) => [i, b]).filter(([, b]) => b && b[0] != null && b[1] != null);
    if (p.length > 1) g += `<path d="M${p.map(([i, b]) => X(i).toFixed(1) + "," + Y(b[1]).toFixed(1)).join("L")}L${p.slice().reverse().map(([i, b]) => X(i).toFixed(1) + "," + Y(b[0]).toFixed(1)).join("L")}Z" fill="${serie[0].kolor}" opacity=".13"/>`;
  }
  if (s.ref != null) g += `<line x1="${x0}" x2="${x1}" y1="${Y(s.ref)}" y2="${Y(s.ref)}" class="ref"/><text x="${x0 + 4}" y="${Y(s.ref) - 5}" class="ref-t">${esc(s.refNazwa || "średnia")} ${fmt(s.ref)}</text>`;
  (s.linie || []).forEach(l => { g += `<line x1="${x0}" x2="${x1}" y1="${Y(l.y)}" y2="${Y(l.y)}" class="ref"/><text x="${x1 - 2}" y="${Y(l.y) - 5}" text-anchor="end" class="ref-t">${esc(l.tekst || "")} ${fmt(l.y)}</text>`; });
  const znacz = (s.znaczniki || []).filter(z => z.i != null && z.i >= 0 && z.i < n);
  let ostX = -99;
  znacz.slice().sort((a, b) => a.i - b.i).forEach(z => {   // pionowa linia + numer nad wykresem (opis w legendzie pod wykresem)
    const x = X(z.i), xt = Math.max(x, ostX + 17); ostX = xt;
    g += `<line x1="${x}" x2="${x}" y1="${T - 4}" y2="${H - B}" class="znacznik"/><circle cx="${xt}" cy="${T - 13}" r="8" class="znacznik-k"/><text x="${xt}" y="${T - 9.5}" text-anchor="middle" class="znacznik-t">${esc(z.tekst)}</text>`;
  });
  const konce = [];
  serie.forEach((q, si) => {
    const Y = Yq(q);
    let d = "", a = "", seg = [];
    const zamknij = () => { if (seg.length > 1 && serie.length === 1) a += `M${seg[0][0]},${Y(lo)}L${seg.map(p => p.join(",")).join("L")}L${seg[seg.length - 1][0]},${Y(lo)}Z`; seg = []; };
    q.y.forEach((v, i) => {
      if (v == null) { if (!q.lacz) zamknij(); return; }
      const p = [X(i).toFixed(1), Y(v).toFixed(1)];
      d += (seg.length ? "L" : "M") + p.join(","); seg.push(p);
    });
    zamknij();
    if (a) g += `<path d="${a}" fill="${q.kolor}" opacity=".10"/>`;
    g += `<path d="${d}" fill="none" stroke="${q.kolor}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"${q.przerywana ? ' stroke-dasharray="6 5" stroke-linecap="butt"' : ""}/>`;
    // pojedyncze punkty (otoczone przerwami) jako kropki
    if (!q.lacz) q.y.forEach((v, i) => { if (v != null && q.y[i - 1] == null && q.y[i + 1] == null) g += `<circle cx="${X(i)}" cy="${Y(v)}" r="2" fill="${q.kolor}"/>`; });
    const ost = q.y.map((v, i) => [i, v]).filter(([, v]) => v != null).pop();
    if (ost) {
      g += q.przerywana ? `<circle cx="${X(ost[0])}" cy="${Y(ost[1])}" r="4" fill="var(--pierscien)" stroke="${q.kolor}" stroke-width="2.5"/>` : `<circle cx="${X(ost[0])}" cy="${Y(ost[1])}" r="4.5" fill="${q.kolor}" stroke="var(--pierscien)" stroke-width="2"/>`;
      if (s.etykietaKonca !== false) konce.push([X(ost[0]) + 8, Y(ost[1]) + 4, fmt(ost[1])]);
    }
  });
  konce.sort((p, q) => p[1] - q[1]).forEach((k, i, t) => { if (i && k[1] - t[i - 1][1] < 13) k[1] = t[i - 1][1] + 13; });
  g += konce.map(([x, y, v]) => `<text x="${x}" y="${y}" class="koniec">${v}</text>`).join("");
  el.innerHTML = `<svg width="${W}" height="${H}">${g}<g class="celownik" style="display:none"><line y1="${T}" y2="${H - B}"/>${serie.map(q => q.przerywana ? `<circle r="4" fill="var(--pierscien)" stroke="${q.kolor}" stroke-width="2.5"/>` : `<circle r="4.5" fill="${q.kolor}" stroke="var(--pierscien)" stroke-width="2"/>`).join("")}</g></svg><div class="dymek"></div>`;
  const svg = el.firstChild, cel = svg.lastChild, dym = el.lastChild;
  const ukryj = () => { cel.style.display = "none"; dym.style.display = "none"; };
  const pokaz = e => {
    if (e.isPrimary === false) return;                       // drugi palec = szczypanie, nie celownik
    const r = svg.getBoundingClientRect(), px = e.clientX - r.left;
    let i = Math.round((px - x0) / ((x1 - x0) / Math.max(1, n - 1))); i = Math.max(0, Math.min(n - 1, i));
    pokazI(i, e);
    if (s.sync) s.sync(s.x[i], el);
    if (s.dotyk) s.dotyk(s.x[i]);
  };
  const pokazI = (i, e) => {
    if (serie.every(q => q.y[i] == null)) { ukryj(); return; }
    cel.style.display = ""; cel.firstChild.setAttribute("x1", X(i)); cel.firstChild.setAttribute("x2", X(i));
    serie.forEach((q, k) => { const c = cel.children[k + 1]; if (q.y[i] == null) c.style.display = "none"; else { c.style.display = ""; c.setAttribute("cx", X(i)); c.setAttribute("cy", Yq(q)(q.y[i])); } });
    dym.innerHTML = `<div class="dt">${esc(s.etDymek ? s.etDymek(s.x[i]) : s.x[i])}</div>` + serie.map(q => q.y[i] == null ? "" :
      `<div>${znakSerii(q, serie)}${serie.length > 1 ? esc(q.nazwa) + " " : ""}<b>${fmt(q.y[i])}</b>${s.jedn ? " " + esc(s.jedn) : ""}</div>`).join("") +
      (s.pasmo && s.pasmo[i] && s.pasmo[i][0] != null ? `<div class="sz">norma ${fmt(s.pasmo[i][0])}–${fmt(s.pasmo[i][1])}</div>` : "");
    dym.style.display = "block";
    const dw = dym.offsetWidth; dym.style.left = Math.max(0, Math.min(W - dw, X(i) - dw / 2)) + "px";
    if (s.klik && e && e.type === "pointerup") s.klik(s.x[i], i);
  };
  el._os = { x0, x1, xs: s.x };
  el._celownik = x => x == null ? ukryj() : pokazI(najblizszy(s.x, x));     // sterowanie z innego wykresu (wspólna oś czasu)
  svg.addEventListener("pointermove", pokaz); svg.addEventListener("pointerdown", pokaz); svg.addEventListener("pointerup", pokaz);
  svg.addEventListener("pointerleave", () => { ukryj(); if (s.sync) s.sync(null, el); });
}

function rysujSlupki(el, s, W, H) {   // s: {x:[], serie:[{nazwa,y:[],kolor}], jedn, dz, zaznacz}
  const n = s.x.length, serie = s.serie;
  if (!n) { el.innerHTML = `<div class="pusto">brak danych</div>`; return; }
  const fmt = v => lb(v, s.dz || 0);
  const sumy = s.x.map((_, i) => serie.reduce((a, q) => a + (q.y[i] || 0), 0));
  const t = zaokr(0, Math.max(...sumy, s.ref || 0, 0.001), 3);
  const hi = t[t.length - 1];
  const R = 4, T = 10, B = 22, osL = Math.max(...t.map(v => fmt(v).length)) * 6.5 + 14;
  const x0 = osL, slot = (W - R - x0) / n, bw = Math.max(2, Math.min(24, slot * 0.7));
  const X = i => x0 + slot * i + (slot - bw) / 2, Y = v => T + (H - T - B) * (1 - v / hi);
  let g = t.map(v => `<line x1="${x0}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" class="siatka"/><text x="${x0 - 6}" y="${Y(v) + 3.5}" text-anchor="end">${fmt(v)}</text>`).join("");
  s.x.forEach((_, i) => {
    let y = Y(0);
    const seg = serie.map(q => q.y[i] || 0), ostatni = seg.map((v, k) => v > 0 ? k : -1).filter(k => k >= 0).pop();
    g += `<g class="slup${s.zaznacz === i ? " zazn" : ""}">`;
    seg.forEach((v, k) => {
      if (v <= 0) return;
      const h = Y(0) - Y(v), gora = k === ostatni;
      const hh = Math.max(1, h - (gora ? 0 : 2));          // 2px przerwy między segmentami
      y -= h;
      g += gora ? `<path d="${zaokrRect(X(i), y, bw, hh, 4)}" fill="${serie[k].kolor}"/>` : `<rect x="${X(i)}" y="${y + 2}" width="${bw}" height="${hh}" fill="${serie[k].kolor}"/>`;
    });
    g += `</g>`;
  });
  if (s.ref != null) g += `<line x1="${x0}" x2="${W - R}" y1="${Y(s.ref)}" y2="${Y(s.ref)}" class="ref"/>`;
  const ileX = Math.min(n, W < 380 ? 4 : 6);
  for (let k = 0; k < ileX; k++) { const i = ileX === 1 ? 0 : Math.round((n - 1) * k / (ileX - 1)); g += `<text x="${X(i) + bw / 2}" y="${H - 6}" text-anchor="middle">${esc(s.etX ? s.etX(s.x[i]) : s.x[i])}</text>`; }
  el.innerHTML = `<svg width="${W}" height="${H}">${g}<rect class="podsw" style="display:none" y="${T}" height="${H - T - B}" width="${slot}" rx="4"/></svg><div class="dymek"></div>`;
  const svg = el.firstChild, pod = svg.lastChild, dym = el.lastChild;
  svg.insertBefore(pod, svg.firstChild);
  const pokaz = e => {
    const r = svg.getBoundingClientRect(); const i = Math.max(0, Math.min(n - 1, Math.floor((e.clientX - r.left - x0) / slot)));
    pod.style.display = ""; pod.setAttribute("x", x0 + slot * i);
    dym.innerHTML = `<div class="dt">${esc(s.etDymek ? s.etDymek(s.x[i]) : s.x[i])}</div>` + serie.filter(q => q.y[i]).map(q =>
      `<div>${znakSerii(q, serie)}${serie.length > 1 ? esc(q.nazwa) + " " : ""}<b>${fmt(q.y[i])}</b>${s.jedn ? " " + esc(s.jedn) : ""}</div>`).join("") +
      (serie.length > 1 ? `<div class="sz">razem ${fmt(sumy[i])}${s.jedn ? " " + esc(s.jedn) : ""}</div>` : "") + (sumy[i] ? "" : `<div class="sz">brak</div>`);
    dym.style.display = "block";
    const dw = dym.offsetWidth; dym.style.left = Math.max(0, Math.min(W - dw, x0 + slot * (i + .5) - dw / 2)) + "px";
    if (s.klik && e.type === "pointerup") s.klik(s.x[i], i);
  };
  svg.addEventListener("pointermove", pokaz); svg.addEventListener("pointerdown", pokaz); svg.addEventListener("pointerup", pokaz);
  svg.addEventListener("pointerleave", () => { pod.style.display = "none"; dym.style.display = "none"; });
}
// ------------------------------------------------------------------ przebieg treningu (tętno, moc, …) i wykresy z czatu
const KANAL = { tetno: ["Tętno", "bpm", "#e5484d"], moc: ["Moc", "W", KOLOR.fiolet], predkosc: ["Prędkość", "km/h", KOLOR.niebieski],
  kadencja: ["Kadencja", "rpm", KOLOR.morski], wysokosc: ["Wysokość", "m", KOLOR.zolty] };
const mmss = s => { s = Math.round(s || 0); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${x}` : `${m}:${x}`; };
const etCzasu = s => { s = Math.round(s || 0); return s >= 3600 ? `${Math.floor(s / 3600)}:${String(Math.floor(s % 3600 / 60)).padStart(2, "0")} h` : `${Math.floor(s / 60)} min`; };
const PRZEBIEG = new Map();
async function przebieg(id, od, doS) {
  const k = `${id}/${od ?? ""}/${doS ?? ""}`;
  if (!PRZEBIEG.has(k)) PRZEBIEG.set(k, api(`aktywnosc/${id}/przebieg?n=500${od != null ? "&od=" + od : ""}${doS != null ? "&do=" + doS : ""}`).catch(e => { PRZEBIEG.delete(k); throw e; }));
  return PRZEBIEG.get(k);
}
const najblizszy = (xs, v) => { let b = -1, bd = Infinity; xs.forEach((x, i) => { const d = Math.abs(x - v); if (d < bd) { bd = d; b = i; } }); return b; };
// wykres na każdy kanał (jedna oś Y na wykres), wspólna oś czasu; znaczniki [{s, tekst}], linie [{kanal, wartosc, tekst}]
function wykresyKanalow(p, kanaly, { znaczniki = [], linie = [], h = 150, dotyk } = {}) {
  const ks = (kanaly || Object.keys(KANAL)).filter(k => KANAL[k] && (p[k] || []).some(v => v != null));
  if (!ks.length) return `<div class="szary">Brak przebiegu w danych z zegarka.</div>`;
  const t0 = p.t[0] ?? 0, t1 = p.t[p.t.length - 1] ?? 0;
  const zs = znaczniki.filter(z => z.s != null && z.s >= t0 - 5 && z.s <= t1 + 5).sort((a, b) => a.s - b.s);
  const etX = t1 - t0 <= 1200 ? mmss : etCzasu;           // przybliżenie: oś w m:ss
  const zn = zs.map((z, k) => ({ i: najblizszy(p.t, z.s), tekst: k + 1 }));
  return ks.map(k => {
    const [nazwa, jedn, kolor] = KANAL[k];
    const serie = [{ nazwa: k === "moc" && p.moc_max ? "średnia" : nazwa, y: p[k], kolor }];
    if (k === "moc" && p.moc_max) serie.push({ nazwa: "max", y: p.moc_max, kolor: kolor + "55" });
    return `<div class="kanal"><div class="kanal-t">${nazwa} <span class="szary">${jedn}</span></div>${wyk({ typ: "linia", x: p.t, serie, jedn, h,
      dz: 0, min: k === "wysokosc" || k === "tetno" ? undefined : 0, etykietaKonca: false, etX, etDymek: mmss, znaczniki: zn, sync: syncKanaly, dotyk,
      linie: linie.filter(l => l.kanal === k).map(l => ({ y: l.wartosc, tekst: l.tekst })) })}</div>`;
  }).join("") + legZnacz(zs);
}
// celownik na jednym kanale pokazuje ten sam moment na pozostałych wykresach z tej samej grupy
function syncKanaly(x, el) {
  const grupa = el.closest(".kanaly, .wyk-czat, .karta"); if (!grupa) return;
  grupa.querySelectorAll(".kanal .wyk").forEach(w => { if (w !== el && w._celownik) w._celownik(x); });
}
const legZnacz = zs => zs.length ? `<ol class="znacz-leg">${zs.map(z => `<li>${esc(z.tekst)}</li>`).join("")}</ol>` : "";
const METRYKI_CZAT = { hrv: ["HRV", "ms", KOLOR.fiolet], sen_h: ["Sen", "h", KOLOR.niebieski, hm], sen_wynik: ["Wynik snu", "", KOLOR.niebieski],
  tetno_spocz: ["Tętno spoczynkowe", "bpm", "#e5484d"], bb_rano: ["Body Battery rano", "", KOLOR.morski], gotowosc: ["Gotowość", "", KOLOR.morski],
  stres: ["Stres", "", KOLOR.zolty], obc_ostre: ["Obciążenie ostre", "", KOLOR.fiolet], acwr: ["Stosunek obciążeń", "", KOLOR.fiolet, v => lb(v, 2)],
  kroki: ["Kroki", "", KOLOR.morski], vo2_rower: ["VO2max rower", "", KOLOR.niebieski], sen_gleboki_h: ["Sen głęboki", "h", KOLOR.niebieski, hm],
  sen_tetno: ["Tętno w nocy", "bpm", "#e5484d"], kcal_akt: ["Kcal aktywne", "kcal", KOLOR.zolty] };
async function wykresDni(w) {
  const doD = w.do || dzisISO(), odD = w.od || dzienMinus(doD, 13);
  const dni = await api(`dni?od=${odD}&do=${doD}`);
  const x = dni.map(d => d.dzien);
  const zs = (w.znaczniki || []).filter(z => z.dzien && x.includes(z.dzien)).sort((a, b) => a.dzien < b.dzien ? -1 : 1);
  return (w.metryki || []).filter(k => METRYKI_CZAT[k]).map(k => {
    const [nazwa, jedn, kolor, f] = METRYKI_CZAT[k];
    const zn = zs.map((z, n) => ({ i: x.indexOf(z.dzien), tekst: n + 1 }));
    return `<div class="kanal"><div class="kanal-t">${nazwa}${jedn ? ` <span class="szary">${jedn}</span>` : ""}</div>${wyk({ typ: "linia", x, serie: [{ nazwa, y: dni.map(d => d[k] ?? null), kolor }],
      jedn: f === hm ? "h" : jedn, fmt: f, dz: k === "hrv" || k === "tetno_spocz" ? 0 : undefined, h: 150, etX: dataKr, etDymek: dataPL, znaczniki: zn,
      linie: (w.linie || []).filter(l => l.kanal === k).map(l => ({ y: l.wartosc, tekst: l.tekst })) })}</div>`;
  }).join("") + legZnacz(zs) || `<div class="szary">brak danych</div>`;
}
async function wykresCzatu(el, w, caly = false) {
  try {
    if (w.rodzaj === "trening") {
      const zoom = w.od_s != null || w.do_s != null;
      const p = await przebieg(w.aktywnosc_id, caly ? null : w.od_s, caly ? null : w.do_s);
      const zakres = zoom && !caly && p.t.length ? `<span class="zakres">🔍 ${mmss(p.t[0])}–${mmss(p.t[p.t.length - 1])}</span>` : "";
      el.innerHTML = zakres + wykresyKanalow(p, w.kanaly, { znaczniki: w.znaczniki || [], linie: w.linie || [], h: 130 })
        + `<div class="wyk-dol">${zoom ? `<button class="link maly przel">${caly ? "🔍 przybliżenie" : "cały przebieg"}</button>` : ""}`
        + `<a class="szary maly" href="#trening/${w.aktywnosc_id}">otwórz trening ›</a></div>`;
      const b = el.querySelector(".przel");
      if (b) b.onclick = () => { el.innerHTML = `<div class="szary">wykres…</div>`; wykresCzatu(el, w, !caly); };
    } else el.innerHTML = await wykresDni(w);
    rysuj(el);
  } catch (e) { if (!(e instanceof Anulowano)) el.innerHTML = `<div class="szary">Nie udało się pobrać wykresu (${esc(e.message)})</div>`; }
}

// znak serii w dymku i legendzie: gdy wykres ma linię przerywaną (średnia), znak to kreska w stylu linii, inaczej kwadracik koloru
const znakSerii = (q, serie) => serie.some(z => z.przerywana) ? `<i class="kr${q.przerywana ? " p" : ""}" style="color:${q.kolor}"></i>` : `<i style="background:${q.kolor}"></i>`;
const legenda = serie => serie.length < 2 ? "" : `<div class="legenda">${serie.map(q => `<span>${znakSerii(q, serie)}${esc(q.nazwa)}</span>`).join("")}</div>`;

// ------------------------------------------------------------------ Dziś
const STATUS = { PRODUCTIVE: "produktywny", MAINTAINING: "utrzymanie", RECOVERY: "regeneracja", UNPRODUCTIVE: "nieproduktywny",
  DETRAINING: "roztrenowanie", OVERREACHING: "przeciążenie", PEAKING: "szczyt", STRAINED: "nadwyrężenie" };
const status = s => s ? (STATUS[String(s).replace(/_\d+$/, "")] || s) : "";

function trening(t, zrobiony, aid) {   // aid: zrobiona aktywność z Garmina → klik otwiera jej dane
  const kroki = (t.kroki || []).map(k => {
    if (k.rodzaj === "powtorz") return `<li>${k.razy}× [${(k.kroki || []).map(opisKroku).join(" → ")}]</li>`;
    return `<li>${opisKroku(k)}</li>`;
  }).join("");
  const st = { na_zegarku: "⌚ na zegarku", zdjety: "", nowy: "czeka", blad: "⚠️ błąd", w_apce: "" }[t.stan] ?? t.stan;
  const cel = aid ? `#trening/${aid}` : t.id && t.sport !== "odpoczynek" ? `#zaplanowany/${t.id}` : "";
  const klik = cel ? ` klik" onclick="if(!event.target.closest('details,a,button'))location.hash='${cel}'` : "";
  return `<div class="trening sport-${t.sport}${zrobiony ? " zrobiony" : ""}${klik}">
    <b>${ikSport(t.sport)}${esc(t.tytul)}</b>${t.min ? `<span class="znaczek">~${t.min} min</span>` : ""}${!zrobiony && t.szac && t.szac.kcal ? `<span class="znaczek">~${t.szac.kcal} kcal</span>` : ""}${st ? `<span class="znaczek">${st}</span>` : ""}${zrobiony ? `<span class="znaczek ok">✓ zrobione</span>` : ""}
    ${wykresTreningu(t)}
    ${t.opis ? `<div class="szary tresc">${esc(t.opis)}</div>` : ""}
    ${kroki ? `<details><summary>kroki</summary><ul class="kroki">${kroki}</ul></details>` : ""}
    ${t.stan === "blad" ? `<div class="szary zle">${esc(t.zrodlo)}</div>` : ""}</div>`;
}
// wykres bloczkowy (jak w interwałach): szerokość = czas kroku, wysokość i kolor = intensywność (strefa)
let PROGI = {};
const STREFA_KOLOR = ["#8e8e93", "#0a84ff", "#30d158", "#ff9f0a", "#ff453a"];
function intensywnosc(k, sport) {  // ~ ułamek progu (1 = próg/FTP)
  const sr = (k.od != null && k.do != null) ? (k.od + k.do) / 2 : null, z = [.5, .68, .83, .97, 1.12];
  if ((k.cel === "strefa_tetna" || k.cel === "strefa_mocy") && k.strefa) return z[Math.min(5, Math.max(1, k.strefa)) - 1];
  if (k.cel === "moc" && sr && PROGI.ftp) return sr / PROGI.ftp;
  const hrp = sport === "bieg" ? PROGI.hr_bieg : PROGI.hr_rower;
  if (k.cel === "tetno" && sr && hrp) return Math.min(1.15, .5 + (sr / hrp - .55) * 1.4);  // tętno rośnie wolniej niż moc
  if (k.cel === "tempo" && sr && PROGI.tempo_bieg) return PROGI.tempo_bieg / sr;
  return { rozgrzewka: .55, schlodzenie: .5, odpoczynek: .48, przerwa: .4 }[k.rodzaj] || .75;
}
function wykresTreningu(t) {
  if (!["rower", "bieg"].includes(t.sport) || !(t.kroki || []).length) return "";
  const bl = [], dodaj = k => {
    const min = k.czas_min || (k.dystans_km ? k.dystans_km * (t.sport === "bieg" ? 5.5 : 2.2) : 3);
    const i = intensywnosc(k, t.sport);
    bl.push({ min, i, z: i < .56 ? 0 : i < .76 ? 1 : i < .91 ? 2 : i < 1.06 ? 3 : 4, op: opisKroku(k).replace(/<[^>]+>/g, "") });
  };
  for (const k of t.kroki) {
    if (k.rodzaj === "powtorz") for (let r = 0; r < (k.razy || 1); r++) (k.kroki || []).forEach(dodaj);
    else dodaj(k);
  }
  const suma = bl.reduce((a, b) => a + b.min, 0);
  if (!suma) return "";
  return `<div class="bloczki" role="img" aria-label="Przebieg treningu">${bl.map(b =>
    `<i title="${esc(b.op)}" style="flex:${b.min.toFixed(2)};height:${Math.round(Math.max(.18, Math.min(1, (b.i - .3) / .9)) * 100)}%;background:${STREFA_KOLOR[b.z]}"></i>`).join("")}</div>
    <div class="bloczki-os"><span>0</span><span>${Math.round(suma)} min</span></div>`;
}
function opisKroku(k) {
  if (k.rodzaj === "cwiczenie") return `${esc(k.nazwa)} ${k.serie ? k.serie + "×" : ""}${k.czas_s ? k.czas_s + " s" : (k.powt || "")}${k.kg ? " @" + k.kg + " kg" : ""}${k.przerwa_s ? `, przerwa ${k.przerwa_s} s` : ""}`;
  const r = { rozgrzewka: "rozgrzewka", praca: "praca", odpoczynek: "luz", schlodzenie: "schłodzenie", przerwa: "przerwa" }[k.rodzaj] || k.rodzaj;
  const ile = k.czas_min ? `${k.czas_min} min` : k.dystans_km ? `${k.dystans_km} km` : "do LAP";
  const tempo = s => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;
  const cel = { strefa_tetna: `Z${k.strefa} tętna`, strefa_mocy: `Z${k.strefa} mocy`, tetno: `${k.od}–${k.do} bpm`, moc: `${k.od}–${k.do} W`,
    kadencja: `${k.od}–${k.do} rpm`, tempo: k.od ? `${tempo(Math.min(k.od, k.do))}–${tempo(Math.max(k.od, k.do))}/km` : "" }[k.cel] || "";
  return `${r} ${ile}${cel ? " · " + cel : ""}${k.opis ? ` <i>(${esc(k.opis)})</i>` : ""}`;
}

// ------------------------------------------------------------------ metryki: definicje, kafle, ekran szczegółów
const godz = m => { m = ((Math.round(m) % 1440) + 1440) % 1440; return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}`; };
const naMin = t => { if (!t) return null; const [h, m] = t.split(":").map(Number); let x = h * 60 + m; if (x < 720) x += 1440; return x; };  // pora snu liczona od południa
const hMin = h => h == null ? "–" : `${Math.floor(h)} h ${String(Math.round((h % 1) * 60)).padStart(2, "0")} min`;
const fm = (m, v) => m.fmt ? (v == null ? "–" : m.fmt(v)) : lb(v, m.dz || 0);
const METRYKI = {
  sen: { n: "Sen", k: "sen_h", jedn: "h", dz: 1, fmt: hm, lepiej: 1, kolor: KOLOR.fiolet, fmtDuzy: hMin, opis: "Długość snu w nocy przed tym dniem." },
  sen_wynik: { n: "Wynik snu", k: "sen_wynik", jedn: "/100", lepiej: 1, kolor: KOLOR.fiolet, min: 0, max: 100 },
  hrv: { n: "HRV", k: "hrv", jedn: "ms", lepiej: 1, kolor: KOLOR.morski, pasmo: "hrv_norma", opis: "Średnie HRV z nocy. Pasmo = Twoja norma z Garmina; poniżej normy zwykle znaczy zmęczenie albo choroba." },
  tetno: { n: "Tętno spocz.", k: "tetno_spocz", jedn: "bpm", lepiej: -1, kolor: KOLOR.niebieski, opis: "Tętno spoczynkowe. Wzrost o 5+ bpm ponad średnią to sygnał zmęczenia." },
  bb: { n: "Body Battery", k: "bb_rano", jedn: "", lepiej: 1, kolor: KOLOR.niebieski, min: 0, max: 100, opis: "Body Battery rano, po nocy." },
  gotowosc: { n: "Gotowość", k: "gotowosc", jedn: "", lepiej: 1, kolor: KOLOR.niebieski, min: 0, max: 100, opis: "Gotowość treningowa Garmina (sen, HRV, regeneracja, obciążenie)." },
  obciazenie: { n: "Obciążenie", k: "obc_ostre", jedn: "", lepiej: 0, kolor: KOLOR.zolty, opis: "Obciążenie ostre (7 dni) na tle przewlekłego (4 tygodnie). Stosunek 0,8–1,3 to bezpieczny rozwój." },
  stres: { n: "Stres", k: "stres", jedn: "", lepiej: -1, kolor: KOLOR.zolty, min: 0, opis: "Średni stres dnia wg Garmina (0–100)." },
  vo2: { n: "VO₂max rower", k: "vo2_rower", jedn: "", dz: 0, lepiej: 1, kolor: KOLOR.niebieski, opis: "Szacowane VO₂max z jazd z miernikiem mocy." },
  kroki: { n: "Kroki", k: "kroki", jedn: "", lepiej: 1, kolor: KOLOR.morski, min: 0, pelnyDzien: true },
};
let WSZYSTKIE = null, wszystkieZ = null;           // sparsowane raz na wersję z pamięci (duży JSON)
async function wszystkieDni() {
  const d = await api("dni?od=2000-01-01"), w = PAMIEC.get("dni?od=2000-01-01");
  if (w && w.s === wszystkieZ && WSZYSTKIE) return WSZYSTKIE;
  wszystkieZ = w && w.s; return WSZYSTKIE = d;
}
const srednia = a => { const v = a.filter(x => x != null); return v.length ? v.reduce((s, x) => s + x, 0) / v.length : null; };
const dzienMinus = (d, n) => { const x = new Date(d + "T12:00"); x.setDate(x.getDate() - n); return x.toISOString().slice(0, 10); };

function delta(m, teraz, odn, nazwa) {   // ▲/▼ z oceną (lepiej/gorzej) — kolor tekstu tylko dla oceny, zawsze z ikoną
  if (teraz == null || odn == null) return "";
  const r = teraz - odn, dz = m.dz || 0;
  if (Math.abs(r) < Math.pow(10, -dz) / 2) return `<span class="delta">= ${nazwa}</span>`;
  const dobre = m.lepiej ? Math.sign(r) === m.lepiej : null;
  return `<span class="delta ${dobre == null ? "" : dobre ? "lepiej" : "gorzej"}">${r > 0 ? "▲" : "▼"} ${m.fmt ? m.fmt(Math.abs(r)) : lb(Math.abs(r), dz)} ${nazwa}</span>`;
}
function wartMetryki(m, d) { const v = d[m.k]; return v == null ? null : v; }

function kafelM(klucz, dni, dzis, { podpis = null } = {}) {
  const m = METRYKI[klucz];
  const z = dni.filter(d => (m.pelnyDzien ? d.dzien < dzis : d.dzien <= dzis) && wartMetryki(m, d) != null);
  const ost = z[z.length - 1];
  const v = ost ? wartMetryki(m, ost) : null;
  const sr7 = srednia(dni.filter(d => d.dzien < (ost || {}).dzien && d.dzien >= dzienMinus((ost || {}).dzien || dzis, 7)).map(d => wartMetryki(m, d)));
  const ostatnie = dni.slice(-14).map(d => wartMetryki(m, d));
  const stare = ost && ost.dzien !== dzis ? `<span class="znaczek">${dataPL(ost.dzien)}</span>` : "";
  return `<a class="kafel" href="#metryka/${klucz}"><div class="n">${m.n}${stare}<svg class="strz" viewBox="0 0 16 16"><path d="M6 3l5 5-5 5"/></svg></div>
    <div class="w">${v == null ? "–" : fm(m, v)}<small>${m.jedn && v != null ? " " + m.jedn : ""}</small></div>
    <div class="d">${podpis ?? delta(m, v, sr7, "vs 7 dni")}</div>${wyk({ typ: "spark", y: ostatnie, kolor: m.kolor })}</a>`;
}

// grupowanie dla długich zakresów: tygodnie / miesiące
function grupuj(dni, kl, okres) {
  if (okres === "dzien") return { x: dni.map(d => d.dzien), y: dni.map(d => typeof kl === "function" ? kl(d) : d[kl]) };
  const g = new Map();
  dni.forEach(d => {
    const x = new Date(d.dzien + "T12:00");
    let k;
    if (okres === "tydzien") { x.setDate(x.getDate() - (x.getDay() + 6) % 7); k = x.toISOString().slice(0, 10); } else k = d.dzien.slice(0, 7) + "-01";
    if (!g.has(k)) g.set(k, []);
    g.get(k).push(typeof kl === "function" ? kl(d) : d[kl]);
  });
  const kl2 = [...g.keys()];
  return { x: kl2, y: kl2.map(k => { const s = srednia(g.get(k)); return s == null ? null : +s.toFixed(2); }) };
}
const ZAKRESY = [[7, "7 dni"], [30, "30 dni"], [90, "90 dni"], [365, "rok"], [0, "wszystko"]];
let zakresM = 30, nocWybrana = null;

async function pokazMetryke(klucz) {
  const m = METRYKI[klucz]; if (!m) { location.hash = "#dzis"; return; }
  $("#tytul").textContent = m.n;
  const wsz = await wszystkieDni();
  const dzis = new Date().toISOString().slice(0, 10);
  const z = wsz.filter(d => wartMetryki(m, d) != null && !(m.pelnyDzien && d.dzien === new Date().toISOString().slice(0, 10)));
  if (!z.length) { widok.innerHTML = `<div class="karta szary">Brak danych dla: ${esc(m.n)}</div>`; return; }
  const ost = z[z.length - 1], v = wartMetryki(m, ost);
  const okno = (n, od = ost.dzien) => z.filter(d => d.dzien < od && d.dzien >= dzienMinus(od, n)).map(d => wartMetryki(m, d));
  const sr7 = srednia(okno(7)), sr30 = srednia(okno(30));
  const rok = z.filter(d => d.dzien > dzienMinus(ost.dzien, 365)).map(d => wartMetryki(m, d));
  const pct = m.lepiej ? Math.round(100 * rok.filter(x => m.lepiej > 0 ? x < v : x > v).length / Math.max(1, rok.length)) : null;
  // rok temu: te same 30 dni rok wcześniej
  const rt = srednia(z.filter(d => d.dzien <= dzienMinus(ost.dzien, 365) && d.dzien > dzienMinus(ost.dzien, 395)).map(d => wartMetryki(m, d)));
  const sr30teraz = srednia(z.filter(d => d.dzien > dzienMinus(ost.dzien, 30)).map(d => wartMetryki(m, d)));

  const od = zakresM ? dzienMinus(dzis, zakresM - 1) : "2000-01-01";
  const wz = wsz.filter(d => d.dzien >= od);
  const okres = !zakresM ? "miesiac" : zakresM >= 365 ? "tydzien" : "dzien";
  const gr = grupuj(wz, m.k, okres);
  const vals = gr.y.filter(x => x != null);
  const srZ = srednia(vals);
  const etX = okres === "miesiac" ? x => MIES[+x.slice(5, 7) - 1] + " " + x.slice(2, 4) : dataKr;
  const etD = okres === "miesiac" ? x => MIES[+x.slice(5, 7) - 1] + " " + x.slice(0, 4) : okres === "tydzien" ? x => "tydz. od " + dataKr(x) : dataPL;
  const serie = [{ nazwa: m.n, y: gr.y, kolor: m.kolor }];
  if (klucz === "obciazenie") serie.push({ nazwa: "przewlekłe", y: grupuj(wz, "obc_przewlekle", okres).y, kolor: KOLOR.niebieski });
  if (klucz === "obciazenie") serie[0].nazwa = "ostre";
  const pasmo = m.pasmo && okres === "dzien" ? wz.map(d => d[m.pasmo]) : null;
  const naj = vals.length ? (m.lepiej < 0 ? Math.min(...vals) : Math.max(...vals)) : null, najg = vals.length ? (m.lepiej < 0 ? Math.max(...vals) : Math.min(...vals)) : null;

  let h = `<div class="karta hero"><div class="szary">${ost.dzien === dzis ? "Dziś" : dataPL(ost.dzien)}</div>
    <div class="duzy">${m.fmtDuzy ? m.fmtDuzy(v) : fm(m, v)}<small>${m.jedn && !m.fmtDuzy ? " " + m.jedn : ""}</small></div>
    <div class="wiersz delty">${delta(m, v, sr7, "vs 7 dni")}${delta(m, v, sr30, "vs 30 dni")}</div>
    ${pct != null ? `<div class="pasek-pct"><i style="width:${pct}%"></i></div><div class="szary">Lepiej niż ${pct}% dni z ostatniego roku</div>` : ""}
    ${klucz === "hrv" && ost.hrv_norma ? `<div class="szary">Norma ${ost.hrv_norma[0]}–${ost.hrv_norma[1]} ms · średnia 7 dni ${lb(ost.hrv_7d)} ms${ost.hrv_status ? " · " + esc(String(ost.hrv_status).toLowerCase()) : ""}</div>` : ""}
    ${klucz === "obciazenie" ? `<div class="szary">Przewlekłe ${lb(ost.obc_przewlekle)} · stosunek ${lb(ost.acwr, 1)}${ost.status ? " · " + esc(status(ost.status)) : ""}</div>` : ""}
    </div>`;
  h += `<div class="zakladki">${ZAKRESY.map(([n, t]) => `<button class="${zakresM === n ? "akt" : ""}" data-z="${n}">${t}</button>`).join("")}</div>`;
  h += `<div class="karta"><div class="kt">${esc(m.n)}${okres !== "dzien" ? ` <span class="szary">· średnie ${okres === "tydzien" ? "tygodniowe" : "miesięczne"}</span>` : ""}</div>
    ${wyk({ typ: "linia", x: gr.x, serie, pasmo, ref: serie.length === 1 ? srZ : null, dz: m.dz || 0, fmt: m.fmt, jedn: m.jedn, min: m.min, max: m.max, etX, etDymek: etD,
      klik: klucz === "sen" && okres === "dzien" ? x => { nocWybrana = x; rysujNoc(); } : null })}
    ${legenda(serie)}
    <div class="statsy"><div><span>średnio</span><b>${fm(m, srZ)}</b></div><div><span>${m.lepiej ? "najlepiej" : "max"}</span><b>${fm(m, naj)}</b></div><div><span>${m.lepiej ? "najsłabiej" : "min"}</span><b>${fm(m, najg)}</b></div><div><span>dni z danymi</span><b>${vals.length}</b></div></div></div>`;
  if (klucz === "sen") h += await sekcjaSnu(z, wz, okres);
  // dni tygodnia
  const dt = [1, 2, 3, 4, 5, 6, 0].map(w => srednia(z.filter(d => d.dzien > dzienMinus(ost.dzien, 90) && new Date(d.dzien + "T12:00").getDay() === w).map(d => wartMetryki(m, d))));
  h += `<div class="karta"><div class="kt">Dni tygodnia <span class="szary">· średnia z 90 dni</span></div>
    ${wyk({ typ: "slupki", x: ["pon", "wt", "śr", "czw", "pt", "sob", "ndz"], serie: [{ nazwa: m.n, y: dt, kolor: m.kolor }], dz: m.dz || 0, jedn: m.jedn, h: 150 })}
    ${klucz === "sen" ? `<div class="szary">${(() => { const t = srednia(dt.slice(0, 4).concat(dt[6])), w = srednia([dt[4], dt[5]]); return t && w ? `Przed szkołą (ndz–czw) średnio ${hMin(t)}, w weekend (pt–sob) ${hMin(w)}.` : ""; })()}</div>` : ""}</div>`;
  // porównanie: ostatnie 30 dni vs rok temu
  h += `<div class="karta"><div class="kt">Porównanie</div><table class="tab">
    <tr><td>Ostatnie 30 dni</td><td><b>${fm(m, sr30teraz)}</b> ${esc(m.jedn)}</td></tr>
    <tr><td>Te same 30 dni rok temu</td><td><b>${fm(m, rt)}</b> ${esc(m.jedn)} ${delta(m, sr30teraz, rt, "")}</td></tr>
    <tr><td>Średnia całej historii</td><td><b>${fm(m, srednia(z.map(d => wartMetryki(m, d))))}</b> ${esc(m.jedn)}</td></tr>
    <tr><td>Rekord</td><td>${(() => { const r = z.reduce((a, d) => a == null || (m.lepiej < 0 ? wartMetryki(m, d) < wartMetryki(m, a) : wartMetryki(m, d) > wartMetryki(m, a)) ? d : a, null); return r ? `<b>${fm(m, wartMetryki(m, r))}</b> ${esc(m.jedn)} <span class="szary">${dataKr(r.dzien)} ${r.dzien.slice(0, 4)}</span>` : "–"; })()}</td></tr></table>
    ${m.opis ? `<div class="szary" style="margin-top:8px">${esc(m.opis)}</div>` : ""}</div>`;
  widok.innerHTML = h;
  widok.querySelectorAll(".zakladki button").forEach(b => b.onclick = () => { zakresM = +b.dataset.z; pokazMetryke(klucz); });
  rysuj(widok);
  if (klucz === "sen") rysujNoc();
}

// ------------------------------------------------------------------ sen: fazy, pora snu, wybrana noc vs średnia
const FAZY = [["sen_gleboki_h", "głęboki", KOLOR.niebieski], ["sen_lekki_h", "lekki", KOLOR.morski], ["sen_rem_h", "REM", KOLOR.fiolet], [d => d.sen_czuwanie_min != null ? d.sen_czuwanie_min / 60 : null, "czuwanie", KOLOR.zolty]];
const faza = (f, d) => typeof f[0] === "function" ? f[0](d) : d[f[0]];
let NOCE = [];
async function sekcjaSnu(z, wz, okres) {
  NOCE = z;
  if (!nocWybrana || !z.some(d => d.dzien === nocWybrana)) nocWybrana = z[z.length - 1].dzien;
  const ost14 = z.slice(-14);
  let h = `<div class="karta"><div class="kt">Fazy snu <span class="szary">· ostatnie 14 nocy, stuknij noc</span></div>
    ${wyk({ typ: "slupki", x: ost14.map(d => d.dzien), serie: FAZY.map(f => ({ nazwa: f[1], y: ost14.map(d => faza(f, d)), kolor: f[2] })), dz: 1, jedn: "h", etX: dataKr, etDymek: dataPL, h: 170,
      klik: x => { nocWybrana = x; rysujNoc(); } })}
    ${legenda(FAZY.map(f => ({ nazwa: f[1], kolor: f[2] })))}</div>
    <div class="karta" id="noc"></div>`;
  const gz = grupuj(wz, d => naMin(d.sen_od), okres), gw = grupuj(wz, d => naMin(d.sen_do), okres);
  h += `<div class="karta"><div class="kt">Pora snu</div>
    ${wyk({ typ: "linia", x: gz.x, serie: [{ nazwa: "zaśnięcie", y: gz.y, kolor: KOLOR.fiolet }, { nazwa: "pobudka", y: gw.y, kolor: KOLOR.zolty }], fmt: godz, krokY: 60, etX: okres === "miesiac" ? x => MIES[+x.slice(5, 7) - 1] : dataKr, etDymek: dataPL, h: 170 })}
    ${legenda([{ nazwa: "zaśnięcie", kolor: KOLOR.fiolet }, { nazwa: "pobudka", kolor: KOLOR.zolty }])}
    <div class="szary">Średnio zasypiasz o ${godz(srednia(gz.y))}, wstajesz o ${godz(srednia(gw.y))}.</div></div>`;
  h += `<div class="karta"><div class="kt">Ostatnie noce</div><div class="noce">${z.slice(-10).reverse().map(d =>
    `<button class="noc-w" data-d="${d.dzien}"><span>${dataPL(d.dzien)}</span><span class="szary">${esc(d.sen_od || "")}–${esc(d.sen_do || "")}</span><b>${hMin(d.sen_h)}</b><span class="szary">${d.sen_wynik ?? "–"}</span></button>`).join("")}</div></div>`;
  setTimeout(() => widok.querySelectorAll(".noc-w").forEach(b => b.onclick = () => { nocWybrana = b.dataset.d; rysujNoc(); $("#noc").scrollIntoView({ behavior: "smooth", block: "center" }); }));
  return h;
}
function rysujNoc() {
  const el = $("#noc"); if (!el) return;
  const d = NOCE.find(x => x.dzien === nocWybrana); if (!d) return;
  const pop = NOCE.filter(x => x.dzien < d.dzien && x.dzien >= dzienMinus(d.dzien, 30));
  const najl = NOCE.filter(x => x.dzien > dzienMinus(d.dzien, 365)).reduce((a, x) => !a || (x.sen_wynik || 0) > (a.sen_wynik || 0) ? x : a, null);
  const fazy = FAZY.map(f => [f, faza(f, d) || 0]), razem = fazy.reduce((s, [, v]) => s + v, 0) || 1;
  const wiersz = (nazwa, kl, fmt, lepiej) => {
    const v = typeof kl === "function" ? kl(d) : d[kl], sr = srednia(pop.map(x => typeof kl === "function" ? kl(x) : x[kl])), b = najl ? (typeof kl === "function" ? kl(najl) : najl[kl]) : null;
    if (v == null && sr == null) return "";
    const r = v != null && sr != null ? v - sr : null, ok = r == null || !lepiej ? "" : Math.sign(r) === lepiej ? "lepiej" : "gorzej";
    return `<tr><td>${nazwa}</td><td><b>${fmt(v)}</b></td><td class="${ok}">${r == null ? "" : (r > 0 ? "▲" : r < 0 ? "▼" : "=") + " " + fmt(Math.abs(r))}</td><td class="szary">${fmt(b)}</td></tr>`;
  };
  const h1 = v => v == null ? "–" : hm(v) + " h", mn = v => v == null ? "–" : Math.round(v * 60) + " min";
  el.innerHTML = `<div class="kt">Noc ${dataPL(d.dzien)} <span class="szary">· ${esc(d.sen_od || "?")}–${esc(d.sen_do || "?")}</span></div>
    <div class="fazy-pasek">${fazy.filter(([, v]) => v > 0).map(([f, v]) => `<i style="flex:${v};background:${f[2]}" title="${f[1]}"></i>`).join("")}</div>
    <div class="fazy-et">${fazy.map(([f, v]) => `<span><i style="background:${f[2]}"></i>${f[1]} <b>${mn(v)}</b> <span class="szary">${Math.round(v / razem * 100)}%</span></span>`).join("")}</div>
    <table class="tab por"><tr><th></th><th>ta noc</th><th>vs 30 dni</th><th>najlepsza*</th></tr>
    ${wiersz("Sen", "sen_h", h1, 1)}${wiersz("Wynik", "sen_wynik", v => lb(v), 1)}${wiersz("Głęboki", "sen_gleboki_h", mn, 1)}${wiersz("REM", "sen_rem_h", mn, 1)}
    ${wiersz("Czuwanie", d => d.sen_czuwanie_min != null ? d.sen_czuwanie_min / 60 : null, mn, -1)}${wiersz("Wybudzenia", "sen_wybudzenia", v => lb(v), -1)}
    ${wiersz("Tętno w nocy", "sen_tetno", v => lb(v), -1)}${wiersz("HRV", "hrv", v => lb(v), 1)}${wiersz("Oddech", "sen_oddech", v => lb(v, 1), 0)}${wiersz("SpO₂", "sen_spo2", v => lb(v), 0)}${wiersz("Stres w nocy", "sen_stres", v => lb(v), -1)}</table>
    <div class="szary" style="margin-top:6px">* najlepsza noc roku wg wyniku${najl ? ": " + dataKr(najl.dzien) + " " + najl.dzien.slice(0, 4) : ""}</div>`;
}

// ------------------------------------------------------------------ Dziś
async function pokazDzis() {
  const [d, jedz, waga] = await Promise.all([api("dzis"), api("dieta").catch(e => { if (e instanceof Anulowano) throw e; return null; }), api("waga").catch(e => { if (e instanceof Anulowano) throw e; return null; })]);
  PROGI = d.progi || {};
  const dni = d.dni;
  const dz = dni.find(x => x.dzien === d.dzis) || {};
  const wcz = dni.slice().reverse().find(x => x.dzien < d.dzis && x.gotowosc != null) || {};
  let h = "";
  if (d.ustawienia_puste) h += `<div class="karta"><h3>Zacznijmy</h3><div>Trener musi Cię poznać: cel, terminy, ile masz czasu, sprzęt i jak ma wyglądać plan. Potem dopyta o szczegóły, ułoży periodyzację i wyśle treningi na zegarek.</div>
    <div class="wiersz" style="margin-top:10px"><a class="btn" href="#start">Odpowiedz na kilka pytań</a></div></div>`;
  if (d.historia && d.historia !== "gotowe") h += `<div class="karta szary">Pobieram całą historię z Garmina… (doszedłem do ${esc(d.historia)})</div>`;
  const got = dz.gotowosc ?? wcz.gotowosc, poz = dz.gotowosc != null ? dz.gotowosc_poziom : wcz.gotowosc_poziom;
  const st = got == null ? null : got >= 70 ? ["dobrze", "Gotowy na mocny trening"] : got >= 40 ? ["uwaga", "Raczej spokojnie"] : ["zle", "Odpocznij albo lekko"];
  h += `<a class="karta hero klik" href="#metryka/gotowosc"><div class="hero-wiersz">
      <div><div class="szary">Gotowość dziś</div><div class="duzy">${got ?? "–"}<small>/100</small></div>
      ${st ? `<span class="status ${st[0]}"><i></i>${st[1]}</span>` : ""}</div>
      ${pierscien(got)}</div>
      <div class="szary" style="margin-top:8px">${[poz && esc(POZIOM[String(poz).toUpperCase()] || String(poz).toLowerCase()), dz.regeneracja_h != null && `regeneracja ${lb(dz.regeneracja_h)} h`, dz.gotowosc_uwaga && esc(UWAGA_G[dz.gotowosc_uwaga] || String(dz.gotowosc_uwaga).toLowerCase().replace(/_/g, " "))].filter(Boolean).join(" · ")}</div></a>`;
  h += kartaPropozycji(d.propozycja) + kartaOceny(d.do_oceny);
  if (d.analiza) {
    const a = d.analiza, oc = { dobrze: "dobrze", uwaga: "uwaga", zle: "zle" }[a.dane.ocena] || "";
    h += `<div class="karta"><div class="szary">${esc({ rano: "Analiza poranna", trening: "Po treningu", tydzien: "Tydzień" }[a.rodzaj] || a.rodzaj)} · ${esc(a.utworzono.slice(5, 16).replace("T", " "))}</div>
      <h3>${oc ? `<span class="kropka ${oc}"></span>` : ""}${esc(a.tytul)}</h3><div>${esc(a.dane.krotko)}</div>
      <div class="wiersz" style="margin-top:10px"><a class="btn" href="#analiza/${a.id}">Czytaj</a><button class="drugi" onclick="omowAnalize(${a.id}, ${esc(JSON.stringify(a.tytul))})">Omów</button></div></div>`;
  }
  h += `<div class="kafle">${kafelM("sen", dni, d.dzis)}${kafelM("hrv", dni, d.dzis)}${kafelM("tetno", dni, d.dzis)}${kafelM("bb", dni, d.dzis)}
    ${kafelM("obciazenie", dni, d.dzis, { podpis: esc(status(dz.status || wcz.status)) })}${kafelM("stres", dni, d.dzis)}
    ${kafelJedzenie(jedz)}${kafelWaga(waga)}</div>`;
  h += `<a class="h2-link" href="#plan"><h2>Plan</h2><span>cały plan<svg class="strz" viewBox="0 0 16 16"><path d="M6 3l5 5-5 5"/></svg></span></a>`;
  const poDniu = {};
  d.plan.forEach(t => (poDniu[t.dzien] = poDniu[t.dzien] || []).push(t));
  if (!d.plan.length) h += `<div class="szary">Brak planu na najbliższe dni.</div>`;
  Object.keys(poDniu).sort().forEach(k => {
    h += `<div class="dzien ${k === d.dzis ? "dzis" : ""}"><div class="data">${k === d.dzis ? "Dziś" : dataPL(k)}</div>${(() => { const ile = JSON.parse(JSON.stringify((d.zrobione_id || {})[k] || {}));   // „zrobione” tylko, gdy był trening tego samego rodzaju
      return poDniu[k].map(t => { const aid = t.sport !== "odpoczynek" && ile[t.sport]?.length ? ile[t.sport].shift() : null; return trening(t, !!aid, aid); }).join(""); })()}</div>`;
  });
  h += `<div class="wiersz" style="margin-top:12px"><a class="btn drugi" href="#plan">📅 Cały plan i periodyzacja</a></div>`;
  h += `<div class="szary stopka">Synchronizacja: ${esc((d.ostatni_sync || "–").replace("T", " ").slice(0, 16))}
    · <a href="#" onclick="akcja('sync');return false">odśwież</a></div>`;
  widok.innerHTML = h;
  rysuj(widok);
}
const POZIOM = { PRIME: "szczyt formy", HIGH: "wysoka", MODERATE: "umiarkowana", LOW: "niska", POOR: "słaba" };
const UWAGA_G = { LISTEN_TO_YOUR_BODY: "słuchaj ciała", RECOVERY_TIME: "trwa regeneracja", GOOD_SLEEP_HISTORY: "dobry sen ostatnio", POOR_SLEEP_HISTORY: "słaby sen ostatnio",
  HIGH_TRAINING_LOAD: "wysokie obciążenie", READY_FOR_HARD: "gotowy na mocny trening", GO_EASY: "lżej dziś", REST: "odpoczynek" };
function pierscien(v) {   // pierścień gotowości: tor + łuk (status → kolor + etykieta obok)
  if (v == null) return "";
  const r = 34, o = 2 * Math.PI * r, kol = v >= 70 ? "var(--dobrze)" : v >= 40 ? "var(--uwaga)" : "var(--zle)";
  return `<svg class="pierscien" width="84" height="84" viewBox="0 0 84 84"><circle cx="42" cy="42" r="${r}" fill="none" stroke="var(--karta2)" stroke-width="8"/>
    <circle cx="42" cy="42" r="${r}" fill="none" stroke="${kol}" stroke-width="8" stroke-linecap="round" stroke-dasharray="${o * v / 100} ${o}" transform="rotate(-90 42 42)"/></svg>`;
}

// ------------------------------------------------------------------ Dane
let zakres = 90;
// Dane: dwie podzakładki — podsumowanie (wykresy, zdrowie) i historia treningów
const podzakladkiDanych = akt => `<div class="zakladki podzak">${[["dane", "Podsumowanie"], ["treningi", "Treningi"]].map(([h, n]) =>
  `<a class="${akt === h ? "akt" : ""}" href="#${h}">${n}</a>`).join("")}</div>`;
async function pokazDane() {
  const dzis = new Date().toISOString().slice(0, 10);
  const od = zakres ? dzienMinus(dzis, zakres - 1) : "2000-01-01";
  const okres = zakres && zakres <= 180 ? "tydzien" : "miesiac";
  const [wsz, agr] = await Promise.all([wszystkieDni(), api("agregaty?okres=" + okres)]);   // równolegle: szybciej na telefonie
  const ag = agr.filter(x => x.okres >= od.slice(0, x.okres.length));
  const etX = okres === "miesiac" ? x => x.slice(5, 7) + "." + x.slice(2, 4) : x => x.slice(5);
  const dni = wsz.filter(d => d.dzien >= dzienMinus(dzis, 29));
  const sporty = [["rower", "rower"], ["bieg", "bieg"], ["silka", "siłka"], ["inne", "inne"]];
  const suma = k => ag.reduce((s, x) => s + (x.h[k] || 0), 0);
  widok.innerHTML = podzakladkiDanych("dane") + `<div class="zakladki">${[[30, "30 dni"], [90, "90 dni"], [365, "rok"], [0, "wszystko"]].map(([v, n]) =>
    `<button class="${zakres === v ? "akt" : ""}" onclick="zakres=${v};pokazDane()">${n}</button>`).join("")}</div>
    <div class="karta"><div class="kt">Godziny treningu <span class="szary">· ${okres === "tydzien" ? "tygodnie" : "miesiące"}</span></div>
      <div class="wiersz suma">${sporty.map(([k, n]) => `<div><span>${n}</span><b>${lb(suma(k))} h</b></div>`).join("")}</div>
      ${wyk({ typ: "slupki", x: ag.map(x => x.okres), serie: sporty.map(([k, n]) => ({ nazwa: n, y: ag.map(x => x.h[k] || 0), kolor: SPORT_KOLOR[k] })), dz: 1, jedn: "h", etX, etDymek: x => (okres === "tydzien" ? "tydzień " : "") + x, h: 190 })}
      ${legenda(sporty.map(([k, n]) => ({ nazwa: n, kolor: SPORT_KOLOR[k] })))}</div>
    <div class="karta"><div class="kt">Obciążenie treningowe</div>
      ${wyk({ typ: "slupki", x: ag.map(x => x.okres), serie: [{ nazwa: "obciążenie", y: ag.map(x => x.obc), kolor: KOLOR.zolty }], etX, etDymek: x => (okres === "tydzien" ? "tydzień " : "") + x, h: 150 })}</div>
    <h2>Zdrowie i forma <span class="szary">· stuknij, żeby zobaczyć historię</span></h2>
    <div class="kafle">${Object.keys(METRYKI).map(k => kafelM(k, dni, dzis)).join("")}</div>`;
  rysuj(widok);
}

async function akcja(rodzaj, dod = {}) {
  const info = document.createElement("div");
  info.className = "karta szary";
  info.innerHTML = `<span class="mysli"></span> <span id="postep"></span>`;
  info.firstChild.textContent = { sync: "Synchronizuję z Garminem", plan: "Trener układa plan i sprawdza go z zasadami", analiza: "Trener analizuje", makrocykl: "Trener układa periodyzację i plan (kilka minut)", badania: "Trener szuka źródeł i przebudowuje plan (8–15 min)" }[rodzaj] || "Pracuję";
  widok.prepend(info);
  try { await czekaj(await api("akcja", { rodzaj, ...dod })); } catch (e) { alert("Błąd: " + e.message); }
  info.remove();
  route();
}

// ------------------------------------------------------------------ Analiza
async function pokazAnalize(id) {
  const a = await api("analizy?id=" + id);
  if (!a) { widok.innerHTML = "Nie ma takiej analizy."; return; }
  api(`analizy/${id}/przeczytane`, {});
  widok.innerHTML = `<div class="karta"><div class="szary">${esc(a.utworzono.replace("T", " ").slice(0, 16))}</div><h3>${esc(a.tytul)}</h3>
    <div class="tresc">${esc(a.tresc)}</div>
    ${a.dane.zmienic_plan ? `<div class="szary" style="margin-top:8px">📅 Zmiana planu: ${esc(a.dane.prosba_do_planu || "")}</div>` : ""}
    <div class="wiersz" style="margin-top:12px"><button onclick="omowAnalize(${a.id}, ${esc(JSON.stringify(a.tytul))})">💬 Omów z trenerem</button></div></div>
    <h2>Wcześniejsze</h2><div id="wczesniejsze" class="ladowanie">…</div>`;
  const l = await api("analizy?limit=30");
  $("#wczesniejsze").outerHTML = l.filter(x => x.id != id).map(x => `<a href="#analiza/${x.id}" style="text-decoration:none;color:inherit"><div class="trening">
    <div class="szary">${esc(x.utworzono.slice(0, 16).replace("T", " "))} · ${esc(x.rodzaj)}</div><b>${esc(x.tytul)}</b></div></a>`).join("") || `<div class="szary">brak</div>`;
}

// ------------------------------------------------------------------ Plan
async function kartaMakro() {
  const m = await api("makrocykl");
  if (!m.makrocykl) return `<div class="karta"><div class="kt">Periodyzacja</div><div class="szary">Brak — podaj cele (czat albo ⚙️), a trener ułoży fazy do celu wg zasad treningu (baza wiedzy ze źródeł).</div></div>`;
  const mk = m.makrocykl, dz = new Date().toISOString().slice(0, 10);
  const fazy = mk.fazy.map(f => {
    const teraz = f.od <= dz && dz <= f.do;
    return `<div class="trening" style="${teraz ? "border-color:var(--akcent)" : "opacity:.8"}"><b>${teraz ? "▶ " : ""}${esc(f.nazwa)}</b> <span class="szary">${esc(f.od.slice(5))}–${esc(f.do.slice(5))} · ${f.godziny_tyg_od}–${f.godziny_tyg_do} h/tydz.</span>
      <div class="szary">${esc(f.cel)}</div>
      ${`<details${teraz ? " open" : ""}><summary>szczegóły fazy</summary><div class="szary">Intensywność: ${esc(f.intensywnosc)}<br>Kluczowe: ${(f.sesje_kluczowe || []).map(esc).join("; ")}<br>Siłka ${f.silka_tyg ?? "–"}/tydz., bieg ${f.bieg_tyg ?? "–"}/tydz. · ${esc(f.rytm || "")}${(f.testy || []).length ? "<br>Testy: " + f.testy.map(esc).join(", ") : ""}</div></details>`}</div>`;
  }).join("");
  const u = m.plan_uzasadnienie;
  const biez = mk.fazy.find(f => f.od <= dz && dz <= f.do);
  return `<details class="karta makro"${localStorage.makroOtwarte === "1" ? " open" : ""} ontoggle="localStorage.makroOtwarte=this.open?'1':'0'"><summary><span class="kt">Periodyzacja ▾</span><span class="szary"> ${biez ? "▶ " + esc(biez.nazwa) + " do " + esc(biez.do.slice(5)) : ""}</span></summary><div style="color:var(--tekst2);font-size:14px">${esc(mk.cel_glowny)}</div><div class="szary">${mk.data_docelowa ? "do " + esc(mk.data_docelowa) + " · " : ""}${esc(m.progi.split("\n")[0] || "")}</div>
    <div style="margin-top:8px">${fazy}</div>
    <details><summary>dlaczego tak (zasady, ocena formy)</summary><div class="tresc szary">${esc(mk.ocena_wyjsciowa)}\n\n${esc(mk.uzasadnienie)}\n\n${(mk.zasady_indywidualne || []).map(x => "• " + esc(x)).join("\n")}</div></details>
    ${u ? `<details><summary>uzasadnienie bieżącego planu</summary><div class="tresc szary">${esc(u.tekst)}${(u.uwagi || []).length ? "\n\n⚠️ Kontrola: " + u.uwagi.map(esc).join("; ") : ""}</div></details>` : ""}
    <div class="wiersz" style="margin-top:8px"><a class="btn drugi" href="#wiedza">📚 Źródła trenera</a><button class="drugi" onclick="if(confirm('Ułożyć periodyzację od nowa i przeplanować?'))akcja('makrocykl')">🔁 Przebuduj periodyzację</button></div></div></details>`;
}

// ---- tierlista ćwiczeń: ocena nowych po treningu (S/A/B/C, ✕ = wykluczone)
const TIERY = [["S", "S: priorytet, najbardziej lubiane"], ["A", "A: bardzo dobre, regularnie"], ["B", "B: zamienniki, uzupełnienie"],
  ["C", "C: tylko gdy trening/sprzęt wymaga"], ["X", "Wykluczone / niepreferowane"]];
function kartaOceny(l) {
  if (!l || !l.length) return "";
  return `<div class="karta" id="ocena-cw"><h3>🏋️ Oceń nowe ćwiczenia</h3><div class="szary">Były na ostatniej siłce, a nie ma ich w tierliście. Ocena trafia do tierlisty w Ustawieniach.</div>
    ${l.map(n => `<div class="ocena-cw" data-n="${esc(n)}"><div>${esc(n)}</div><div class="wiersz chipy">${TIERY.map(([t]) =>
      `<button class="chip" onclick="ocenCw(this,'${t}')">${t === "X" ? "✕" : t}</button>`).join("")}<button class="chip szary" onclick="ocenCw(this,'pomin')">pomiń</button></div></div>`).join("")}</div>`;
}
async function ocenCw(b, t) {
  const w = b.closest(".ocena-cw");
  w.querySelectorAll("button").forEach(x => x.disabled = true);
  try { await api("tierlista", { nazwa: w.dataset.n, tier: t }); } catch (e) { w.querySelectorAll("button").forEach(x => x.disabled = false); return alert("Nie zapisało się: " + e.message); }
  w.remove();
  const k = document.getElementById("ocena-cw");
  if (k && !k.querySelector(".ocena-cw")) k.remove();
}

function kartaPropozycji(p) {
  if (!p) return "";
  return `<div class="karta" style="border:1px solid var(--akcent)"><div class="kt">❓ Trener pyta: zmienić plan?</div>
    <div>${esc(p.komentarz || "")}</div>
    <div class="szary" style="margin-top:6px;white-space:pre-line">${p.zmiany.map(esc).join("\n")}</div>
    <div class="szary" style="margin-top:6px">Słabo się czujesz albo źle spałeś → zmień. Czujesz się dobrze → zostaw plan.</div>
    <div class="wiersz" style="margin-top:10px"><button onclick="akcja('propozycja',{zmien:true})">✅ Zmień</button><button class="drugi" onclick="akcja('propozycja',{zmien:false})">💪 Zostaw, czuję się dobrze</button><a class="btn drugi" href="#czat">💬 Omów</a></div></div>`;
}

async function pokazPlan() {
  const [d, makro] = await Promise.all([api("plan"), kartaMakro()]);
  const dni = [];
  for (let i = -7; i <= 14; i++) { const x = new Date(d.dzis + "T12:00"); x.setDate(x.getDate() + i); dni.push(x.toISOString().slice(0, 10)); }
  PROGI = d.progi || {};
  let h = makro + `<div class="karta"><label>Poproś o zmianę (opcjonalnie)</label><textarea id="prosba" rows="2" placeholder="np. w czwartek nie mogę, w weekend dłuższy rower"></textarea>
    <div class="wiersz" style="margin-top:8px"><button onclick="akcja('plan',{prosba:$('#prosba').value})">📅 Przeplanuj</button></div></div>`;
  for (const k of dni) {
    const pl = d.plan.filter(t => t.dzien === k), zr = d.zrobione[k] || [];
    if (!pl.length && !zr.length && k < d.dzis) continue;
    if (k === d.dzis) h += `<div id="plan-dzis"></div>` + kartaPropozycji(d.propozycja);
    h += `<div class="dzien ${k === d.dzis ? "dzis" : ""}"><div class="data">${k === d.dzis ? `Dziś<small>${dataPL(k)}</small>` : dataPL(k)}</div>
      ${(() => { const uz = new Set(); return pl.map(t => { const a = t.sport !== "odpoczynek" && zr.find(a => kat(a.typ) === t.sport && !uz.has(a.id)); if (a) uz.add(a.id); return trening(t, !!a, a?.id); }).join(""); })()}
      ${zr.map(a => `<div class="trening zrobiony klik sport-${kat(a.typ)}" onclick="location.hash='#trening/${a.id}'">✓ ${esc(a.nazwa)} <span class="szary">${a.min} min${a.km ? " · " + a.km + " km" : ""}${a.obc ? " · obc " + a.obc : ""}</span></div>`).join("")}
      ${!pl.length && !zr.length ? `<div class="szary">—</div>` : ""}</div>`;
  }
  h += `<div style="height:40vh"></div>`;  // żeby dzisiaj dało się przewinąć na samą górę
  widok.innerHTML = h;
  const kotwica = $("#plan-dzis");
  if (kotwica) SKR.scrollTo(0, kotwica.getBoundingClientRect().top + SKR.scrollTop - ($("header")?.offsetHeight || 0) - 8);
}


// ------------------------------------------------------------------ Treningi
let filtr = "";
async function pokazTreningi(dalej = false) {
  const lista = await api(`aktywnosci?limit=40&offset=${dalej ? document.querySelectorAll(".lista-akt .trening").length : 0}${filtr ? "&sport=" + filtr : ""}`);
  const wiersze = lista.map(a => `<div class="trening sport-${kat(a.typ)}" onclick="location.hash='#trening/${a.id}'">
    <div><b>${esc(a.nazwa)}</b><div class="szary">${esc(a.start.replace("T", " "))}</div></div>
    <div style="text-align:right" class="szary">${a.min} min${a.km ? "<br>" + a.km + " km" : ""}${a.moc ? "<br>" + a.moc + " W" : ""}${a.tetno ? "<br>♥ " + a.tetno : ""}</div></div>`).join("");
  if (dalej) { $(".lista-akt").insertAdjacentHTML("beforeend", wiersze); return; }
  widok.innerHTML = podzakladkiDanych("treningi") + `<div class="zakladki">${[["", "wszystko"], ["rower", "🚴 rower"], ["bieg", "🏃 bieg"], ["silka", "🏋️ siłka"], ["inne", "inne"]].map(([v, n]) =>
    `<button class="${filtr === v ? "akt" : ""}" onclick="filtr='${v}';pokazTreningi()">${n}</button>`).join("")}</div>
    <div class="lista-akt">${wiersze}</div><button class="drugi" style="width:100%" onclick="pokazTreningi(true)">Więcej</button>`;
}
const POLA_T = [["min", "czas", v => hm(v / 60) + " h"], ["km", "dystans", v => lb(v, 2) + " km"], ["tetno", "tętno śr.", v => v + " bpm"], ["tetno_max", "tętno max", v => v + " bpm"],
  ["moc", "moc śr.", v => v + " W"], ["moc_np", "moc NP", v => v + " W"], ["moc_max", "moc max", v => v + " W"], ["kmh", "prędkość", v => lb(v, 1) + " km/h"],
  ["tempo", "tempo", v => v], ["kadencja", "kadencja", v => v + " rpm"], ["przewyzszenie", "przewyższenie", v => v + " m"], ["obc", "obciążenie", v => v],
  ["te_aer", "efekt tlenowy", v => lb(v, 1)], ["te_anaer", "efekt beztlenowy", v => lb(v, 1)], ["tss", "TSS", v => v], ["if_", "IF", v => lb(v, 2)],
  ["serie", "serie", v => v], ["kcal", "kcal", v => v]];
const EFEKT = { RECOVERY: "regeneracja", BASE: "baza", TEMPO: "tempo", LACTATE_THRESHOLD: "próg", THRESHOLD: "próg", VO2MAX: "VO2max",
  ANAEROBIC_CAPACITY: "beztlenowy", SPRINT: "sprint", AEROBIC_BASE: "baza tlenowa", NO_BENEFIT: "brak efektu" };
async function pokazTrening(id) {
  const a = await api("aktywnosc/" + id);
  PROGI = a.progi || {};
  const godzina = (a.start || "").slice(11, 16);
  let h = `<div class="karta"><div class="szary">${esc(a.dzien_slownie || "")}${godzina ? " · " + godzina : ""}</div>
    <h3>${ikSport(kat(a.typ))}${esc(a.nazwa)}</h3>${a.efekt ? `<span class="znaczek">${esc(EFEKT[a.efekt] || a.efekt.toLowerCase().replace(/_/g, " "))}</span>` : ""}
    <div class="statki">${POLA_T.filter(([k]) => a[k] != null && (!a.wiecej || GLOWNE.includes(k))).map(([k, n, f]) => `<div><span>${n}</span><b>${esc(f(a[k]))}</b></div>`).join("")}</div>
    <button style="margin-top:12px;width:100%" onclick="omowTrening(${a.id}, ${esc(JSON.stringify(a.nazwa + " (" + (a.dzien_slownie || "") + ")"))})">💬 Omów trening</button></div>`;
  if (a.strefy_min) {
    const suma = a.strefy_min.reduce((x, y) => x + y, 0) || 1;
    h += `<div class="karta"><h3>Strefy tętna</h3><div class="strefy">${a.strefy_min.map((m, i) => m ? `<i style="flex:${m};background:${STREFA_KOLOR[i]}" title="Z${i + 1}: ${m} min"></i>` : "").join("")}</div>
      <div class="strefy-leg">${a.strefy_min.map((m, i) => `<span><i style="background:${STREFA_KOLOR[i]}"></i>Z${i + 1} <b>${m}</b> min <small>${Math.round(m / suma * 100)}%</small></span>`).join("")}</div></div>`;
  }
  const w = a.wiecej || {};
  if (w.strefy_mocy) {
    const suma = w.strefy_mocy.reduce((x, y) => x + y, 0) || 1;
    h += `<div class="karta"><h3>Strefy mocy</h3><div class="strefy">${w.strefy_mocy.map((m, i) => m ? `<i style="flex:${m};background:${STREFA_MOCY[i]}"></i>` : "").join("")}</div>
      <div class="strefy-leg">${w.strefy_mocy.map((m, i) => `<span><i style="background:${STREFA_MOCY[i]}"></i>Z${i + 1} <b>${lb(m, m < 10 ? 1 : 0)}</b> min <small>${Math.round(m / suma * 100)}%</small></span>`).join("")}</div></div>`;
  }
  if ((w.krzywa_mocy || []).length > 2) {
    const k = w.krzywa_mocy;
    h += `<div class="karta"><h3>Krzywa mocy <span class="szary maly">najlepsza średnia z okna</span></h3>${wyk({ typ: "linia", x: k.map(q => q[0]), h: 170,
      serie: [{ nazwa: "moc", y: k.map(q => q[1]), kolor: KOLOR.fiolet }], jedn: "W", dz: 0, min: 0, etykietaKonca: false, etX: okno, etDymek: s => "najlepsze " + okno(s),
      linie: PROGI.ftp ? [{ y: PROGI.ftp, tekst: "FTP" }] : [] })}</div>`;
  }
  if ((w.grupy || []).length) h += `<div class="karta"><h3>Wszystkie statystyki</h3>${w.grupy.map(([g, pola]) =>
    `<div class="grupa-t">${esc(g)}</div><div class="statki">${pola.map(([n, v]) => `<div><span>${esc(n)}</span><b>${esc(v)}</b></div>`).join("")}</div>`).join("")}</div>`;
  if (a.cwiczenia) h += `<div class="karta"><h3>Ćwiczenia</h3>${Object.entries(a.cwiczenia).map(([k, v]) => `<div class="cw"><b>${esc(k)}</b><span class="szary">${esc(v)}</span></div>`).join("")}</div>`;
  if (kat(a.typ) !== "silka") h += `<div class="karta"><h3>Przebieg</h3><div class="zoom-pasek" style="display:none"><span class="zakres"></span>
      <span class="zoom-przyc"><button data-z="-">−</button><button data-z="+">+</button><button data-z="<">‹</button><button data-z=">">›</button><button data-z="0">cały</button></span></div>
      <div id="przebieg" class="kanaly"><div class="szary">Pobieram przebieg z Garmina…</div></div>
      <div class="szary maly zoom-pod" style="display:none">Dotknij wykresu, żeby zobaczyć wartości. Rozsuń dwa palce albo użyj +, żeby przybliżyć.</div></div><div id="okrazenia"></div>`;
  widok.innerHTML = h;
  rysuj(widok);
  if (kat(a.typ) === "silka") return;
  try {
    const p = await przebieg(id);
    const el = $("#przebieg"); if (!el) return;
    if (!p.t.length) { el.innerHTML = `<div class="szary">Garmin nie ma przebiegu tego treningu.</div>`; return; }
    przyblizanie(el, id, p);
    const ok = p.okrazenia || [];
    if (ok.length > 1) $("#okrazenia").innerHTML = `<div class="karta"><h3>Okrążenia</h3><div style="overflow-x:auto"><table class="tab"><tr><th>#</th><th>czas</th><th>km</th><th>♥ śr</th><th>♥ max</th>${ok.some(o => o.moc) ? "<th>W</th><th>NP</th>" : ""}<th>km/h</th></tr>
      ${ok.map(o => `<tr><td>${o.nr}</td><td>${mmss(o.s)}</td><td>${lb(o.km, 2)}</td><td>${o.tetno ?? "–"}</td><td>${o.tetno_max ?? "–"}</td>${ok.some(q => q.moc) ? `<td>${o.moc ?? "–"}</td><td>${o.moc_np ?? "–"}</td>` : ""}<td>${lb(o.kmh, 1)}</td></tr>`).join("")}</table></div></div>`;
  } catch (e) { if (!(e instanceof Anulowano)) { const el = $("#przebieg"); if (el) el.innerHTML = `<div class="szary">Nie udało się pobrać przebiegu (${esc(e.message)})</div>`; } }
}
const GLOWNE = ["min", "km", "tetno", "moc", "moc_np", "tss", "kmh", "tempo", "serie", "kcal", "obc"];
const STREFA_MOCY = ["#8e8e93", "#0a84ff", "#30d158", "#ffd60a", "#ff9f0a", "#ff453a", "#bf5af2"];
const okno = s => s < 60 ? s + " s" : s < 3600 ? s / 60 + " min" : lb(s / 3600, s % 3600 ? 1 : 0) + " h";
// przebieg z przybliżaniem: szczypanie dwoma palcami albo przyciski; po zmianie zakresu dociągamy dokładniejszy wycinek z serwera
function przyblizanie(el, id, pelny) {
  const karta = el.closest(".karta"), pasek = karta.querySelector(".zoom-pasek"), napis = karta.querySelector(".zakres");
  const koniec = pelny.koniec || pelny.t[pelny.t.length - 1], linie = PROGI.ftp ? [{ kanal: "moc", wartosc: PROGI.ftp, tekst: "FTP" }] : [];
  const Z = { od: 0, do: koniec, punkt: null, nr: 0 };
  pasek.style.display = ""; karta.querySelector(".zoom-pod").style.display = "";
  const rysujZakres = async () => {
    const nr = ++Z.nr, caly = Z.od <= 0 && Z.do >= koniec;
    const p = caly ? pelny : await przebieg(id, Math.round(Z.od), Math.round(Z.do)).catch(() => null);
    if (nr !== Z.nr || !p || !p.t.length) return;
    el.innerHTML = wykresyKanalow(p, null, { linie, dotyk: x => { Z.punkt = x; } });
    rysuj(el);
    napis.textContent = caly ? "cały przebieg" : `🔍 ${mmss(Z.od)}–${mmss(Z.do)}`;
    karta.querySelector('[data-z="0"]').disabled = caly;
  };
  const ustaw = (od, doS) => {
    let dl = Math.max(30, Math.min(koniec, doS - od));
    od = Math.max(0, Math.min(koniec - dl, od)); Z.od = od; Z.do = od + dl; rysujZakres();
  };
  const zoom = (k, srodek) => { const dl = (Z.do - Z.od) * k, c = srodek ?? Z.punkt ?? (Z.od + Z.do) / 2; ustaw(c - dl * (c - Z.od) / (Z.do - Z.od), c - dl * (c - Z.od) / (Z.do - Z.od) + dl); };
  pasek.onclick = e => {
    const b = e.target.closest("button"); if (!b) return;
    const dl = Z.do - Z.od;
    ({ "+": () => zoom(.5), "-": () => zoom(2), "<": () => ustaw(Z.od - dl / 2, Z.do - dl / 2), ">": () => ustaw(Z.od + dl / 2, Z.do + dl / 2), "0": () => ustaw(0, koniec) })[b.dataset.z]();
  };
  // szczypanie: podgląd przez skalowanie SVG, przeliczenie po puszczeniu palców
  const palce = new Map(); let start = null;
  const czasX = px => { const w = el.querySelector(".kanal .wyk"); if (!w || !w._os) return null;
    const { x0, x1, xs } = w._os, r = w.getBoundingClientRect(); return xs[0] + (px - r.left - x0) / (x1 - x0) * (xs[xs.length - 1] - xs[0]); };
  const svgi = () => el.querySelectorAll(".kanal svg");
  el.addEventListener("pointerdown", e => { palce.set(e.pointerId, e.clientX);
    if (palce.size === 2) { const [a, b] = [...palce.values()]; start = { d: Math.abs(a - b) || 1, m: (a + b) / 2, k: 1 }; } });
  el.addEventListener("pointermove", e => {
    if (!palce.has(e.pointerId)) return; palce.set(e.pointerId, e.clientX);
    if (palce.size !== 2 || !start) return;
    const [a, b] = [...palce.values()]; start.k = Math.max(.2, Math.min(20, Math.abs(a - b) / start.d));
    svgi().forEach(s => { const r = s.getBoundingClientRect(); s.style.transformOrigin = `${start.m - r.left}px 50%`; s.style.transform = `scaleX(${start.k})`; });
    napis.textContent = `🔍 ×${lb(start.k, 1)}`;
  });
  const koniecPalca = e => {
    palce.delete(e.pointerId);
    if (!start || palce.size) return;
    const { k, m } = start; start = null;
    svgi().forEach(s => { s.style.transform = ""; });
    const c = czasX(m);
    if (Math.abs(k - 1) > .08 && c != null) zoom(1 / k, c); else rysujZakres();
  };
  el.addEventListener("pointerup", koniecPalca); el.addEventListener("pointercancel", koniecPalca);
  rysujZakres();
}
function omowTrening(id, opis) { sessionStorage.omow = JSON.stringify({ id, tekst: `Omów trening: ${opis}` }); location.hash = "#czat"; }
function omowAnalize(id, tytul) { sessionStorage.omow = JSON.stringify({ analiza: id, tekst: `Omów analizę: ${tytul}` }); location.hash = "#czat/" + id; }

function szacStatki(z) {
  if (!z) return "";
  const p = [["kcal", "~kcal", v => "~" + v], ["tetno", "♥ śr.", v => `~${v} ±5`], ["tetno_max", "♥ max", v => "~" + v], ["moc", "moc śr.", v => `~${v} W`],
    ["moc_np", "moc NP", v => `~${v} W`], ["tss", "TSS", v => "~" + v], ["km", "dystans", v => `~${lb(v, 1)} km`], ["tempo", "tempo", v => "~" + v]];
  return p.filter(([k]) => z[k] != null).map(([k, n, f]) => `<div><span>${n}</span><b>${esc(f(z[k]))}</b></div>`).join("");
}
async function pokazZaplanowany(id) {
  const t = await api("plan/" + id);
  PROGI = t.progi || {};
  const kroki = (t.kroki || []).map(k => k.rodzaj === "powtorz" ? `<li>${k.razy}× [${(k.kroki || []).map(opisKroku).join(" → ")}]</li>` : `<li>${opisKroku(k)}</li>`).join("");
  const st = { na_zegarku: "⌚ na zegarku", zdjety: "✓ zdjęty z zegarka", nowy: "czeka na wysłanie", blad: "⚠️ błąd", w_apce: "tylko w apce" }[t.stan] ?? t.stan;
  widok.innerHTML = `<div class="karta"><div class="szary">${esc(t.dzien_slownie || t.dzien)}</div><h3>${ikSport(t.sport)}${esc(t.tytul)}</h3>
    <div class="statki">${t.min ? `<div><span>czas</span><b>${hm(t.min / 60)} h</b></div>` : ""}${szacStatki(t.szac)}${st ? `<div><span>stan</span><b>${esc(st)}</b></div>` : ""}</div>
    ${t.szac && t.szac.kcal ? `<div class="szary maly" style="margin-top:6px">~ to szacunek z Twoich progów i poprzednich treningów; Garmin policzy dokładnie po treningu.</div>` : ""}
    ${wykresTreningu(t)}${t.opis ? `<div class="tresc" style="margin-top:10px">${esc(t.opis)}</div>` : ""}</div>
    ${kroki ? `<div class="karta"><h3>Kroki</h3><ul class="kroki">${kroki}</ul></div>` : ""}
    <div class="karta"><button class="drugi" style="width:100%" onclick="sessionStorage.szkic=${esc(JSON.stringify(`Pytanie o trening ${t.tytul} (${t.dzien_slownie || t.dzien}): `))};location.hash='#czat'">💬 Zapytaj trenera o ten trening</button></div>`;
}

// ------------------------------------------------------------------ Czat
async function pokazCzat(analizaId) {
  const msgs = await api("czat");
  WYK_CZAT = [];
  widok.innerHTML = `<div class="czat" id="czat" data-ostatni="${Math.max(0, ...msgs.map(m => m.id || 0))}">${msgs.map(m => msg(m)).join("") || `<div class="szary">Napisz, do czego trenujesz, kiedy masz czas i co chcesz zmienić. Możesz pytać o dowolne dane z całej historii.</div>`}</div>
    <div style="height:70px"></div>
    <div class="pisz"><textarea id="tekst" placeholder="${analizaId ? "Omów analizę…" : "Napisz do trenera…"}"></textarea><button id="wyslij">➤</button></div>`;
  const t = $("#tekst");
  if (sessionStorage.szkic) { t.value = sessionStorage.szkic; delete sessionStorage.szkic; }
  $("#wyslij").onclick = () => wyslij(analizaId);
  $("#wyslij").disabled = !!czatZadanie;
  t.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey && !/iPhone|iPad/.test(navigator.userAgent)) { e.preventDefault(); wyslij(analizaId); } });
  // wykresy: ostatnie 6 od razu, starsze dopiero gdy się je przewinie
  const wk = [...document.querySelectorAll(".wyk-czat")];
  const laduj = el => { if (el._z) return; el._z = 1; wykresCzatu(el, WYK_CZAT[+el.dataset.n]); };
  wk.slice(-6).forEach(laduj);
  if (wk.length > 6 && "IntersectionObserver" in window) { const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { io.unobserve(e.target); laduj(e.target); } })); wk.slice(0, -6).forEach(el => io.observe(el)); }
  pokazMysli($("#czat"));
  trzymajDol();
  dociagnijCzat();                     // z pamięci mogło przyjść coś starego: dociągnij to, co trener dopisał w międzyczasie
  if (!czatZadanie && sessionStorage.czatZadanie) sledzCzat(+sessionStorage.czatZadanie);   // apka przeładowana w trakcie
  if (sessionStorage.omow) {
    const o = JSON.parse(sessionStorage.omow); delete sessionStorage.omow;
    t.value = o.tekst; wyslij(o.analiza || analizaId, o.analiza ? {} : { aktywnosc_id: o.id, omow: true });
  }
}
let WYK_CZAT = [];
// czat zawsze od samego dołu: przez 2 s po wejściu/wysłaniu każde urośnięcie czatu (wykresy, dymek) dociąga na dół,
// chyba że sam przewiniesz palcem
let dolStop = null;
function trzymajDol() {
  dolStop?.();
  const el = $("#czat"); if (!el) return;
  const dol = () => SKR.scrollTo(0, SKR.scrollHeight);
  dol(); requestAnimationFrame(dol);
  const ro = "ResizeObserver" in window ? new ResizeObserver(dol) : null; ro?.observe(el);
  const t = setInterval(dol, 150);
  const stop = () => { ro?.disconnect(); clearInterval(t); clearTimeout(k); ["touchstart", "wheel"].forEach(z => SKR.removeEventListener(z, stop)); if (dolStop === stop) dolStop = null; };
  const k = setTimeout(stop, 2000);
  ["touchstart", "wheel"].forEach(z => SKR.addEventListener(z, stop, { passive: true, once: true }));
  dolStop = stop;
}
const msg = m => `<div class="msg ${m.kto}"${m.id ? ` data-id="${m.id}"` : ""}>${esc(m.tresc)}${m.akcje && m.akcje.length ? `<div class="akcje">${m.akcje.map(esc).join(" · ")}</div>` : ""}</div>` +
  (m.wykresy || []).map(w => { WYK_CZAT.push(w); return `<div class="msg-wyk">${w.tytul ? `<div class="msg-wyk-t">${esc(w.tytul)}</div>` : ""}<div class="wyk-czat" data-n="${WYK_CZAT.length - 1}"><div class="szary">wykres…</div></div></div>`; }).join("");
async function wyslij(analizaId, dod = {}) {
  const t = $("#tekst"), tresc = t.value.trim();
  if (!tresc || czatZadanie) return;
  t.value = ""; $("#wyslij").disabled = true;
  $("#czat").insertAdjacentHTML("beforeend", msg({ kto: "ja lokalna", tresc }));
  czatZadanie = -1; pokazMysli($("#czat"));
  trzymajDol();
  let zid;
  try { zid = await api("czat", { tresc, analiza_id: analizaId ? +analizaId : null, ...dod }); }
  catch (e) { czatZadanie = 0; alert("Błąd: " + e.message); t.value = tresc; $("#czat .lokalna")?.remove(); pokazMysli($("#czat")); $("#wyslij").disabled = false; return; }
  sledzCzat(zid);
}
// zadanie czatu w tle: odpowiedź trenera pokazuje się od razu, gdy jest w bazie (nie czeka na układanie planu);
// dymek „układa plan” wisi do końca zadania. Działa też po przejściu na inną zakładkę i powrocie (i po przeładowaniu).
let czatZadanie = 0;
async function sledzCzat(zid) {
  czatZadanie = zid; sessionStorage.czatZadanie = zid;
  const el = $("#czat"); if (el) { pokazMysli(el); $("#wyslij") && ($("#wyslij").disabled = true); }
  try { await czekaj(zid, () => sprawdzDane()); }
  catch (e) { if (!/^\d|404/.test(e.message)) alert("Błąd: " + e.message); }
  czatZadanie = 0; delete sessionStorage.czatZadanie;
  const b = $("#wyslij"); if (b) b.disabled = false;
  await sprawdzDane();
  await dociagnijCzat();
  const c = $("#czat"); if (c) pokazMysli(c);
}
function pokazMysli(el) {
  if (!el) return;
  el.querySelector("#mysli")?.remove();
  if (!czatZadanie) return;
  const ost = [...el.querySelectorAll(".msg")].pop();
  const planuje = ost && ost.classList.contains("trener") && /przeplanowanie|nowa periodyzacja/.test(ost.querySelector(".akcje")?.textContent || "");
  el.insertAdjacentHTML("beforeend", `<div class="msg trener mysli" id="mysli">${planuje ? "Trener układa plan i wysyła na zegarek" : "Trener myśli"}</div>`);
}
// dopisz nowe wiadomości bez przerysowania ekranu (tekst w polu pisania zostaje)
let czatDociaga = null;
function dociagnijCzat() {
  if (!czatDociaga) czatDociaga = (async () => {
    const el = $("#czat");
    if (!el || !location.hash.startsWith("#czat")) return;
    let s; try { s = await siec("czat"); } catch (_) { return; }
    PAMIEC.set("czat", { s, t: Date.now() });
    if ($("#czat") !== el) return;
    const msgs = JSON.parse(s), ids = new Set(msgs.map(m => m.id));
    const blisko = SKR.scrollHeight - SKR.scrollTop - SKR.clientHeight < 250;
    const byly = new Set(el.querySelectorAll(".wyk-czat"));
    if ([...el.querySelectorAll(".msg[data-id]")].some(x => !ids.has(+x.dataset.id))) {   // coś usunięte (np. notka „czekam”)
      el.innerHTML = msgs.map(m => msg(m)).join("");
    } else {
      const nowe = msgs.filter(m => m.id > +(el.dataset.ostatni || 0));
      if (!nowe.length) { pokazMysli(el); return; }
      if (nowe.some(m => m.kto === "ja")) el.querySelectorAll(".lokalna").forEach(x => x.remove());
      el.querySelectorAll("#mysli, :scope > .szary").forEach(x => x.remove());
      el.insertAdjacentHTML("beforeend", nowe.map(m => msg(m)).join(""));
    }
    el.dataset.ostatni = Math.max(0, ...msgs.map(m => m.id || 0));
    el.querySelectorAll(".wyk-czat").forEach(w => { if (!byly.has(w) && !w._z) { w._z = 1; wykresCzatu(w, WYK_CZAT[+w.dataset.n]); } });
    pokazMysli(el);
    if (blisko) trzymajDol();
  })().finally(() => { czatDociaga = null; });
  return czatDociaga;
}

// ------------------------------------------------------------------ Ustawienia
async function pokazUstawienia() {
  location.hash = "#ustawienia";
}
async function ekranUstawien() {
  const u = await api("ustawienia");
  const pr = (k, n) => `<div class="przelacznik"><span>${n}</span><input type="checkbox" id="u-${k}" ${u[k] ? "checked" : ""}></div>`;
  const pushStan = !("PushManager" in window) ? "Na iPhonie: Safari → Share → Add to Home Screen, potem otwórz apkę z ekranu głównego." :
    Notification.permission === "granted" ? "włączone ✅" : Notification.permission === "denied" ? "zablokowane w ustawieniach iOS" : "wyłączone";
  widok.innerHTML = `<a class="btn" style="width:100%;text-align:center;margin-bottom:12px" href="#start">📝 Ankieta: cele i jak ma wyglądać plan</a>
    <div class="karta"><h3>Cele i warunki</h3>
    <label>Do czego trenujesz (cele, zawody, terminy)</label><textarea id="u-cele" rows="3">${esc(u.cele)}</textarea>
    <label>Kiedy możesz trenować</label><textarea id="u-dostepnosc" rows="2">${esc(u.dostepnosc)}</textarea>
    <label>Sprzęt (rower, trenażer, siłownia…)</label><textarea id="u-sprzet" rows="2">${esc(u.sprzet)}</textarea>
    <label>Sporty w planie</label><div class="wiersz">${["rower", "bieg", "silka"].map(s => `<label style="margin:0"><input type="checkbox" class="sport" value="${s}" ${u.sporty.includes(s) ? "checked" : ""}> ${SPORT_IKONA[s]} ${{ rower: "rower", bieg: "bieg", silka: "siłka" }[s]}</label>`).join("")}</div>
    <label>Planuj na ile dni do przodu</label><input type="number" id="u-plan_dni" min="3" max="14" value="${u.plan_dni}"></div>
    <div class="karta"><h3>Automatyka</h3>${pr("auto_zegarek", "Treningi same idą na zegarek")}${pr("analiza_rano", "Analiza poranna po śnie")}${pr("push", "Powiadomienia push")}${pr("linphone", "Kopia na Linphone")}
    <div class="wiersz" style="margin-top:10px"><span class="szary">Push: ${pushStan}</span></div>
    <div class="wiersz" style="margin-top:8px"><button onclick="wlaczPush()">🔔 Włącz powiadomienia</button><button class="drugi" onclick="testPush(this)">Test za 10 s</button></div></div>
    <div class="karta" id="karta-tlo"></div>
    <div class="karta"><h3>🖥️ Panel serwera</h3><div class="szary">Stan Pi, Minecraft, NAS, zdrowie. Bez ponownego logowania.</div>
      <a class="btn" id="do-panelu" style="margin-top:8px;display:inline-block;text-decoration:none">Przejdź do panelu</a></div>
    <div class="karta"><h3>🔐 Zapamiętane urządzenia</h3><div id="urz" class="szary">…</div>
      <button class="drugi" style="margin-top:8px" onclick="if(confirm('Wylogować wszystkie inne urządzenia?'))api('urzadzenia',{}).then(ekranUstawien)">Wyloguj inne urządzenia</button></div>
    <div class="karta"><h3>🏋️ Tierlista ćwiczeń siłowych</h3><div class="szary">Jedno ćwiczenie na linię. Trener układa siłkę głównie z S i A; wykluczonych nie daje. Nowe ćwiczenia oceniasz po treningu na ekranie Dziś.</div>
      ${TIERY.map(([t, n]) => `<label>${esc(n)}</label><textarea id="u-tier-${t}" rows="${Math.min(10, Math.max(2, ((u.tierlista || {})[t] || []).length + 1))}">${esc(((u.tierlista || {})[t] || []).join("\n"))}</textarea>`).join("")}
      <label>Zasady układania treningów</label><textarea id="u-zasady_silka" rows="6">${esc(u.zasady_silka || "")}</textarea></div>
    <div class="karta"><h3>Pamięć trenera</h3><div class="szary">Ustalenia z rozmów (jedno na linię)</div><textarea id="u-pamiec" rows="5">${esc((u.pamiec || []).join("\n"))}</textarea></div>
    <div class="wiersz"><button onclick="zapiszUst()">💾 Zapisz</button><button class="drugi" onclick="akcja('analiza')">📊 Analiza teraz</button><button class="drugi" onclick="akcja('sync')">🔄 Synchronizuj</button></div>`;
  $("#do-panelu").href = adresPanelu();
  urzadzenia();
  kartaTla();
}
async function urzadzenia() {
  const l = await api("urzadzenia");
  const el = document.getElementById("urz");
  if (el) el.innerHTML = l.map(u => `• ${esc(/iPhone/.test(u.opis) ? "iPhone" : /iPad/.test(u.opis) ? "iPad" : /Windows/.test(u.opis) ? "PC (Windows)" : /Mac/.test(u.opis) ? "Mac" : u.opis.slice(0, 40))} — ostatnio ${esc((u.ostatnio || "").slice(0, 10))}`).join("<br>") || "brak";
}
async function zapiszUst() {
  const u = { cele: $("#u-cele").value, dostepnosc: $("#u-dostepnosc").value, sprzet: $("#u-sprzet").value, plan_dni: +$("#u-plan_dni").value,
    sporty: [...document.querySelectorAll(".sport:checked")].map(x => x.value),
    tierlista: Object.fromEntries(TIERY.map(([t]) => [t, $("#u-tier-" + t).value.split("\n").map(s => s.trim()).filter(Boolean)])), zasady_silka: $("#u-zasady_silka").value.trim(), pamiec: $("#u-pamiec").value.split("\n").map(s => s.trim()).filter(Boolean) };
  ["auto_zegarek", "analiza_rano", "push", "linphone"].forEach(k => u[k] = $("#u-" + k).checked);
  await api("ustawienia", u);
  if (confirm("Zapisane. Przeplanować teraz według nowych ustawień?")) { location.hash = "#plan"; setTimeout(() => akcja("plan"), 300); }
}
async function testPush(b) {
  await api("push/test", { za: 10 });
  b.disabled = true;
  for (let i = 10; i > 0; i--) { b.textContent = `Zablokuj telefon… ${i}`; await new Promise(r => setTimeout(r, 1000)); }
  b.textContent = "Wysłane"; setTimeout(() => { b.textContent = "Test za 10 s"; b.disabled = false; }, 3000);
}
async function wlaczPush() {
  try {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) return alert("Najpierw dodaj apkę do ekranu głównego (Safari → Share → Add to Home Screen) i otwórz ją stamtąd.");
    const p = await Notification.requestPermission();
    if (p !== "granted") return alert("Brak zgody na powiadomienia.");
    const reg = await navigator.serviceWorker.ready;
    const klucz = await api("push/klucz");
    const raw = atob(klucz.replace(/-/g, "+").replace(/_/g, "/") + "==".slice(0, (4 - klucz.length % 4) % 4));
    const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: Uint8Array.from(raw, c => c.charCodeAt(0)) });
    await api("push/subskrybuj", sub.toJSON());
    await api("push/test", {});
    ekranUstawien();
  } catch (e) { alert("Nie udało się: " + e.message); }
}

// ------------------------------------------------------------------ Tło: domyślne kolorowe albo własna tapeta
// Tapeta zostaje na tym urządzeniu (IndexedDB, zmniejszona do 2000 px), nie idzie na serwer.
// Każdy tryb (kolory / tapeta) ma własne ustawienia szkła; nowa tapeta zaczyna od środka, szkło zostaje.
const TLO_DOM = { kolory: { szklo: 50, ciemn: 0 }, tapeta: { szklo: 50, ciemn: 15, ciemno: 35, dop: "cover", x: 50, y: 50, zoom: 100 } };
const TLO = { tryb: "kolory", ust: {} };
try { const z = JSON.parse(localStorage.getItem("trener:tlo") || "{}");
  TLO.tryb = z.tryb || "kolory"; TLO.ust = z.ust || {};
  if (z.ciemno != null && !TLO.ust.tapeta) TLO.ust.tapeta = { ciemno: z.ciemno };   // stary zapis
} catch (e) {}
const tloU = () => { const u = TLO.ust[TLO.tryb] ||= {}; for (const [k, v] of Object.entries(TLO_DOM[TLO.tryb])) u[k] ??= v; return u; };   // ten sam obiekt (suwaki trzymają do niego referencję)
const tloZapisz = () => localStorage.setItem("trener:tlo", JSON.stringify(TLO));
const tloBaza = () => new Promise((ok, zle) => { const r = indexedDB.open("trener-tlo", 1); r.onupgradeneeded = () => r.result.createObjectStore("t"); r.onsuccess = () => ok(r.result); r.onerror = () => zle(r.error); });
async function tloPlik(blob) {
  const db = await tloBaza();
  return new Promise((ok, zle) => { const tx = db.transaction("t", blob === undefined ? "readonly" : "readwrite"), st = tx.objectStore("t");
    const r = blob === undefined ? st.get("tapeta") : blob === null ? st.delete("tapeta") : st.put(blob, "tapeta");
    r.onsuccess = () => ok(r.result); r.onerror = () => zle(r.error); });
}
// tylko zmienne CSS i styl #tapeta: szybkie, do podglądu na żywo przy suwakach
function tloStyl() {
  const u = tloU(), el = document.getElementById("tapeta"), root = document.documentElement.style;
  root.setProperty("--mleko", ((100 - u.szklo) / 100).toFixed(2));
  root.setProperty("--ciemn", (u.ciemn / 100).toFixed(2));
  document.body.classList.toggle("ultra", u.szklo >= 100);
  if (!el) return;
  el.style.setProperty("--ciemno", ((u.ciemno ?? 35) / 100).toFixed(2));
  el.style.backgroundSize = { cover: "cover", contain: "contain", rozciagnij: "100% 100%" }[u.dop] || "cover";
  el.style.backgroundPosition = `${u.x ?? 50}% ${u.y ?? 50}%`;
  el.style.transformOrigin = `${u.x ?? 50}% ${u.y ?? 50}%`;
  el.style.transform = (u.zoom || 100) > 100 ? `scale(${u.zoom / 100})` : "";
}
let tloUrl = null;
async function zastosujTlo() {
  let el = document.getElementById("tapeta");
  if (!el) { el = document.createElement("div"); el.id = "tapeta"; document.body.prepend(el); }
  const blob = TLO.tryb === "tapeta" ? await tloPlik().catch(() => null) : null;
  if (tloUrl) { URL.revokeObjectURL(tloUrl); tloUrl = null; }
  if (blob) { tloUrl = URL.createObjectURL(blob); el.style.backgroundImage = `url("${tloUrl}")`; }
  document.body.classList.toggle("tapeta", !!blob);
  tloStyl();
}
async function wgrajTapete(plik) {
  if (!plik) return;
  const img = await createImageBitmap(plik).catch(() => null);
  if (!img) return alert("Nie udało się otworzyć zdjęcia.");
  const k = Math.min(1, 2000 / Math.max(img.width, img.height)), c = document.createElement("canvas");
  c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
  c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
  const blob = await new Promise(r => c.toBlob(r, "image/jpeg", .88));
  await tloPlik(blob);
  TLO.tryb = "tapeta"; Object.assign(tloU(), { x: 50, y: 50, zoom: 100 }); tloZapisz();
  await zastosujTlo(); kartaTla();
}
const suwak = (id, napis, v, min, max, krok, pokaz) =>
  `<label class="suwak"><span>${napis}</span><b id="${id}-ile">${pokaz(v)}</b></label><input type="range" id="${id}" min="${min}" max="${max}" step="${krok}" value="${v}">`;
const pokazSzklo = v => v >= 100 ? "✨ ultraszkło" : v <= 0 ? "mleczne" : v + "%";
async function kartaTla() {
  const k = document.getElementById("karta-tlo"); if (!k) return;
  const jest = !!(await tloPlik().catch(() => null)), u = tloU(), tap = TLO.tryb === "tapeta";
  k.innerHTML = `<h3>🎨 Tło</h3><div class="szary">Zapamiętane tylko na tym urządzeniu. Każde tło ma swoje ustawienia szkła.</div>
    <div class="chipy wiersz" style="margin-top:10px">
      <button class="chip ${!tap ? "akt" : ""}" data-t="kolory">🌈 Kolorowe (domyślne)</button>
      <button class="chip ${tap ? "akt" : ""}" data-t="tapeta">🖼️ Moja tapeta</button></div>
    ${tap ? `<div class="wiersz" style="margin-top:10px"><button class="drugi" id="tlo-wybierz">${jest ? "Zmień zdjęcie" : "Wybierz zdjęcie"}</button>${jest ? `<button class="drugi" id="tlo-usun">Usuń tapetę</button>` : ""}</div>
    <input type="file" id="tlo-plik" accept="image/*" hidden>
    ${jest ? `<div class="grupa-t">Ułożenie tapety</div>
    <div class="chipy wiersz">${[["cover", "Wypełnij"], ["contain", "Cała"], ["rozciagnij", "Rozciągnij"]].map(([d, n]) => `<button class="chip ${u.dop === d ? "akt" : ""}" data-dop="${d}">${n}</button>`).join("")}</div>
    ${suwak("tlo-x", "Poziomo", u.x, 0, 100, 1, v => ["⬅︎ lewo", "środek", "prawo ➡︎"][v < 34 ? 0 : v > 66 ? 2 : 1] + ` ${v}%`)}
    ${suwak("tlo-y", "Pionowo", u.y, 0, 100, 1, v => ["⬆︎ góra", "środek", "dół ⬇︎"][v < 34 ? 0 : v > 66 ? 2 : 1] + ` ${v}%`)}
    ${suwak("tlo-zoom", "Powiększenie", u.zoom, 100, 300, 5, v => v + "%")}
    ${suwak("tlo-ciemno", "Przyciemnienie tapety", u.ciemno, 0, 85, 5, v => v + "%")}` : ""}` : ""}
    <div class="grupa-t">Szkło</div>
    ${suwak("tlo-szklo", "Mleczne ↔ przezroczyste", u.szklo, 0, 100, 5, pokazSzklo)}
    ${suwak("tlo-ciemn", "Przyciemnienie szkła", u.ciemn, 0, 100, 5, v => v + "%")}
    <button class="drugi" id="tlo-reset" style="margin-top:12px">Przywróć domyślne</button>`;
  k.querySelectorAll("[data-t]").forEach(b => b.onclick = async () => {
    TLO.tryb = b.dataset.t; tloZapisz();
    await zastosujTlo(); kartaTla();
    if (TLO.tryb === "tapeta" && !jest) $("#tlo-plik", k)?.click();
  });
  k.querySelectorAll("[data-dop]").forEach(b => b.onclick = () => { u.dop = b.dataset.dop; tloZapisz(); tloStyl(); kartaTla(); });
  const pl = $("#tlo-plik", k);
  if (pl) { pl.onchange = () => wgrajTapete(pl.files[0]); $("#tlo-wybierz", k).onclick = () => pl.click(); }
  const us = $("#tlo-usun", k); if (us) us.onclick = async () => { await tloPlik(null); TLO.tryb = "kolory"; tloZapisz(); await zastosujTlo(); kartaTla(); };
  $("#tlo-reset", k).onclick = () => { const z = TLO.tryb === "tapeta" ? { dop: u.dop, x: u.x, y: u.y, zoom: u.zoom } : {}; for (const k in u) delete u[k]; Object.assign(u, TLO_DOM[TLO.tryb], z); tloZapisz(); tloStyl(); kartaTla(); };
  [["tlo-x", "x", v => ["⬅︎ lewo", "środek", "prawo ➡︎"][v < 34 ? 0 : v > 66 ? 2 : 1] + ` ${v}%`], ["tlo-y", "y", v => ["⬆︎ góra", "środek", "dół ⬇︎"][v < 34 ? 0 : v > 66 ? 2 : 1] + ` ${v}%`],
   ["tlo-zoom", "zoom", v => v + "%"], ["tlo-ciemno", "ciemno", v => v + "%"], ["tlo-szklo", "szklo", pokazSzklo], ["tlo-ciemn", "ciemn", v => v + "%"]].forEach(([id, pole, f]) => {
    const r = $("#" + id, k); if (!r) return;
    r.oninput = () => { u[pole] = +r.value; $(`#${id}-ile`, k).textContent = f(+r.value); tloStyl(); };
    r.onchange = tloZapisz;
  });
}
zastosujTlo();

// ------------------------------------------------------------------ Jedzenie: dziennik kalorii, skaner kodów, cel od trenera
const POSILEK = { sniadanie: "Śniadanie", drugie: "Drugie śniadanie", obiad: "Obiad", przekaska: "Przekąski", kolacja: "Kolacja" };
const MAKRO = [["b", "Białko", KOLOR.niebieski], ["w", "Węglowodany", KOLOR.zolty], ["t", "Tłuszcz", KOLOR.fiolet]];
const dzisISO = () => { const x = new Date(); x.setMinutes(x.getMinutes() - x.getTimezoneOffset()); return x.toISOString().slice(0, 10); };
let DIETA = null, dietaDzien = null;

function kolko(zj, cel, dzwiek = 84) {   // pierścień kcal: ile zjedzone z celu; ponad cel = kolor uwagi + etykieta
  const r = 34, o = 2 * Math.PI * r, p = cel ? Math.min(zj / cel, 1) : 0, ponad = cel && zj > cel * 1.05;
  return `<svg class="pierscien" width="${dzwiek}" height="${dzwiek}" viewBox="0 0 84 84"><circle cx="42" cy="42" r="${r}" fill="none" stroke="var(--karta2)" stroke-width="8"/>
    <circle cx="42" cy="42" r="${r}" fill="none" stroke="${ponad ? "var(--uwaga)" : "var(--akcent)"}" stroke-width="8" stroke-linecap="round" stroke-dasharray="${o * p} ${o}" transform="rotate(-90 42 42)"/></svg>`;
}
const paskiMakro = (s, c) => `<div class="makra">${MAKRO.map(([k, n, kol]) => `<div><div class="wiersz-m"><span>${n}</span><b>${lb(s[k])}<small> / ${lb(c[k])} g</small></b></div>
  <div class="pasek-pct"><i style="width:${Math.min(100, 100 * (s[k] || 0) / (c[k] || 1))}%;background:${kol}"></i></div></div>`).join("")}</div>`;

// tydzień pon–nd: liczy się średnia, nie każdy dzień z osobna (jednego dnia więcej, drugiego mniej)
// jedna sekcja tygodnia (kcal albo białko): łączny bilans, słupki, średnia i ile dziennie do niedzieli
const TYDZ = [
  { k: "kcal", kc: "cel", jedn: "kcal", nazwa: "Kalorie", kolor: KOLOR.morski, h: 130 },
  { k: "b", kc: "cel_b", jedn: "g", nazwa: "Białko", kolor: KOLOR.niebieski, h: 110 }
];
function tydzienMakro(m, ctx) {
  const { hist, d, dzien, dzis, dni, po } = ctx, jn = ` ${m.jedn}`;
  const zj = k => k === dzien ? d.suma[m.k] : po[k] ? po[k][m.k] : null;
  const cel = k => (k === dzien ? d.cel[m.k] : po[k] && po[k][m.kc]) || d.cel[m.k];
  // dni zamknięte = przed dzisiaj i z wpisami (dzisiejszy dzień jeszcze trwa, nie zaniża bilansu)
  const zam = dni.filter(k => k < dzis && zj(k) != null), jestDzis = dni.includes(dzis);
  const lacznie = v => v >= 0 ? `nadwyżka <b>+${lb(Math.round(v))}${jn}</b>` : `brakło <b>${lb(Math.round(-v))}${jn}</b>`;
  const bilans = zam.reduce((a, k) => a + zj(k) - cel(k), 0), sredniCel = srednia(dni.filter(k => k <= dzis).map(cel));
  const zostaloDni = jestDzis ? dni.filter(k => k >= dzis).length : 0;
  const naDzien = zostaloDni ? Math.round(d.cel[m.k] - bilans / zostaloDni) : null;
  const ileDni = n => `${n} ${n === 1 ? "dzień" : "dni"}`;
  const naglowek = zam.length ? `Łącznie: ${lacznie(bilans)} <span class="szary">(${ileDni(zam.length)}${jestDzis ? ", bez dzisiaj" : ""})</span>`
    : `<span class="szary">${jestDzis ? "Pierwszy dzień tygodnia: bilans od jutra." : "Brak wpisów."}</span>`;
  const opis = [
    zam.length && `Średnio <b>${lb(srednia(zam.map(zj)))}</b>${jn}/dzień przy celu ~${lb(sredniCel)}${jn}.`,
    naDzien != null && zam.length && `Żeby tydzień wyszedł na cel: ~<b>${lb(naDzien)}</b>${jn} dziennie do niedzieli (${ileDni(zostaloDni)}).`
  ].filter(Boolean).map(t => `<div>${t}</div>`).join("");
  // poprzedni tydzień (pełny), żeby w poniedziałek też było co zobaczyć
  const pop = ctx.pop.filter(k => po[k] && po[k][m.k] != null);
  const bilP = pop.reduce((a, k) => a + po[k][m.k] - cel(k), 0);
  const opisP = pop.length ? `<div>Poprzedni tydzień: łącznie ${lacznie(bilP)}, średnio ${lb(srednia(pop.map(k => po[k][m.k])))}${jn}/dzień przy celu ~${lb(srednia(pop.map(cel)))}${jn} (${ileDni(pop.length)}).</div>` : "";
  return `<div class="tydz-sek"><div class="tydz-l"><b>${m.nazwa}</b> · ${naglowek}</div>
    ${wyk({ typ: "slupki", x: dni, serie: [{ nazwa: m.nazwa.toLowerCase(), y: dni.map(k => k > dzis ? null : zj(k)), kolor: m.kolor }], ref: sredniCel, refNazwa: "cel", jedn: m.jedn, etX: k => DNI[new Date(k + "T12:00").getDay()], etDymek: dataPL, h: m.h })}
    <div class="szary" style="margin-top:6px">${opis}${opisP}</div></div>`;
}
function tydzienKcal(hist, d, dzien, dzis) {
  const pon = dzienMinus(dzien, (new Date(dzien + "T12:00").getDay() + 6) % 7);
  const dni = Array.from({ length: 7 }, (_, i) => dzienMinus(pon, -i)), po = Object.fromEntries(hist.map(q => [q.dzien, q]));
  if (!dni.some(k => k < dzis && (k === dzien || po[k])) && !dni.includes(dzis)) return "";
  const ctx = { hist, d, dzien, dzis, dni, po, pop: Array.from({ length: 7 }, (_, i) => dzienMinus(pon, 7 - i)) };
  return `<div class="karta"><div class="kt">Ten tydzień <span class="szary">· ${dataKr(pon)} – ${dataKr(dni[6])}</span></div>
    ${TYDZ.map(m => tydzienMakro(m, ctx)).join("")}</div>`;
}

async function pokazJedzenie(dzien) {
  dietaDzien = dzien && /^\d{4}-\d\d-\d\d$/.test(dzien) ? dzien : dzisISO();
  const [d, hist] = await Promise.all([api("dieta?dzien=" + dietaDzien), api("dieta/historia?dni=28")]);
  DIETA = d;
  const c = d.cel, s = d.suma, zostalo = Math.round(c.kcal - s.kcal), dzis = dzisISO();
  let h = `<div class="dni-nav"><a class="btn drugi" href="#jedzenie/${dzienMinus(dietaDzien, 1)}">‹</a>
    <b>${dietaDzien === dzis ? "Dziś" : dietaDzien === dzienMinus(dzis, -1) ? "Jutro" : dataPL(dietaDzien)}</b>
    ${dietaDzien < dzienMinus(dzis, -1) ? `<a class="btn drugi" href="#jedzenie/${dzienMinus(dietaDzien, -1)}">›</a>` : `<span style="width:44px"></span>`}</div>`;
  h += `<div class="karta hero"><div class="hero-wiersz"><div>
      <div class="szary">${zostalo >= 0 ? "Zostało" : "Ponad cel"}</div>
      <div class="duzy">${lb(Math.abs(zostalo))}<small>kcal</small></div>
      <div class="szary">zjedzone ${lb(s.kcal)} z ${lb(c.kcal)} kcal</div></div>${kolko(s.kcal, c.kcal)}</div>
    ${paskiMakro(s, c)}</div>`;
  d.posilki.forEach(p => {
    const w = d.wpisy.filter(x => x.posilek === p), sk = w.reduce((a, x) => a + x.kcal, 0);
    h += `<div class="karta posilek"><div class="kt wiersz" style="justify-content:space-between"><span>${POSILEK[p]}</span><span class="posilek-suma">${w.length ? `${MAKRO.map(([k, n, kol]) => `<b style="color:${kol}" title="${n}">${lb(w.reduce((a, x) => a + (x[k] || 0), 0))}</b>`).join("")}<span class="szary">${lb(sk)} kcal</span>` : ""}</span></div>
      ${w.map(x => `<div class="pozycja klik" onclick="edytujWpis(${x.id})"><div><div>${esc(x.nazwa)}</div><div class="szary">${x.gram ? lb(x.gram) + " g · " : ""}B ${lb(x.b)} · W ${lb(x.w)} · T ${lb(x.t)}</div></div><b>${lb(x.kcal)}</b></div>`).join("")}
      <button class="drugi dodaj" onclick="dodajJedzenie('${p}')">+ Dodaj</button></div>`;
  });
  const hx = hist.filter(x => x.dzien >= dzienMinus(dzis, 13));
  if (hx.length > 1) {
    const x = Array.from({ length: 14 }, (_, i) => dzienMinus(dzis, 13 - i)), po = Object.fromEntries(hx.map(q => [q.dzien, q]));
    const cele = hx.map(q => q.cel).filter(Boolean);
    h += `<div class="karta"><div class="kt">Ostatnie 2 tygodnie</div>
      ${wyk({ typ: "slupki", x, serie: [{ nazwa: "zjedzone", y: x.map(k => po[k] ? po[k].kcal : null), kolor: KOLOR.niebieski }], ref: cele.length ? srednia(cele) : null, refNazwa: "cel", jedn: "kcal", etX: dataKr, etDymek: dataPL, h: 150 })}
      <div class="szary">Średnio ${lb(srednia(hx.map(q => q.kcal)))} kcal, białko ${lb(srednia(hx.map(q => q.b)))} g (dni z wpisami).</div></div>`;
  }
  // na dole: cel na dziś i tydzień
  h += `<div class="karta" id="cel-trenera"><div class="kt">Cel ${dietaDzien > dzis ? "na jutro" : dietaDzien < dzis ? "tego dnia" : "na dziś"} ${c.zrodlo === "trener" ? `<span class="znaczek">od trenera</span>` : `<span class="znaczek">ze wzoru</span>`}</div>
    ${c.liczy ? `<div class="szary"><span class="mysli">Trener liczy cel pod dzisiejszy trening</span></div>` : ""}
    ${dietaDzien > dzis ? `<div class="szary">Wstępnie z planu treningu. Trener policzy dokładny cel jutro rano (sen, Garmin).</div>` : ""}
    ${c.komentarz ? `<div>${esc(c.komentarz)}</div>` : ""}${c.pory ? `<div class="szary" style="margin-top:6px">${esc(c.pory)}</div>` : ""}
    <div class="szary" style="margin-top:8px">${[c.masa && `masa ${lb(c.masa, 1)} kg`, c.fat && `tłuszcz ${lb(c.fat, 1)}%`, `wydatek ~${lb(c.tdee)} kcal`, c.spocz && `spoczynkowe ${lb(c.spocz)}`, c.ruch_dnia && `ruch w ciągu dnia ~${lb(c.ruch_dnia)}`,
      c.trening_kcal ? `treningi ~${lb(c.trening_kcal)}${c.trening_zrobione && c.trening_zrobione < c.trening_kcal ? ` (zrobione ${lb(c.trening_zrobione)} + plan ~${lb(c.trening_kcal - c.trening_zrobione)})` : c.trening_zrobione ? " (zrobione)" : " (plan)"}` : "dzień bez treningu",
      c.ruch_ekstra && `dodatkowy ruch dziś +${lb(c.ruch_ekstra)}`].filter(Boolean).join(" · ")}</div>
    ${dietaDzien > dzis ? "" : `<div class="wiersz" style="margin-top:10px"><button class="drugi" onclick="przeliczCel()">Przelicz</button></div>`}</div>`;
  h += tydzienKcal(hist, d, dietaDzien, dzis);
  widok.innerHTML = h;
  rysuj(widok);
  if (c.liczy) czekajNaCel(dietaDzien);
}

async function czekajNaCel(dzien) {
  const nr = nawNr;
  for (let i = 0; i < 40; i++) {
    await new Promise(r => setTimeout(r, 5000));
    if (nr !== nawNr || !location.hash.startsWith("#jedzenie")) return;
    let d; try { d = await api("dieta?dzien=" + dzien); } catch (e) { return; }
    if (!d.cel.liczy) { if (!zajety()) pokazJedzenie(dzien); return; }
  }
}
async function przeliczCel() {
  const k = $("#cel-trenera");
  if (k) k.insertAdjacentHTML("beforeend", `<div class="szary"><span class="mysli">Trener liczy</span></div>`);
  try { await czekaj(await api("dieta/przelicz", { dzien: dietaDzien })); } catch (e) { alert("Błąd: " + e.message); }
  pokazJedzenie(dietaDzien);
}

// ---- arkusz (okno od dołu) do dodawania / edycji
function arkusz(html) {
  zamknijArkusz();
  const t = document.createElement("div");
  t.className = "arkusz-tlo";
  t.innerHTML = `<div class="arkusz" role="dialog"><div class="uchwyt"></div>${html}</div>`;
  t.addEventListener("click", e => { if (e.target === t) zamknijArkusz(); });
  document.body.appendChild(t);
  document.body.classList.add("arkusz-otwarty");
  return t.firstChild;
}
function zamknijArkusz() {
  stopSkaner();
  document.querySelectorAll(".arkusz-tlo").forEach(x => x.remove());
  document.querySelectorAll("input[data-zdj]").forEach(x => x.remove());
  document.body.classList.remove("arkusz-otwarty");
}

let posilekDod = "przekaska", szukT = 0;
function dodajJedzenie(posilek) {
  posilekDod = posilek;
  const a = arkusz(`<div class="kt">Dodaj · ${POSILEK[posilek]}</div>
    <div class="wiersz"><button onclick="skanuj()" class="skanuj"><svg viewBox="0 0 24 24"><path d="M4 7V5a1 1 0 0 1 1-1h2M17 4h2a1 1 0 0 1 1 1v2M20 17v2a1 1 0 0 1-1 1h-2M7 20H5a1 1 0 0 1-1-1v-2M7 8v8M10 8v8M13 8v8M16 8v8"/></svg>Skanuj kod</button>
      <button class="drugi" onclick="formRecznie()">Wpisz ręcznie</button></div>
    <div class="wiersz" style="margin-top:8px"><button class="drugi" onclick="tabelkaZdjecie()">📷 Zdjęcie tabelki</button>
      <button class="drugi" onclick="posilekZdjecie()">🍽️ Zdjęcie posiłku</button></div>
    <input type="text" id="szukaj" placeholder="Szukaj produktu…" autocomplete="off" style="margin-top:12px">
    <div id="wyniki" class="wyniki"><div class="szary" style="padding:10px 2px">Ładuję ostatnie…</div></div>`);
  const inp = a.querySelector("#szukaj");
  inp.oninput = () => { clearTimeout(szukT); szukT = setTimeout(() => szukaj(inp.value), 450); };
  szukaj("");
}
let PRODUKTY = {};
async function szukaj(q) {
  const el = $("#wyniki"); if (!el) return;
  if (q) el.innerHTML = `<div class="szary" style="padding:10px 2px"><span class="mysli">Szukam</span></div>`;
  let l;
  try { l = await api("produkty?q=" + encodeURIComponent(q)); } catch (e) { el.innerHTML = `<div class="szary">${esc(e.message)}</div>`; return; }
  if (($("#szukaj") || {}).value !== q && q !== "") return;
  l.forEach(p => PRODUKTY[p.kod] = p);
  el.innerHTML = l.length ? (q ? "" : `<div class="szary" style="padding:4px 2px">Ostatnio</div>`) + l.map(p => `<div class="pozycja klik" onclick="wybierz('${esc(p.kod)}')">
      <div><div>${esc(p.nazwa)}</div><div class="szary">${esc(p.marka || "")}${p.marka ? " · " : ""}na 100 g: B ${lb(p.b, 1)} · W ${lb(p.w, 1)} · T ${lb(p.t, 1)}</div></div><b>${lb(p.kcal)}</b></div>`).join("")
    : `<div class="szary" style="padding:10px 2px">${q ? "Nic nie znalazłem. Zeskanuj kod albo wpisz ręcznie." : "Jeszcze nic nie jadłeś w apce. Zeskanuj kod albo wyszukaj."}</div>`;
}

function wybierz(kod) {
  const p = PRODUKTY[kod]; if (!p) return;
  const g0 = p.czesto_g || p.porcja_g || 100;
  const zw = p.czesto_g, cale = p.masa_g && Math.round(p.masa_g), por = p.porcja_g && Math.round(p.porcja_g);
  const chipy = [[zw, "zwykle"], [cale, "całe"], [por, "porcja"], [50], [100], [150], [200], [250]]
    .filter(([g], i, t) => g && t.findIndex(([h]) => h === g) === i);
  const a = arkusz(`<div class="kt">${esc(p.nazwa)}</div><div class="szary">${esc(p.marka || "")}${p.marka ? " · " : ""}na 100 g: ${lb(p.kcal)} kcal · B ${lb(p.b, 1)} · W ${lb(p.w, 1)} · T ${lb(p.t, 1)}
      · <a href="javascript:void 0" onclick="poprawProdukt('${esc(p.kod)}', () => wybierz('${esc(p.kod)}'))">Popraw</a></div>
    <label>Ile gramów</label><input type="number" id="gram" inputmode="decimal" value="${g0}">
    <div class="chipy wiersz">${chipy.map(([g, n]) => `<button class="chip" data-g="${g}">${g} g${n ? ` <span class="szary">· ${n}</span>` : ""}</button>`).join("")}</div>
    <div id="podglad" class="podglad"></div>
    <label>Posiłek</label><select id="posilek">${Object.entries(POSILEK).map(([k, n]) => `<option value="${k}" ${k === posilekDod ? "selected" : ""}>${n}</option>`).join("")}</select>
    <div class="wiersz" style="margin-top:14px"><button id="ok">Dodaj</button><button class="drugi" onclick="dodajJedzenie(posilekDod)">Wróć</button></div>`);
  const gi = a.querySelector("#gram");
  const pod = () => { const k = (+gi.value || 0) / 100; a.querySelector("#podglad").innerHTML = `<b>${lb(p.kcal * k)} kcal</b> · B ${lb(p.b * k)} g · W ${lb(p.w * k)} g · T ${lb(p.t * k)} g`; };
  gi.oninput = pod; pod();
  a.querySelectorAll("[data-g]").forEach(b => b.onclick = () => { gi.value = b.dataset.g; pod(); });
  a.querySelector("#ok").onclick = async () => {
    const gram = +gi.value; if (!(gram > 0)) { gi.focus(); return; }
    try { await api("dieta/wpis", { dzien: dietaDzien, posilek: a.querySelector("#posilek").value, kod: p.kod, gram }); } catch (e) { alert(e.message); return; }
    zamknijArkusz(); pokazJedzenie(dietaDzien);
  };
}

function formRecznie(kod = "", zdj = null, pod = {}) {
  const a = arkusz(`<div class="kt">Nowy produkt</div>${kod ? `<div class="szary">${pod.nazwa ? `Open Food Facts zna ${esc(pod.nazwa)}, ale bez wartości odżywczych.` : `Kodu ${esc(kod)} nie ma w Open Food Facts.`} Zeskanuj tabelkę z opakowania, a wpiszę makro sam; zapamiętam produkt na następny raz.</div>
    <button id="r-skan" style="width:100%;margin-top:10px">📷 Zeskanuj tabelkę</button>` : `<div class="szary">Wartości na 100 g (z etykiety). Zapamiętam produkt.</div>`}
    <label>Nazwa</label><input type="text" id="r-nazwa" value="${esc([pod.nazwa, pod.marka && !(pod.nazwa || "").includes(pod.marka) ? pod.marka : ""].filter(Boolean).join(" · "))}">
    <label>Wpisuję wartości</label><div class="chipy wiersz"><button class="chip akt" data-tryb="100">na 100 g</button><button class="chip" data-tryb="cale">na całe opakowanie</button></div>
    <div class="pola4"><div><label>kcal</label><input type="number" inputmode="decimal" id="r-kcal"></div><div><label>białko</label><input type="number" inputmode="decimal" id="r-b"></div>
      <div><label>węgle</label><input type="number" inputmode="decimal" id="r-w"></div><div><label>tłuszcz</label><input type="number" inputmode="decimal" id="r-t"></div></div>
    <div class="szary" id="r-przel" style="margin-top:4px"></div>
    <div class="wiersz" style="margin-top:8px"><button class="drugi" id="r-zdj">${kod ? "🖼️ Z galerii" : "📷 Odczytaj ze zdjęcia"}</button><span class="szary" id="r-info"></span></div>
    <div class="pola4"><div><label>Ile zjadłeś (g)</label><input type="number" inputmode="decimal" id="r-g" value="100"></div>
      <div><label id="r-masa-l">Całe opakowanie (g)</label><input type="number" inputmode="decimal" id="r-masa" value="${pod.masa_g || ""}" placeholder="opcjonalnie"></div></div>
    <div class="wiersz" style="margin-top:14px"><button id="ok">Dodaj</button><button class="drugi" onclick="dodajJedzenie(posilekDod)">Wróć</button></div>`);
  a.querySelector("#r-zdj").onclick = () => wybierzZdjecie(f => czytajTabelke(a, f));
  const sk = a.querySelector("#r-skan");
  if (sk) sk.onclick = () => wybierzZdjecie(f => czytajTabelke(a, f), true);
  if (zdj) czytajTabelke(a, zdj);
  const v = id => a.querySelector(id).value.replace(",", ".");
  // „na całe opakowanie”: wartości z przodu paczki → przeliczamy na 100 g z masy opakowania
  const tryb = () => a.querySelector("[data-tryb].akt").dataset.tryb;
  const na100 = x => tryb() === "cale" ? (+v("#r-masa") > 0 ? Math.round(x * 1000 / +v("#r-masa")) / 10 : NaN) : x;
  const przel = () => {
    const m = +v("#r-masa"), e = a.querySelector("#r-przel");
    a.querySelector("#r-masa").placeholder = tryb() === "cale" ? "wymagane" : "opcjonalnie";
    if (tryb() !== "cale") { e.textContent = "Tak jak w tabelce, kolumna „100 g”."; return; }
    if (!(m > 0)) { e.textContent = "Wpisz niżej, ile waży całe opakowanie — przeliczę na 100 g."; return; }
    e.textContent = v("#r-kcal") === "" ? `Przeliczę na 100 g (opakowanie ${m} g).` :
      `Na 100 g: ${lb(na100(+v("#r-kcal")))} kcal · B ${lb(na100(+v("#r-b") || 0), 1)} · W ${lb(na100(+v("#r-w") || 0), 1)} · T ${lb(na100(+v("#r-t") || 0), 1)}`;
  };
  a.querySelectorAll("[data-tryb]").forEach(b => b.onclick = () => {
    a.querySelectorAll("[data-tryb]").forEach(x => x.classList.toggle("akt", x === b));
    const g = a.querySelector("#r-g");
    if (b.dataset.tryb === "cale" && +v("#r-masa") > 0 && g.value === "100") g.value = v("#r-masa");
    if (b.dataset.tryb === "cale" && !(+v("#r-masa") > 0)) a.querySelector("#r-masa").focus();
    przel();
  });
  ["#r-kcal", "#r-b", "#r-w", "#r-t", "#r-masa"].forEach(id => a.querySelector(id).addEventListener("input", przel));
  let gRecznie = false; a.querySelector("#r-g").addEventListener("input", () => gRecznie = true);
  a.querySelector("#r-masa").addEventListener("input", () => { if (tryb() === "cale" && !gRecznie && +v("#r-masa") > 0) a.querySelector("#r-g").value = v("#r-masa"); });
  a._na100 = () => a.querySelector('[data-tryb="100"]').click();      // tabelka ze zdjęcia jest zawsze na 100 g
  przel();
  a.querySelector("#ok").onclick = async () => {
    const nazwa = v("#r-nazwa").trim(), kcal = na100(+v("#r-kcal")), gram = +v("#r-g");
    if (tryb() === "cale" && !(+v("#r-masa") > 0)) { alert("Podaj, ile waży całe opakowanie (g)"); a.querySelector("#r-masa").focus(); return; }
    if (!nazwa || !(kcal >= 0) || v("#r-kcal") === "" || !(gram > 0)) { alert("Podaj nazwę, kcal i gramy"); return; }
    try { await api("dieta/wpis", { dzien: dietaDzien, posilek: posilekDod, gram, produkt: { kod, nazwa, kcal, b: na100(+v("#r-b") || 0), w: na100(+v("#r-w") || 0), t: na100(+v("#r-t") || 0), masa_g: +v("#r-masa") || null } }); } catch (e) { alert(e.message); return; }
    zamknijArkusz(); pokazJedzenie(dietaDzien);
  };
  if (!zdj && !kod) a.querySelector("#r-nazwa").focus();
}

function edytujWpis(id) {
  const x = DIETA.wpisy.find(q => q.id === id); if (!x) return;
  const a = arkusz(`<div class="kt">${esc(x.nazwa)}</div><div class="szary">${lb(x.kcal)} kcal · B ${lb(x.b)} · W ${lb(x.w)} · T ${lb(x.t)}</div>
    ${x.gram ? `<label>Gramy</label><input type="number" inputmode="decimal" id="gram" value="${x.gram}">` : ""}
    <div class="wiersz" style="margin-top:14px">${x.gram ? `<button id="ok">Zapisz</button>` : ""}<button class="drugi zle-t" id="usun">Usuń</button>
      ${x.kod ? `<button class="drugi" id="popraw">Popraw wartości produktu</button>` : ""}</div>`);
  if (x.kod) a.querySelector("#popraw").onclick = () => poprawProdukt(x.kod, () => edytujWpis(id));
  if (x.gram) a.querySelector("#ok").onclick = async () => { await api("dieta/wpis", { id, gram: +a.querySelector("#gram").value, dzien: dietaDzien }); zamknijArkusz(); pokazJedzenie(dietaDzien); };
  a.querySelector("#usun").onclick = async () => { await api("dieta/wpis", { usun: id, dzien: dietaDzien }); zamknijArkusz(); pokazJedzenie(dietaDzien); };
}

// ---- zdjęcia: tabelka wartości odżywczych i gotowy posiłek (czyta Claude na Pi)
function wybierzZdjecie(fn, aparat = false) {        // wywołuj prosto z kliknięcia (iOS wymaga gestu); aparat albo galeria
  const i = document.createElement("input"); i.type = "file"; i.accept = "image/*";
  if (aparat) i.setAttribute("capture", "environment");              // od razu aparat (bez pytania o galerię)
  // iOS gubi zdarzenie change, gdy pole nie jest w dokumencie — wpinamy je niewidoczne i sprzątamy po wyborze
  i.style.cssText = "position:fixed;left:-1000px;top:0;width:1px;height:1px;opacity:0";
  document.querySelectorAll("input[data-zdj]").forEach(x => x.remove());
  i.dataset.zdj = 1; document.body.appendChild(i);
  let raz = false;
  const wez = () => { if (raz || !i.files || !i.files[0]) return; raz = true; const f = i.files[0]; setTimeout(() => i.remove(), 1000); fn(f); };
  i.addEventListener("change", wez); i.addEventListener("input", wez);
  i.click();
}
async function naJpg(f, max = 1600) {
  const url = URL.createObjectURL(f), img = new Image();
  try {
    await new Promise((ok, zle) => { img.onload = ok; img.onerror = () => zle(new Error("to nie jest zdjęcie")); img.src = url; });
    return await zmniejsz(img, max, .85);
  } finally { URL.revokeObjectURL(url); }
}
async function wyslijDoAI(sciezka, f, pola = {}) {
  const fd = new FormData();
  if (f) fd.append("zdjecie", await naJpg(f), "z.jpg");
  Object.entries(pola).forEach(([k, v]) => fd.append(k, v));
  const r = await fetch("/api/" + sciezka, { method: "POST", body: fd });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.blad || "serwer: " + r.status);
  return czekaj(j);
}
function tabelkaZdjecie() { wybierzZdjecie(f => formRecznie("", f)); }
async function czytajTabelke(a, f) {
  const info = a.querySelector("#r-info");
  info.innerHTML = `<span class="mysli">Czytam tabelkę</span>`;
  try {
    const w = await wyslijDoAI("dieta/etykieta", f);
    if (!a.isConnected) return;
    const ust = (id, v) => { const e = a.querySelector(id); if (e && v != null && v !== "") e.value = v; };
    if (w.nazwa && !a.querySelector("#r-nazwa").value) ust("#r-nazwa", w.nazwa);
    if (a._na100) a._na100();
    ust("#r-kcal", w.kcal); ust("#r-b", w.b); ust("#r-w", w.w); ust("#r-t", w.t);
    if (w.porcja_g && a.querySelector("#r-g")) ust("#r-g", Math.round(w.porcja_g));
    if (w.porcja_g && a.querySelector("#r-porcja")) ust("#r-porcja", Math.round(w.porcja_g));
    if (w.masa_g && a.querySelector("#r-masa") && !a.querySelector("#r-masa").value) ust("#r-masa", Math.round(w.masa_g));
    a.querySelector("#r-kcal")?.dispatchEvent(new Event("input"));
    info.textContent = "Odczytane — sprawdź z etykietą." + (w.uwagi ? " " + w.uwagi : "");
    if (!a.querySelector("#r-nazwa").value) a.querySelector("#r-nazwa").focus();
  } catch (e) { if (a.isConnected) info.textContent = "Błąd: " + e.message; }
}

async function poprawProdukt(kod, wroc) {
  let p = PRODUKTY[kod];
  if (!p) { try { p = PRODUKTY[kod] = await api("produkt/" + encodeURIComponent(kod)); } catch (e) { alert(e.message); return; } }
  const a = arkusz(`<div class="kt">Popraw produkt</div><div class="szary">Wartości na 100 g. Poprawię też wszystkie wpisy z tym produktem.</div>
    <label>Nazwa</label><input type="text" id="r-nazwa" value="${esc(p.nazwa)}">
    <div class="pola4"><div><label>kcal</label><input type="number" inputmode="decimal" id="r-kcal" value="${p.kcal}"></div><div><label>białko</label><input type="number" inputmode="decimal" id="r-b" value="${p.b}"></div>
      <div><label>węgle</label><input type="number" inputmode="decimal" id="r-w" value="${p.w}"></div><div><label>tłuszcz</label><input type="number" inputmode="decimal" id="r-t" value="${p.t}"></div></div>
    <div class="pola4"><div><label>Porcja (g)</label><input type="number" inputmode="decimal" id="r-porcja" value="${p.porcja_g || ""}" placeholder="opcjonalnie"></div>
      <div><label>Całe opakowanie (g)</label><input type="number" inputmode="decimal" id="r-masa" value="${p.masa_g || ""}" placeholder="opcjonalnie"></div></div>
    <div class="wiersz" style="margin-top:8px"><button class="drugi" id="r-zdj">📷 Odczytaj ze zdjęcia</button><span class="szary" id="r-info"></span></div>
    <div class="wiersz" style="margin-top:14px"><button id="ok">Zapisz</button><button class="drugi" id="wroc">Wróć</button></div>`);
  a.querySelector("#r-zdj").onclick = () => wybierzZdjecie(f => czytajTabelke(a, f));
  a.querySelector("#wroc").onclick = wroc;
  a.querySelector("#ok").onclick = async () => {
    const v = id => a.querySelector(id).value.replace(",", ".");
    if (v("#r-kcal") === "" || !(+v("#r-kcal") >= 0)) { alert("Podaj kcal"); return; }
    let n;
    try { n = await api("produkt/" + encodeURIComponent(kod), { nazwa: v("#r-nazwa").trim(), kcal: +v("#r-kcal"), b: +v("#r-b") || 0, w: +v("#r-w") || 0, t: +v("#r-t") || 0, porcja_g: +v("#r-porcja") || null, masa_g: +v("#r-masa") || null }); }
    catch (e) { alert(e.message); return; }
    PRODUKTY[kod] = n;
    if (location.hash.startsWith("#jedzenie")) await pokazJedzenie(dietaDzien);
    wroc();
  };
}

let posZdj = null;
function posilekZdjecie() {
  posZdj = null;
  const a = arkusz(`<div class="kt">Zdjęcie posiłku</div><div class="szary">Zrób zdjęcie talerza z góry (najlepiej ze sztućcem obok) i napisz, co mniej więcej jest w środku. Trener oszacuje gramy i makro i sprawdzi opis ze zdjęciem.</div>
    <div class="wiersz" style="margin-top:10px"><button class="drugi" id="p-zdj">📷 Dodaj zdjęcie</button><img id="p-min" class="p-min" hidden></div>
    <label>Co tam jest</label><textarea id="p-opis" rows="3" placeholder="np. kurczak smażony, ryż ok. 1 woreczek, surówka z marchewki"></textarea>
    <div class="wiersz" style="margin-top:14px"><button id="p-ok">Oszacuj</button><button class="drugi" onclick="dodajJedzenie(posilekDod)">Wróć</button></div>
    <div id="p-wynik"></div>`);
  a.querySelector("#p-zdj").onclick = () => wybierzZdjecie(f => {
    posZdj = f; const m = a.querySelector("#p-min"); m.src = URL.createObjectURL(f); m.hidden = false;
    a.querySelector("#p-zdj").textContent = "📷 Zmień zdjęcie";
  });
  a.querySelector("#p-ok").onclick = async () => {
    const opis = a.querySelector("#p-opis").value.trim(), wy = a.querySelector("#p-wynik"), b = a.querySelector("#p-ok");
    if (!posZdj && !opis) { alert("Dodaj zdjęcie albo opis"); return; }
    b.disabled = true;
    wy.innerHTML = `<div class="szary" style="margin-top:12px"><span class="mysli">Trener ogląda posiłek</span></div>`;
    try {
      const w = await wyslijDoAI("dieta/posilek", posZdj, { opis });
      if (a.isConnected) listaSzacunku(a, w);
    } catch (e) { if (a.isConnected) wy.innerHTML = `<div class="szary" style="margin-top:12px">Błąd: ${esc(e.message)}</div>`; }
    b.disabled = false;
  };
}
function listaSzacunku(a, w) {
  const wy = a.querySelector("#p-wynik");
  const POLA = [["kcal", "kcal"], ["b", "B"], ["w", "W"], ["t", "T"]];
  const wiersz = (p = { nazwa: "", gram: 100, kcal: 0, b: 0, w: 0, t: 0 }) => `<div class="szac" data-baza='${esc(JSON.stringify(p))}'>
      <div class="wiersz"><input type="text" class="s-nazwa" value="${esc(p.nazwa)}" placeholder="składnik"><input type="number" inputmode="decimal" class="s-gram" value="${p.gram || ""}"><span class="szary">g</span><button class="drugi zle-t s-usun" aria-label="usuń">✕</button></div>
      <div class="pola4">${POLA.map(([k, n]) => `<div><label>${n}</label><input type="number" inputmode="decimal" class="s-${k}" value="${+(+p[k] || 0).toFixed(k === "kcal" ? 0 : 1)}"></div>`).join("")}</div></div>`;
  wy.innerHTML = `<div class="kt" style="margin-top:16px">Szacunek <span class="szary">· pewność ${{ niska: "niska", srednia: "średnia", wysoka: "wysoka" }[w.pewnosc] || w.pewnosc}</span></div>
    ${w.komentarz ? `<div class="karta-info">${esc(w.komentarz)}</div>` : ""}
    <div id="s-lista">${w.pozycje.map(wiersz).join("")}</div>
    <button class="drugi" id="s-plus" style="margin-top:8px">+ składnik</button>
    <div class="podglad" id="s-suma"></div>
    <label>Posiłek</label><select id="s-posilek">${Object.entries(POSILEK).map(([k, n]) => `<option value="${k}" ${k === posilekDod ? "selected" : ""}>${n}</option>`).join("")}</select>
    <div class="wiersz" style="margin-top:14px"><button id="s-dodaj">Dodaj wszystko</button></div>`;
  const lista = wy.querySelector("#s-lista");
  const num = el => +String(el.value).replace(",", ".") || 0;
  const suma = () => {
    const s = { kcal: 0, b: 0, w: 0, t: 0 };
    lista.querySelectorAll(".szac").forEach(r => POLA.forEach(([k]) => s[k] += num(r.querySelector(".s-" + k))));
    wy.querySelector("#s-suma").innerHTML = `Razem: <b>${lb(s.kcal)} kcal</b> · B ${lb(s.b)} g · W ${lb(s.w)} g · T ${lb(s.t)} g`;
  };
  const podlacz = r => {
    const g = r.querySelector(".s-gram");
    g.oninput = () => {      // zmiana gramów przelicza makro proporcjonalnie do szacunku
      const b = JSON.parse(r.dataset.baza); if (!(b.gram > 0)) return;
      const k = num(g) / b.gram;
      POLA.forEach(([x]) => r.querySelector(".s-" + x).value = +(b[x] * k).toFixed(x === "kcal" ? 0 : 1));
      suma();
    };
    POLA.forEach(([x]) => r.querySelector(".s-" + x).oninput = () => {   // ręczna poprawka = nowa baza do przeliczania
      const b = { gram: num(g) }; POLA.forEach(([y]) => b[y] = num(r.querySelector(".s-" + y)));
      r.dataset.baza = JSON.stringify(b); suma();
    });
    r.querySelector(".s-usun").onclick = () => { r.remove(); suma(); };
  };
  lista.querySelectorAll(".szac").forEach(podlacz);
  wy.querySelector("#s-plus").onclick = () => { lista.insertAdjacentHTML("beforeend", wiersz()); podlacz(lista.lastElementChild); lista.lastElementChild.querySelector(".s-nazwa").focus(); };
  suma();
  wy.querySelector("#s-dodaj").onclick = async () => {
    const poz = [...lista.querySelectorAll(".szac")].map(r => ({ nazwa: r.querySelector(".s-nazwa").value.trim(), gram: num(r.querySelector(".s-gram")) || null,
      ...Object.fromEntries(POLA.map(([k]) => [k, num(r.querySelector(".s-" + k))])) })).filter(p => p.nazwa);
    if (!poz.length) { alert("Lista jest pusta"); return; }
    const posilek = wy.querySelector("#s-posilek").value, bt = wy.querySelector("#s-dodaj"); bt.disabled = true;
    try { for (const p of poz) await api("dieta/wpis", { dzien: dietaDzien, posilek, ...p }); }
    catch (e) { alert(e.message); bt.disabled = false; return; }
    zamknijArkusz(); pokazJedzenie(dietaDzien);
  };
}

// ---- skaner kodów kreskowych (ZXing, ładowany dopiero przy pierwszym skanowaniu; działa też w Safari)
let skaner = null;
const zaladujZxing = () => window.ZXing ? Promise.resolve() : new Promise((ok, zle) => {
  const s = document.createElement("script"); s.src = "/zxing.min.js"; s.onload = ok; s.onerror = () => zle(new Error("nie udało się wczytać skanera")); document.head.appendChild(s);
});
async function skanuj() {
  const a = arkusz(`<div class="kt">Skanuj kod kreskowy</div><div class="kamera"><video id="kam" playsinline muted></video><i class="ramka"></i></div>
    <div class="szary" id="sk-info" style="margin-top:8px">Nakieruj aparat na kod kreskowy produktu.</div>
    <div class="wiersz" style="margin-top:10px"><input type="text" inputmode="numeric" id="sk-kod" placeholder="albo wpisz cyfry kodu" style="flex:1"><button class="drugi" id="sk-ok">OK</button></div>
    <div class="wiersz" style="margin-top:10px"><button class="drugi" onclick="dodajJedzenie(posilekDod)">Wróć</button></div>`);
  a.querySelector("#sk-ok").onclick = () => { const k = a.querySelector("#sk-kod").value.replace(/\D/g, ""); if (k) znalezionyKod(k); };
  try {
    await zaladujZxing();
    const hints = new Map();
    hints.set(ZXing.DecodeHintType.POSSIBLE_FORMATS, [ZXing.BarcodeFormat.EAN_13, ZXing.BarcodeFormat.EAN_8, ZXing.BarcodeFormat.UPC_A, ZXing.BarcodeFormat.UPC_E]);
    skaner = new ZXing.BrowserMultiFormatReader(hints, 300);
    const video = a.querySelector("#kam");
    await skaner.decodeFromConstraints({ video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 720 } } }, video, (w) => {
      if (w && skaner) { const k = w.getText(); navigator.vibrate && navigator.vibrate(60); stopSkaner(); znalezionyKod(k); }
    });
  } catch (e) {
    const i = $("#sk-info"); if (i) i.textContent = "Aparat niedostępny (" + e.message + "). Wpisz cyfry kodu spod kreskówki.";
  }
}
function stopSkaner() { if (skaner) { try { skaner.reset(); } catch (_) {} skaner = null; } }
async function znalezionyKod(kod) {
  const i = $("#sk-info"); if (i) i.innerHTML = `<span class="mysli">Szukam ${esc(kod)}</span>`;
  const r = await fetch("/api/produkt/" + encodeURIComponent(kod));
  if (r.ok) { const p = await r.json(); PRODUKTY[p.kod] = p; wybierz(p.kod); return; }
  if (r.status === 404) { let pod = {}; try { pod = await r.json(); } catch (_) {} formRecznie(kod, null, pod); return; }
  let b = ""; try { b = (await r.json()).blad; } catch (_) {}
  if (i) i.textContent = b || "Błąd " + r.status;
}

// ------------------------------------------------------------------ Waga: masa, skład ciała, zdjęcia (dziennik Progres z portalu)
const TYPY_ZDJ = { przod: "przód", bok: "bok", biceps: "biceps", tyl: "tył", tylbiceps: "tył biceps", inne: "inne" };
let WAGA = null, zakresW = 90, wagaPokaz = "masa", wagaPod = localStorage.getItem("wagaPod") || "pomiary", wagaSr = localStorage.getItem("wagaSr") || "dzien";
let wagaTrend = localStorage.getItem("wagaTrend") !== "0", wagaSklad = localStorage.getItem("wagaSklad") || "razem";   // linie średniej 7 dni; skład na jednym albo dwóch wykresach
async function pokazWage() {
  const d = WAGA = await api("waga");
  const wp = Object.entries(d.wpisy || {}).sort(([a], [b]) => a < b ? -1 : 1).map(([dzien, v]) => ({ dzien, ...v }));
  const dzis = dzisISO();
  const ost = k => wp.filter(x => x[k] != null).slice(-1)[0];
  const om = ost("masa"), of = ost("fat"), oM = ost("muscle");
  const przed = (k, n) => { if (!ost(k)) return null; const gr = dzienMinus(ost(k).dzien, n); const x = wp.filter(q => q[k] != null && q.dzien <= gr).slice(-1)[0]; return x ? x[k] : null; };
  const dlt = (k, n, lepiej, jedn) => { const a = ost(k), b = przed(k, n); if (!a || b == null) return ""; const r = a[k] - b; if (Math.abs(r) < 0.05) return `<span class="delta">= ${n} dni temu</span>`;
    return `<span class="delta ${Math.sign(r) === lepiej ? "lepiej" : "gorzej"}">${r > 0 ? "▲" : "▼"} ${lb(Math.abs(r), 1)} ${jedn} vs ${n} dni temu</span>`; };
  const zd = (d.zdjecia || []).slice().sort((a, b) => a.data < b.data ? 1 : a.data > b.data ? -1 : (a.dodano || "") < (b.dodano || "") ? -1 : 1);
  const ileZd = {}; zd.forEach(z => ileZd[z.data] = (ileZd[z.data] || 0) + 1);
  let h = `<div class="zakladki pod-w"><button class="${wagaPod === "pomiary" ? "akt" : ""}" data-pod="pomiary">Pomiary</button><button class="${wagaPod === "zdjecia" ? "akt" : ""}" data-pod="zdjecia">Zdjęcia <span class="szary">${zd.length}</span></button></div>`;
  if (wagaPod === "zdjecia") { widok.innerHTML = h + galeriaPomiarow(zd, d.wpisy || {}); podpiszWage(); return; }
  h += `<div class="karta hero"><div class="szary">${om ? (om.dzien === dzis ? "Dziś" : dataPL(om.dzien)) : "Brak pomiarów"}</div>
    <div class="duzy">${om ? lb(om.masa, 1) : "–"}<small>kg</small></div>
    <div class="wiersz delty">${dlt("masa", 7, -1, "kg")}${dlt("masa", 30, -1, "kg")}</div>
    <div class="wiersz suma">${of ? `<div><span>tłuszcz</span><b>${lb(of.fat, 1)}%</b>${dlt("fat", 30, -1, "pp")}</div>` : ""}
      ${of && om ? `<div><span>tkanka tłuszczowa</span><b>${lb(om.masa * of.fat / 100, 1)} kg</b></div>` : ""}
      ${oM ? `<div><span>mięśnie</span><b>${lb(oM.muscle, 1)}%</b>${dlt("muscle", 30, 1, "pp")}</div>` : ""}</div></div>`;
  h += `<div class="karta"><div class="kt">Nowy pomiar</div>
    <div class="pola4"><div><label>Data</label><input type="date" id="w-data" value="${dzis}"></div><div><label>Masa (kg)</label><input type="number" inputmode="decimal" id="w-masa" step="0.1"></div>
      <div><label>Tłuszcz %</label><input type="number" inputmode="decimal" id="w-fat" step="0.1"></div><div><label>Mięśnie %</label><input type="number" inputmode="decimal" id="w-muscle" step="0.1"></div></div>
    <label>Notatka</label><input type="text" id="w-nota" placeholder="opcjonalnie">
    <label>Zdjęcia</label><div class="kolejka" id="w-kolejka"></div>
    <label class="btn drugi" style="margin:6px 0 0">📷 Dodaj zdjęcia<input type="file" accept="image/*" multiple id="w-zdj" hidden></label>
    <div id="z-info" class="szary"></div>
    <div class="wiersz" style="margin-top:12px"><button id="w-zapisz">Zapisz</button><span class="szary">Waż się rano, po toalecie, przed jedzeniem.</span></div></div>`;
  const od = zakresW ? dzienMinus(dzis, zakresW - 1) : "0000";
  const wz = wp.filter(x => x.dzien >= od);
  h += `<div class="zakladki">${[[30, "30 dni"], [90, "90 dni"], [365, "rok"], [0, "wszystko"]].map(([n, t]) => `<button class="${zakresW === n ? "akt" : ""}" data-zw="${n}">${t}</button>`).join("")}</div>
    <div class="zakladki">${[["dzien", "Każdy pomiar"], ["tydzien", "Średnia tyg."], ["miesiac", "Średnia mies."]].map(([k, t]) => `<button class="${wagaSr === k ? "akt" : ""}" data-sr="${k}">${t}</button>`).join("")}</div>
    <div class="wiersz opcje-w">${wagaSr === "dzien" ? `<span class="opcja"><span class="szary">Średnia 7 dni</span><span class="zakladki mini"><button class="${wagaTrend ? "akt" : ""}" data-wt="1">Wł.</button><button class="${wagaTrend ? "" : "akt"}" data-wt="0">Wył.</button></span></span>` : ""}
      <span class="opcja"><span class="szary">Skład</span><span class="zakladki mini"><button class="${wagaSklad === "razem" ? "akt" : ""}" data-ws="razem">Razem</button><button class="${wagaSklad === "osobno" ? "akt" : ""}" data-ws="osobno">Osobno</button></span></span></div>`;
  const zM = wz.filter(x => x.masa != null);
  const sr = wagaSr !== "dzien", G = sr ? grupujWage(wz, wagaSr) : null;
  // wspólna oś dat dla masy i składu: te same daty od–do na obu wykresach; brak wartości = puste miejsce (linia zaczyna się od 1. pomiaru)
  const osW = (sr ? G : wz).filter(x => x.masa != null || x.fat != null || x.muscle != null), xW = osW.map(x => x.dzien);
  const etG = wagaSr === "tydzien" ? dataKr : k => `${MIES[+k.slice(5, 7) - 1]} ${k.slice(2, 4)}`;
  const dymG = k => { const g = G.find(q => q.dzien === k); return (wagaSr === "tydzien" ? `tydzień od ${dataKr(k)}` : `${MIES[+k.slice(5, 7) - 1]} ${k.slice(0, 4)}`) + ` · ${g.n} ${g.n === 1 ? "pomiar" : g.n < 5 ? "pomiary" : "pomiarów"}`; };
  const nazwaSr = wagaSr === "tydzien" ? "średnia tygodniowa" : "średnia miesięczna";
  // średnia krocząca 7 dni = prawdziwy trend (pojedyncze ważenie skacze o ±1 kg od wody)
  const trend = osW.map(x => srednia(zM.filter(q => q.dzien <= x.dzien && q.dzien > dzienMinus(x.dzien, 7)).map(q => q.masa)));
  const gM = sr && G.filter(x => x.masa != null);
  h += sr ? `<div class="karta"><div class="kt">Masa <span class="szary">· kg, ${nazwaSr}</span></div>
    ${wyk({ typ: "linia", x: xW, serie: [{ nazwa: nazwaSr, y: osW.map(x => x.masa), kolor: KOLOR.niebieski, lacz: true }], dz: 1, jedn: "kg", etX: etG, etDymek: dymG })}
    ${zmianaSr(gM, wagaSr)}${tempoTekst(zM)}</div>` : `<div class="karta"><div class="kt">Masa <span class="szary">· kg</span></div>
    ${wyk({ typ: "linia", x: xW, serie: [{ nazwa: "ważenie", y: osW.map(x => x.masa), kolor: KOLOR.niebieski, lacz: true }, { nazwa: "średnia 7 dni", y: trend.map(v => v == null ? null : +v.toFixed(2)), kolor: KOLOR.niebieski, przerywana: true, lacz: true }].slice(0, wagaTrend ? 2 : 1), dz: 1, jedn: "kg", etX: dataKr, etDymek: dataPL })}
    ${legenda([{ nazwa: "ważenie", kolor: KOLOR.niebieski }, { nazwa: "średnia 7 dni", kolor: KOLOR.niebieski, przerywana: true }].slice(0, wagaTrend ? 2 : 1))}
    ${tempoTekst(zM)}</div>`;
  const zS = (sr ? G : wz).filter(x => x.fat != null || x.muscle != null);
  if (zS.length) {
    const kg = wagaPokaz === "kg";
    const y = (x, k) => x[k] == null ? null : kg ? (sr ? x[k + "Kg"] : x.masa != null ? +(x.masa * x[k] / 100).toFixed(1) : null) : x[k];
    // średnia krocząca 7 dni (tylko „Każdy pomiar”; przy średnich tyg./mies. linia już jest średnią)
    const sr7 = k => osW.map(x => { const v = srednia(zS.filter(q => q.dzien <= x.dzien && q.dzien > dzienMinus(x.dzien, 7)).map(q => y(q, k)).filter(v => v != null)); return v == null ? null : +v.toFixed(2); });
    const fat = { nazwa: "tłuszcz", y: osW.map(x => y(x, "fat")), kolor: KOLOR.zolty, lacz: true }, mus = { nazwa: "mięśnie", y: osW.map(x => y(x, "muscle")), kolor: KOLOR.morski, os: "prawa", lacz: true };
    const tr = !sr && wagaTrend;   // linie średniej 7 dni
    const fatT = tr && { nazwa: "tłuszcz, średnia 7 dni", y: sr7("fat"), kolor: KOLOR.zolty, przerywana: true, lacz: true };
    const musT = tr && { nazwa: "mięśnie, średnia 7 dni", y: sr7("muscle"), kolor: KOLOR.morski, os: "prawa", przerywana: true, lacz: true };
    const jd = kg ? "kg" : "%", przel = `<span class="zakladki mini"><button class="${kg ? "" : "akt"}" data-wp="masa">%</button><button class="${kg ? "akt" : ""}" data-wp="kg">kg</button></span>`;
    const opcje = { typ: "linia", x: xW, dz: 1, jedn: jd, etX: sr ? etG : dataKr, etDymek: sr ? dymG : dataPL };
    const naglowek = t => `<div class="kt wiersz" style="justify-content:space-between"><span>${t}${sr ? ` <span class="szary">· ${nazwaSr}</span>` : ""}</span>${przel}</div>`;
    if (wagaSklad === "osobno") {   // dwa wykresy, każdy z jedną osią na całą wysokość; ta sama oś dat co masa
      [[fat, fatT, "Tłuszcz"], [mus, musT, "Mięśnie"]].forEach(([a, b, t]) => {
        const se = [Object.assign({}, a, { os: null }), b && Object.assign({}, b, { os: null, nazwa: "średnia 7 dni" })].filter(Boolean);
        if (se[0].y.every(v => v == null)) return;
        h += `<div class="karta">${naglowek(t + ` <span class="szary">· ${jd}</span>`)}${wyk(Object.assign({ serie: se }, opcje))}${legenda([Object.assign({}, se[0], { nazwa: "pomiar" }), se[1]].filter(Boolean))}</div>`;
      });
    } else {
      const sS = [fat, mus, fatT, musT].filter(Boolean);
      h += `<div class="karta">${naglowek("Skład ciała")}${wyk(Object.assign({ serie: sS, h: 200 }, opcje))}
      ${legenda(tr ? [fat, mus, { nazwa: "średnia 7 dni", kolor: "var(--tekst2)", przerywana: true }] : [fat, mus])}</div>`;
    }
  }
  h += `<h2>Historia</h2><div class="karta">${wp.length ? wp.slice().reverse().map((x, i) => `<div class="pozycja klik${i >= 10 ? " ukryty" : ""}" data-wd="${x.dzien}"><div><div>${dataPL(x.dzien)} ${x.dzien.slice(0, 4)}</div>
      <div class="szary">${[x.fat != null && `tłuszcz ${lb(x.fat, 1)}%`, x.muscle != null && `mięśnie ${lb(x.muscle, 1)}%`, ileZd[x.dzien] && `📷 ${ileZd[x.dzien]}`, x.notatka && esc(x.notatka)].filter(Boolean).join(" · ")}</div></div><b>${x.masa != null ? lb(x.masa, 1) + " kg" : ""}</b></div>`).join("") : `<div class="szary">Brak wpisów.</div>`}${wp.length > 10 ? `<button class="drugi dodaj" id="w-wiecej" style="margin-top:10px">Pokaż wszystkie (${wp.length})</button>` : ""}</div>`;
  widok.innerHTML = h;
  const wi = $("#w-wiecej"); if (wi) wi.onclick = () => { widok.querySelectorAll(".pozycja.ukryty").forEach(x => x.classList.remove("ukryty")); wi.remove(); };
  rysuj(widok);
  widok.querySelectorAll("[data-zw]").forEach(b => b.onclick = () => { zakresW = +b.dataset.zw; pokazWage(); });
  widok.querySelectorAll("[data-wp]").forEach(b => b.onclick = () => { wagaPokaz = b.dataset.wp; pokazWage(); });
  widok.querySelectorAll("[data-wt]").forEach(b => b.onclick = () => { wagaTrend = b.dataset.wt === "1"; localStorage.setItem("wagaTrend", b.dataset.wt); pokazWage(); });
  widok.querySelectorAll("[data-ws]").forEach(b => b.onclick = () => { wagaSklad = b.dataset.ws; localStorage.setItem("wagaSklad", wagaSklad); pokazWage(); });
  widok.querySelectorAll("[data-sr]").forEach(b => b.onclick = () => { wagaSr = b.dataset.sr; localStorage.setItem("wagaSr", wagaSr); pokazWage(); });
  widok.querySelectorAll("[data-wd]").forEach(el => el.onclick = () => edytujPomiar(el.dataset.wd));
  podpiszWage();
  KOLEJKA = [];
  $("#w-zdj").onchange = e => { dodajDoKolejki(e.target.files, $("#w-kolejka")); e.target.value = ""; };
  $("#w-zapisz").onclick = zapiszPomiar;
}

// wspólne dla obu podzakładek
function podpiszWage() {
  widok.querySelectorAll("[data-pod]").forEach(b => b.onclick = () => { wagaPod = b.dataset.pod; localStorage.setItem("wagaPod", wagaPod); pokazWage(); });
  widok.querySelectorAll("[data-zid]").forEach(el => el.onclick = e => { e.preventDefault(); pokazZdjecie(el.dataset.zid); });
  widok.querySelectorAll("[data-zdod]").forEach(el => el.onclick = () => dodajZdjeciaDo(el.dataset.zdod));
}

// Zdjęcia pogrupowane po pomiarze (dniu), najnowsze na górze
function galeriaPomiarow(zd, wpisy) {
  if (!zd.length) return `<div class="karta szary">Brak zdjęć. Dodasz je w zakładce Pomiary, w „Nowy pomiar”.</div>`;
  const grupy = []; zd.forEach(z => { const g = grupy[grupy.length - 1]; if (g && g.dzien === z.data) g.z.push(z); else grupy.push({ dzien: z.data, z: [z] }); });
  return grupy.map(g => { const w = wpisy[g.dzien] || {};
    const opis = [w.masa != null && `${lb(w.masa, 1)} kg`, w.fat != null && `tłuszcz ${lb(w.fat, 1)}%`, w.muscle != null && `mięśnie ${lb(w.muscle, 1)}%`].filter(Boolean).join(" · ");
    return `<div class="karta"><div class="kt wiersz" style="justify-content:space-between"><span>${dataPL(g.dzien)} ${g.dzien.slice(0, 4)}</span>
      <button class="drugi mini-btn" data-zdod="${g.dzien}">+ zdjęcie</button></div>
      ${opis ? `<div class="szary">${opis}</div>` : ""}${w.notatka ? `<div class="szary">${esc(w.notatka)}</div>` : ""}
      <div class="galeria">${g.z.map(z => `<a class="miniatura" href="#" data-zid="${z.id}"><img loading="lazy" src="/api/waga/plik/${z.id}_m.jpg" alt=""><span>${TYPY_ZDJ[z.typ] || z.typ}</span></a>`).join("")}</div></div>`; }).join("")
    + `<div class="szary" style="margin:4px 4px 12px">Film z sylwetki i porównania „przed / po” są w <a href="${adresPanelu()}strony/progres/" target="_blank" rel="noopener">Progres na portalu</a>.</div>`;
}

// kolejka zdjęć przed wysłaniem: miniatura + wybór strony
let KOLEJKA = [];
const KOL_TYPY = ["przod", "bok", "tyl", "biceps", "tylbiceps", "inne"];
function dodajDoKolejki(pliki, el) {
  [...pliki].forEach(f => KOLEJKA.push({ f, url: URL.createObjectURL(f), typ: KOL_TYPY[Math.min(KOLEJKA.length, KOL_TYPY.length - 1)] }));
  rysujKolejke(el);
}
function rysujKolejke(el) {
  el.innerHTML = KOLEJKA.map((k, i) => `<div class="kol-el"><img src="${k.url}" alt=""><button class="kol-x" data-kx="${i}" aria-label="Usuń">×</button>
    <select data-kt="${i}">${Object.entries(TYPY_ZDJ).map(([t, n]) => `<option value="${t}" ${t === k.typ ? "selected" : ""}>${n}</option>`).join("")}</select></div>`).join("");
  el.querySelectorAll("[data-kt]").forEach(s => s.onchange = () => KOLEJKA[+s.dataset.kt].typ = s.value);
  el.querySelectorAll("[data-kx]").forEach(b => b.onclick = () => { URL.revokeObjectURL(KOLEJKA[+b.dataset.kx].url); KOLEJKA.splice(+b.dataset.kx, 1); rysujKolejke(el); });
}
async function wyslijKolejke(data, info) {
  for (let i = 0; i < KOLEJKA.length; i++) {
    info.innerHTML = `<span class="mysli">Wysyłam zdjęcie ${i + 1} z ${KOLEJKA.length}</span>`;
    await wyslijZdjecie(KOLEJKA[i].f, data, KOLEJKA[i].typ);
  }
  KOLEJKA.forEach(k => URL.revokeObjectURL(k.url)); KOLEJKA = [];
}
function dodajZdjeciaDo(dzien) {
  KOLEJKA = [];
  const a = arkusz(`<div class="kt">Zdjęcia · ${dataPL(dzien)} ${dzien.slice(0, 4)}</div><div class="kolejka" id="a-kolejka"></div>
    <label class="btn drugi" style="margin:6px 0 0">📷 Wybierz zdjęcia<input type="file" accept="image/*" multiple id="a-zdj" hidden></label>
    <div id="a-info" class="szary"></div><div class="wiersz" style="margin-top:12px"><button id="ok">Zapisz</button></div>`);
  a.querySelector("#a-zdj").onchange = e => { dodajDoKolejki(e.target.files, a.querySelector("#a-kolejka")); e.target.value = ""; };
  a.querySelector("#ok").onclick = async () => {
    if (!KOLEJKA.length) { alert("Wybierz zdjęcia."); return; }
    try { await wyslijKolejke(dzien, a.querySelector("#a-info")); } catch (e) { a.querySelector("#a-info").textContent = "Błąd: " + e.message; return; }
    zamknijArkusz(); pokazWage();
  };
}

// średnie tygodniowe (od poniedziałku) albo miesięczne; kg składników liczone z każdego pomiaru osobno
function grupujWage(wz, tryb) {
  const klucz = d => { if (tryb === "miesiac") return d.slice(0, 7) + "-01"; const x = new Date(d + "T12:00"); return dzienMinus(d, (x.getDay() + 6) % 7); };
  const m = new Map();
  wz.forEach(x => { const k = klucz(x.dzien); if (!m.has(k)) m.set(k, []); m.get(k).push(x); });
  const zaok = v => v == null ? null : +v.toFixed(2);
  return [...m].sort(([a], [b]) => a < b ? -1 : 1).map(([dzien, t]) => ({ dzien, n: t.length,
    masa: zaok(srednia(t.map(x => x.masa))), fat: zaok(srednia(t.map(x => x.fat))), muscle: zaok(srednia(t.map(x => x.muscle))),
    fatKg: zaok(srednia(t.map(x => x.masa != null && x.fat != null ? x.masa * x.fat / 100 : null))),
    muscleKg: zaok(srednia(t.map(x => x.masa != null && x.muscle != null ? x.masa * x.muscle / 100 : null))) }));
}
function zmianaSr(g, tryb) {   // zmiana ostatniej średniej względem poprzedniej
  if (g.length < 2) return "";
  const r = g[g.length - 1].masa - g[g.length - 2].masa;
  return `<div class="szary" style="margin-top:8px">${r <= 0 ? "▼" : "▲"} ${lb(Math.abs(r), 1)} kg vs poprzedni ${tryb === "tydzien" ? "tydzień" : "miesiąc"}${g[g.length - 1].dzien === grupujWage([{ dzien: dzisISO() }], tryb)[0].dzien ? ` (bieżący ${tryb === "tydzien" ? "tydzień" : "miesiąc"} jeszcze trwa)` : ""}</div>`;
}

function tempoTekst(zM) {   // tempo z trendu: ostatnie 3 tygodnie średniej
  if (zM.length < 4) return "";
  const k = zM[zM.length - 1], od = dzienMinus(k.dzien, 21);
  const a = zM.filter(x => x.dzien >= od && x.dzien <= dzienMinus(k.dzien, 14)), b = zM.filter(x => x.dzien > dzienMinus(k.dzien, 7));
  if (!a.length || !b.length) return "";
  const r = (srednia(b.map(x => x.masa)) - srednia(a.map(x => x.masa))) / 2, pct = 100 * r / k.masa;
  const ok = pct <= -0.3 && pct >= -0.9, za = pct < -0.9;
  return `<div class="szary" style="margin-top:8px"><span class="status ${ok ? "dobrze" : za ? "uwaga" : ""}"><i></i>${r <= 0 ? "▼" : "▲"} ${lb(Math.abs(r), 2)} kg/tydz.</span>
    ${ok ? " Dobre tempo spalania tłuszczu." : za ? " Za szybko: tracisz też mięśnie. Jedz trochę więcej." : pct > 0 ? " Masa rośnie." : " Wolno: sprawdź dziennik jedzenia."}</div>`;
}

async function zapiszPomiar() {
  const v = id => { const s = $(id).value.replace(",", "."); return s === "" ? null : +s; };
  const b = { data: $("#w-data").value, masa: v("#w-masa"), fat: v("#w-fat"), muscle: v("#w-muscle"), notatka: $("#w-nota").value.trim() || null };
  const sa = b.masa != null || b.fat != null || b.muscle != null || b.notatka;
  if (!sa && !KOLEJKA.length) { alert("Wpisz masę albo skład, albo dodaj zdjęcia."); return; }
  const btn = $("#w-zapisz"); btn.disabled = true;
  try {
    if (sa) {
      const stary = (WAGA.wpisy || {})[b.data] || {};
      Object.keys(b).forEach(k => { if (b[k] == null && k !== "data") b[k] = stary[k] ?? undefined; });
      await api("waga/wpis", JSON.parse(JSON.stringify(b)));
    }
    if (KOLEJKA.length) await wyslijKolejke(b.data || dzisISO(), $("#z-info"));
  } catch (e) { btn.disabled = false; $("#z-info").textContent = "Błąd: " + e.message; return; }
  pokazWage();
}
function edytujPomiar(dzien) {
  const x = (WAGA.wpisy || {})[dzien] || {};
  const a = arkusz(`<div class="kt">${dataPL(dzien)} ${dzien.slice(0, 4)}</div>
    <div class="pola4"><div><label>Masa</label><input type="number" inputmode="decimal" id="e-masa" value="${x.masa ?? ""}"></div><div><label>Tłuszcz %</label><input type="number" inputmode="decimal" id="e-fat" value="${x.fat ?? ""}"></div>
      <div><label>Mięśnie %</label><input type="number" inputmode="decimal" id="e-muscle" value="${x.muscle ?? ""}"></div></div>
    <label>Notatka</label><input type="text" id="e-nota" value="${esc(x.notatka || "")}">
    <div class="wiersz" style="margin-top:14px"><button id="ok">Zapisz</button><button class="drugi zle-t" id="usun">Usuń wpis</button></div>`);
  const v = id => { const s = a.querySelector(id).value.replace(",", "."); return s === "" ? undefined : +s; };
  a.querySelector("#ok").onclick = async () => { await api("waga/wpis", { data: dzien, masa: v("#e-masa"), fat: v("#e-fat"), muscle: v("#e-muscle"), notatka: a.querySelector("#e-nota").value.trim() || undefined }); zamknijArkusz(); pokazWage(); };
  a.querySelector("#usun").onclick = async () => { if (!confirm("Usunąć pomiar z " + dzien + "?")) return; await api("waga/wpis", { data: dzien }); zamknijArkusz(); pokazWage(); };
}

function pokazZdjecie(zid) {
  const z = (WAGA.zdjecia || []).find(q => q.id === zid); if (!z) return;
  const a = arkusz(`<div class="kt">${dataPL(z.data)} ${z.data.slice(0, 4)} · ${TYPY_ZDJ[z.typ] || z.typ}</div><img class="zdjecie" id="zd-duze" src="/api/waga/plik/${z.id}.jpg" alt=""><div class="szary" style="margin-top:6px;text-align:center">Dotknij, żeby przybliżyć</div>
    <div class="wiersz" style="margin-top:12px"><select id="zt" style="flex:1">${Object.entries(TYPY_ZDJ).map(([k, n]) => `<option value="${k}" ${k === z.typ ? "selected" : ""}>${n}</option>`).join("")}</select>
      <button class="drugi zle-t" id="usun">Usuń</button></div>`);
  a.querySelector("#zd-duze").onclick = () => powiekszZdjecie(`/api/waga/plik/${z.id}.jpg`);
  a.querySelector("#zt").onchange = async e => { await api("waga/zdjecie/" + zid, { typ: e.target.value }); WAGA = await api("waga"); };
  a.querySelector("#usun").onclick = async () => { if (!confirm("Usunąć zdjęcie? (trafi do kosza na NAS)")) return; await api("waga/zdjecie/" + zid, { usun: true }); zamknijArkusz(); pokazWage(); };
}

// Pełny ekran: dwa palce = przybliż, jeden = przesuń, podwójne stuknięcie = 2,5× / z powrotem, kółko myszy też działa
function powiekszZdjecie(src) {
  const t = document.createElement("div"); t.className = "lupa";
  t.innerHTML = `<img src="${src}" alt="" draggable="false"><button class="lupa-x" aria-label="Zamknij">×</button>`;
  document.body.appendChild(t);
  const img = t.querySelector("img"), palce = new Map();
  let s = 1, x = 0, y = 0, start = null, ostTap = 0, ruch = false;
  const ogranicz = () => { if (s <= 1) { s = 1; x = 0; y = 0; return; }
    const w = img.offsetWidth, h = img.offsetHeight;   // rozmiar bez transformacji
    const mx = Math.max(0, (w * s - innerWidth) / 2), my = Math.max(0, (h * s - innerHeight) / 2);
    x = Math.max(-mx, Math.min(mx, x)); y = Math.max(-my, Math.min(my, y)); };
  const ustaw = (anim) => { img.style.transition = anim ? "transform .25s ease" : "none"; img.style.transform = `translate(${x}px,${y}px) scale(${s})`; };
  const zoomDo = (ns, cx, cy) => {   // przybliż wokół punktu (cx, cy) ekranu
    ns = Math.max(1, Math.min(6, ns)); const ox = cx - innerWidth / 2, oy = cy - innerHeight / 2;
    x = ox - (ox - x) * ns / s; y = oy - (oy - y) * ns / s; s = ns; ogranicz(); };
  const zamknij = () => t.remove();
  t.querySelector(".lupa-x").onclick = zamknij;
  t.addEventListener("pointerdown", e => { if (e.target.closest(".lupa-x")) return; t.setPointerCapture(e.pointerId); palce.set(e.pointerId, [e.clientX, e.clientY]); ruch = false;
    const p = [...palce.values()];
    start = p.length === 2 ? { d: Math.hypot(p[0][0] - p[1][0], p[0][1] - p[1][1]), s, x, y, cx: (p[0][0] + p[1][0]) / 2, cy: (p[0][1] + p[1][1]) / 2 }
                           : { px: e.clientX, py: e.clientY, x, y }; });
  t.addEventListener("pointermove", e => { if (!palce.has(e.pointerId)) return; palce.set(e.pointerId, [e.clientX, e.clientY]); const p = [...palce.values()];
    if (p.length === 2 && start.d) { ruch = true; const d = Math.hypot(p[0][0] - p[1][0], p[0][1] - p[1][1]), cx = (p[0][0] + p[1][0]) / 2, cy = (p[0][1] + p[1][1]) / 2;
      s = start.s; x = start.x + cx - start.cx; y = start.y + cy - start.cy; zoomDo(start.s * d / start.d, cx, cy); ustaw(); }
    else if (p.length === 1 && start.px != null) { const dx = e.clientX - start.px, dy = e.clientY - start.py; if (Math.hypot(dx, dy) > 6) ruch = true;
      if (s > 1) { x = start.x + dx; y = start.y + dy; ogranicz(); ustaw(); } } });
  const koniec = e => { palce.delete(e.pointerId); const p = [...palce.values()];
    if (p.length === 1) start = { px: p[0][0], py: p[0][1], x, y };
    if (palce.size || ruch) return;
    const teraz = Date.now();
    if (teraz - ostTap < 300) { if (s > 1) { s = 1; x = 0; y = 0; } else zoomDo(2.5, e.clientX, e.clientY); ustaw(true); ostTap = 0; }
    else { ostTap = teraz; if (s === 1 && e.target === t) setTimeout(() => { if (ostTap === teraz) zamknij(); }, 300); } };
  t.addEventListener("pointerup", koniec); t.addEventListener("pointercancel", e => palce.delete(e.pointerId));
  t.addEventListener("wheel", e => { e.preventDefault(); zoomDo(s * (e.deltaY < 0 ? 1.15 : 1 / 1.15), e.clientX, e.clientY); ustaw(); }, { passive: false });
}

function zmniejsz(img, max, jakosc) {   // przez canvas: mniejszy plik i bez EXIF (GPS)
  const s = Math.min(1, max / Math.max(img.naturalWidth, img.naturalHeight));
  const c = document.createElement("canvas"); c.width = Math.round(img.naturalWidth * s); c.height = Math.round(img.naturalHeight * s);
  c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
  return new Promise(ok => c.toBlob(ok, "image/jpeg", jakosc));
}
async function wyslijZdjecie(f, data, typ) {   // rzuca błędem; odświeżenie robi wywołujący
  const url = URL.createObjectURL(f), img = new Image();
  try { await new Promise((ok, zle) => { img.onload = ok; img.onerror = () => zle(new Error("to nie jest zdjęcie")); img.src = url; }); }
  finally { URL.revokeObjectURL(url); }
  const [duze, male] = [await zmniejsz(img, 1800, .88), await zmniejsz(img, 480, .8)];
  const fd = new FormData();
  fd.append("plik", duze, "z.jpg"); fd.append("miniatura", male, "m.jpg");
  fd.append("data", data); fd.append("typ", typ);
  const r = await fetch("/api/waga/zdjecie", { method: "POST", body: fd });
  if (!r.ok) throw new Error("serwer: " + r.status);
}

// kafle na Dziś
function kafelJedzenie(d) {
  if (!d) return "";
  const c = d.cel, s = d.suma, p = c.kcal ? Math.min(100, 100 * s.kcal / c.kcal) : 0;
  return `<a class="kafel" href="#jedzenie"><div class="n">Kalorie<svg class="strz" viewBox="0 0 16 16"><path d="M6 3l5 5-5 5"/></svg></div>
    <div class="w">${lb(s.kcal)}<small> / ${lb(c.kcal)}</small></div>
    <div class="d">${s.n ? `białko ${lb(s.b)} / ${lb(c.b)} g` : "dotknij, by wpisać"}</div>
    <div class="pasek-pct" style="margin-top:10px"><i style="width:${p}%;${s.kcal > c.kcal * 1.05 ? "background:var(--uwaga)" : ""}"></i></div></a>`;
}
function kafelWaga(w) {
  if (!w) return "";
  const wp = Object.entries(w.wpisy || {}).filter(([, v]) => v.masa != null).sort(([a], [b]) => a < b ? -1 : 1);
  const o = wp[wp.length - 1];
  const fat = Object.entries(w.wpisy || {}).filter(([, v]) => v.fat != null).sort(([a], [b]) => a < b ? -1 : 1).slice(-1)[0];
  const m = { lepiej: -1, dz: 1 };
  const st = o ? wp.filter(([k]) => k <= dzienMinus(o[0], 7)).slice(-1)[0] : null;
  return `<a class="kafel" href="#progres"><div class="n">Waga${o && o[0] !== dzisISO() ? `<span class="znaczek">${dataPL(o[0])}</span>` : ""}<svg class="strz" viewBox="0 0 16 16"><path d="M6 3l5 5-5 5"/></svg></div>
    <div class="w">${o ? lb(o[1].masa, 1) : "–"}<small>${o ? " kg" : ""}</small></div>
    <div class="d">${st ? delta(m, o[1].masa, st[1].masa, "kg vs tydz.") : fat ? `tłuszcz ${lb(fat[1].fat, 1)}%` : "dotknij, by wpisać"}</div>
    ${wyk({ typ: "spark", y: wp.slice(-14).map(([, v]) => v.masa), kolor: KOLOR.niebieski })}</a>`;
}

// ------------------------------------------------------------------ router
// Przejścia: zakładka → zakładka: ekran przesuwa się w bok (nowy wjeżdża od strony klikniętej zakładki);
// otwarcie szczegółów: nowy ekran rośnie z dotkniętej karty na cały ekran; wyjście: ekran kurczy się z powrotem do karty.
const ZAKLADKI = ["dzis", "progres", "jedzenie", "dane", "czat"];
const DETALE = new Set(["analiza", "metryka", "trening", "zaplanowany", "plan", "ustawienia", "wiedza"]);   // Plan otwiera się z Dziś
const RODZIC = { analiza: "dzis", plan: "dzis", metryka: "dane", trening: "dane", zaplanowany: "plan", ustawienia: "dzis", wiedza: "dzis" };
const _ih = Object.getOwnPropertyDescriptor(Element.prototype, "innerHTML");
const spokojnie = matchMedia("(prefers-reduced-motion: reduce)");
const SPR = "cubic-bezier(.32, .72, 0, 1)";            // jak przejścia w iOS
let przejscie = null, ladTimer = 0, poprz = null, ostatniKlik = null, anim = [];
const ZRODLA = new Map();                              // hash szczegółów → {rect karty, przewinięcie, hash rodzica}
document.addEventListener("click", e => {
  const el = e.target.closest(".kafel, .trening, .karta.klik, a.karta, .hero, .klik, #btn-ust, a, button");
  if (el) ostatniKlik = { r: el.getBoundingClientRect(), t: Date.now() };
}, true);
const ramka = (r, b) => `inset(${Math.max(0, r.top - b.top)}px ${Math.max(0, b.right - r.right)}px ${Math.max(0, b.bottom - r.bottom)}px ${Math.max(0, r.left - b.left)}px round var(--r))`;
const srodek = () => { const w = innerWidth, h = innerHeight; return { top: h * .4, bottom: h * .6, left: w * .3, right: w * .7 }; };

function skonczAnimacje() { anim.forEach(x => x.finish ? x.finish() : x.remove()); anim = []; }
function duch() {                                     // stary ekran wyjęty z #widok (te same węzły, wykresy zostają)
  const r = widok.getBoundingClientRect(), g = document.createElement("div");
  g.className = "duch";
  g.style.cssText = `top:${r.top}px;left:${r.left}px;width:${r.width}px`;
  while (widok.firstChild) g.appendChild(widok.firstChild);
  document.body.appendChild(g);
  return g;
}
function animuj(el, kl, opt) { const x = el.animate(kl, opt); anim.push(x); return x; }

function pokazZPrzejsciem(v) {
  const p = przejscie; przejscie = null; clearTimeout(ladTimer);
  skonczAnimacje();
  const g = !spokojnie.matches && p.typ !== "zanik" && widok.firstElementChild && !widok.firstElementChild.matches(".ladowanie") ? duch() : null;
  _ih.set.call(widok, v);
  SKR.scrollTo(0, p.y || 0);
  if (spokojnie.matches) return;
  const o = { duration: 460, easing: SPR };
  if (!g) {
    animuj(widok, [{ opacity: 0, transform: "scale(.985)" }, { opacity: 1, transform: "none" }], { duration: 260, easing: "ease-out" });
    return;
  }
  anim.push(g);
  const sprzataj = x => x.finished.then(() => g.remove(), () => g.remove());
  if (p.typ === "bok") {
    const stoi = g.firstElementChild?.matches(".podzak") && widok.firstElementChild?.matches(".podzak");   // Podsumowanie | Treningi
    if (stoi) {
      g.firstElementChild.style.visibility = "hidden";
      [...widok.children].slice(1).forEach(c => animuj(c, [{ transform: `translateX(${p.k * 100}%)` }, { transform: "none" }], o));
    } else animuj(widok, [{ transform: `translateX(${p.k * 100}%)` }, { transform: "none" }], o);
    sprzataj(animuj(g, [{ transform: "none", opacity: 1 }, { transform: `translateX(${-p.k * 100}%)`, opacity: 1 }], o));
  } else if (p.r.width < 80 && (p.typ === "otworz" || p.typ === "zamknij")) {   // ikona (zębatka): wyrasta z niej i do niej wraca
    const el = p.typ === "otworz" ? widok : g, b = el.getBoundingClientRect();
    const o = `${p.r.left + p.r.width / 2 - b.left}px ${p.r.top + p.r.height / 2 - b.top}px`;
    el.classList.add("nad"); el.style.transformOrigin = o;
    const zw = [{ transform: "scale(.04)", opacity: 0, borderRadius: "40px" }, { transform: "none", opacity: 1, borderRadius: "0px" }];
    const x = animuj(el, p.typ === "otworz" ? zw : [...zw].reverse(), { duration: p.typ === "otworz" ? 460 : 380, easing: SPR });
    const inny = p.typ === "otworz" ? g : widok;
    animuj(inny, p.typ === "otworz" ? [{ transform: "none", opacity: 1 }, { transform: "scale(.94)", opacity: .25 }] : [{ transform: "scale(.94)", opacity: .25 }, { transform: "none", opacity: 1 }], { duration: 460, easing: SPR });
    const koniec = () => { el.classList.remove("nad"); el.style.transformOrigin = ""; if (el === g) g.remove(); else g.remove(); };
    x.finished.then(koniec, koniec);
  } else if (p.typ === "otworz") {
    widok.classList.add("nad");
    const b = widok.getBoundingClientRect();
    const x = animuj(widok, [{ clipPath: ramka(p.r, b), opacity: .5 }, { clipPath: "inset(0px 0px 0px 0px round 0px)", opacity: 1, offset: .9 }, { clipPath: "inset(0px 0px 0px 0px round 0px)", opacity: 1 }], { duration: 500, easing: SPR });
    x.finished.then(() => widok.classList.remove("nad"), () => widok.classList.remove("nad"));
    sprzataj(animuj(g, [{ transform: "none", opacity: 1, filter: "blur(0)" }, { transform: "scale(.93)", opacity: 0, filter: "blur(6px)" }], { duration: 500, easing: SPR }));
  } else if (p.typ === "zamknij") {
    g.classList.add("nad");
    const b = g.getBoundingClientRect();
    animuj(widok, [{ transform: "scale(.93)", opacity: .3, filter: "blur(6px)" }, { transform: "none", opacity: 1, filter: "blur(0)" }], { duration: 440, easing: SPR });
    sprzataj(animuj(g, [{ clipPath: "inset(0px 0px 0px 0px round 0px)", opacity: 1 }, { clipPath: ramka(p.r, b), opacity: .7, offset: .85 }, { clipPath: ramka(p.r, b), opacity: 0 }], { duration: 420, easing: SPR }));
  }
}
// przełączniki (.zakladki): pigułka przepływa ze starego wyboru na nowy
function stanZakladek() {
  return [...widok.querySelectorAll(".zakladki")].map(z => {
    const a = z.querySelector(".akt"); if (!a) return null;
    const zr = z.getBoundingClientRect(), ar = a.getBoundingClientRect();
    return { l: ar.left - zr.left + z.scrollLeft, w: ar.width, klucz: z.textContent };
  });
}
function plynPigulke(z, st) {
  const a = z.querySelector(".akt"); if (!a || !st || spokojnie.matches) return;
  const zr = z.getBoundingClientRect(), ar = a.getBoundingClientRect(), l = ar.left - zr.left + z.scrollLeft;
  if (Math.abs(l - st.l) < 1) return;
  const p = document.createElement("i");
  p.className = "pigulka";
  p.style.cssText = `top:${ar.top - zr.top}px;height:${ar.height}px;left:${l}px;width:${ar.width}px`;
  z.classList.add("plynie"); z.prepend(p);
  const x = p.animate([{ left: st.l + "px", width: st.w + "px" }, { left: l + "px", width: ar.width + "px" }], { duration: 440, easing: SPR });
  const k = () => { p.remove(); z.classList.remove("plynie"); };
  x.finished.then(k, k);
}
// zmiana zakresu (30 dni / 90 dni / rok / wszystko, filtry): treść pod przełącznikiem odpływa w bok, nowa wpływa
let zmianaZakresu = null;
document.addEventListener("click", e => {
  const b = e.target.closest("#widok .zakladki:not(.podzak) button");
  if (!b) return;
  const z = b.parentElement, bs = [...z.querySelectorAll("button")], k = Math.sign(bs.indexOf(b) - bs.indexOf(z.querySelector(".akt")));
  zmianaZakresu = k ? { k, i: [...widok.querySelectorAll(".zakladki")].indexOf(z), t: Date.now() } : null;
}, true);
const dziecko = (rodzic, el) => { while (el && el.parentElement !== rodzic) el = el.parentElement; return el; };
function pokazZakres(v, zk) {
  skonczAnimacje();
  const g = spokojnie.matches ? null : duch();
  _ih.set.call(widok, v);
  if (!g) return;
  anim.push(g);
  const zg = dziecko(g, g.querySelectorAll(".zakladki")[zk.i]), zn = dziecko(widok, widok.querySelectorAll(".zakladki")[zk.i]);
  if (!zg || !zn) { g.remove(); return; }
  [...g.children].slice(0, [...g.children].indexOf(zg) + 1).forEach(c => c.style.visibility = "hidden");
  [...widok.children].slice([...widok.children].indexOf(zn) + 1).forEach(c =>
    animuj(c, [{ transform: `translateX(${zk.k * 56}px)`, opacity: 0 }, { transform: "none", opacity: 1 }], { duration: 440, delay: 150, easing: SPR, fill: "backwards" }));
  const x = animuj(g, [{ transform: "none", opacity: 1 }, { transform: `translateX(${-zk.k * 40}px)`, opacity: 0 }], { duration: 170, easing: "ease-in", fill: "forwards" });
  x.finished.then(() => g.remove(), () => g.remove());
}
// czat: pole pisania wypływa z dolnego paska jak kropla (i wraca do niego przy wyjściu)
function kropla(el, wej) {
  if (spokojnie.matches) { if (!wej) el.remove(); return; }
  const c = $('nav a[data-t="czat"]').getBoundingClientRect(), r = el.getBoundingClientRect();
  el.style.transformOrigin = `${c.left + c.width / 2 - r.left}px 50%`;
  const dy = c.top + c.height / 2 - (r.top + r.height / 2);
  const kl = [
    { transform: `translateY(${dy}px) scale(.1, .45)`, borderRadius: "50%", opacity: 0, filter: "blur(3px)", easing: "cubic-bezier(.2,.8,.3,1)" },
    { transform: `translateY(${dy * .4}px) scale(.14, 1.08)`, borderRadius: "50%", opacity: 1, filter: "blur(0px)", offset: .3, easing: "cubic-bezier(.45,0,.2,1)" },
    { transform: "translateY(-7px) scale(1.04, .9)", borderRadius: "28px", opacity: 1, filter: "blur(0px)", offset: .66, easing: "ease-in-out" },
    { transform: "translateY(2px) scale(.985, 1.04)", borderRadius: "28px", opacity: 1, filter: "blur(0px)", offset: .84, easing: "ease-in-out" },
    { transform: "none", borderRadius: "28px", opacity: 1, filter: "blur(0px)" }];
  const x = el.animate(wej ? kl : [kl[4], kl[2], kl[1], kl[0]].map(({ offset, easing, ...k }) => k), { duration: wej ? 760 : 380, easing: wej ? "linear" : "cubic-bezier(.5,0,.75,.4)" });
  [...el.children].forEach(d => d.animate(wej ? [{ opacity: 0 }, { opacity: 0, offset: .5 }, { opacity: 1 }] : [{ opacity: 1 }, { opacity: 0, offset: .3 }, { opacity: 0 }], { duration: wej ? 760 : 380 }));
  x.finished.then(() => { el.style.transformOrigin = ""; if (!wej) el.remove(); }, () => { if (!wej) el.remove(); });
}
function poPokazaniu(stare) {
  const nowe = [...widok.querySelectorAll(".zakladki")];
  nowe.forEach((z, i) => { if (stare[i] && stare[i].klucz === z.textContent) plynPigulke(z, stare[i]); });
  const nowa = widok.querySelector(":scope > .pisz"), stara = document.querySelector("body > .pisz:not(.odplywa)");
  if (nowa) { if (stara) stara.remove(); document.body.appendChild(nowa); if (!stara) kropla(nowa, true); }
  else if (stara && !widok.firstElementChild?.matches(".ladowanie")) { stara.classList.add("odplywa"); kropla(stara, false); }
}
Object.defineProperty(widok, "innerHTML", { configurable: true, get() { return _ih.get.call(this); }, set(v) {
  const stare = stanZakladek();
  const zk = !przejscie && zmianaZakresu && Date.now() - zmianaZakresu.t < 2000 ? zmianaZakresu : null;
  zmianaZakresu = null;
  if (przejscie) pokazZPrzejsciem(v); else if (zk) pokazZakres(v, zk); else _ih.set.call(this, v);
  try { poPokazaniu(stare); } catch (e) { console.error(e); }   // ozdobniki nie mogą zepsuć ekranu
} });
const trwaAnimacja = () => (anim = anim.filter(x => x.playState ? x.playState === "running" : x.isConnected)).length > 0;

const pozycja = (t, zak) => t === "treningi" ? 3.5 : ZAKLADKI.indexOf(zak);
const EKRANY = { dzis: pokazDzis, plan: pokazPlan, dane: pokazDane, treningi: () => pokazTreningi(), czat: a => pokazCzat(a), analiza: a => pokazAnalize(a), ustawienia: ekranUstawien, start: pokazStart, wiedza: pokazWiedze, metryka: a => pokazMetryke(a), jedzenie: a => pokazJedzenie(a), progres: pokazWage, trening: a => pokazTrening(a), zaplanowany: a => pokazZaplanowany(a) };

async function route() {
  if (czekaUpdate) { location.reload(); return; }
  const nr = ++nawNr;
  const hash = location.hash.slice(1) || "dzis";
  const [t, arg] = hash.split("/");
  if (t === "waga") { location.replace("#progres"); return; }   // stary adres (powiadomienia, zakładki)
  const zak = t === "analiza" || t === "plan" || t === "zaplanowany" ? "dzis" : t === "metryka" || t === "trening" || t === "treningi" ? "dane" : t;
  const i = ZAKLADKI.indexOf(zak), nav = $("nav");
  nav.querySelectorAll("a").forEach(a => a.classList.toggle("akt", a.dataset.t === zak));
  if (i >= 0) nav.style.setProperty("--i", i);
  nav.classList.toggle("bez-zak", i < 0);
  $("#tytul").textContent = { dzis: "Trener", plan: "Plan", dane: "Dane", treningi: "Dane", czat: "Czat z trenerem", analiza: "Analiza", ustawienia: "Ustawienia", start: "Poznajmy się", wiedza: "Źródła trenera", jedzenie: "Jedzenie", progres: "Progres", trening: "Trening", zaplanowany: "Zaplanowany trening" }[t] || "Trener";
  document.body.classList.toggle("detal", DETALE.has(t) && t !== "ustawienia");    // Ustawienia zamyka zębatka, więc zostaje logo
  // rodzaj przejścia
  if (poprz) poprz.y = SKR.scrollTop;                // przewinięcie ekranu, z którego wychodzisz
  const teraz = { t, hash, poz: pozycja(t, zak), y: 0 };
  let p = { typ: "zanik" };
  if (poprz && poprz.hash !== hash) {
    if (DETALE.has(t) && !DETALE.has(poprz.t)) {
      const r = ostatniKlik && Date.now() - ostatniKlik.t < 1500 ? ostatniKlik.r : srodek();
      ZRODLA.set(hash, { r, y: poprz.y, rodzic: poprz.hash });
      p = { typ: "otworz", r };
    } else if (DETALE.has(poprz.t) && !DETALE.has(t)) {
      const z = ZRODLA.get(poprz.hash);
      p = z && z.rodzic === hash ? { typ: "zamknij", r: z.r, y: z.y } : { typ: "zamknij", r: srodek() };
    } else if (!DETALE.has(t) && !DETALE.has(poprz.t) && teraz.poz >= 0 && poprz.poz >= 0 && teraz.poz !== poprz.poz)
      p = { typ: "bok", k: Math.sign(teraz.poz - poprz.poz) };
  }
  poprz = teraz;
  przejscie = p;
  ostatniKlik = null;
  clearTimeout(ladTimer);
  if (!widok.firstElementChild) _ih.set.call(widok, `<div class="ladowanie">Ładuję…</div>`);
  else ladTimer = setTimeout(() => {               // brak w pamięci i sieć wolna: dopiero wtedy „Ładuję…”
    if (nr === nawNr && przejscie) { skonczAnimacje(); _ih.set.call(widok, `<div class="ladowanie">Ładuję…</div>`); SKR.scrollTo(0, 0); }
  }, 450);
  WYK.clear();
  zamknijArkusz();
  uzyte = new Set();
  nawigacja = true;
  try {
    await (EKRANY[t] || pokazDzis)(arg);
  } catch (e) {
    if (e instanceof Anulowano || nr !== nawNr) return;
    if (!/nie jest zapamiętane/.test(e.message)) widok.innerHTML = `<div class="karta zle">Błąd: ${esc(e.message)}</div>`;
  } finally { if (nr === nawNr) nawigacja = false; }
  if (nr === nawNr) { przejscie = null; clearTimeout(ladTimer); }
  if (nr === nawNr && i >= 0) {                    // zapamiętaj, czego zakładka potrzebuje → wczytywanie z góry
    const tr = JSON.parse(localStorage.getItem("trasyApi") || "{}");
    tr[t] = [...uzyte].slice(0, 30);
    localStorage.setItem("trasyApi", JSON.stringify(tr));
  }
  wczytajZGory(800);
}
// po cichu: świeże dane z tła → przerysuj ten sam ekran bez animacji, w tym samym miejscu
let cichyTimer = 0;
function przerysujPoCichu() {
  clearTimeout(cichyTimer);
  cichyTimer = setTimeout(async () => {
    const [t, arg] = (location.hash.slice(1) || "dzis").split("/");
    if (przejscie || ["czat", "start", "ustawienia"].includes(t) || zajety() || document.body.classList.contains("arkusz-otwarty") ||
        document.activeElement?.matches("input, textarea, select") || trwaAnimacja()) return;
    const nr = nawNr, y = SKR.scrollTop;
    WYK.clear();
    try { await (EKRANY[t] || pokazDzis)(arg); } catch (_) { return; }
    if (nr === nawNr) SKR.scrollTo(0, y);
  }, 120);
}
// wczytywanie z góry: wszystko, czego potrzebują zakładki, leży w pamięci zanim w nie wejdziesz
let zGoryTimer = 0;
function wczytajZGory(ms) {
  clearTimeout(zGoryTimer);
  zGoryTimer = setTimeout(async () => {
    const d = new Date(), dz = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    const tr = JSON.parse(localStorage.getItem("trasyApi") || "{}");
    const duze = ["dni?od=2000-01-01", "agregaty?okres=miesiac", "agregaty?okres=tydzien"];   // ~2 s każde: na koniec, żeby nie blokowały reszty
    const lista = new Set(["dzis", "dieta", "waga", "plan", "makrocykl", "dieta?dzien=" + dz, "czat", "ustawienia", "aktywnosci?limit=40&offset=0",
      "dieta/historia?dni=28", ...Object.values(tr).flat().filter(p => !duze.includes(p)), ...duze]);
    const doPobrania = [...lista].filter(p => /^dieta\?dzien=/.test(p) ? p === "dieta?dzien=" + dz : true)
      .filter(p => { const w = PAMIEC.get(p); return !w || w.brudne || Date.now() - w.t > 60e3; });
    for (let k = 0; k < doPobrania.length; k += 3)   // po 3 naraz, żeby nie zapchać telefonu
      await Promise.all(doPobrania.slice(k, k + 3).map(p => pobierzDoPamieci(p).catch(() => {})));
  }, ms);
}
document.addEventListener("visibilitychange", () => {   // powrót do apki: odśwież to, co widać, i resztę w tle
  if (document.hidden) return;
  uzyte.forEach(p => { const w = PAMIEC.get(p); if (w) w.t = 0; });
  uzyte.forEach(odswiezWTle);
  wczytajZGory(1500);
});
// odświeżanie na żywo: tani odcisk danych z Pi co minutę (co ~3 s, gdy trener coś robi). Gdy trener zmieni plan,
// kalendarz, cele itp. — pamięć idzie do odświeżenia, a widoczna zakładka przerysowuje się po cichu.
let ODCISK = null, sprTimer = 0, sprTrwa = null;
function sprawdzDane() {
  if (!sprTrwa) sprTrwa = (async () => {
    clearTimeout(sprTimer);
    let w = null;
    if (!document.hidden) try { w = JSON.parse(await siec("wersja")); } catch (_) {}
    if (w) {
      if (ODCISK && w.dane !== ODCISK.dane) {
        PAMIEC.forEach(x => x.brudne = true);
        uzyte.forEach(odswiezWTle);
        wczytajZGory(800);
      }
      if (ODCISK && w.czat !== ODCISK.czat) { const c = PAMIEC.get("czat"); if (c) c.brudne = true; dociagnijCzat(); }
      ODCISK = w;
    }
    sprTimer = setTimeout(sprawdzDane, czatZadanie || (w && w.trwa) ? 3000 : 60000);
  })().finally(() => { sprTrwa = null; });
  return sprTrwa;
}
document.addEventListener("visibilitychange", () => { if (!document.hidden) sprawdzDane(); });
setTimeout(sprawdzDane, 1500);
// ‹ w nagłówku na ekranach szczegółów: wraca tam, skąd przyszedłeś (z animacją zmniejszania)
$("#btn-wstecz").onclick = () => {
  const z = ZRODLA.get(location.hash.slice(1));
  if (z && history.length > 1) history.back(); else location.hash = "#" + (RODZIC[(location.hash.slice(1) || "").split("/")[0]] || "dzis");
};
window.addEventListener("hashchange", route);
// iOS ignoruje user-scalable=no — blokujemy gest szczypania ręcznie (podwójne stuknięcie blokuje touch-action w CSS)
["gesturestart", "gesturechange", "gestureend"].forEach(g => document.addEventListener(g, e => e.preventDefault(), { passive: false }));
document.addEventListener("touchmove", e => { if (e.touches.length > 1) e.preventDefault(); }, { passive: false });
window.addEventListener("unhandledrejection", e => { if (e.reason instanceof Anulowano) e.preventDefault(); });

// ------------------------------------------------------------------ auto-aktualizacja
// Pi podaje wersję plików; gdy się zmieni, apka przeładowuje się sama (nie trzeba jej zamykać)
const WERSJA = document.querySelector('meta[name="wersja"]')?.content;
let czekaUpdate = false;
const zajety = () => !!(document.getElementById("postep") || location.hash.startsWith("#start") || document.querySelector(".arkusz-tlo, input[data-zdj]") ||
  [...document.querySelectorAll("textarea, input[type=text], input[type=number]")].some(x => x.value && x.closest(".pisz, #widok") && document.activeElement === x) ||
  ($(".pisz textarea")?.value || "").trim());
async function sprawdzWersje() {
  if (!WERSJA || document.hidden) return;
  try {
    const w = (await (await fetch("/wersja", { cache: "no-store" })).text()).trim();
    if (!w || w === WERSJA) return;
    if (zajety()) czekaUpdate = true; else location.reload();
  } catch (_) {}
}
document.addEventListener("visibilitychange", () => { if (!document.hidden) sprawdzWersje(); });
window.addEventListener("pageshow", sprawdzWersje);
setInterval(sprawdzWersje, 60000);
$("#btn-ust").onclick = () => location.hash.startsWith("#ustawienia") ? $("#btn-wstecz").onclick() : pokazUstawienia();  // drugi klik zamyka
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
document.addEventListener("focusin", e => { if (e.target.matches(".pisz textarea")) document.body.classList.add("pisze"); });
document.addEventListener("focusout", e => { if (e.target.matches(".pisz textarea")) setTimeout(() => { if (!document.activeElement?.matches(".pisz textarea")) document.body.classList.remove("pisze"); }, 250); });
route();

// ------------------------------------------------------------------ Ankieta startowa
const KROKI = [
  { t: "🎯 Do czego trenujesz?", p: [
    { k: "cele", typ: "multi", o: ["Wyścigi XCO (MTB)", "Maratony MTB", "Wyścigi szosowe", "Długie trasy / gran fondo", "Wyższe FTP i forma", "Bieg (np. 5–10 km)", "Siła i sylwetka", "Zdrowie i kondycja"] },
    { k: "cel_opis", typ: "tekst", l: "Własnymi słowami (co chcesz osiągnąć, np. „top 10 w juniorach”, „FTP 270 W”)" }] },
  { t: "📅 Terminy", p: [
    { k: "zawody", typ: "tekst", l: "Zawody i ważne daty (który start najważniejszy?)", ph: "np. 16.05 XC — najważniejszy; 12.04 start testowy" },
    { k: "szkola", typ: "tekst", l: "Szkoła: egzaminy, ferie, wyjazdy", ph: "np. ferie 15–28.02, matura próbna w marcu" }] },
  { t: "⏱️ Ile masz czasu?", p: [
    { k: "dni", typ: "dni", o: ["—", "do 1 h", "1–1,5 h", "1,5–2 h", "2–3 h", "3 h+"] },
    { k: "gdzie", typ: "jeden", l: "Gdzie jeździsz zimą", o: ["na zewnątrz", "trenażer", "zależy od pogody"] }] },
  { t: "🚲 Sprzęt", p: [
    { k: "sprzet", typ: "multi", o: ["rower szosowy", "MTB", "gravel", "trenażer smart", "miernik mocy", "pas tętna", "siłownia (pełna)", "siłownia szkolna", "sprzęt w domu"] }] },
  { t: "🏋️ Siłownia i bieganie", p: [
    { k: "silka", typ: "jeden", l: "Siłownia w tygodniu", o: ["0", "1", "2", "3"] },
    { k: "bieg", typ: "jeden", l: "Bieganie", o: ["nie", "1× w tygodniu", "2–3× w tygodniu"] }] },
  { t: "🎨 Jak ma wyglądać plan", p: [
    { k: "styl", typ: "jeden", l: "Charakter", o: ["spokojnie — zdrowie i przyjemność", "zrównoważony", "ambitnie — maksimum progresu"] },
    { k: "zegarek", typ: "jeden", l: "Treningi na zegarku", o: ["szczegółowe (moc/tętno, interwały)", "proste (czas + strefa)"] },
    { k: "analizy", typ: "jeden", l: "Analizy", o: ["krótkie", "szczegółowe z liczbami"] },
    { k: "powiadomienia", typ: "jeden", l: "Powiadomienia", o: ["codziennie rano + po treningu", "tylko ważne zmiany"] }] },
  { t: "🩺 Zdrowie i reszta", p: [
    { k: "zdrowie", typ: "tekst", l: "Kontuzje, bóle, ograniczenia", ph: "np. kolano po upadku, nic" },
    { k: "inne", typ: "tekst", l: "Coś jeszcze, co trener powinien wiedzieć?" }] },
];
let ank = null, krokNr = 0;
const DNI_T = ["pon", "wt", "śr", "czw", "pt", "sob", "ndz"];

async function pokazStart() {
  if (!ank) { const s = await api("start"); ank = s.ankieta || {}; }
  rysujKrok();
}
function rysujKrok() {
  const kr = KROKI[krokNr];
  const pola = kr.p.map(p => {
    const v = ank[p.k];
    if (p.typ === "multi" || p.typ === "jeden") return `${p.l ? `<label>${esc(p.l)}</label>` : ""}<div class="wiersz chipy" data-k="${p.k}" data-typ="${p.typ}">${p.o.map(o =>
      `<button class="chip ${(p.typ === "multi" ? (v || []).includes(o) : v === o) ? "akt" : ""}" data-v="${esc(o)}">${esc(o)}</button>`).join("")}</div>`;
    if (p.typ === "tekst") return `<label>${esc(p.l)}</label><textarea data-k="${p.k}" rows="3" placeholder="${esc(p.ph || "")}">${esc(v || "")}</textarea>`;
    if (p.typ === "dni") return DNI_T.map(d => `<div class="przelacznik"><span>${d}</span><select data-dzien="${d}" style="width:auto">${p.o.map(o =>
      `<option ${((v || {})[d] || "—") === o ? "selected" : ""}>${o}</option>`).join("")}</select></div>`).join("");
  }).join("");
  widok.innerHTML = `<div class="szary">Krok ${krokNr + 1} z ${KROKI.length}</div><div class="pasek"><i style="width:${(krokNr + 1) / KROKI.length * 100}%"></i></div>
    <div class="karta"><h3>${kr.t}</h3>${pola}</div>
    <div class="wiersz">${krokNr ? `<button class="drugi" onclick="zbierz();krokNr--;rysujKrok()">← Wstecz</button>` : ""}
    <button onclick="zbierz();dalej()">${krokNr === KROKI.length - 1 ? "Wyślij trenerowi ✓" : "Dalej →"}</button></div>`;
  widok.querySelectorAll(".chipy").forEach(g => g.addEventListener("click", e => {
    const b = e.target.closest(".chip"); if (!b) return;
    if (g.dataset.typ === "jeden") g.querySelectorAll(".chip").forEach(x => x !== b && x.classList.remove("akt"));
    b.classList.toggle("akt");
  }));
  SKR.scrollTo(0, 0);
}
function zbierz() {
  widok.querySelectorAll(".chipy").forEach(g => {
    const w = [...g.querySelectorAll(".chip.akt")].map(b => b.dataset.v);
    ank[g.dataset.k] = g.dataset.typ === "multi" ? w : (w[0] || "");
  });
  widok.querySelectorAll("textarea[data-k]").forEach(t => ank[t.dataset.k] = t.value.trim());
  const dni = widok.querySelectorAll("select[data-dzien]");
  if (dni.length) { ank.dni = {}; dni.forEach(s => ank.dni[s.dataset.dzien] = s.value === "—" ? "" : s.value); }
}
async function dalej() {
  if (krokNr < KROKI.length - 1) { krokNr++; rysujKrok(); return; }
  widok.innerHTML = `<div class="karta mysli">Trener czyta Twoje odpowiedzi i dane z Garmina</div>`;
  try {
    const w = await czekaj(await api("start", ank));
    pokazPytania(w);
  } catch (e) { widok.innerHTML = `<div class="karta zle">Błąd: ${esc(e.message)}</div><button onclick="rysujKrok()">Wróć</button>`; }
}
function pokazPytania(w) {
  const pyt = w.pytania || [];
  widok.innerHTML = `<div class="karta"><h3>🧑‍🏫 Trener</h3><div class="tresc">${esc(w.podsumowanie)}</div></div>
    ${pyt.length ? `<h2>Jeszcze ${pyt.length === 1 ? "jedno pytanie" : "kilka pytań"}</h2>` : ""}
    ${pyt.map((p, i) => `<div class="karta" data-i="${i}"><b>${esc(p.pytanie)}</b>
      ${(p.opcje || []).length ? `<div class="wiersz chipy" data-typ="${p.wielokrotny ? "multi" : "jeden"}" style="margin-top:8px">${p.opcje.map(o => `<button class="chip" data-v="${esc(o)}">${esc(o)}</button>`).join("")}</div>` : ""}
      <textarea rows="2" placeholder="${(p.opcje || []).length ? "albo napisz po swojemu" : "odpowiedź"}" style="margin-top:8px"></textarea></div>`).join("")}
    <button style="width:100%" id="uloz">🗺️ Ułóż periodyzację i plan</button>
    <div class="szary" style="margin-top:8px">Trener najpierw sprawdzi bazę wiedzy pod Twój cel i poszuka źródeł, potem ułoży periodyzację i plan (8–15 min). Możesz zamknąć apkę — dostaniesz powiadomienie, a treningi same trafią na zegarek.</div>`;
  widok.querySelectorAll(".chipy").forEach(g => g.addEventListener("click", e => {
    const b = e.target.closest(".chip"); if (!b) return;
    if (g.dataset.typ === "jeden") g.querySelectorAll(".chip").forEach(x => x !== b && x.classList.remove("akt"));
    b.classList.toggle("akt");
  }));
  $("#uloz").onclick = async () => {
    const odp = pyt.map((p, i) => {
      const k = widok.querySelector(`[data-i="${i}"]`);
      const wyb = [...k.querySelectorAll(".chip.akt")].map(b => b.dataset.v), t = k.querySelector("textarea").value.trim();
      return { pytanie: p.pytanie, odpowiedz: [...wyb, t].filter(Boolean).join("; ") };
    });
    widok.innerHTML = `<div class="karta mysli">Trener układa periodyzację do Twojego celu, plan tygodnia i sprawdza go z zasadami treningu</div>
      <div class="szary" id="postep"></div><div class="szary">Najpierw trener sprawdza, czy baza wiedzy pasuje do celu, i szuka źródeł w internecie (badania, federacje, przepisy). Zwykle 8–15 minut — możesz zamknąć apkę, dostaniesz powiadomienie.</div>`;
    try {
      await czekaj(await api("start/koniec", { odpowiedzi: odp }));
      location.hash = "#plan";
    } catch (e) { widok.innerHTML = `<div class="karta zle">Błąd: ${esc(e.message)}</div>`; }
  };
}

// ------------------------------------------------------------------ Źródła (baza wiedzy)
const linki = t => esc(t).replace(/https?:\/\/[^\s)<]+/g, u => `<a href="${u}" target="_blank" rel="noopener" style="color:var(--akcent);word-break:break-all">${u}</a>`);
function md(t) {   // prosty Markdown: nagłówki, listy, **pogrubienia**, tabele jako tekst, linki
  const linie = [];
  t.replace(/^# .*\n?/, "").split("\n").forEach(l => {
    if (/^\s{2,}\S/.test(l) && linie.length && !/^\s*[-*]\s|^\s*\d+\.\s/.test(l)) linie[linie.length - 1] += " " + l.trim();
    else linie.push(l);
  });
  let h = "", lista = false;
  for (let l of linie) {
    let x = linki(l).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
    const m = l.match(/^\s*(?:[-*]|\d+\.)\s+/);
    if (m && !lista) { h += "<ul style='padding-left:18px;margin:4px 0'>"; lista = true; }
    if (!m && lista) { h += "</ul>"; lista = false; }
    if (/^#{2,4} /.test(l)) h += `<div style="color:var(--tekst);font-weight:700;margin:10px 0 4px">${x.replace(/^#+ /, "")}</div>`;
    else if (m) h += `<li>${x.replace(/^\s*(?:[-*]|\d+\.)\s+/, "")}</li>`;
    else if (l.trim()) h += `<div style="margin:3px 0">${x}</div>`;
  }
  return h + (lista ? "</ul>" : "");
}
async function pokazWiedze() {
  const w = await api("wiedza"), b = w.badania;
  let h = "";
  if (b) {
    const o = b.ocena;
    h += `<div class="karta"><h3>🔎 Ocena bazy pod Twój cel</h3><div class="szary">${esc(b.kiedy.replace("T", " ").slice(0, 16))}</div>
      <div class="tresc" style="margin-top:6px">${esc(o.dopasowanie)}</div>
      ${o.braki.length ? `<div style="margin-top:8px"><b>Braki:</b><div class="szary">${o.braki.map(x => "• " + esc(x)).join("<br>")}</div></div>` : ""}
      ${o.watpliwosci.length ? `<div style="margin-top:8px"><b>Wątpliwości:</b><div class="szary">${o.watpliwosci.map(x => "• " + esc(x)).join("<br>")}</div></div>` : ""}
      <div style="margin-top:8px"><b>Zbadane tematy:</b><div class="szary">${b.pliki.map(p => p.odrzucony ? `✗ ${esc(p.tytul)} (odrzucony: brak działających źródeł)` :
        `✓ ${esc(p.tytul)} — źródła: ${p.dzialajace}/${p.zrodla} działa`).join("<br>")}</div></div></div>`;
  } else h += `<div class="karta szary">Badania pod cel pojawią się po ankiecie startowej.</div>`;
  h += `<button class="drugi" style="width:100%;margin-bottom:12px" onclick="if(confirm('Poszukać źródeł od nowa i przebudować periodyzację?'))akcja('badania')">🔎 Poszukaj źródeł od nowa</button>`;
  for (const rodz of ["pod cel", "ogólna"]) {
    const pl = w.pliki.filter(p => p.rodzaj === rodz);
    if (!pl.length) continue;
    h += `<h2>${rodz === "pod cel" ? "Wiedza pod Twój cel" : "Baza ogólna"}</h2>` + pl.map(p =>
      `<details class="karta"><summary style="font-size:15px;color:var(--tekst)"><b>${esc((p.tresc.match(/^# (.+)$/m) || [, p.plik])[1])}</b></summary>
       <div class="szary" style="margin-top:8px;font-size:13px">${md(p.tresc)}</div></details>`).join("");
  }
  widok.innerHTML = h;
}

// iOS: przewija się body (patrz styl.css), więc okno ma zawsze stać na 0. Klawiatura (albo powrót z aparatu) potrafi
// je przesunąć i zostawić — wtedy dolne menu, nagłówek i tło wiszą w połowie ekranu. Cofamy okno, gdy nic nie jest wpisywane.
(() => {
  const pisze = () => document.activeElement?.matches("input, textarea, select");
  const napraw = () => requestAnimationFrame(() => {
    if (pisze()) return;
    if (window.scrollY || window.scrollX || document.documentElement.scrollTop) window.scrollTo(0, 0);
    const n = $("nav"); if (n) { n.style.transform = "translate3d(-50%, 0.01px, 0)"; requestAnimationFrame(() => n.style.transform = ""); }
  });
  window.addEventListener("scroll", () => { if (!pisze()) napraw(); }, { passive: true });
  window.visualViewport?.addEventListener("resize", () => { setTimeout(napraw, 60); setTimeout(napraw, 400); });
  document.addEventListener("focusout", e => { if (e.target.matches("input, textarea, select")) { setTimeout(napraw, 100); setTimeout(napraw, 450); } });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) setTimeout(napraw, 200); });
  SKR.addEventListener("scroll", () => { if (window.scrollY && !pisze()) napraw(); }, { passive: true });
})();
