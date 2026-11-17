"use strict";
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const api = async (p, opt) => {
  const r = await fetch("/api/" + p, opt && { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(opt) });
  if (!r.ok) throw new Error(r.status + " " + p);
  return r.json();
};
const DNI = ["ndz", "pon", "wt", "śr", "czw", "pt", "sob"];
const SPORT_IKONA = { rower: "🚴", bieg: "🏃", silka: "🏋️", odpoczynek: "😴", inne: "⚡" };
const kat = t => !t ? "inne" : /cycl|bik|ride/.test(t) ? "rower" : /run/.test(t) ? "bieg" : t === "strength_training" ? "silka" : "inne";
const dataPL = d => { const x = new Date(d + "T12:00"); return `${DNI[x.getDay()]} ${x.getDate()}.${String(x.getMonth() + 1).padStart(2, "0")}`; };
const widok = $("#widok");

async function czekaj(zid, co) {
  for (let i = 0; i < 400; i++) {
    await new Promise(r => setTimeout(r, i < 10 ? 1500 : 3000));
    const z = await api("zadanie/" + zid);
    if (z.stan !== "trwa") { if (z.stan === "blad") throw new Error(z.wynik); return z.wynik; }
    if (co) co(i);
  }
  throw new Error("za długo");
}

// ------------------------------------------------------------------ wykresy (SVG)
function linia(punkty, { kolor = "var(--akcent)", pasmo = null, min = null, max = null, jedn = "" } = {}) {
  const p = punkty.filter(x => x.y != null);
  if (p.length < 2) return `<div class="szary">za mało danych</div>`;
  const W = 340, H = 150, L = 30, B = 18;
  const ys = p.map(x => x.y).concat(pasmo ? pasmo.flat().filter(v => v != null) : []);
  const lo = min ?? Math.floor(Math.min(...ys) * 0.95), hi = max ?? Math.ceil(Math.max(...ys) * 1.05);
  const X = i => L + (W - L - 4) * i / (punkty.length - 1), Y = v => 4 + (H - B - 8) * (1 - (v - lo) / ((hi - lo) || 1));
  const idx = new Map(punkty.map((x, i) => [x, i]));
  let d = "";
  p.forEach((x, k) => { d += (k ? "L" : "M") + X(idx.get(x)).toFixed(1) + "," + Y(x.y).toFixed(1); });
  let pas = "";
  if (pasmo) {
    const g = punkty.map((x, i) => [i, pasmo[i]]).filter(([, b]) => b && b[0] != null && b[1] != null);
    if (g.length > 1) pas = `<path d="M${g.map(([i, b]) => X(i) + "," + Y(b[1])).join("L")}L${g.reverse().map(([i, b]) => X(i) + "," + Y(b[0])).join("L")}Z" fill="rgba(62,207,142,.12)"/>`;
  }
  const et = [0, Math.floor(punkty.length / 2), punkty.length - 1].map((i, n) => `<text x="${X(i)}" y="${H - 4}" text-anchor="${["start", "middle", "end"][n]}">${esc(punkty[i].e)}</text>`).join("");
  return `<svg class="wykres" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${pas}
    <text x="0" y="12">${hi}${jedn}</text><text x="0" y="${H - B}">${lo}${jedn}</text>
    <path d="${d}" fill="none" stroke="${kolor}" stroke-width="2" vector-effect="non-scaling-stroke"/>${et}</svg>`;
}
function slupki(dane, serie) {   // dane: [{e, wart:{seria: v}}], serie: [[klucz, kolor]]
  if (!dane.length) return `<div class="szary">brak danych</div>`;
  const W = 340, H = 150, L = 26, B = 18;
  const max = Math.max(1, ...dane.map(d => serie.reduce((s, [k]) => s + (d.wart[k] || 0), 0)));
  const bw = (W - L) / dane.length;
  let r = "";
  dane.forEach((d, i) => {
    let y = H - B;
    serie.forEach(([k, kol]) => {
      const h = (d.wart[k] || 0) / max * (H - B - 6);
      if (h > 0) { y -= h; r += `<rect x="${L + i * bw + 1}" y="${y}" width="${Math.max(1, bw - 2)}" height="${h}" fill="${kol}" rx="1"/>`; }
    });
  });
  const et = [0, Math.floor(dane.length / 2), dane.length - 1].map((i, n) => `<text x="${L + (i + .5) * bw}" y="${H - 4}" text-anchor="${["start", "middle", "end"][n]}">${esc(dane[i].e)}</text>`).join("");
  return `<svg class="wykres" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><text x="0" y="12">${Math.round(max)}</text>${r}${et}</svg>
    <div class="legenda">${serie.map(([k, c]) => `<span><i style="background:${c}"></i>${k}</span>`).join("")}</div>`;
}

// ------------------------------------------------------------------ Dziś
const kafel = (n, w, d = "", kl = "") => `<div class="kafel"><div class="n">${n}</div><div class="w ${kl}">${w ?? "–"}</div><div class="d">${d}</div></div>`;
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
    <b>${SPORT_IKONA[t.sport] || ""} ${esc(t.tytul)}</b>${t.min ? `<span class="znaczek">~${t.min} min</span>` : ""}${st ? `<span class="znaczek">${st}</span>` : ""}${zrobiony ? `<span class="znaczek ok">✓ zrobione</span>` : ""}
    ${t.opis ? `<div class="szary">${esc(t.opis)}</div>` : ""}
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

async function pokazDzis() {
  const d = await api("dzis");
  const dz = d.dni.find(x => x.dzien === d.dzis) || {};
  const wcz = d.dni.find(x => x.dzien < d.dzis && x.sen_h) || {};
  let h = "";
  if (d.ustawienia_puste) h += `<div class="karta"><h3>👋 Zacznijmy</h3><div>Powiedz trenerowi, do czego trenujesz, kiedy masz czas i jaki masz sprzęt — wtedy ułoży plan i wyśle treningi na zegarek.</div>
    <div class="wiersz" style="margin-top:10px"><a class="btn" href="#czat">💬 Napisz w czacie</a><button class="drugi" onclick="pokazUstawienia()">⚙️ Ustawienia</button></div></div>`;
  if (d.historia && d.historia !== "gotowe") h += `<div class="karta szary">⏳ Pobieram całą historię z Garmina… (doszedłem do ${esc(d.historia)})</div>`;
  if (d.analiza) {
    const a = d.analiza, oc = { dobrze: "ok", uwaga: "uwaga", zle: "zle" }[a.dane.ocena] || "";
    h += `<div class="karta"><div class="szary">${esc({ rano: "Analiza poranna", trening: "Po treningu", tydzien: "Tydzień" }[a.rodzaj] || a.rodzaj)} · ${esc(a.utworzono.slice(5, 16).replace("T", " "))}</div>
      <h3 class="${oc}">${esc(a.tytul)}</h3><div>${esc(a.dane.krotko)}</div>
      <div class="wiersz" style="margin-top:10px"><a class="btn" href="#analiza/${a.id}">Czytaj</a><a class="btn drugi" href="#czat/${a.id}">💬 Omów</a></div></div>`;
  }
  const s = dz.sen_h ? dz : {};
  const hrvKl = dz.hrv && dz.hrv_norma ? (dz.hrv < dz.hrv_norma[0] ? "zle" : dz.hrv > dz.hrv_norma[1] ? "uwaga" : "ok") : "";
  const got = dz.gotowosc ?? wcz.gotowosc;
  h += `<div class="kafle">
    ${kafel("Sen", s.sen_h ? s.sen_h.toFixed(1) + " h" : null, s.sen_wynik ? `wynik ${s.sen_wynik} · REM ${Math.round((s.sen_rem_h || 0) * 60)}′` : "", s.sen_wynik >= 80 ? "ok" : s.sen_wynik < 60 ? "zle" : "")}
    ${kafel("HRV", dz.hrv, dz.hrv_norma ? `norma ${dz.hrv_norma[0]}–${dz.hrv_norma[1]}` : "", hrvKl)}
    ${kafel("Tętno spocz.", dz.tetno_spocz ?? wcz.tetno_spocz, "bpm")}
    ${kafel("Body Battery", dz.bb_rano ?? dz.bb_max, dz.bb_rano ? "rano" : "max")}
    ${kafel("Gotowość", got, esc(dz.gotowosc_poziom || ""), got >= 70 ? "ok" : got < 40 ? "zle" : "uwaga")}
    ${kafel("Obciążenie", dz.obc_ostre ?? wcz.obc_ostre, esc(status(dz.status || wcz.status)))}</div>`;
  h += `<h2>Plan</h2>`;
  const poDniu = {};
  d.plan.forEach(t => (poDniu[t.dzien] = poDniu[t.dzien] || []).push(t));
  if (!d.plan.length) h += `<div class="szary">Brak planu na najbliższe dni.</div>`;
  Object.keys(poDniu).sort().forEach(k => {
    h += `<div class="dzien ${k === d.dzis ? "dzis" : ""}"><div class="data">${k === d.dzis ? "Dziś" : dataPL(k)}</div>${poDniu[k].map(t => trening(t, d.zrobione_dni.includes(k) && t.sport !== "odpoczynek")).join("")}</div>`;
  });
  const dni = d.dni.slice(-30);
  h += `<h2>30 dni</h2><div class="karta"><div class="szary">HRV (pasmo = norma)</div>${linia(dni.map(x => ({ y: x.hrv, e: dataPL(x.dzien) })), { kolor: "var(--ok)", pasmo: dni.map(x => x.hrv_norma) })}</div>
    <div class="karta"><div class="szary">Sen (h)</div>${linia(dni.map(x => ({ y: x.sen_h, e: dataPL(x.dzien) })), { kolor: "#9b8cff" })}</div>
    <div class="karta"><div class="szary">Tętno spoczynkowe</div>${linia(dni.map(x => ({ y: x.tetno_spocz, e: dataPL(x.dzien) })), { kolor: "var(--zle)" })}</div>`;
  h += `<div class="szary" style="text-align:center">Ostatnia synchronizacja: ${esc((d.ostatni_sync || "–").replace("T", " ").slice(0, 16))}
    · <a href="#" onclick="akcja('sync');return false" style="color:var(--akcent)">odśwież</a></div>`;
  widok.innerHTML = h;
}

async function akcja(rodzaj, dod = {}) {
  const info = document.createElement("div");
  info.className = "karta szary mysli";
  info.textContent = { sync: "Synchronizuję z Garminem", plan: "Trener układa plan", analiza: "Trener analizuje" }[rodzaj] || "Pracuję";
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
async function pokazPlan() {
  const d = await api("plan");
  const dni = [];
  for (let i = -7; i <= 14; i++) { const x = new Date(d.dzis + "T12:00"); x.setDate(x.getDate() + i); dni.push(x.toISOString().slice(0, 10)); }
  let h = `<div class="karta"><label>Poproś o zmianę (opcjonalnie)</label><textarea id="prosba" rows="2" placeholder="np. w czwartek nie mogę, w weekend dłuższy rower"></textarea>
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

// ------------------------------------------------------------------ Dane
let zakres = 90;
async function pokazDane() {
  const od = zakres ? new Date(Date.now() - zakres * 864e5).toISOString().slice(0, 10) : "2000-01-01";
  const [dni, agr] = await Promise.all([api("dni?od=" + od), api("agregaty?okres=" + (zakres && zakres <= 180 ? "tydzien" : "miesiac"))]);
  const ag = agr.filter(x => x.okres >= od.slice(0, x.okres.length));
  const P = (k, kol, o = {}) => linia(dni.map(x => ({ y: x[k], e: dataPL(x.dzien) })), { kolor: kol, ...o });
  widok.innerHTML = `<div class="zakladki">${[[30, "30 dni"], [90, "90 dni"], [365, "rok"], [0, "cała historia"]].map(([v, n]) =>
    `<button class="${zakres === v ? "akt" : ""}" onclick="zakres=${v};pokazDane()">${n}</button>`).join("")}</div>
    <div class="karta"><div class="szary">Godziny treningu (${zakres && zakres <= 180 ? "tygodnie" : "miesiące"})</div>${slupki(ag.map(x => ({ e: x.okres.slice(2), wart: x.h })), [["rower", "var(--rower)"], ["bieg", "var(--bieg)"], ["silka", "var(--silka)"], ["inne", "var(--inne)"]])}</div>
    <div class="karta"><div class="szary">Obciążenie treningowe</div>${slupki(ag.map(x => ({ e: x.okres.slice(2), wart: { obciążenie: x.obc } })), [["obciążenie", "var(--uwaga)"]])}</div>
    <div class="karta"><div class="szary">HRV</div>${P("hrv", "var(--ok)", { pasmo: dni.map(x => x.hrv_norma) })}</div>
    <div class="karta"><div class="szary">Sen (h)</div>${P("sen_h", "#9b8cff")}</div>
    <div class="karta"><div class="szary">Wynik snu</div>${P("sen_wynik", "#9b8cff")}</div>
    <div class="karta"><div class="szary">Tętno spoczynkowe</div>${P("tetno_spocz", "var(--zle)")}</div>
    <div class="karta"><div class="szary">Body Battery rano</div>${P("bb_rano", "var(--akcent)")}</div>
    <div class="karta"><div class="szary">Gotowość treningowa</div>${P("gotowosc", "var(--uwaga)")}</div>
    <div class="karta"><div class="szary">Obciążenie ostre / przewlekłe</div>${P("obc_ostre", "var(--uwaga)")}${P("obc_przewlekle", "var(--szary)")}</div>
    <div class="karta"><div class="szary">VO₂max rower</div>${P("vo2_rower", "var(--rower)")}</div>
    <div class="karta"><div class="szary">Stres dzienny</div>${P("stres", "var(--szary)")}</div>`;
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
  widok.innerHTML = `<div class="karta"><h3>Cele i warunki</h3>
    <label>Do czego trenujesz (cele, zawody, terminy)</label><textarea id="u-cele" rows="3">${esc(u.cele)}</textarea>
    <label>Kiedy możesz trenować</label><textarea id="u-dostepnosc" rows="2">${esc(u.dostepnosc)}</textarea>
    <label>Sprzęt (rower, trenażer, siłownia…)</label><textarea id="u-sprzet" rows="2">${esc(u.sprzet)}</textarea>
    <label>Sporty w planie</label><div class="wiersz">${["rower", "bieg", "silka"].map(s => `<label style="margin:0"><input type="checkbox" class="sport" value="${s}" ${u.sporty.includes(s) ? "checked" : ""}> ${SPORT_IKONA[s]} ${{ rower: "rower", bieg: "bieg", silka: "siłka" }[s]}</label>`).join("")}</div>
    <label>Planuj na ile dni do przodu</label><input type="number" id="u-plan_dni" min="3" max="14" value="${u.plan_dni}"></div>
    <div class="karta"><h3>Automatyka</h3>${pr("auto_zegarek", "Treningi same idą na zegarek")}${pr("analiza_rano", "Analiza poranna po śnie")}${pr("push", "Powiadomienia push")}${pr("linphone", "Kopia na Linphone")}
    <div class="wiersz" style="margin-top:10px"><span class="szary">Push: ${pushStan}</span></div>
    <div class="wiersz" style="margin-top:8px"><button onclick="wlaczPush()">🔔 Włącz powiadomienia</button><button class="drugi" onclick="api('push/test',{}).then(n=>alert('Wysłano do '+n+' urządzeń'))">Test</button></div></div>
    <div class="karta"><h3>Pamięć trenera</h3><div class="szary">Ustalenia z rozmów (jedno na linię)</div><textarea id="u-pamiec" rows="5">${esc((u.pamiec || []).join("\n"))}</textarea></div>
    <div class="wiersz"><button onclick="zapiszUst()">💾 Zapisz</button><button class="drugi" onclick="akcja('analiza')">📊 Analiza teraz</button><button class="drugi" onclick="akcja('sync')">🔄 Synchronizuj</button></div>`;
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
  document.querySelectorAll("nav a").forEach(a => a.classList.toggle("akt", a.dataset.t === t || (t === "analiza" && a.dataset.t === "dzis")));
  $("#tytul").textContent = { dzis: "Trener", plan: "Plan", dane: "Dane", treningi: "Treningi", czat: "Czat z trenerem", analiza: "Analiza", ustawienia: "Ustawienia" }[t] || "Trener";
  widok.innerHTML = `<div class="ladowanie">Ładuję…</div>`;
  try {
    await ({ dzis: pokazDzis, plan: pokazPlan, dane: pokazDane, treningi: () => pokazTreningi(), czat: () => pokazCzat(arg), analiza: () => pokazAnalize(arg), ustawienia: ekranUstawien }[t] || pokazDzis)();
  } catch (e) { widok.innerHTML = `<div class="karta zle">Błąd: ${esc(e.message)}</div>`; }
}
window.addEventListener("hashchange", route);
$("#btn-ust").onclick = pokazUstawienia;
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
route();
