"use strict";
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const api = async (p, opt) => {
  const r = await fetch("/api/" + p, opt && { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(opt) });
  if (r.status === 401) { niezapamietane(); throw new Error("To urządzenie nie jest zapamiętane"); }
  if (!r.ok) throw new Error(r.status + " " + p);
  return r.json();
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

function niezapamietane() {
  widok.innerHTML = `<div class="karta"><h3>🔐 Zapamiętaj to urządzenie</h3>
    <div>Apka jest dostępna z internetu, ale wpuszcza tylko Twoje urządzenia. Wpisz jednorazowy kod parowania
    (dostaniesz go od Claude albo na Pi: <code>python -m trener kod</code>, ważny 15 min).</div>
    <div class="wiersz" style="margin-top:10px"><input id="kod" type="text" placeholder="KOD" autocomplete="one-time-code" autocapitalize="characters"
      style="flex:1;min-width:0;font-size:18px;letter-spacing:.15em;text-transform:uppercase">
    <button id="paruj">Połącz</button></div><div id="paruj-info" class="szary" style="margin-top:6px"></div></div>`;
  $("#paruj").onclick = async () => {
    const info = $("#paruj-info"); info.textContent = "Sprawdzam…";
    const r = await fetch("/api/paruj", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ kod: $("#kod").value }) });
    if (r.ok) { info.textContent = "✅ Zapamiętane"; setTimeout(() => location.reload(), 500); }
    else info.textContent = (await r.json().catch(() => ({}))).blad || "Błąd " + r.status;
  };
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
    <circle cx="${X(li)}" cy="${Y(lv)}" r="3.5" fill="${s.kolor}" stroke="var(--karta)" stroke-width="2"/></svg>`;
}

function rysujLinie(el, s, W, H) {
  const n = s.x.length, serie = s.serie;
  const wart = serie.flatMap(q => q.y).concat(s.pasmo ? s.pasmo.flat() : []).concat(s.ref != null ? [s.ref] : []).filter(v => v != null);
  if (wart.length < 2) { el.innerHTML = `<div class="pusto">za mało danych</div>`; return; }
  const fmt = s.fmt || (v => lb(v, s.dz || 0));
  const t = zaokr(s.min ?? Math.min(...wart), s.max ?? Math.max(...wart), 4, s.krokY);
  const lo = t[0], hi = t[t.length - 1];
  const L = 6, R = 6, T = 10, B = 22, osL = Math.max(...t.map(v => fmt(v).length)) * 6.5 + 8;
  const x0 = L + osL, x1 = W - R - (s.etykietaKonca === false ? 0 : 30);
  const X = i => n === 1 ? (x0 + x1) / 2 : x0 + (x1 - x0) * i / (n - 1), Y = v => T + (H - T - B) * (1 - (v - lo) / (hi - lo));
  let g = t.map(v => `<line x1="${x0}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" class="siatka"/><text x="${x0 - 6}" y="${Y(v) + 3.5}" text-anchor="end">${fmt(v)}</text>`).join("");
  // podpisy osi X: ~4 równo rozłożone
  const ileX = Math.min(n, W < 380 ? 3 : 5);
  for (let k = 0; k < ileX; k++) { const i = ileX === 1 ? 0 : Math.round((n - 1) * k / (ileX - 1)); g += `<text x="${X(i)}" y="${H - 6}" text-anchor="${k === 0 ? "start" : k === ileX - 1 ? "end" : "middle"}">${esc(s.etX ? s.etX(s.x[i]) : s.x[i])}</text>`; }
  if (s.pasmo) {   // np. norma HRV
    const p = s.pasmo.map((b, i) => [i, b]).filter(([, b]) => b && b[0] != null && b[1] != null);
    if (p.length > 1) g += `<path d="M${p.map(([i, b]) => X(i).toFixed(1) + "," + Y(b[1]).toFixed(1)).join("L")}L${p.slice().reverse().map(([i, b]) => X(i).toFixed(1) + "," + Y(b[0]).toFixed(1)).join("L")}Z" fill="${serie[0].kolor}" opacity=".13"/>`;
  }
  if (s.ref != null) g += `<line x1="${x0}" x2="${x1}" y1="${Y(s.ref)}" y2="${Y(s.ref)}" class="ref"/><text x="${x0 + 4}" y="${Y(s.ref) - 5}" class="ref-t">${esc(s.refNazwa || "średnia")} ${fmt(s.ref)}</text>`;
  const konce = [];
  serie.forEach((q, si) => {
    let d = "", a = "", seg = [];
    const zamknij = () => { if (seg.length > 1 && serie.length === 1) a += `M${seg[0][0]},${Y(lo)}L${seg.map(p => p.join(",")).join("L")}L${seg[seg.length - 1][0]},${Y(lo)}Z`; seg = []; };
    q.y.forEach((v, i) => {
      if (v == null) { zamknij(); return; }
      const p = [X(i).toFixed(1), Y(v).toFixed(1)];
      d += (seg.length ? "L" : "M") + p.join(","); seg.push(p);
    });
    zamknij();
    if (a) g += `<path d="${a}" fill="${q.kolor}" opacity=".10"/>`;
    g += `<path d="${d}" fill="none" stroke="${q.kolor}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"${q.przerywana ? ' stroke-dasharray="1 5"' : ""}/>`;
    // pojedyncze punkty (otoczone przerwami) jako kropki
    q.y.forEach((v, i) => { if (v != null && q.y[i - 1] == null && q.y[i + 1] == null) g += `<circle cx="${X(i)}" cy="${Y(v)}" r="2" fill="${q.kolor}"/>`; });
    const ost = q.y.map((v, i) => [i, v]).filter(([, v]) => v != null).pop();
    if (ost) {
      g += `<circle cx="${X(ost[0])}" cy="${Y(ost[1])}" r="4.5" fill="${q.kolor}" stroke="var(--karta)" stroke-width="2"/>`;
      if (s.etykietaKonca !== false) konce.push([X(ost[0]) + 8, Y(ost[1]) + 4, fmt(ost[1])]);
    }
  });
  konce.sort((p, q) => p[1] - q[1]).forEach((k, i, t) => { if (i && k[1] - t[i - 1][1] < 13) k[1] = t[i - 1][1] + 13; });
  g += konce.map(([x, y, v]) => `<text x="${x}" y="${y}" class="koniec">${v}</text>`).join("");
  el.innerHTML = `<svg width="${W}" height="${H}">${g}<g class="celownik" style="display:none"><line y1="${T}" y2="${H - B}"/>${serie.map(q => `<circle r="4.5" fill="${q.kolor}" stroke="var(--karta)" stroke-width="2"/>`).join("")}</g></svg><div class="dymek"></div>`;
  const svg = el.firstChild, cel = svg.lastChild, dym = el.lastChild;
  const pokaz = e => {
    const r = svg.getBoundingClientRect(), px = e.clientX - r.left;
    let i = Math.round((px - x0) / ((x1 - x0) / Math.max(1, n - 1))); i = Math.max(0, Math.min(n - 1, i));
    if (serie.every(q => q.y[i] == null)) { cel.style.display = "none"; dym.style.display = "none"; return; }
    cel.style.display = ""; cel.firstChild.setAttribute("x1", X(i)); cel.firstChild.setAttribute("x2", X(i));
    serie.forEach((q, k) => { const c = cel.children[k + 1]; if (q.y[i] == null) c.style.display = "none"; else { c.style.display = ""; c.setAttribute("cx", X(i)); c.setAttribute("cy", Y(q.y[i])); } });
    dym.innerHTML = `<div class="dt">${esc(s.etDymek ? s.etDymek(s.x[i]) : s.x[i])}</div>` + serie.map(q => q.y[i] == null ? "" :
      `<div><i style="background:${q.kolor}"></i>${serie.length > 1 ? esc(q.nazwa) + " " : ""}<b>${fmt(q.y[i])}</b>${s.jedn ? " " + esc(s.jedn) : ""}</div>`).join("") +
      (s.pasmo && s.pasmo[i] && s.pasmo[i][0] != null ? `<div class="sz">norma ${fmt(s.pasmo[i][0])}–${fmt(s.pasmo[i][1])}</div>` : "");
    dym.style.display = "block";
    const dw = dym.offsetWidth; dym.style.left = Math.max(0, Math.min(W - dw, X(i) - dw / 2)) + "px";
    if (s.klik && e.type === "pointerup") s.klik(s.x[i], i);
  };
  svg.addEventListener("pointermove", pokaz); svg.addEventListener("pointerdown", pokaz); svg.addEventListener("pointerup", pokaz);
  svg.addEventListener("pointerleave", () => { cel.style.display = "none"; dym.style.display = "none"; });
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
      `<div><i style="background:${q.kolor}"></i>${serie.length > 1 ? esc(q.nazwa) + " " : ""}<b>${fmt(q.y[i])}</b>${s.jedn ? " " + esc(s.jedn) : ""}</div>`).join("") +
      (serie.length > 1 ? `<div class="sz">razem ${fmt(sumy[i])}${s.jedn ? " " + esc(s.jedn) : ""}</div>` : "") + (sumy[i] ? "" : `<div class="sz">brak</div>`);
    dym.style.display = "block";
    const dw = dym.offsetWidth; dym.style.left = Math.max(0, Math.min(W - dw, x0 + slot * (i + .5) - dw / 2)) + "px";
    if (s.klik && e.type === "pointerup") s.klik(s.x[i], i);
  };
  svg.addEventListener("pointermove", pokaz); svg.addEventListener("pointerdown", pokaz); svg.addEventListener("pointerup", pokaz);
  svg.addEventListener("pointerleave", () => { pod.style.display = "none"; dym.style.display = "none"; });
}
const legenda = serie => serie.length < 2 ? "" : `<div class="legenda">${serie.map(q => `<span><i style="background:${q.kolor}"></i>${esc(q.nazwa)}</span>`).join("")}</div>`;

// ------------------------------------------------------------------ Dziś
const STATUS = { PRODUCTIVE: "produktywny", MAINTAINING: "utrzymanie", RECOVERY: "regeneracja", UNPRODUCTIVE: "nieproduktywny",
  DETRAINING: "roztrenowanie", OVERREACHING: "przeciążenie", PEAKING: "szczyt", STRAINED: "nadwyrężenie" };
const status = s => s ? (STATUS[String(s).replace(/_\d+$/, "")] || s) : "";

function trening(t, zrobiony) {
  const kroki = (t.kroki || []).map(k => {
    if (k.rodzaj === "powtorz") return `<li>${k.razy}× [${(k.kroki || []).map(opisKroku).join(" → ")}]</li>`;
    return `<li>${opisKroku(k)}</li>`;
  }).join("");
  const st = { na_zegarku: "⌚ na zegarku", nowy: "czeka", blad: "⚠️ błąd", w_apce: "" }[t.stan] ?? t.stan;
  return `<div class="trening sport-${t.sport}${zrobiony ? " zrobiony" : ""}">
    <b>${ikSport(t.sport)}${esc(t.tytul)}</b>${t.min ? `<span class="znaczek">~${t.min} min</span>` : ""}${st ? `<span class="znaczek">${st}</span>` : ""}${zrobiony ? `<span class="znaczek ok">✓ zrobione</span>` : ""}
    ${t.opis ? `<div class="szary tresc">${esc(t.opis)}</div>` : ""}
    ${kroki ? `<details><summary>kroki</summary><ul class="kroki">${kroki}</ul></details>` : ""}
    ${t.stan === "blad" ? `<div class="szary zle">${esc(t.zrodlo)}</div>` : ""}</div>`;
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
const METRYKI = {
  sen: { n: "Sen", k: "sen_h", jedn: "h", dz: 1, lepiej: 1, kolor: KOLOR.fiolet, fmtDuzy: hMin, opis: "Długość snu w nocy przed tym dniem." },
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
let WSZYSTKIE = null, wszystkieCzas = 0;
async function wszystkieDni() {
  if (!WSZYSTKIE || Date.now() - wszystkieCzas > 5 * 60e3) { WSZYSTKIE = await api("dni?od=2000-01-01"); wszystkieCzas = Date.now(); }
  return WSZYSTKIE;
}
const srednia = a => { const v = a.filter(x => x != null); return v.length ? v.reduce((s, x) => s + x, 0) / v.length : null; };
const dzienMinus = (d, n) => { const x = new Date(d + "T12:00"); x.setDate(x.getDate() - n); return x.toISOString().slice(0, 10); };

function delta(m, teraz, odn, nazwa) {   // ▲/▼ z oceną (lepiej/gorzej) — kolor tekstu tylko dla oceny, zawsze z ikoną
  if (teraz == null || odn == null) return "";
  const r = teraz - odn, dz = m.dz || 0;
  if (Math.abs(r) < Math.pow(10, -dz) / 2) return `<span class="delta">= ${nazwa}</span>`;
  const dobre = m.lepiej ? Math.sign(r) === m.lepiej : null;
  return `<span class="delta ${dobre == null ? "" : dobre ? "lepiej" : "gorzej"}">${r > 0 ? "▲" : "▼"} ${lb(Math.abs(r), dz)} ${nazwa}</span>`;
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
    <div class="w">${v == null ? "–" : lb(v, m.dz || 0)}<small>${m.jedn && v != null ? " " + m.jedn : ""}</small></div>
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
    <div class="duzy">${m.fmtDuzy ? m.fmtDuzy(v) : lb(v, m.dz || 0)}<small>${m.jedn && !m.fmtDuzy ? " " + m.jedn : ""}</small></div>
    <div class="wiersz delty">${delta(m, v, sr7, "vs 7 dni")}${delta(m, v, sr30, "vs 30 dni")}</div>
    ${pct != null ? `<div class="pasek-pct"><i style="width:${pct}%"></i></div><div class="szary">Lepiej niż ${pct}% dni z ostatniego roku</div>` : ""}
    ${klucz === "hrv" && ost.hrv_norma ? `<div class="szary">Norma ${ost.hrv_norma[0]}–${ost.hrv_norma[1]} ms · średnia 7 dni ${lb(ost.hrv_7d)} ms${ost.hrv_status ? " · " + esc(String(ost.hrv_status).toLowerCase()) : ""}</div>` : ""}
    ${klucz === "obciazenie" ? `<div class="szary">Przewlekłe ${lb(ost.obc_przewlekle)} · stosunek ${lb(ost.acwr, 1)}${ost.status ? " · " + esc(status(ost.status)) : ""}</div>` : ""}
    </div>`;
  h += `<div class="zakladki">${ZAKRESY.map(([n, t]) => `<button class="${zakresM === n ? "akt" : ""}" data-z="${n}">${t}</button>`).join("")}</div>`;
  h += `<div class="karta"><div class="kt">${esc(m.n)}${okres !== "dzien" ? ` <span class="szary">· średnie ${okres === "tydzien" ? "tygodniowe" : "miesięczne"}</span>` : ""}</div>
    ${wyk({ typ: "linia", x: gr.x, serie, pasmo, ref: serie.length === 1 ? srZ : null, dz: m.dz || 0, jedn: m.jedn, min: m.min, max: m.max, etX, etDymek: etD,
      klik: klucz === "sen" && okres === "dzien" ? x => { nocWybrana = x; rysujNoc(); } : null })}
    ${legenda(serie)}
    <div class="statsy"><div><span>średnio</span><b>${lb(srZ, m.dz || 0)}</b></div><div><span>${m.lepiej ? "najlepiej" : "max"}</span><b>${lb(naj, m.dz || 0)}</b></div><div><span>${m.lepiej ? "najsłabiej" : "min"}</span><b>${lb(najg, m.dz || 0)}</b></div><div><span>dni z danymi</span><b>${vals.length}</b></div></div></div>`;
  if (klucz === "sen") h += await sekcjaSnu(z, wz, okres);
  // dni tygodnia
  const dt = [1, 2, 3, 4, 5, 6, 0].map(w => srednia(z.filter(d => d.dzien > dzienMinus(ost.dzien, 90) && new Date(d.dzien + "T12:00").getDay() === w).map(d => wartMetryki(m, d))));
  h += `<div class="karta"><div class="kt">Dni tygodnia <span class="szary">· średnia z 90 dni</span></div>
    ${wyk({ typ: "slupki", x: ["pon", "wt", "śr", "czw", "pt", "sob", "ndz"], serie: [{ nazwa: m.n, y: dt, kolor: m.kolor }], dz: m.dz || 0, jedn: m.jedn, h: 150 })}
    ${klucz === "sen" ? `<div class="szary">${(() => { const t = srednia(dt.slice(0, 4).concat(dt[6])), w = srednia([dt[4], dt[5]]); return t && w ? `Przed szkołą (ndz–czw) średnio ${hMin(t)}, w weekend (pt–sob) ${hMin(w)}.` : ""; })()}</div>` : ""}</div>`;
  // porównanie: ostatnie 30 dni vs rok temu
  h += `<div class="karta"><div class="kt">Porównanie</div><table class="tab">
    <tr><td>Ostatnie 30 dni</td><td><b>${lb(sr30teraz, m.dz || 0)}</b> ${esc(m.jedn)}</td></tr>
    <tr><td>Te same 30 dni rok temu</td><td><b>${lb(rt, m.dz || 0)}</b> ${esc(m.jedn)} ${delta(m, sr30teraz, rt, "")}</td></tr>
    <tr><td>Średnia całej historii</td><td><b>${lb(srednia(z.map(d => wartMetryki(m, d))), m.dz || 0)}</b> ${esc(m.jedn)}</td></tr>
    <tr><td>Rekord</td><td>${(() => { const r = z.reduce((a, d) => a == null || (m.lepiej < 0 ? wartMetryki(m, d) < wartMetryki(m, a) : wartMetryki(m, d) > wartMetryki(m, a)) ? d : a, null); return r ? `<b>${lb(wartMetryki(m, r), m.dz || 0)}</b> ${esc(m.jedn)} <span class="szary">${dataKr(r.dzien)} ${r.dzien.slice(0, 4)}</span>` : "–"; })()}</td></tr></table>
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
  const h1 = v => v == null ? "–" : lb(v, 1) + " h", mn = v => v == null ? "–" : Math.round(v * 60) + " min";
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
  const d = await api("dzis");
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
  if (d.analiza) {
    const a = d.analiza, oc = { dobrze: "dobrze", uwaga: "uwaga", zle: "zle" }[a.dane.ocena] || "";
    h += `<div class="karta"><div class="szary">${esc({ rano: "Analiza poranna", trening: "Po treningu", tydzien: "Tydzień" }[a.rodzaj] || a.rodzaj)} · ${esc(a.utworzono.slice(5, 16).replace("T", " "))}</div>
      <h3>${oc ? `<span class="kropka ${oc}"></span>` : ""}${esc(a.tytul)}</h3><div>${esc(a.dane.krotko)}</div>
      <div class="wiersz" style="margin-top:10px"><a class="btn" href="#analiza/${a.id}">Czytaj</a><a class="btn drugi" href="#czat/${a.id}">Omów</a></div></div>`;
  }
  h += `<div class="kafle">${kafelM("sen", dni, d.dzis)}${kafelM("hrv", dni, d.dzis)}${kafelM("tetno", dni, d.dzis)}${kafelM("bb", dni, d.dzis)}
    ${kafelM("obciazenie", dni, d.dzis, { podpis: esc(status(dz.status || wcz.status)) })}${kafelM("stres", dni, d.dzis)}</div>`;
  h += `<h2>Plan</h2>`;
  const poDniu = {};
  d.plan.forEach(t => (poDniu[t.dzien] = poDniu[t.dzien] || []).push(t));
  if (!d.plan.length) h += `<div class="szary">Brak planu na najbliższe dni.</div>`;
  Object.keys(poDniu).sort().forEach(k => {
    h += `<div class="dzien ${k === d.dzis ? "dzis" : ""}"><div class="data">${k === d.dzis ? "Dziś" : dataPL(k)}</div>${poDniu[k].map(t => trening(t, d.zrobione_dni.includes(k) && t.sport !== "odpoczynek")).join("")}</div>`;
  });
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
async function pokazDane() {
  const wsz = await wszystkieDni();
  const dzis = new Date().toISOString().slice(0, 10);
  const od = zakres ? dzienMinus(dzis, zakres - 1) : "2000-01-01";
  const okres = zakres && zakres <= 180 ? "tydzien" : "miesiac";
  const agr = await api("agregaty?okres=" + okres);
  const ag = agr.filter(x => x.okres >= od.slice(0, x.okres.length));
  const etX = okres === "miesiac" ? x => x.slice(5, 7) + "." + x.slice(2, 4) : x => x.slice(5);
  const dni = wsz.filter(d => d.dzien >= dzienMinus(dzis, 29));
  const sporty = [["rower", "rower"], ["bieg", "bieg"], ["silka", "siłka"], ["inne", "inne"]];
  const suma = k => ag.reduce((s, x) => s + (x.h[k] || 0), 0);
  widok.innerHTML = `<div class="zakladki">${[[30, "30 dni"], [90, "90 dni"], [365, "rok"], [0, "wszystko"]].map(([v, n]) =>
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
    <div class="wiersz" style="margin-top:12px"><a class="btn" href="#czat/${a.id}">💬 Omów z trenerem</a></div></div>
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
      ${teraz ? `<details><summary>szczegóły fazy</summary><div class="szary">Intensywność: ${esc(f.intensywnosc)}<br>Kluczowe: ${(f.sesje_kluczowe || []).map(esc).join("; ")}<br>Siłka ${f.silka_tyg ?? "–"}/tydz., bieg ${f.bieg_tyg ?? "–"}/tydz. · ${esc(f.rytm || "")}${(f.testy || []).length ? "<br>Testy: " + f.testy.map(esc).join(", ") : ""}</div></details>` : ""}</div>`;
  }).join("");
  const u = m.plan_uzasadnienie;
  return `<div class="karta"><div class="kt">Periodyzacja</div><div style="color:var(--tekst2);font-size:14px">${esc(mk.cel_glowny)}</div><div class="szary">${mk.data_docelowa ? "do " + esc(mk.data_docelowa) + " · " : ""}${esc(m.progi.split("\n")[0] || "")}</div>
    <div style="margin-top:8px">${fazy}</div>
    <details><summary>dlaczego tak (zasady, ocena formy)</summary><div class="tresc szary">${esc(mk.ocena_wyjsciowa)}\n\n${esc(mk.uzasadnienie)}\n\n${(mk.zasady_indywidualne || []).map(x => "• " + esc(x)).join("\n")}</div></details>
    ${u ? `<details><summary>uzasadnienie bieżącego planu</summary><div class="tresc szary">${esc(u.tekst)}${(u.uwagi || []).length ? "\n\n⚠️ Kontrola: " + u.uwagi.map(esc).join("; ") : ""}</div></details>` : ""}
    <div class="wiersz" style="margin-top:8px"><a class="btn drugi" href="#wiedza">📚 Źródła trenera</a><button class="drugi" onclick="if(confirm('Ułożyć periodyzację od nowa i przeplanować?'))akcja('makrocykl')">🔁 Przebuduj periodyzację</button></div></div>`;
}

async function pokazPlan() {
  const [d, makro] = await Promise.all([api("plan"), kartaMakro()]);
  const dni = [];
  for (let i = -7; i <= 14; i++) { const x = new Date(d.dzis + "T12:00"); x.setDate(x.getDate() + i); dni.push(x.toISOString().slice(0, 10)); }
  let h = makro + `<div class="karta"><label>Poproś o zmianę (opcjonalnie)</label><textarea id="prosba" rows="2" placeholder="np. w czwartek nie mogę, w weekend dłuższy rower"></textarea>
    <div class="wiersz" style="margin-top:8px"><button onclick="akcja('plan',{prosba:$('#prosba').value})">📅 Przeplanuj</button></div></div>`;
  for (const k of dni) {
    const pl = d.plan.filter(t => t.dzien === k), zr = d.zrobione[k] || [];
    if (!pl.length && !zr.length && k < d.dzis) continue;
    h += `<div class="dzien ${k === d.dzis ? "dzis" : ""}"><div class="data">${k === d.dzis ? "Dziś · " : ""}${dataPL(k)}</div>
      ${pl.map(t => trening(t, zr.some(a => kat(a.typ) === t.sport))).join("")}
      ${zr.map(a => `<div class="trening zrobiony sport-${kat(a.typ)}">✓ ${esc(a.nazwa)} <span class="szary">${a.min} min${a.km ? " · " + a.km + " km" : ""}${a.obc ? " · obc " + a.obc : ""}</span></div>`).join("")}
      ${!pl.length && !zr.length ? `<div class="szary">—</div>` : ""}</div>`;
  }
  widok.innerHTML = h;
}


// ------------------------------------------------------------------ Treningi
let filtr = "";
async function pokazTreningi(dalej = false) {
  const lista = await api(`aktywnosci?limit=40&offset=${dalej ? document.querySelectorAll(".lista-akt .trening").length : 0}${filtr ? "&sport=" + filtr : ""}`);
  const wiersze = lista.map(a => `<div class="trening sport-${kat(a.typ)}" onclick="szczegoly(${a.id}, this)">
    <div><b>${esc(a.nazwa)}</b><div class="szary">${esc(a.start.replace("T", " "))}</div></div>
    <div style="text-align:right" class="szary">${a.min} min${a.km ? "<br>" + a.km + " km" : ""}${a.moc ? "<br>" + a.moc + " W" : ""}${a.tetno ? "<br>♥ " + a.tetno : ""}</div></div>`).join("");
  if (dalej) { $(".lista-akt").insertAdjacentHTML("beforeend", wiersze); return; }
  widok.innerHTML = `<div class="zakladki">${[["", "wszystko"], ["rower", "🚴 rower"], ["bieg", "🏃 bieg"], ["silka", "🏋️ siłka"], ["inne", "inne"]].map(([v, n]) =>
    `<button class="${filtr === v ? "akt" : ""}" onclick="filtr='${v}';pokazTreningi()">${n}</button>`).join("")}</div>
    <div class="lista-akt">${wiersze}</div><button class="drugi" style="width:100%" onclick="pokazTreningi(true)">Więcej</button>`;
}
async function szczegoly(id, el) {
  if (el.nextElementSibling?.classList.contains("szcz")) { el.nextElementSibling.remove(); return; }
  const a = await api("aktywnosc/" + id);
  const pola = [["efekt", "efekt"], ["te_aer", "TE aerob."], ["te_anaer", "TE anaerob."], ["obc", "obciążenie"], ["tetno", "tętno śr."], ["tetno_max", "tętno max"],
    ["moc", "moc śr."], ["moc_np", "NP"], ["tss", "TSS"], ["if_", "IF"], ["kadencja", "kadencja"], ["kmh", "km/h"], ["tempo", "tempo"], ["przewyzszenie", "przewyższenie"], ["kcal", "kcal"]];
  el.insertAdjacentHTML("afterend", `<div class="karta szcz">${pola.filter(([k]) => a[k] != null).map(([k, n]) => `<div class="wiersz" style="justify-content:space-between"><span class="szary">${n}</span><b>${esc(a[k])}</b></div>`).join("")}
    ${a.strefy_min ? `<div class="szary" style="margin-top:6px">Strefy tętna (min): ${a.strefy_min.map((m, i) => `Z${i + 1} ${m}`).join(" · ")}</div>` : ""}
    ${a.cwiczenia ? `<div style="margin-top:6px">${Object.entries(a.cwiczenia).map(([k, v]) => `<div><b>${esc(k)}</b>: <span class="szary">${esc(v)}</span></div>`).join("")}</div>` : ""}
    <a class="btn drugi" style="margin-top:8px;display:inline-block" href="#czat" data-szkic="${esc(`Omówmy trening: ${a.nazwa} (${a.start})`)}" onclick="sessionStorage.szkic=this.dataset.szkic">💬 Omów</a></div>`);
}

// ------------------------------------------------------------------ Czat
async function pokazCzat(analizaId) {
  const msgs = await api("czat");
  widok.innerHTML = `<div class="czat" id="czat">${msgs.map(m => msg(m)).join("") || `<div class="szary">Napisz, do czego trenujesz, kiedy masz czas i co chcesz zmienić. Możesz pytać o dowolne dane z całej historii.</div>`}</div>
    <div style="height:70px"></div>
    <div class="pisz"><textarea id="tekst" placeholder="${analizaId ? "Omów analizę…" : "Napisz do trenera…"}"></textarea><button id="wyslij">➤</button></div>`;
  const t = $("#tekst");
  if (sessionStorage.szkic) { t.value = sessionStorage.szkic; delete sessionStorage.szkic; }
  $("#wyslij").onclick = () => wyslij(analizaId);
  t.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey && !/iPhone|iPad/.test(navigator.userAgent)) { e.preventDefault(); wyslij(analizaId); } });
  window.scrollTo(0, document.body.scrollHeight);
}
const msg = m => `<div class="msg ${m.kto}">${esc(m.tresc)}${m.akcje && m.akcje.length ? `<div class="akcje">${m.akcje.map(esc).join(" · ")}</div>` : ""}</div>`;
async function wyslij(analizaId) {
  const t = $("#tekst"), tresc = t.value.trim();
  if (!tresc) return;
  t.value = ""; $("#wyslij").disabled = true;
  $("#czat").insertAdjacentHTML("beforeend", msg({ kto: "ja", tresc }) + `<div class="msg trener mysli" id="mysli">Trener myśli</div>`);
  window.scrollTo(0, document.body.scrollHeight);
  try {
    const zid = await api("czat", { tresc, analiza_id: analizaId ? +analizaId : null });
    await czekaj(zid, i => { if (i === 25) $("#mysli").textContent = "Trener układa plan i wysyła na zegarek"; });
  } catch (e) { alert("Błąd: " + e.message); }
  pokazCzat(analizaId);
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
    <div class="wiersz" style="margin-top:8px"><button onclick="wlaczPush()">🔔 Włącz powiadomienia</button><button class="drugi" onclick="api('push/test',{}).then(n=>alert('Wysłano do '+n+' urządzeń'))">Test</button></div></div>
    <div class="karta"><h3>🔐 Zapamiętane urządzenia</h3><div id="urz" class="szary">…</div>
      <button class="drugi" style="margin-top:8px" onclick="if(confirm('Wylogować wszystkie inne urządzenia?'))api('urzadzenia',{}).then(ekranUstawien)">Wyloguj inne urządzenia</button></div>
    <div class="karta"><h3>Pamięć trenera</h3><div class="szary">Ustalenia z rozmów (jedno na linię)</div><textarea id="u-pamiec" rows="5">${esc((u.pamiec || []).join("\n"))}</textarea></div>
    <div class="wiersz"><button onclick="zapiszUst()">💾 Zapisz</button><button class="drugi" onclick="akcja('analiza')">📊 Analiza teraz</button><button class="drugi" onclick="akcja('sync')">🔄 Synchronizuj</button></div>`;
  urzadzenia();
}
async function urzadzenia() {
  const l = await api("urzadzenia");
  const el = document.getElementById("urz");
  if (el) el.innerHTML = l.map(u => `• ${esc(/iPhone/.test(u.opis) ? "iPhone" : /iPad/.test(u.opis) ? "iPad" : /Windows/.test(u.opis) ? "PC (Windows)" : /Mac/.test(u.opis) ? "Mac" : u.opis.slice(0, 40))} — ostatnio ${esc((u.ostatnio || "").slice(0, 10))}`).join("<br>") || "brak";
}
async function zapiszUst() {
  const u = { cele: $("#u-cele").value, dostepnosc: $("#u-dostepnosc").value, sprzet: $("#u-sprzet").value, plan_dni: +$("#u-plan_dni").value,
    sporty: [...document.querySelectorAll(".sport:checked")].map(x => x.value), pamiec: $("#u-pamiec").value.split("\n").map(s => s.trim()).filter(Boolean) };
  ["auto_zegarek", "analiza_rano", "push", "linphone"].forEach(k => u[k] = $("#u-" + k).checked);
  await api("ustawienia", u);
  if (confirm("Zapisane. Przeplanować teraz według nowych ustawień?")) { location.hash = "#plan"; setTimeout(() => akcja("plan"), 300); }
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

// ------------------------------------------------------------------ router
async function route() {
  const [t, arg] = (location.hash.slice(1) || "dzis").split("/");
  document.querySelectorAll("nav a").forEach(a => a.classList.toggle("akt", a.dataset.t === t || (t === "analiza" && a.dataset.t === "dzis") || (t === "metryka" && a.dataset.t === "dane")));
  $("#tytul").textContent = { dzis: "Trener", plan: "Plan", dane: "Dane", treningi: "Treningi", czat: "Czat z trenerem", analiza: "Analiza", ustawienia: "Ustawienia", start: "Poznajmy się", wiedza: "Źródła trenera" }[t] || "Trener";
  widok.innerHTML = `<div class="ladowanie">Ładuję…</div>`; WYK.clear(); window.scrollTo(0, 0);
  try {
    await ({ dzis: pokazDzis, plan: pokazPlan, dane: pokazDane, treningi: () => pokazTreningi(), czat: () => pokazCzat(arg), analiza: () => pokazAnalize(arg), ustawienia: ekranUstawien, start: pokazStart, wiedza: pokazWiedze, metryka: () => pokazMetryke(arg) }[t] || pokazDzis)();
  } catch (e) { if (!/nie jest zapamiętane/.test(e.message)) widok.innerHTML = `<div class="karta zle">Błąd: ${esc(e.message)}</div>`; }
}
window.addEventListener("hashchange", route);
$("#btn-ust").onclick = pokazUstawienia;
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
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
  window.scrollTo(0, 0);
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
