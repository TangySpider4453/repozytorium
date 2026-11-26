"use strict";
const $ = s => document.querySelector(s);
const MIESIACE = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia", "września",
  "października", "listopada", "grudnia"];
const ZAMEK = '<svg class="kafel-zamek" viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="11" width="14" height="10" rx="2.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3" fill="none" stroke="currentColor" stroke-width="2"/></svg>';
let S = null;                 // stan z /api/stan
const parametry = new URLSearchParams(location.search);
const symulacja = parametry.get("dzien") ? "?dzien=" + encodeURIComponent(parametry.get("dzien")) : "";

const esc = t => String(t ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const odmiana = (n, a, b, c) => n === 1 ? a : (n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? b : c);
const dataPl = iso => { const d = new Date(iso + "T12:00:00"); return `${d.getDate()} ${MIESIACE[d.getMonth()]}`; };
const standalone = () => window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
const iOS = () => /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);

// ---------------------------------------------------------------- dane
async function wczytaj() {
  const r = await fetch("/api/stan" + symulacja, { cache: "no-store" });
  if (r.status === 401) { $("#zamek").classList.remove("ukryte"); $("#aplikacja").classList.add("ukryte"); return; }
  S = await r.json();
  $("#zamek").classList.add("ukryte");
  $("#aplikacja").classList.remove("ukryte");
  rysujStart();
  rysujAdwent();
  plakietka(S.adwent.nieotwarte);
}

function plakietka(n) {
  if (!navigator.setAppBadge) return;
  (n > 0 ? navigator.setAppBadge(n) : navigator.clearAppBadge()).catch(() => {});
}

// ---------------------------------------------------------------- ekran główny
function rysujStart() {
  document.title = S.tytul || "Dla Ciebie";
  const h = new Date().getHours();
  const pora = h < 5 ? "Dobranoc" : h < 12 ? "Dzień dobry" : h < 18 ? "Cześć" : "Dobry wieczór";
  $("#powitanie-etykieta").textContent = S.tytul || "Dla Ciebie";
  $("#powitanie").textContent = S.imie ? `${pora}, ${S.imie}` : pora;
  const a = S.adwent, dzis = a.kafelki.find(k => k.status === "dzis");
  const przed = a.kafelki.every(k => k.status === "wkrotce");
  let opis;
  if (przed) {
    const dni = Math.min(...a.kafelki.map(k => k.za_dni));
    opis = `Pierwsze okienko za ${dni} ${odmiana(dni, "dzień", "dni", "dni")}.`;
  } else if (dzis && !dzis.otwarte) opis = `Dzisiejsze okienko (nr ${dzis.nr}) czeka na Ciebie ✨`;
  else if (dzis) opis = `Dzisiejsze okienko otwarte. Jutro kolejne!`;
  else opis = "Wszystkie okienka już się otworzyły 🎄";
  $("#karta-adwent-opis").textContent = opis;
  $("#karta-adwent-stan").textContent = `${a.otwartych} / 24 otwartych`;
  $("#karta-adwent-pasek").style.width = `${a.otwartych / 24 * 100}%`;
  rysujInfo();
}

function rysujInfo() {
  const el = $("#karty-info");
  el.innerHTML = "";
  if (S.symulacja) el.insertAdjacentHTML("beforeend",
    `<div class="info"><div class="info-ikona">👀</div><div class="info-tekst"><b>Podgląd admina</b> jakby był ${dataPl(S.dzis)}.</div></div>`);
  if (iOS() && !standalone()) {
    el.insertAdjacentHTML("beforeend", `<div class="info"><div class="info-ikona">📲</div><div class="info-tekst">
      <b>Dodaj mnie do ekranu początkowego</b>: stuknij <b>Udostępnij</b> (kwadrat ze strzałką) i wybierz
      <b>Do ekranu początkowego</b>. Wtedy dostaniesz powiadomienie, gdy otworzy się nowe okienko.</div></div>`);
    return;
  }
  if (!("Notification" in window) || !("serviceWorker" in navigator) || !("PushManager" in window)) return;
  if (Notification.permission === "granted") { zapiszPush(false); return; }
  if (Notification.permission === "denied") return;
  el.insertAdjacentHTML("beforeend", `<div class="info"><div class="info-ikona">🔔</div><div class="info-tekst">
    <b>Włącz powiadomienia</b>, żeby wiedzieć, kiedy otwiera się nowe okienko.</div>
    <button class="przycisk" id="wlacz-push" type="button">Włącz</button></div>`);
  $("#wlacz-push").onclick = () => zapiszPush(true);
}

async function zapiszPush(pytaj) {
  try {
    if (pytaj && (await Notification.requestPermission()) !== "granted") return rysujInfo();
    const reg = await navigator.serviceWorker.ready;
    let sub = await reg.pushManager.getSubscription();
    if (!sub) {
      const k = S.vapid.replace(/-/g, "+").replace(/_/g, "/");
      const klucz = Uint8Array.from(atob(k + "=".repeat((4 - k.length % 4) % 4)), c => c.charCodeAt(0));
      sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: klucz });
    }
    await fetch("/api/push", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(sub) });
    if (pytaj) rysujInfo();
  } catch (e) { console.warn("push", e); }
}

// ---------------------------------------------------------------- kalendarz
function kafel(k, i) {
  const opoz = `style="animation-delay:${Math.min(i, 24) * 25}ms"`;
  if (k.status === "dzis") {
    const nowy = !k.otwarte;
    return `<button class="kafel kafel-dzis ${nowy ? "nowy" : ""}" data-nr="${k.nr}" ${opoz} type="button">
      <span class="kafel-plakietka">${nowy ? "DZIŚ · OTWÓRZ" : "DZIŚ"}</span>
      <span class="kafel-emoji">${k.otwarte ? esc(k.emoji) : "🎁"}</span>
      <span class="kafel-nr">${k.nr}</span>
      <span class="kafel-dol">${k.otwarte ? `<b>${esc(k.tytul)}</b>Stuknij, żeby zobaczyć jeszcze raz` : `<b>Twoje dzisiejsze okienko</b>${dataPl(k.data)}`}</span>
    </button>`;
  }
  if (k.status === "wkrotce") {
    const za = k.za_dni === 1 ? "jutro" : `za ${k.za_dni} ${odmiana(k.za_dni, "dzień", "dni", "dni")}`;
    return `<button class="kafel kafel-wkrotce" data-nr="${k.nr}" data-wkrotce ${opoz} type="button" aria-label="Okienko ${k.nr}, ${za}">
      ${ZAMEK}<span class="kafel-nr">${k.nr}</span><span class="kafel-dol">${za}</span></button>`;
  }
  return `<button class="kafel kafel-minione ${k.otwarte ? "" : "nieotwarte"}" data-nr="${k.nr}" ${opoz} type="button">
    <span class="kafel-emoji">${k.otwarte ? esc(k.emoji) : "🎁"}</span><span class="kafel-nr">${k.nr}</span>
    <span class="kafel-dol">${k.otwarte ? esc(k.tytul) : "nieotwarte!"}</span></button>`;
}

function rysujAdwent() {
  const a = S.adwent;
  $("#rok").textContent = a.rok;
  const grupy = [["dzis", "Dzisiaj", ""], ["wkrotce", "Wkrótce", "otwierają się po kolei"], ["minione", "Minione", ""]];
  let i = 0;
  $("#sekcje").innerHTML = grupy.map(([st, nazwa, opis]) => {
    const lista = a.kafelki.filter(k => k.status === st);
    if (!lista.length) return "";
    const ile = st === "minione" ? `<small>${lista.filter(k => k.otwarte).length} z ${lista.length} otwartych</small>` : opis ? `<small>${opis}</small>` : "";
    return `<section class="sekcja"><h2 class="sekcja-tytul">${nazwa}${ile}</h2>
      <div class="siatka">${lista.map(k => kafel(k, i++)).join("")}</div></section>`;
  }).join("");
  const przed = a.kafelki.every(k => k.status === "wkrotce");
  $("#odliczanie").classList.toggle("ukryte", !przed);
  if (przed) odliczaj();
}

let licznik = null;
function odliczaj() {
  clearInterval(licznik);
  const cel = new Date(S.adwent.start).getTime();
  const krok = () => {
    let s = Math.max(0, Math.floor((cel - Date.now()) / 1000));
    if (s === 0) { clearInterval(licznik); return wczytaj(); }
    const d = Math.floor(s / 86400); s %= 86400;
    const g = Math.floor(s / 3600); s %= 3600;
    const m = Math.floor(s / 60); s %= 60;
    $("#odliczanie-liczby").innerHTML = [[d, odmiana(d, "dzień", "dni", "dni")], [g, "godz."], [m, "min"], [s, "sek"]]
      .map(([n, j]) => `<div><b>${String(n).padStart(2, "0")}</b><span>${j}</span></div>`).join("");
  };
  krok();
  licznik = setInterval(krok, 1000);
}

$("#sekcje").addEventListener("click", e => {
  const b = e.target.closest(".kafel");
  if (!b) return;
  if (b.hasAttribute("data-wkrotce") && !S.admin) {
    b.animate([{ transform: "rotate(0)" }, { transform: "rotate(-4deg)" }, { transform: "rotate(4deg)" }, { transform: "rotate(0)" }],
      { duration: 380, easing: "ease-in-out" });
    navigator.vibrate?.(20);
    return;
  }
  otworz(+b.dataset.nr);
});

async function otworz(nr) {
  const k = S.adwent.kafelki.find(x => x.nr === nr);
  const r = await fetch(`/api/dzien/${nr}${symulacja}`, { cache: "no-store" });
  if (!r.ok) return;
  const d = await r.json();
  $("#okno-data").textContent = `Okienko ${nr} · ${dataPl(k.data)}`;
  $("#okno-emoji").textContent = d.emoji || "🎁";
  $("#okno-tytul").textContent = d.tytul || "";
  $("#okno-tekst").textContent = d.tekst || "";
  const plik = $("#okno-plik");
  plik.innerHTML = "";
  if (d.plik) {
    const u = "/pliki/" + encodeURIComponent(d.plik);
    if (/\.(mp4|mov)$/i.test(d.plik)) plik.innerHTML = `<video src="${u}" controls playsinline></video>`;
    else if (/\.(mp3|m4a)$/i.test(d.plik)) plik.innerHTML = `<audio src="${u}" controls></audio>`;
    else plik.innerHTML = `<img src="${u}" alt="">`;
  }
  const l = $("#okno-link");
  l.classList.toggle("ukryte", !d.link);
  if (d.link) { l.href = d.link; l.textContent = d.link_tekst || "Otwórz"; }
  $("#okno").classList.remove("ukryte");
  document.body.style.overflow = "hidden";
  if (!k.otwarte) { konfetti(); k.otwarte = true; S.adwent.otwartych++; }
  S.adwent.nieotwarte = d.nieotwarte;
  plakietka(d.nieotwarte);
}

function zamknij() {
  $("#okno").classList.add("ukryte");
  document.body.style.overflow = "";
  $("#okno-plik").querySelectorAll("video,audio").forEach(m => m.pause());
  rysujStart();
  rysujAdwent();
}
$("#okno").addEventListener("click", e => { if (e.target.hasAttribute("data-zamknij")) zamknij(); });
document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("#okno").classList.contains("ukryte")) zamknij(); });

// ---------------------------------------------------------------- nawigacja
function pokaz() {
  const adwent = location.hash === "#adwent";
  $("#widok-start").classList.toggle("ukryte", adwent);
  $("#widok-adwent").classList.toggle("ukryte", !adwent);
  window.scrollTo(0, 0);
}
$("#karta-adwent").onclick = () => { location.hash = "adwent"; };
$("#wstecz").onclick = () => { if (history.length > 1 && document.referrer !== "") history.back(); else location.hash = ""; };
window.addEventListener("hashchange", pokaz);

// ---------------------------------------------------------------- śnieg i konfetti
function snieg() {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const c = $("#snieg"), x = c.getContext("2d");
  let W, H, p;
  const rozmiar = () => {
    const dpr = Math.min(devicePixelRatio || 1, 2);
    W = innerWidth; H = innerHeight; c.width = W * dpr; c.height = H * dpr; x.setTransform(dpr, 0, 0, dpr, 0, 0);
    p = Array.from({ length: Math.round(Math.min(70, W / 12)) }, () => ({
      x: Math.random() * W, y: Math.random() * H, r: Math.random() * 1.8 + .6, v: Math.random() * .4 + .2, f: Math.random() * 6.28 }));
  };
  rozmiar(); addEventListener("resize", rozmiar);
  const klatka = () => {
    x.clearRect(0, 0, W, H);
    x.fillStyle = "rgba(255,250,240,.8)";
    for (const s of p) {
      s.y += s.v; s.f += .01; s.x += Math.sin(s.f) * .3;
      if (s.y > H + 4) { s.y = -4; s.x = Math.random() * W; }
      x.beginPath(); x.arc(s.x, s.y, s.r, 0, 6.28); x.fill();
    }
    if (!document.hidden) requestAnimationFrame(klatka); else document.addEventListener("visibilitychange", () => requestAnimationFrame(klatka), { once: true });
  };
  klatka();
}

function konfetti() {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const c = $("#konfetti"), x = c.getContext("2d");
  const dpr = Math.min(devicePixelRatio || 1, 2), W = innerWidth, H = innerHeight;
  c.width = W * dpr; c.height = H * dpr; x.setTransform(dpr, 0, 0, dpr, 0, 0);
  const kolory = ["#e9c47d", "#f7efe4", "#c43c62", "#f3d595", "#8fb7a5"];
  const p = Array.from({ length: 120 }, () => ({
    x: W / 2, y: H * .45, vx: (Math.random() - .5) * 14, vy: -Math.random() * 14 - 4,
    r: Math.random() * 6.28, vr: (Math.random() - .5) * .3, w: Math.random() * 6 + 4, k: kolory[Math.random() * 5 | 0] }));
  const t0 = performance.now();
  const klatka = t => {
    x.clearRect(0, 0, W, H);
    for (const q of p) {
      q.vy += .35; q.vx *= .99; q.x += q.vx; q.y += q.vy; q.r += q.vr;
      x.save(); x.translate(q.x, q.y); x.rotate(q.r); x.fillStyle = q.k; x.fillRect(-q.w / 2, -q.w / 4, q.w, q.w / 2); x.restore();
    }
    if (t - t0 < 2600) requestAnimationFrame(klatka); else x.clearRect(0, 0, W, H);
  };
  requestAnimationFrame(klatka);
}

// ---------------------------------------------------------------- start
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
document.addEventListener("visibilitychange", () => { if (!document.hidden) wczytaj(); });
setInterval(() => { if (!document.hidden) wczytaj(); }, 5 * 60 * 1000);   // o północy nowe okienko pojawi się samo
pokaz();
snieg();
wczytaj();
