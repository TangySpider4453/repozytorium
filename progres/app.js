/* Progres sylwetki: pomiary z wagi, zdjęcia z typem (przód / bok / biceps / tył), wykresy i film z postępu.
   Dane: /api/progres (Raspberry Pi). Rozpoznawanie sylwetki: MediaPipe Pose (pliki w ./mp/, działa w przeglądarce).
   Wyrównanie: z barków i bioder liczymy środek tułowia (cx, cy) i jego długość (s, ułamek wysokości zdjęcia);
   w filmie każda klatka jest skalowana i przesuwana tak, żeby tułów był zawsze w tym samym miejscu i tej samej wielkości. */

const TYPY = [["przod", "Przód"], ["bok", "Bok"], ["biceps", "Przód + biceps"], ["tyl", "Tył"], ["tylbiceps", "Tył + biceps"], ["inne", "Inne"]];
const BICEPS = ["biceps", "tylbiceps"];   // rodzaje, w których można dopasować „same ręce”
const NAZWA = Object.fromEntries(TYPY);
const API = "/api/progres";
const $ = id => document.getElementById(id);
const pad = n => String(n).padStart(2, "0");
const iso = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const dzis = () => iso(new Date());
const MIES = ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"];
const DNI = ["niedziela", "poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota"];
const pd = s => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
const krotko = s => { const d = pd(s); return `${d.getDate()} ${MIES[d.getMonth()]} ${d.getFullYear()}`; };
const num = v => { v = String(v || "").trim().replace(",", "."); if(!v) return null; const n = Number(v); return Number.isFinite(n) ? n : NaN; };
const pl = (x, d = 1) => x == null ? "–" : x.toFixed(d).replace(".", ",");
const el = (t, a = {}, ...k) => { const e = document.createElement(t); for(const [n, v] of Object.entries(a)){ if(v == null) continue; if(n === "text") e.textContent = v; else if(n === "class") e.className = v; else if(n.startsWith("on")) e[n] = v; else e.setAttribute(n, v); } e.append(...k.filter(x => x != null)); return e; };
const plik = (z, m) => `${API}/plik/${z.id}${m ? "_m" : ""}.jpg`;

let DANE = {wpisy:{}, zdjecia:[], ustawienia:{}};
async function wczytaj(){ const r = await fetch(API, {cache:"no-store"}); if(!r.ok) throw new Error(r.status); DANE = await r.json(); }
async function post(url, body){ const r = await fetch(url, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)}); if(!r.ok) throw new Error("serwer odpowiedział " + r.status); return r.json(); }

/* ---------- zakładki ---------- */
const tabs = [...document.querySelectorAll("nav.tabs button")];
function pokaz(id){
  tabs.forEach(b => b.setAttribute("aria-selected", b.dataset.tab === id));
  document.querySelectorAll("section.tab").forEach(s => s.hidden = s.id !== id);
  try{ localStorage.setItem("progres:zakladka", id); }catch(e){}
  if(id === "historia") rysujHistorie();
  if(id === "film") filmUstaw();
}
tabs.forEach(b => b.onclick = () => pokaz(b.dataset.tab));

/* ---------- rozpoznawanie sylwetki (MediaPipe) ---------- */
let detektor = null;
async function wezDetektor(){
  if(detektor) return detektor;
  detektor = (async () => {
    const {FilesetResolver, PoseLandmarker} = await import("./mp/vision_bundle.mjs");
    const pliki = await FilesetResolver.forVisionTasks(new URL("./mp/wasm", location.href).href);
    const opcje = d => ({baseOptions:{modelAssetPath:new URL("./mp/pose_landmarker_full.task", location.href).href, delegate:d}, runningMode:"IMAGE", numPoses:1});
    try{ return await PoseLandmarker.createFromOptions(pliki, opcje("GPU")); }
    catch(e){ return await PoseLandmarker.createFromOptions(pliki, opcje("CPU")); }
  })();
  return detektor;
}
/* barki 11, 12; biodra 23, 24 -> środek tułowia i długość tułowia (jako ułamek wysokości zdjęcia) */
async function wykryj(canvas){
  try{
    const det = await wezDetektor();
    const res = det.detect(canvas);
    const L = res.landmarks && res.landmarks[0];
    if(!L) return null;
    const W = canvas.width, H = canvas.height, p = i => ({x:L[i].x * W, y:L[i].y * H, v:L[i].visibility ?? 1});
    const [ls, rs, lh, rh] = [p(11), p(12), p(23), p(24)];
    const sh = {x:(ls.x + rs.x) / 2, y:(ls.y + rs.y) / 2}, hp = {x:(lh.x + rh.x) / 2, y:(lh.y + rh.y) / 2};
    const tul = Math.hypot(sh.x - hp.x, sh.y - hp.y);
    if(!(tul > H * 0.03)) return null;
    const ok = Math.min(ls.v, rs.v, lh.v, rh.v) > 0.3;
    const lm = L.map(q => [+q.x.toFixed(4), +q.y.toFixed(4), +(q.visibility ?? 1).toFixed(2)]);   // wszystkie 33 punkty
    return {pose:{cx:+((sh.x + hp.x) / 2 / W).toFixed(4), cy:+((sh.y + hp.y) / 2 / H).toFixed(4), s:+(tul / H).toFixed(4), ok}, lm};
  }catch(e){ console.warn("rozpoznawanie sylwetki:", e); return null; }
}

/* ---------- data zrobienia zdjęcia z EXIF (DateTimeOriginal) ---------- */
async function dataExif(file){
  try{
    const b = new DataView(await file.slice(0, 256 * 1024).arrayBuffer());
    if(b.getUint16(0) !== 0xFFD8) return null;
    let o = 2;
    while(o < b.byteLength - 4){
      const mk = b.getUint16(o), len = b.getUint16(o + 2);
      if(mk === 0xFFE1 && b.getUint32(o + 4) === 0x45786966){
        const t = o + 10, le = b.getUint16(t) === 0x4949;
        const u16 = x => b.getUint16(t + x, le), u32 = x => b.getUint32(t + x, le);
        const tag = (ifd, want) => { const n = u16(ifd); for(let i = 0; i < n; i++){ const e = ifd + 2 + i * 12; if(u16(e) === want) return e; } return -1; };
        const e1 = tag(u32(4), 0x8769); if(e1 < 0) return null;
        const e2 = tag(u32(e1 + 8), 0x9003); if(e2 < 0) return null;
        const off = u32(e2 + 8); let s = ""; for(let i = 0; i < 10; i++) s += String.fromCharCode(b.getUint8(t + off + i));
        const m = s.match(/^(\d{4}):(\d{2}):(\d{2})$/); return m ? `${m[1]}-${m[2]}-${m[3]}` : null;
      }
      if((mk & 0xFF00) !== 0xFF00) return null;
      o += 2 + len;
    }
  }catch(e){}
  return null;
}

/* ---------- zmniejszanie zdjęcia (orientacja EXIF jest stosowana przez przeglądarkę) ---------- */
async function wczytajObraz(file){
  const url = URL.createObjectURL(file);
  try{ const img = new Image(); img.src = url; await img.decode(); return img; } finally { setTimeout(() => URL.revokeObjectURL(url), 1000); }
}
function naCanvas(img, maks){
  const k = Math.min(1, maks / Math.max(img.naturalWidth, img.naturalHeight));
  const c = document.createElement("canvas"); c.width = Math.round(img.naturalWidth * k); c.height = Math.round(img.naturalHeight * k);
  c.getContext("2d").drawImage(img, 0, 0, c.width, c.height); return c;
}
const doBloba = (c, q) => new Promise(res => c.toBlob(res, "image/jpeg", q));

/* ---------- DODAJ ---------- */
const NOWE = [];
function ustawFormularz(data, zachowaj){
  $("fData").value = data;
  const w = DANE.wpisy[data];
  // „zachowaj”: przy zmianie daty z EXIF nie kasuj wpisanych liczb, tylko uzupełnij puste pola zapisanymi wartościami
  // pole wypełnione automatycznie (data-auto) można podmienić; to, co wpisałeś ręcznie, zostaje
  const wstaw = (id, v) => { const e = $(id); if(!zachowaj || !e.value.trim() || e.dataset.auto) { e.value = v; if(v) e.dataset.auto = "1"; else delete e.dataset.auto; } };
  wstaw("fMasa", w && w.masa != null ? pl(w.masa) : "");
  wstaw("fFat", w && w.fat != null ? pl(w.fat) : "");
  wstaw("fMuscle", w && w.muscle != null ? pl(w.muscle) : "");
  wstaw("fNotatka", w && w.notatka || "");
  const ile = DANE.zdjecia.filter(z => z.data === data).length;
  $("fIstnieje").hidden = !(w || ile);
  $("fIstnieje").textContent = `Dla ${krotko(data)} są już zapisane ${w ? "wyniki z wagi" : ""}${w && ile ? " i " : ""}${ile ? ile + " " + (ile === 1 ? "zdjęcie" : ile % 10 >= 2 && ile % 10 <= 4 && (ile % 100 < 12 || ile % 100 > 14) ? "zdjęcia" : "zdjęć") : ""}. Zapis podmieni wyniki, a zdjęcia dopisze.`;
  NOWE.forEach(n => { if(!n.wlasnaData) n.data = data; rysujNowe(n); });
}
/* „Użyj daty ze zdjęcia”: ta data trafia do pomiaru i do wszystkich wybranych zdjęć */
function uzyjDaty(d){
  NOWE.forEach(n => n.wlasnaData = false);
  ustawFormularz(d, true);
}
$("fData").onchange = () => ustawFormularz($("fData").value || dzis());
["fMasa", "fFat", "fMuscle", "fNotatka"].forEach(id => $(id).addEventListener("input", () => delete $(id).dataset.auto));

$("fPliki").onchange = async e => {
  const files = [...e.target.files]; e.target.value = "";
  for(const file of files){
    const n = {id:Math.random().toString(36).slice(2), typ:"przod", data:$("fData").value || dzis(), wlasnaData:false, status:"wczytuję…", pose:undefined};
    NOWE.push(n); n.el = el("div", {class:"it"}); $("nowe").append(n.el); rysujNowe(n);
    try{
      n.exif = await dataExif(file);
      if(!n.exif && file.lastModified){ const d = iso(new Date(file.lastModified)); if(d !== dzis()) n.exif = d; }
      const img = await wczytajObraz(file);
      n.duzy = naCanvas(img, 1800); n.maly = naCanvas(img, 480);
      n.status = "rozpoznaję sylwetkę…"; rysujNowe(n);
      const wyk = await wykryj(n.duzy); n.pose = wyk ? wyk.pose : null; n.lm = wyk ? wyk.lm : [];
      n.status = n.pose ? (n.pose.ok ? "✓ sylwetka rozpoznana" : "✓ rozpoznana (częściowo zasłonięta, sprawdź kadr)") : "⚠ nie rozpoznano: kadr ustawisz ręcznie po zapisie";
    }catch(err){ n.status = "Nie udało się wczytać zdjęcia: " + err.message; n.blad = true; }
    rysujNowe(n);
  }
};
function rysujNowe(n){
  if(!n.el) return;
  n.el.innerHTML = "";
  const podglad = el("canvas", {width:110, height:146});
  if(n.maly){
    const c = podglad, k = Math.min(c.width / n.maly.width, c.height / n.maly.height), w = n.maly.width * k, h = n.maly.height * k;
    const g = c.getContext("2d"); g.drawImage(n.maly, (c.width - w) / 2, (c.height - h) / 2, w, h);
    if(n.pose){ g.strokeStyle = "#34C759"; g.lineWidth = 2; const x = (c.width - w) / 2 + n.pose.cx * w, y = (c.height - h) / 2 + n.pose.cy * h, s = n.pose.s * h;
      g.beginPath(); g.moveTo(x, y - s / 2); g.lineTo(x, y + s / 2); g.moveTo(x - 6, y); g.lineTo(x + 6, y); g.stroke(); }
  }
  const chips = el("div", {class:"chips"});
  TYPY.forEach(([k, nazwa]) => chips.append(el("button", {"aria-pressed":String(n.typ === k), text:nazwa, onclick:() => { n.typ = k; rysujNowe(n); }})));
  const data = el("input", {type:"date", value:n.data, onchange:e => { n.data = e.target.value || $("fData").value; n.wlasnaData = true; }});
  const prawa = el("div", {}, chips, el("label", {class:"f", style:"margin-top:8px"}, "Data zdjęcia", data));
  if(n.exif && n.exif !== n.data) prawa.append(el("button", {class:"btn small", style:"margin-top:6px;padding:6px 10px", text:`Użyj daty ze zdjęcia: ${krotko(n.exif)}`, onclick:() => uzyjDaty(n.exif)}));
  prawa.append(el("div", {class:"st " + (n.blad ? "err" : ""), text:n.status}),
    el("button", {class:"btn bad small", style:"margin-top:6px;padding:6px 10px", text:"Usuń z listy", onclick:() => { NOWE.splice(NOWE.indexOf(n), 1); n.el.remove(); }}));
  n.el.append(podglad, prawa);
}

$("zapisz").onclick = async () => {
  const info = $("zapiszInfo"), btn = $("zapisz"), data = $("fData").value || dzis();
  const masa = num($("fMasa").value), fat = num($("fFat").value), muscle = num($("fMuscle").value), notatka = $("fNotatka").value.trim();
  if([masa, fat, muscle].some(Number.isNaN)){ info.className = "small err"; info.textContent = "Wpisz liczby (np. 78,4)."; return; }
  if(NOWE.some(n => n.pose === undefined && !n.blad)){ info.className = "small err"; info.textContent = "Poczekaj, aż zdjęcia się wczytają."; return; }
  btn.disabled = true; info.className = "small";
  try{
    const stary = DANE.wpisy[data];
    if(masa != null || fat != null || muscle != null || notatka || stary){
      info.textContent = "Zapisuję wyniki…";
      DANE = await post(API + "/wpis", {data, masa, fat, muscle, notatka});
    }
    const doWyslania = NOWE.filter(n => !n.blad && n.duzy);
    for(let i = 0; i < doWyslania.length; i++){
      const n = doWyslania[i];
      info.textContent = `Wysyłam zdjęcie ${i + 1} z ${doWyslania.length}…`;
      const fd = new FormData();
      fd.append("plik", await doBloba(n.duzy, 0.88), "zdjecie.jpg");
      fd.append("miniatura", await doBloba(n.maly, 0.8), "miniatura.jpg");
      fd.append("data", n.data); fd.append("typ", n.typ); fd.append("pose", JSON.stringify(n.pose || null)); fd.append("lm", JSON.stringify(n.lm || []));
      const r = await fetch(API + "/zdjecie", {method:"POST", body:fd});
      if(!r.ok) throw new Error("zdjęcie " + (i + 1) + ": serwer odpowiedział " + r.status);
      NOWE.splice(NOWE.indexOf(n), 1); n.el.remove();
    }
    await wczytaj();
    info.className = "small okmsg"; info.textContent = "Zapisano ✓";
    ustawFormularz(data);
  }catch(err){ info.className = "small err"; info.textContent = "Nie udało się: " + err.message; }
  btn.disabled = false;
};

/* ---------- HISTORIA: wykresy i dni ---------- */
function wykres(tytul, serie, jedn, zak){
  // serie: [{nazwa, kolor, pkt:[[data, wartosc]]}] - jedna oś y, wspólna jednostka; zak = {x0, x1} (ms) albo null = całość
  const wszystkie = serie.flatMap(s => s.pkt);
  const box = el("div", {class:"chart"}, el("h3", {text:tytul}));
  if(new Set(wszystkie.map(p => p[0])).size < 2){ box.append(el("p", {class:"muted small", text:"Wykres pojawi się po pomiarach z co najmniej dwóch dni."})); return box; }
  const W = Math.max(300, Math.round(($("wykresy").clientWidth || 600) - 34)), H = 190, L = 40, R = serie.length > 1 ? 100 : 64, T = 10, B = 24;
  const ms = p => pd(p[0]).getTime();
  let x0, x1;
  if(zak){ x0 = zak.x0; x1 = zak.x1; } else { const xs = wszystkie.map(ms); x0 = Math.min(...xs); x1 = Math.max(...xs); }
  if(x1 === x0) x1 = x0 + 864e5;
  // w oknie: punkty z zakresu + po jednym sąsiedzie z każdej strony (linia wychodzi za krawędź i jest przycinana)
  serie = serie.map(s => { const w = s.pkt.filter(p => ms(p) >= x0 && ms(p) <= x1), przed = s.pkt.filter(p => ms(p) < x0).pop(), po = s.pkt.find(p => ms(p) > x1);
    return Object.assign({}, s, {pkt:w, linia:[przed, ...w, po].filter(Boolean)}); });
  const all = serie.flatMap(s => s.pkt);
  if(!all.length){ box.append(el("p", {class:"muted small", text:"Brak pomiarów w tym okresie. Przesuń suwak albo wybierz dłuższy zakres."})); return box; }
  const ys = all.map(p => p[1]);
  let y0 = Math.min(...ys), y1 = Math.max(...ys); const pad_ = Math.max((y1 - y0) * 0.15, 0.5); y0 -= pad_; y1 += pad_;
  const X = t => L + (t - x0) / (x1 - x0) * (W - L - R), Y = v => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
  const ns = "http://www.w3.org/2000/svg", S = (t, a) => { const e = document.createElementNS(ns, t); for(const k in a) e.setAttribute(k, a[k]); return e; };
  const svg = S("svg", {viewBox:`0 0 ${W} ${H}`, role:"img", "aria-label":tytul});
  for(let i = 0; i <= 3; i++){
    const v = y0 + (y1 - y0) * i / 3, y = Y(v);
    svg.append(S("line", {x1:L, x2:W - R, y1:y, y2:y, stroke:"var(--grid)", "stroke-width":1}));
    const t = S("text", {x:L - 6, y:y + 4, "text-anchor":"end", "font-size":12, fill:"var(--muted)"}); t.textContent = pl(v); svg.append(t);
  }
  [x0, x1].forEach((t, i) => { const e = S("text", {x:X(t), y:H - 6, "text-anchor":i ? "end" : "start", "font-size":12, fill:"var(--muted)"}); e.textContent = krotko(iso(new Date(t))); svg.append(e); });
  const clipId = "c" + Math.random().toString(36).slice(2);
  const defs = S("defs", {}), cp = S("clipPath", {id:clipId}); cp.append(S("rect", {x:L, y:0, width:W - L - R, height:H - B})); defs.append(cp); svg.append(defs);
  serie.forEach(s => {
    if(!s.linia.length) return;
    const d = s.linia.map((p, i) => (i ? "L" : "M") + X(pd(p[0]).getTime()).toFixed(1) + "," + Y(Math.min(Math.max(p[1], y0 - (y1 - y0)), y1 + (y1 - y0))).toFixed(1)).join("");
    svg.append(S("path", {d, fill:"none", stroke:s.kolor, "stroke-width":2, "stroke-linejoin":"round", "stroke-linecap":"round", "clip-path":`url(#${clipId})`}));
    if(!s.pkt.length) return;
    s.pkt.forEach(p => svg.append(S("circle", {cx:X(pd(p[0]).getTime()), cy:Y(p[1]), r:4, fill:s.kolor, stroke:"var(--surface)", "stroke-width":2})));
    const last = s.pkt[s.pkt.length - 1], lab = S("text", {x:X(pd(last[0]).getTime()) + 8, y:Y(last[1]) + 4, "font-size":13, fill:"var(--ink)", "font-weight":700});
    lab.textContent = (serie.length > 1 ? s.nazwa + " " : "") + pl(last[1]) + jedn; svg.append(lab);
  });
  const cross = S("line", {y1:T, y2:H - B, stroke:"var(--muted)", "stroke-width":1, "stroke-dasharray":"3 3", visibility:"hidden"}); svg.append(cross);
  const wrap = el("div", {class:"chartwrap"}, svg), tip = el("div", {class:"tip", hidden:""}); wrap.append(tip);
  const daty = [...new Set(all.map(p => p[0]))].sort();
  svg.addEventListener("pointermove", ev => {
    const r = svg.getBoundingClientRect(), x = (ev.clientX - r.left) / r.width * W;
    let best = daty[0]; for(const d of daty) if(Math.abs(X(pd(d).getTime()) - x) < Math.abs(X(pd(best).getTime()) - x)) best = d;
    const cx = X(pd(best).getTime()); cross.setAttribute("x1", cx); cross.setAttribute("x2", cx); cross.setAttribute("visibility", "visible");
    tip.hidden = false; tip.innerHTML = ""; tip.append(el("b", {text:krotko(best)}));
    serie.forEach(s => { const p = s.pkt.find(q => q[0] === best); if(p) tip.append(el("div", {}, el("span", {style:`display:inline-block;width:10px;height:3px;background:${s.kolor};margin-right:6px;vertical-align:middle`}), `${s.nazwa}: ${pl(p[1])}${jedn}`)); });
    const px = cx / W * r.width; tip.style.left = Math.min(Math.max(px - 60, 0), r.width - 140) + "px"; tip.style.top = "-6px";
  });
  svg.addEventListener("pointerleave", () => { tip.hidden = true; cross.setAttribute("visibility", "hidden"); });
  box.append(wrap);
  if(serie.length > 1) box.append(el("div", {class:"legend"}, ...serie.map(s => el("span", {}, el("i", {style:`background:${s.kolor}`}), s.nazwa))));
  return box;
}
/* zakres wykresów: liczba dni (null = całość) i koniec okna (suwak); zapamiętywane w tej przeglądarce */
const ZAKRESY = [[7, "7 dni"], [30, "Miesiąc"], [61, "2 mies."], [91, "3 mies."], [182, "6 mies."], [365, "Rok"], [null, "Całość"]];
let WYK = {dni:null, koniec:null};
try{ Object.assign(WYK, JSON.parse(localStorage.getItem("progres:wykres") || "{}")); }catch(e){}
const zapiszWYK = () => { try{ localStorage.setItem("progres:wykres", JSON.stringify(WYK)); }catch(e){} };
const DZIEN = 864e5;
function rysujWykresy(){
  const wpisy = Object.entries(DANE.wpisy).sort((a, b) => a[0].localeCompare(b[0]));
  const ser = k => wpisy.filter(([, w]) => w[k] != null).map(([d, w]) => [d, w[k]]);
  const cs = getComputedStyle(document.documentElement), s1 = cs.getPropertyValue("--s1").trim(), s2 = cs.getPropertyValue("--s2").trim();
  const daty = wpisy.filter(([, w]) => w.masa != null || w.fat != null || w.muscle != null).map(([d]) => pd(d).getTime());
  const dmin = daty.length ? daty[0] : Date.now(), dmax = daty.length ? daty[daty.length - 1] : Date.now(), rozpietosc = Math.round((dmax - dmin) / DZIEN);
  const okno = WYK.dni && WYK.dni < rozpietosc + 1;
  let zak = null;
  if(okno){
    const kmin = dmin + (WYK.dni - 1) * DZIEN;
    const koniec = Math.min(Math.max(WYK.koniec == null ? dmax : WYK.koniec, kmin), dmax);
    zak = {x0:koniec - (WYK.dni - 1) * DZIEN, x1:koniec, kmin};
  }
  const box = $("wykresy"); box.innerHTML = "";
  // zakres: gotowe przyciski + własna liczba dni
  const chips = el("div", {class:"chips"});
  ZAKRESY.forEach(([d, n]) => chips.append(el("button", {"aria-pressed":String(WYK.dni === d), text:n, onclick:() => { WYK.dni = d; WYK.koniec = null; zapiszWYK(); rysujWykresy(); }})));
  const wlasne = el("input", {type:"number", min:2, max:3650, inputmode:"numeric", placeholder:"np. 45", style:"width:90px;height:38px", value:ZAKRESY.some(([d]) => d === WYK.dni) ? "" : WYK.dni});
  wlasne.onchange = () => { const v = parseInt(wlasne.value); if(v >= 2){ WYK.dni = Math.min(v, 3650); WYK.koniec = null; zapiszWYK(); rysujWykresy(); } };
  box.append(el("h2", {text:"Wykresy"}), el("div", {class:"f", style:"margin-bottom:6px"}, "Zakres", chips),
    el("label", {class:"row small", style:"margin-bottom:8px;font-weight:700"}, "Własny zakres:", wlasne, el("span", {class:"muted", style:"font-weight:400", text:"dni"})),
    wykres("Masa ciała (kg)", [{nazwa:"masa", kolor:s1, pkt:ser("masa")}], " kg", zak),
    wykres("Skład ciała (%)", [{nazwa:"tłuszcz", kolor:s1, pkt:ser("fat")}, {nazwa:"mięśnie", kolor:s2, pkt:ser("muscle")}], "%", zak));
  // suwak od dołu: przesuwa okno w czasie (wspólny dla obu wykresów)
  if(okno){
    const kroki = Math.round((dmax - zak.kmin) / DZIEN);
    const sw = el("input", {type:"range", min:0, max:kroki, step:1, value:Math.round((zak.x1 - zak.kmin) / DZIEN), "aria-label":"Przesuń zakres wykresu"});
    const opis = el("div", {class:"small", style:"text-align:center;font-weight:700", text:`${krotko(iso(new Date(zak.x0)))} – ${krotko(iso(new Date(zak.x1)))}`});
    let raf = 0;
    sw.oninput = () => { WYK.koniec = zak.kmin + (+sw.value) * DZIEN; zapiszWYK(); cancelAnimationFrame(raf); raf = requestAnimationFrame(() => { rysujWykresy(); const n = $("wykresy").querySelector('input[type=range]'); if(n) n.focus(); }); };
    box.append(el("div", {class:"przesun"}, el("div", {class:"row small muted", style:"justify-content:space-between"}, el("span", {text:"◀ starsze"}), el("span", {text:"nowsze ▶"})), sw, opis));
  } else if(WYK.dni) box.append(el("p", {class:"muted small", style:"margin:0", text:"Wszystkie pomiary mieszczą się w tym zakresie, więc nie ma czego przesuwać."}));
}
function rysujHistorie(){
  rysujWykresy();
  const dni = [...new Set([...Object.keys(DANE.wpisy), ...DANE.zdjecia.map(z => z.data)])].sort().reverse();
  const box = $("dni"); box.innerHTML = "";
  if(!dni.length){ box.append(el("p", {class:"muted", text:"Jeszcze nic nie ma. Dodaj pierwszy pomiar w zakładce „Dodaj”."})); return; }
  dni.forEach(d => {
    const w = DANE.wpisy[d] || {}, zd = DANE.zdjecia.filter(z => z.data === d);
    const dt = pd(d);
    const vals = el("div", {class:"vals"});
    if(w.masa != null) vals.append(el("span", {}, "masa ", el("b", {text:pl(w.masa) + " kg"})));
    if(w.fat != null) vals.append(el("span", {}, "tłuszcz ", el("b", {text:pl(w.fat) + "%"})));
    if(w.muscle != null) vals.append(el("span", {}, "mięśnie ", el("b", {text:pl(w.muscle) + "%"})));
    if(w.notatka) vals.append(el("span", {text:"„" + w.notatka + "”"}));
    const th = el("div", {class:"thumbs"});
    zd.forEach(z => th.append(el("button", {class:"th", onclick:() => otworzZdjecie(z)}, el("img", {src:plik(z, true), alt:NAZWA[z.typ], loading:"lazy"}),
      z.pose || z.reczne ? null : el("b", {class:"warn", text:"kadr"}), el("span", {text:NAZWA[z.typ]}))));
    box.append(el("div", {class:"dzien"},
      el("div", {class:"row", style:"justify-content:space-between"}, el("h3", {text:`${DNI[dt.getDay()]}, ${krotko(d)}`}),
        el("button", {class:"btn small", style:"padding:5px 10px", text:"Edytuj", onclick:() => { ustawFormularz(d); pokaz("dodaj"); window.scrollTo({top:0}); }})),
      vals, zd.length ? th : null));
  });
}

/* ---------- wyrównanie klatki ---------- */
/* CEL = szablon kadru: tułów ma CEL.s wysokości kadru, jego środek jest w poziomie na środku i na CEL.y wysokości.
   Ustawiany suwakami „Przybliżenie” i „Wysokość” (FM.celS, FM.celY); po zmianie sylwetka i tak jest centrowana. */
const CEL = {y:0.44, s:0.26};
function synchCEL(){ CEL.s = FM.celS || 0.26; CEL.y = FM.celY || 0.44; }
/* położenie zdjęcia w kadrze W×H: skala k i lewy górny róg (ox, oy) */
/* ---------- wzór szkieletu dla każdego rodzaju zdjęcia i dopasowanie do niego ----------
   Wzór = średnie położenie 33 punktów MediaPipe ze wszystkich zdjęć danego rodzaju (uogólniona analiza Prokrustesa:
   skala + przesunięcie, bez obrotu), w jednostkach długości tułowia, środek tułowia w (0, 0).
   Każde zdjęcie dopasowujemy do wzoru ważoną metodą najmniejszych kwadratów; wagi zależą od rodzaju zdjęcia:
   tułów i barki liczą się najbardziej, ręce mało (na boku jeszcze mniej), w trybie „same ręce” tylko barki, łokcie, nadgarstki. */
const WAGI = {
  przod:     {0:1, 7:.5, 8:.5, 11:3, 12:3, 13:.5, 14:.5, 15:.2, 16:.2, 23:3, 24:3, 25:1, 26:1, 27:.5, 28:.5},
  tyl:       {0:.5, 7:.7, 8:.7, 11:3, 12:3, 13:.5, 14:.5, 15:.2, 16:.2, 23:3, 24:3, 25:1, 26:1, 27:.5, 28:.5},
  bok:       {0:.5, 7:1, 8:1, 11:3.5, 12:3.5, 13:.15, 14:.15, 15:.05, 16:.05, 23:3.5, 24:3.5, 25:1, 26:1, 27:.5, 28:.5},
  biceps:    {0:1, 7:.5, 8:.5, 11:3, 12:3, 13:.3, 14:.3, 15:.1, 16:.1, 23:3, 24:3, 25:1, 26:1, 27:.5, 28:.5},
  tylbiceps: {0:.5, 7:.7, 8:.7, 11:3, 12:3, 13:.3, 14:.3, 15:.1, 16:.1, 23:3, 24:3, 25:1, 26:1, 27:.5, 28:.5},
};
const WAGI_RECE = {11:2, 12:2, 13:3, 14:3, 15:3, 16:3};
const wagiTypu = typ => (FM.rece && BICEPS.includes(typ)) ? WAGI_RECE : (WAGI[typ] || WAGI.przod);
const maPunkty = z => Array.isArray(z.lm) && z.lm.length === 33;
const px = (z, i) => [z.lm[i][0] * z.w, z.lm[i][1] * z.h];
function tulow(P){ const sh = [(P[11][0] + P[12][0]) / 2, (P[11][1] + P[12][1]) / 2], hp = [(P[23][0] + P[24][0]) / 2, (P[23][1] + P[24][1]) / 2];
  return {c:[(sh[0] + hp[0]) / 2, (sh[1] + hp[1]) / 2], L:Math.hypot(sh[0] - hp[0], sh[1] - hp[1])}; }
/* ważone dopasowanie P -> M: s*P + t (bez obrotu) */
function dopasujPunkty(P, M, w){
  let sw = 0, pc = [0, 0], mc = [0, 0];
  for(let i = 0; i < P.length; i++){ if(!(w[i] > 0) || !M[i]) continue; sw += w[i]; pc[0] += w[i] * P[i][0]; pc[1] += w[i] * P[i][1]; mc[0] += w[i] * M[i][0]; mc[1] += w[i] * M[i][1]; }
  if(sw <= 0) return null;
  pc = [pc[0] / sw, pc[1] / sw]; mc = [mc[0] / sw, mc[1] / sw];
  let num = 0, den = 0;
  for(let i = 0; i < P.length; i++){ if(!(w[i] > 0) || !M[i]) continue;
    const ax = P[i][0] - pc[0], ay = P[i][1] - pc[1]; num += w[i] * (ax * (M[i][0] - mc[0]) + ay * (M[i][1] - mc[1])); den += w[i] * (ax * ax + ay * ay); }
  if(!(den > 0) || !(num > 0)) return null;
  const s = num / den; return {s, tx:mc[0] - s * pc[0], ty:mc[1] - s * pc[1]};
}
function wagiZdjecia(z, W8){ return z.lm.map((q, i) => (W8[i] || 0) * (q[2] >= 0.3 ? q[2] : 0)); }
let WZORY = {}, DOPAS = {}, wzoryKlucz = "";
function resetWzorow(){ WZORY = {}; DOPAS = {}; wzoryKlucz = ""; }
function sprawdzKlucz(){ const k = (FM.rece ? "r" : "s") + DANE.zdjecia.filter(maPunkty).length + "|" + DANE.zdjecia.length; if(k !== wzoryKlucz){ resetWzorow(); wzoryKlucz = k; } }
function wzor(typ){
  sprawdzKlucz();
  if(typ in WZORY) return WZORY[typ];
  const zd = DANE.zdjecia.filter(z => z.typ === typ && maPunkty(z));
  if(!zd.length) return WZORY[typ] = null;
  const W8 = wagiTypu(typ), Ps = zd.map(z => z.lm.map((_, i) => px(z, i)));
  const srednia = AL => { const M = []; for(let i = 0; i < 33; i++){ let sx = 0, sy = 0, sv = 0;
      AL.forEach((A, k) => { const v = zd[k].lm[i][2] >= 0.3 ? zd[k].lm[i][2] : 0; sx += v * A[i][0]; sy += v * A[i][1]; sv += v; });
      M.push(sv > 0 ? [sx / sv, sy / sv] : null); } return M; };
  // start: każde zdjęcie znormalizowane własnym tułowiem, potem 3 rundy dopasowania do średniej
  let AL = Ps.map(P => { const t = tulow(P); return P.map(p => [(p[0] - t.c[0]) / t.L, (p[1] - t.c[1]) / t.L]); });
  let M = srednia(AL);
  for(let it = 0; it < 3; it++){
    AL = Ps.map((P, k) => { const d = dopasujPunkty(P, M, wagiZdjecia(zd[k], W8)); return d ? P.map(p => [d.s * p[0] + d.tx, d.s * p[1] + d.ty]) : AL[k]; });
    M = srednia(AL);
  }
  if(!M[11] || !M[12] || !M[23] || !M[24]) return WZORY[typ] = null;
  const t = tulow(M);                                     // wzór: środek tułowia (0, 0), tułów = 1
  M = M.map(p => p && [(p[0] - t.c[0]) / t.L, (p[1] - t.c[1]) / t.L]);
  return WZORY[typ] = {M, n:zd.length};
}
/* dopasowanie zdjęcia: {s, tx, ty} (piksele zdjęcia -> jednostki wzoru) albo null */
function dopasowanie(z){
  sprawdzKlucz();
  if(z.id in DOPAS) return DOPAS[z.id];
  let d = null;
  const wz = maPunkty(z) && wzor(z.typ);
  if(wz) d = dopasujPunkty(z.lm.map((_, i) => px(z, i)), wz.M, wagiZdjecia(z, wagiTypu(z.typ)));
  if(!d && z.pose && z.pose.s > 0){ const s = 1 / (z.pose.s * z.h); d = {s, tx:-z.pose.cx * z.w * s, ty:-z.pose.cy * z.h * s}; }
  return DOPAS[z.id] = d;
}
function geom(z, W, H, iw, ih){
  iw = iw || z.w; ih = ih || z.h;
  const r = z.reczne || {}, p = z.pose, d = dopasowanie(z), L = CEL.s * H, zz = r.z || 1;
  if(d) return {k:zz * L * d.s * (z.w / iw), ox:W / 2 + (r.dx || 0) * L + zz * L * d.tx, oy:CEL.y * H + (r.dy || 0) * L + zz * L * d.ty, w:iw * zz * L * d.s * (z.w / iw), h:ih * zz * L * d.s * (z.w / iw)};
  let k, ox, oy;
  if(p && p.s > 0){
    k = (CEL.s * H) / (p.s * ih) * (r.z || 1);
    ox = W / 2 + (r.dx || 0) * CEL.s * H - p.cx * iw * k;
    oy = CEL.y * H + (r.dy || 0) * CEL.s * H - p.cy * ih * k;
  } else {
    k = H / ih * (r.z || 1);
    ox = (W - iw * k) / 2 + (r.dx || 0) * CEL.s * H;
    oy = (H - ih * k) / 2 + (r.dy || 0) * CEL.s * H;
  }
  return {k, ox, oy, w:iw * k, h:ih * k};
}
function rysujKlatke(g, img, z, W, H, alfa = 1){
  const q = geom(z, W, H, img.naturalWidth || img.width, img.naturalHeight || img.height);
  g.globalAlpha = alfa; g.drawImage(img, q.ox, q.oy, q.w, q.h); g.globalAlpha = 1;
}
/* ramka końcowa (co trafia do filmu), w pikselach kadru; zawsze ma proporcje kadru.
   ręczna (FM.ramka, ułamki kadru) > automatyczna (część wspólna wszystkich klatek, bez krawędzi zdjęć) > cały kadr */
function ramkaAuto(kl, W, H){
  if(!kl.length) return null;
  let x0 = 0, y0 = 0, x1 = W, y1 = H;
  kl.forEach(z => { const q = geom(z, W, H); x0 = Math.max(x0, q.ox); y0 = Math.max(y0, q.oy); x1 = Math.min(x1, q.ox + q.w); y1 = Math.min(y1, q.oy + q.h); });
  const w = Math.min(x1 - x0, (y1 - y0) * W / H), h = w * H / W;
  if(!(w > W * 0.2)) return null;                       // części wspólnej prawie nie ma: nie przycinamy
  const ax = W / 2, ay = CEL.y * H;                      // przycinamy „wokół tułowia”, żeby został w tym samym miejscu kadru
  let x = ax - ax / W * w, y = ay - ay / H * h;
  x = Math.min(Math.max(x, x0), x1 - w); y = Math.min(Math.max(y, y0), y1 - h);
  return {x, y, w, h};
}
function ramkaKoncowa(kl, W, H){
  const m = FM.ramka;
  if(m && m.w > 0) return {x:m.x * W, y:m.y * H, w:m.w * W, h:m.w * H};
  if(FM.przytnij !== false){ const a = ramkaAuto(kl, W, H); if(a) return a; }
  return {x:0, y:0, w:W, h:H};
}
/* rysuj z przycięciem: ramka r rozciągnięta na cały kadr */
function wRamce(g, r, W, rysuj){ const sc = W / r.w; g.save(); g.setTransform(sc, 0, 0, sc, -r.x * sc, -r.y * sc); rysuj(); g.restore(); }
const CACHE = new Map();
function obraz(z){
  if(!CACHE.has(z.id)) CACHE.set(z.id, new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = plik(z); }));
  return CACHE.get(z.id);
}

/* ---------- podgląd zdjęcia + kadrowanie ---------- */
function zamknij(){ $("modal").hidden = true; $("modalBox").innerHTML = ""; }
$("modal").onclick = e => { if(e.target === $("modal")) zamknij(); };
document.addEventListener("keydown", e => { if(e.key === "Escape" && !$("modal").hidden) zamknij(); });
function otworzZdjecie(z){
  const box = $("modalBox"); box.innerHTML = ""; $("modal").hidden = false;
  const chips = el("div", {class:"chips"});
  TYPY.forEach(([k, n]) => chips.append(el("button", {"aria-pressed":String(z.typ === k), text:n, onclick:async () => { DANE = await post(`${API}/zdjecie/${z.id}`, {typ:k}); z.typ = k; otworzZdjecie(DANE.zdjecia.find(q => q.id === z.id)); rysujHistorie(); }})));
  const data = el("input", {type:"date", value:z.data});
  box.append(el("img", {src:plik(z), alt:NAZWA[z.typ]}), el("div", {class:"f", style:"margin-bottom:8px"}, "Rodzaj", chips),
    el("div", {class:"row"}, el("label", {class:"f", style:"flex:1"}, "Data", data),
      el("button", {class:"btn", style:"align-self:flex-end", text:"Zmień datę", onclick:async () => { if(!data.value) return; DANE = await post(`${API}/zdjecie/${z.id}`, {data:data.value}); rysujHistorie(); zamknij(); }})),
    el("div", {class:"row", style:"margin-top:12px"},
      el("button", {class:"btn primary", text:"✂ Kadrowanie", onclick:() => kadruj(z)}),
      el("button", {class:"btn bad", text:"Usuń zdjęcie", onclick:async () => { if(!confirm("Usunąć to zdjęcie? (trafi do kosza na Raspberry)")) return; DANE = await post(`${API}/zdjecie/${z.id}`, {usun:true}); rysujHistorie(); zamknij(); }}),
      el("button", {class:"btn", text:"Zamknij", onclick:zamknij})));
}
async function kadruj(z, poZapisie){
  Object.assign(FM, DANE.ustawienia.film || {}); synchCEL();
  const box = $("modalBox"); box.innerHTML = ""; $("modal").hidden = false;
  const [Wf, Hf] = formatWH();
  const c = el("canvas", {width:Wf / 2, height:Hf / 2}), g = c.getContext("2d");
  const r = Object.assign({dx:0, dy:0, z:1}, z.reczne || {});
  const poprz = DANE.zdjecia.filter(q => q.typ === z.typ && q.id !== z.id && q.data <= z.data).sort((a, b) => b.data.localeCompare(a.data))[0];
  const img = await obraz(z), img2 = poprz ? await obraz(poprz) : null;
  const duch = el("input", {type:"range", min:0, max:0.8, step:0.05, value:img2 ? 0.4 : 0});
  const szk = el("input", {type:"checkbox", checked:""}); szk.onchange = () => rys();
  const rys = () => { g.fillStyle = "#000"; g.fillRect(0, 0, c.width, c.height);
    rysujKlatke(g, img, Object.assign({}, z, {reczne:r}), c.width, c.height);
    if(img2 && +duch.value) rysujKlatke(g, img2, poprz, c.width, c.height, +duch.value);
    if(szk.checked) szkielet(g, c.width, c.height, z.typ);
    g.strokeStyle = "rgba(52,199,89,.7)"; g.setLineDash([6, 6]); g.beginPath(); g.moveTo(c.width / 2, 0); g.lineTo(c.width / 2, c.height);
    const y = CEL.y * c.height; g.moveTo(0, y); g.lineTo(c.width, y); g.stroke(); g.setLineDash([]); };
  duch.oninput = rys;
  const krok = (k, v) => () => { r[k] = +(r[k] + v).toFixed(3); rys(); };
  let drag = null;
  c.onpointerdown = e => { drag = {x:e.clientX, y:e.clientY, dx:r.dx, dy:r.dy}; c.setPointerCapture(e.pointerId); };
  c.onpointermove = e => { if(!drag) return; const sc = c.getBoundingClientRect().height * CEL.s; r.dx = +(drag.dx + (e.clientX - drag.x) / sc).toFixed(3); r.dy = +(drag.dy + (e.clientY - drag.y) / sc).toFixed(3); rys(); };
  c.onpointerup = () => drag = null;
  const zapisz = async () => { const reczne = (r.dx || r.dy || r.z !== 1) ? r : null; DANE = await post(`${API}/zdjecie/${z.id}`, {reczne}); if(poZapisie) poZapisie(); else rysujHistorie(); zamknij(); };
  const wykryjPon = async () => { status.textContent = "Rozpoznaję…"; const cc = naCanvas(img, 1800); const wyk = await wykryj(cc);
    if(!wyk){ status.textContent = "Nie udało się rozpoznać sylwetki. Ustaw kadr ręcznie."; return; }
    DANE = await post(`${API}/zdjecie/${z.id}`, {pose:wyk.pose, lm:wyk.lm}); z.pose = wyk.pose; z.lm = wyk.lm; resetWzorow(); status.textContent = "✓ rozpoznano"; rys(); };
  const status = el("p", {class:"small muted", text:z.pose ? "Sylwetka rozpoznana automatycznie. Popraw, jeśli trzeba." : "Sylwetka nierozpoznana: przesuń i przybliż ręcznie."});
  box.append(el("h2", {text:`Kadrowanie: ${NAZWA[z.typ]}, ${krotko(z.data)}`}), status,
    el("div", {class:"stage"}, c),
    el("p", {class:"small muted", style:"margin:0", text:"Przeciągnij zdjęcie palcem. Zielone linie to miejsce tułowia. " + (img2 ? "Półprzezroczyste jest poprzednie zdjęcie tego typu." : "")}),
    img2 ? el("label", {class:"f small", style:"margin:6px 0"}, `Poprzednie zdjęcie (${krotko(poprz.data)}) – przezroczystość`, duch) : null,
    el("label", {class:"row small", style:"font-weight:700"}, szk, ` Szkielet-wzór „${NAZWA[z.typ]}”`),
    el("div", {class:"row", style:"margin-top:8px"},
      el("button", {class:"btn", text:"−", title:"oddal", onclick:() => { r.z = +(r.z / 1.04).toFixed(3); rys(); }}),
      el("button", {class:"btn", text:"+", title:"przybliż", onclick:() => { r.z = +(r.z * 1.04).toFixed(3); rys(); }}),
      el("button", {class:"btn", text:"←", onclick:krok("dx", -0.03)}), el("button", {class:"btn", text:"→", onclick:krok("dx", 0.03)}),
      el("button", {class:"btn", text:"↑", onclick:krok("dy", -0.03)}), el("button", {class:"btn", text:"↓", onclick:krok("dy", 0.03)}),
      el("button", {class:"btn", text:"Wyzeruj", onclick:() => { r.dx = 0; r.dy = 0; r.z = 1; rys(); }}),
      el("button", {class:"btn", text:"Rozpoznaj ponownie", onclick:wykryjPon})),
    el("div", {class:"row", style:"margin-top:10px"}, el("button", {class:"btn primary", text:"Zapisz kadr", onclick:zapisz}), el("button", {class:"btn", text:"Anuluj", onclick:zamknij})));
  rys();
}

/* ---------- FILM ---------- */
let FM = {tryb:"seria", typ:"przod", od:"", do:"", co:7, sek:0.5, format:"4:5", przejscie:0.25, napisy:true, pp1:"", pp2:"", ppT:1.5, ppTr:1};
function formatWH(){ return {"4:5":[1080, 1350], "9:16":[1080, 1920], "1:1":[1080, 1080]}[FM.format] || [1080, 1350]; }
function klatki(){
  const zd = DANE.zdjecia.filter(z => z.typ === FM.typ && (!FM.od || z.data >= FM.od) && (!FM.do || z.data <= FM.do)).sort((a, b) => a.data.localeCompare(b.data) || a.dodano.localeCompare(b.dodano));
  if(!zd.length) return [];
  const co = Math.max(1, Math.round(FM.co) || 1), wyn = [];
  let t = pd(FM.od || zd[0].data); const koniec = pd(FM.do || zd[zd.length - 1].data);
  while(t <= koniec){
    const a = iso(t), b = new Date(t); b.setDate(b.getDate() + co); const bi = iso(b);
    const z = zd.find(q => q.data >= a && q.data < bi); if(z) wyn.push(z);
    t = b;
  }
  return wyn;
}
/* plan filmu: zdjęcia (kl), długość w sekundach (dl) i stan(s) = co widać w chwili s:
   a, b = indeksy zdjęć w kl, w = udział zdjęcia b (0..1), napis = indeksy zdjęć do podpisu.
   Ten sam plan liczy render na Raspberry (progres_render.py), więc film z Pi wygląda jak podgląd. */
function plan(){
  if(FM.tryb === "pp"){
    const z1 = DANE.zdjecia.find(z => z.id === FM.pp1), z2 = DANE.zdjecia.find(z => z.id === FM.pp2);
    if(!z1 || !z2 || z1.id === z2.id) return {kl:[], dl:0, stan:() => null};
    const t = Math.max(0.1, FM.ppT || 1.5), tr = Math.max(0, FM.ppTr || 0);
    // zdjęcie 1 → przejście → oba nałożone 50/50 → przejście → zdjęcie 2
    const stan = s => {
      let w;
      if(s < t) w = 0;
      else if(s < t + tr) w = 0.5 * (s - t) / tr;
      else if(s < 2 * t + tr) w = 0.5;
      else if(s < 2 * t + 2 * tr) w = 0.5 + 0.5 * (s - 2 * t - tr) / tr;
      else w = 1;
      return {a:0, b:1, w, napis:w < 0.25 ? [0] : w > 0.75 ? [1] : [0, 1]};
    };
    return {kl:[z1, z2], dl:3 * t + 2 * tr, stan};
  }
  const kl = klatki(), n = kl.length, sek = Math.max(0.1, FM.sek), fade = Math.min(FM.przejscie || 0, sek);
  return {kl, dl:n ? n * sek + 0.6 : 0, stan:s => {
    const i = Math.min(Math.floor(s / sek), n - 1), wK = s - i * sek;
    if(fade > 0 && i + 1 < n && wK > sek - fade) return {a:i, b:i + 1, w:(wK - (sek - fade)) / fade, napis:[i]};
    return {a:i, b:null, w:0, napis:[i]};
  }};
}
function zdjeciaTypu(){ return DANE.zdjecia.filter(z => z.typ === FM.typ).sort((a, b) => a.data.localeCompare(b.data) || a.dodano.localeCompare(b.dodano)); }
/* starsze zdjęcia mają tylko środek tułowia: uzupełnij im 33 punkty (raz, w tle, w tej przeglądarce) */
let uzupelnianie = false;
async function uzupelnijPunkty(){
  if(uzupelnianie) return;
  const brak = DANE.zdjecia.filter(z => !Array.isArray(z.lm));
  if(!brak.length) return;
  uzupelnianie = true;
  const info = $("fmPunkty");
  for(let i = 0; i < brak.length; i++){
    const z = brak[i];
    if(info){ info.hidden = false; info.textContent = `Uzupełniam punkty sylwetki w starszych zdjęciach: ${i + 1} z ${brak.length}…`; }
    try{
      const img = await obraz(z), wyk = await wykryj(naCanvas(img, 1800));
      DANE = await post(`${API}/zdjecie/${z.id}`, wyk ? {lm:wyk.lm, pose:wyk.pose} : {lm:[]});
    }catch(e){ console.warn("uzupełnianie punktów:", e); }
  }
  resetWzorow(); uzupelnianie = false;
  if(info){ info.textContent = "✓ Punkty sylwetki uzupełnione, kadry przeliczone."; setTimeout(() => info.hidden = true, 4000); }
  if(!$("film").hidden) filmUstaw();
}
function filmUstaw(){
  Object.assign(FM, DANE.ustawienia.film || {});
  const ileTyp = k => DANE.zdjecia.filter(z => z.typ === k).length;
  if(!ileTyp(FM.typ)){ const t = TYPY.find(([k]) => ileTyp(k)); if(t) FM.typ = t[0]; }
  $("fmCaly").setAttribute("aria-pressed", String(!FM.od && !FM.do));
  const pp = FM.tryb === "pp";
  $("fmTrybSeria").setAttribute("aria-pressed", String(!pp)); $("fmTrybPP").setAttribute("aria-pressed", String(pp));
  $("fmSeria").hidden = pp; $("fmPP").hidden = !pp;
  const zt = zdjeciaTypu();
  if(pp && zt.length >= 2){
    if(!zt.some(z => z.id === FM.pp1)) FM.pp1 = zt[0].id;
    if(!zt.some(z => z.id === FM.pp2) || FM.pp2 === FM.pp1) FM.pp2 = zt[zt.length - 1].id;
  }
  [["fmPP1", FM.pp1], ["fmPP2", FM.pp2]].forEach(([id, v]) => { const sel = $(id); sel.innerHTML = "";
    zt.forEach((z, i) => { const nr = zt.filter(q => q.data === z.data).length > 1 ? ` (${zt.filter(q => q.data === z.data).indexOf(z) + 1})` : "";
      sel.append(el("option", {value:z.id, text:`${krotko(z.data)}${nr}${DANE.wpisy[z.data] && DANE.wpisy[z.data].masa != null ? " · " + pl(DANE.wpisy[z.data].masa) + " kg" : ""}`})); }); sel.value = v; });
  $("fmPPT").value = String(FM.ppT).replace(".", ","); $("fmPPTr").value = String(FM.ppTr).replace(".", ",");
  const ch = $("fmTyp"); ch.innerHTML = "";
  TYPY.forEach(([k, n]) => { const ile = DANE.zdjecia.filter(z => z.typ === k).length; if(!ile && k !== FM.typ) return;
    ch.append(el("button", {"aria-pressed":String(FM.typ === k), text:`${n} (${ile})`, onclick:() => { FM.typ = k; zapiszFM(); filmUstaw(); }})); });
  $("fmOd").value = FM.od; $("fmDo").value = FM.do; $("fmCo").value = FM.co; $("fmSek").value = String(FM.sek).replace(".", ",");
  $("fmFormat").value = FM.format; $("fmPrzejscie").value = String(FM.przejscie).replace(".", ","); $("fmNapisy").checked = !!FM.napisy;
  const [W, H] = formatWH(); const c = $("fmCanvas"); if(c.width !== W || c.height !== H){ c.width = W; c.height = H; }
  $("fmDopas").hidden = !BICEPS.includes(FM.typ);
  $("fmDopSyl").setAttribute("aria-pressed", String(!FM.rece)); $("fmDopRece").setAttribute("aria-pressed", String(!!FM.rece));
  const wz = wzor(FM.typ);
  $("fmWzor").textContent = wz ? `Wzór szkieletu „${NAZWA[FM.typ]}” liczony ze średniej z ${wz.n} ${wz.n === 1 ? "zdjęcia" : "zdjęć"}${FM.rece && BICEPS.includes(FM.typ) ? ", dopasowanie tylko do rąk (barki, łokcie, nadgarstki)" : ""}.` : "";
  uzupelnijPunkty();
  const P = plan(), k = P.kl, sek = Math.max(0.1, FM.sek);
  if(pp) $("fmInfo").textContent = k.length === 2 ? `Przed i po: ${krotko(k[0].data)} → ${krotko(k[1].data)}. Film ${pl(P.dl, 1)} s: zdjęcie 1 (${pl(FM.ppT, 1)} s) → przejście (${pl(FM.ppTr, 1)} s) → oba nałożone (${pl(FM.ppT, 1)} s) → przejście → zdjęcie 2.` : "Wybierz dwa różne zdjęcia tego rodzaju (potrzebne są co najmniej 2).";
  else {
    const przej = FM.przejscie > 0 ? `przejście ${pl(Math.min(FM.przejscie, sek), 2)} s` + (FM.przejscie > sek ? " (skrócone do czasu klatki)" : "") : "cięcie bez przejścia";
    $("fmInfo").textContent = k.length ? `${k.length} klatek (${krotko(k[0].data)} → ${krotko(k[k.length - 1].data)}), film ok. ${pl(P.dl - 0.6, 1)} s, ${przej}.` : "Brak zdjęć tego rodzaju w wybranym zakresie.";
  }
  const kl = $("fmKlatki"); kl.innerHTML = "";
  k.forEach(z => kl.append(el("button", {class:z.pose || z.reczne ? "" : "bez", onclick:() => kadruj(z, filmUstaw)}, el("img", {src:plik(z, true), alt:"", loading:"lazy"}), krotko(z.data).replace(/ \d{4}$/, ""))));
  if(k.length) pokazKlatke(0);
  rysujSzablon();
  listaFilmow();
}
function zapiszFM(){ post(API + "/ustawienia", {film:FM}).catch(() => {}); DANE.ustawienia.film = Object.assign({}, FM); }
["fmOd", "fmDo", "fmCo", "fmSek", "fmFormat", "fmPrzejscie", "fmNapisy"].forEach(id => $(id).onchange = () => {
  FM.od = $("fmOd").value; FM.do = $("fmDo").value; FM.co = Math.max(1, parseInt($("fmCo").value) || 1);
  const s = num($("fmSek").value); FM.sek = Number.isFinite(s) && s > 0 ? Math.min(s, 10) : 0.5;
  FM.format = $("fmFormat").value; const pz = num($("fmPrzejscie").value); FM.przejscie = Number.isFinite(pz) && pz > 0 ? Math.min(pz, 10) : 0; FM.napisy = $("fmNapisy").checked;
  zapiszFM(); filmUstaw();
});
$("fmCaly").onclick = () => { FM.od = ""; FM.do = ""; zapiszFM(); filmUstaw(); };
$("fmTrybSeria").onclick = () => { FM.tryb = "seria"; zapiszFM(); filmUstaw(); };
$("fmDopSyl").onclick = () => { FM.rece = false; resetWzorow(); zapiszFM(); filmUstaw(); };
$("fmDopRece").onclick = () => { FM.rece = true; resetWzorow(); zapiszFM(); filmUstaw(); };
$("fmTrybPP").onclick = () => { FM.tryb = "pp"; zapiszFM(); filmUstaw(); };
["fmPP1", "fmPP2", "fmPPT", "fmPPTr"].forEach(id => $(id).onchange = () => {
  FM.pp1 = $("fmPP1").value; FM.pp2 = $("fmPP2").value;
  const t = num($("fmPPT").value), tr = num($("fmPPTr").value);
  FM.ppT = Number.isFinite(t) && t > 0 ? Math.min(t, 20) : 1.5; FM.ppTr = Number.isFinite(tr) && tr >= 0 ? Math.min(tr, 20) : 1;
  zapiszFM(); filmUstaw();
});
function tekstNapisu(zs){
  const W_ = z => DANE.wpisy[z.data] || {};
  if(zs.length === 2){
    const [a, b] = zs.map(W_), cz = [`${krotko(zs[0].data)} → ${krotko(zs[1].data)}`];
    if(a.masa != null && b.masa != null) cz.push(`${pl(a.masa)} → ${pl(b.masa)} kg`);
    if(a.fat != null && b.fat != null) cz.push(`${pl(a.fat)} → ${pl(b.fat)}% tł.`);
    return cz.join("  ·  ");
  }
  const w = W_(zs[0]), czesci = [krotko(zs[0].data)];
  if(w.masa != null) czesci.push(pl(w.masa) + " kg"); if(w.fat != null) czesci.push(pl(w.fat) + "% tł."); if(w.muscle != null) czesci.push(pl(w.muscle) + "% mięśni");
  return czesci.join("  ·  ");
}
function napis(g, zs, W, H){
  if(!FM.napisy) return;
  if(!Array.isArray(zs)) zs = [zs];
  const t = tekstNapisu(zs); let fs = Math.round(W * 0.038);
  g.font = `700 ${fs}px "Alegreya Sans", sans-serif`; g.textAlign = "center"; g.textBaseline = "middle";
  let tw = g.measureText(t).width;
  while(tw > W * 0.88){ fs = Math.floor(fs * 0.92); g.font = `700 ${fs}px "Alegreya Sans", sans-serif`; tw = g.measureText(t).width; }
  const y = H - Math.round(W * 0.038) * 1.6;
  g.fillStyle = "rgba(0,0,0,.55)"; g.beginPath(); g.roundRect ? g.roundRect(W / 2 - tw / 2 - fs * 0.7, y - fs * 0.85, tw + fs * 1.4, fs * 1.7, fs * 0.5) : g.rect(W / 2 - tw / 2 - fs * 0.7, y - fs * 0.85, tw + fs * 1.4, fs * 1.7); g.fill();
  g.fillStyle = "#fff"; g.fillText(t, W / 2, y);
}
async function pokazKlatke(i){
  synchCEL();
  const k = plan().kl; if(!k[i]) return; const c = $("fmCanvas"), g = c.getContext("2d"), W = c.width, H = c.height, r = ramkaKoncowa(k, W, H);
  const img = await obraz(k[i]); g.fillStyle = "#000"; g.fillRect(0, 0, W, H);
  wRamce(g, r, W, () => rysujKlatke(g, img, k[i], W, H)); napis(g, k[i], W, H);
}
/* odtwarzanie w czasie rzeczywistym (podgląd i nagrywanie używają tego samego) */
async function odtworz(onKoniec){
  const P = plan(), k = P.kl; if(!k.length) return;
  $("fmStatus").textContent = "Wczytuję zdjęcia…";
  const imgs = await Promise.all(k.map(obraz));
  synchCEL();
  const c = $("fmCanvas"), g = c.getContext("2d"), W = c.width, H = c.height, rk = ramkaKoncowa(k, W, H);
  const total = P.dl; let start = null;
  $("fmStatus").textContent = "";
  return new Promise(res => {
    const krok = t => {
      if(start == null) start = t;
      const el_ = (t - start) / 1000, st = P.stan(Math.min(el_, total - 1e-6));
      g.fillStyle = "#000"; g.fillRect(0, 0, W, H);
      wRamce(g, rk, W, () => {
        rysujKlatke(g, imgs[st.a], k[st.a], W, H);
        if(st.b != null && st.w > 0) rysujKlatke(g, imgs[st.b], k[st.b], W, H, st.w);
      });
      napis(g, st.napis.map(i => k[i]), W, H);
      if(el_ < total) requestAnimationFrame(krok); else { res(); if(onKoniec) onKoniec(); }
    };
    requestAnimationFrame(krok);
  });
}
$("fmPlay").onclick = () => odtworz();
$("fmNagraj").onclick = async () => {
  const c = $("fmCanvas");
  if(!c.captureStream || !window.MediaRecorder){ $("fmStatus").textContent = "Ta przeglądarka nie umie nagrywać filmu. Spróbuj w Safari albo Chrome."; return; }
  const typy = ["video/mp4;codecs=avc1", "video/mp4", "video/webm;codecs=vp9", "video/webm"];
  const mime = typy.find(t => MediaRecorder.isTypeSupported(t)) || "";
  const stream = c.captureStream(30), rec = new MediaRecorder(stream, mime ? {mimeType:mime, videoBitsPerSecond:6e6} : {}), czesci = [];
  rec.ondataavailable = e => { if(e.data.size) czesci.push(e.data); };
  const gotowe = new Promise(res => rec.onstop = res);
  $("fmNagraj").disabled = $("fmPlay").disabled = true;
  rec.start(250); $("fmStatus").textContent = "⏺ Nagrywam… nie przełączaj karty.";
  await odtworz(); rec.stop(); await gotowe;
  const blob = new Blob(czesci, {type:rec.mimeType || mime || "video/webm"}), ext = (rec.mimeType || mime).includes("mp4") ? "mp4" : "webm";
  const url = URL.createObjectURL(blob), v = $("fmVideo"); v.src = url; v.hidden = false;
  const kl = plan().kl, nazwa = `progres-${FM.tryb === "pp" ? "przed-po-" : ""}${FM.typ}-${(kl[0] || {}).data || ""}_${(kl[kl.length - 1] || {}).data || ""}.${ext}`;
  const plikFilmu = new File([blob], nazwa, {type:blob.type}), mb = (blob.size / 1e6).toFixed(1).replace(".", ",");
  const box = $("fmPobierz"); box.innerHTML = "";
  // eksport: pobranie pliku albo systemowe „Udostępnij” (na iPhonie/iPadzie: Zapisz wideo w Zdjęciach, AirDrop, komunikatory)
  const wiersz = el("div", {class:"row", style:"justify-content:center"},
    el("a", {class:"btn primary", href:url, download:nazwa, text:`⬇ Pobierz plik (${ext.toUpperCase()}, ${mb} MB)`}));
  if(navigator.canShare && navigator.canShare({files:[plikFilmu]}))
    wiersz.append(el("button", {class:"btn", text:"📤 Udostępnij / Zapisz w Zdjęciach", onclick:() => navigator.share({files:[plikFilmu], title:"Progres"}).catch(() => {})}));
  box.append(wiersz);
  $("fmStatus").textContent = "Gotowe. Film możesz pobrać albo udostępnić. Na iPhonie/iPadzie „Udostępnij” → „Zapisz wideo” zapisze go w Zdjęciach.";
  $("fmNagraj").disabled = $("fmPlay").disabled = false;
};

/* ---------- szablon kadru: przybliżenie, wysokość, szkielet, ramka przycięcia ---------- */
let szNr = 0, szTryb = null;   // szTryb: "rysuj" (nowa ramka) albo {start, ramka} przy przesuwaniu
const POLACZENIA = [[11,12],[11,23],[12,24],[23,24],[11,13],[13,15],[12,14],[14,16],[23,25],[25,27],[24,26],[26,28],[7,8],[0,7],[0,8]];
function szkielet(g, W, H, typ){
  const wz = wzor(typ || FM.typ);
  if(wz){
    const L = CEL.s * H, X = p => [W / 2 + L * p[0], CEL.y * H + L * p[1]], M = wz.M, W8 = wagiTypu(typ || FM.typ);
    g.save(); g.strokeStyle = "rgba(77,183,201,.95)"; g.fillStyle = "rgba(77,183,201,.95)"; g.lineWidth = Math.max(2, W / 220); g.lineCap = "round";
    POLACZENIA.forEach(([a, b]) => { if(!M[a] || !M[b]) return; const A = X(M[a]), B = X(M[b]); g.beginPath(); g.moveTo(A[0], A[1]); g.lineTo(B[0], B[1]); g.stroke(); });
    if(M[0] && M[7] && M[8]){ const c = X(M[0]); g.beginPath(); g.arc(c[0], c[1], L * Math.max(0.12, Math.hypot(M[7][0] - M[8][0], M[7][1] - M[8][1]) * 0.75), 0, Math.PI * 2); g.stroke(); }
    // kropki: im większa, tym bardziej punkt liczy się przy dopasowaniu
    M.forEach((p, i) => { const w = W8[i] || 0; if(!p || !w) return; const c = X(p); g.beginPath(); g.arc(c[0], c[1], Math.max(2, W / 260) * (1 + w), 0, Math.PI * 2); g.fill(); });
    g.setLineDash([6, 6]); g.globalAlpha = .6; g.beginPath(); g.moveTo(0, CEL.y * H); g.lineTo(W, CEL.y * H); g.stroke(); g.restore();
    return;
  }
  const cx = W / 2, cy = CEL.y * H, L = CEL.s * H;
  const ram = cy - L / 2, bio = cy + L / 2;
  g.save(); g.strokeStyle = "rgba(77,183,201,.95)"; g.lineWidth = Math.max(2, W / 200); g.lineCap = "round";
  const linia = (...p) => { g.beginPath(); g.moveTo(p[0], p[1]); for(let i = 2; i < p.length; i += 2) g.lineTo(p[i], p[i + 1]); g.stroke(); };
  g.beginPath(); g.arc(cx, ram - L * 0.42, L * 0.2, 0, Math.PI * 2); g.stroke();          // głowa
  linia(cx, ram - L * 0.22, cx, ram);                                                         // szyja
  linia(cx - L * 0.45, ram, cx + L * 0.45, ram);                                              // barki
  linia(cx - L * 0.3, bio, cx + L * 0.3, bio);                                                // biodra
  linia(cx - L * 0.45, ram, cx - L * 0.3, bio); linia(cx + L * 0.45, ram, cx + L * 0.3, bio); // tułów
  linia(cx - L * 0.45, ram, cx - L * 0.55, ram + L * 0.6, cx - L * 0.58, ram + L * 1.15);     // ręce
  linia(cx + L * 0.45, ram, cx + L * 0.55, ram + L * 0.6, cx + L * 0.58, ram + L * 1.15);
  linia(cx - L * 0.2, bio, cx - L * 0.25, bio + L * 0.85, cx - L * 0.27, bio + L * 1.7);      // nogi
  linia(cx + L * 0.2, bio, cx + L * 0.25, bio + L * 0.85, cx + L * 0.27, bio + L * 1.7);
  g.setLineDash([6, 6]); g.globalAlpha = .6; linia(0, cy, W, cy); g.restore();
}
async function rysujSzablon(){
  const c = $("szCanvas"); if(!c) return;
  synchCEL();
  const [Wf, Hf] = formatWH(); if(c.width !== Wf / 2 || c.height !== Hf / 2){ c.width = Wf / 2; c.height = Hf / 2; }
  const g = c.getContext("2d"), W = c.width, H = c.height, kl = plan().kl;
  $("szS").value = CEL.s; $("szY").value = CEL.y; $("szSv").textContent = `(tułów = ${Math.round(CEL.s * 100)}% wysokości)`; $("szYv").textContent = `(${Math.round(CEL.y * 100)}% od góry)`;
  $("szPrzytnij").checked = FM.przytnij !== false;
  g.fillStyle = "#000"; g.fillRect(0, 0, W, H);
  szNr = Math.min(Math.max(szNr, 0), Math.max(kl.length - 1, 0));
  $("szNr").textContent = kl.length ? `zdjęcie ${szNr + 1} z ${kl.length} · ${krotko(kl[szNr].data)}` : "brak zdjęć";
  if(kl.length) rysujKlatke(g, await obraz(kl[szNr]), kl[szNr], W, H);
  g.save(); g.strokeStyle = "rgba(255,255,255,.35)"; g.lineWidth = 1;                         // krawędzie wszystkich zdjęć
  kl.forEach(z => { const q = geom(z, W, H); g.strokeRect(q.ox, q.oy, q.w, q.h); }); g.restore();
  const r = ramkaKoncowa(kl, W, H);
  g.save(); g.fillStyle = "rgba(0,0,0,.55)"; g.beginPath(); g.rect(0, 0, W, H); g.rect(r.x, r.y, r.w, r.h); g.fill("evenodd");
  g.strokeStyle = "#34C759"; g.lineWidth = 3; g.strokeRect(r.x, r.y, r.w, r.h); g.restore();
  if($("szSzkielet").checked) szkielet(g, W, H);
  const reczna = FM.ramka && FM.ramka.w > 0, auto = !reczna && FM.przytnij !== false && ramkaAuto(kl, W, H);
  $("szInfo").textContent = reczna ? "Film używa Twojej ramki. Przeciągnij ją palcem, żeby przesunąć." :
    auto ? `Przycięte automatycznie do części wspólnej wszystkich ${kl.length} zdjęć: w filmie nie będzie widać krawędzi.` :
    FM.przytnij !== false && kl.length ? "Zdjęcia za bardzo się różnią, żeby przyciąć automatycznie: popraw kadry pojedynczych zdjęć albo narysuj ramkę." : "Bez przycięcia.";
  $("szRysuj").setAttribute("aria-pressed", String(szTryb === "rysuj")); $("szRysuj").textContent = szTryb === "rysuj" ? "▭ Przeciągnij po podglądzie…" : "▭ Narysuj własną ramkę";
}
function szZmiana(){ zapiszFM(); rysujSzablon(); pokazKlatke(0); }
$("szS").oninput = () => { FM.celS = +$("szS").value; rysujSzablon(); };
$("szY").oninput = () => { FM.celY = +$("szY").value; rysujSzablon(); };
$("szS").onchange = $("szY").onchange = szZmiana;
$("szSzkielet").onchange = () => rysujSzablon();
$("szPrzytnij").onchange = () => { FM.przytnij = $("szPrzytnij").checked; szZmiana(); };
$("szPoprz").onclick = () => { szNr--; rysujSzablon(); };
$("szNast").onclick = () => { szNr++; rysujSzablon(); };
$("szUsun").onclick = () => { FM.ramka = null; szTryb = null; szZmiana(); };
$("szReset").onclick = () => { FM.celS = 0.26; FM.celY = 0.44; FM.ramka = null; FM.przytnij = true; szTryb = null; szZmiana(); };
$("szRysuj").onclick = () => { szTryb = szTryb === "rysuj" ? null : "rysuj"; rysujSzablon(); };
(() => {
  const c = $("szCanvas"); if(!c) return;
  const pkt = e => { const b = c.getBoundingClientRect(); return {x:(e.clientX - b.left) / b.width, y:(e.clientY - b.top) / b.height}; };
  let akcja = null;
  c.addEventListener("pointerdown", e => {
    const p = pkt(e), m = FM.ramka;
    if(szTryb === "rysuj") akcja = {typ:"nowa", p0:p};
    else if(m && m.w > 0 && p.x >= m.x && p.x <= m.x + m.w && p.y >= m.y && p.y <= m.y + m.w * 1) akcja = {typ:"ruch", p0:p, m0:Object.assign({}, m)};
    else return;
    c.setPointerCapture(e.pointerId); e.preventDefault();
  });
  c.addEventListener("pointermove", e => {
    if(!akcja) return; const p = pkt(e);
    // ramka ma proporcje kadru: w ułamkach szerokości i wysokości jej „w” jest wspólne (h = w w ułamkach wysokości)
    if(akcja.typ === "nowa"){
      const w = Math.min(1, Math.max(0.15, Math.max(Math.abs(p.x - akcja.p0.x), Math.abs(p.y - akcja.p0.y))));
      const x = p.x < akcja.p0.x ? akcja.p0.x - w : akcja.p0.x, y = p.y < akcja.p0.y ? akcja.p0.y - w : akcja.p0.y;
      FM.ramka = {x:Math.min(Math.max(x, 0), 1 - w), y:Math.min(Math.max(y, 0), 1 - w), w};
    } else {
      const m = akcja.m0; FM.ramka = {x:Math.min(Math.max(m.x + p.x - akcja.p0.x, 0), 1 - m.w), y:Math.min(Math.max(m.y + p.y - akcja.p0.y, 0), 1 - m.w), w:m.w};
    }
    FM.ramka = {x:+FM.ramka.x.toFixed(4), y:+FM.ramka.y.toFixed(4), w:+FM.ramka.w.toFixed(4)};
    rysujSzablon();
  });
  const koniec = () => { if(!akcja) return; akcja = null; szTryb = null; szZmiana(); };
  c.addEventListener("pointerup", koniec); c.addEventListener("pointercancel", koniec);
})();

/* ---------- render na Raspberry: zlecenie i lista gotowych filmów ---------- */
function opisFilmu(){
  const k = plan().kl, typ = NAZWA[FM.typ] || FM.typ;
  if(FM.tryb === "pp") return k.length === 2 ? `${typ} · przed i po: ${krotko(k[0].data)} → ${krotko(k[1].data)}` : typ;
  return k.length ? `${typ} · seria ${krotko(k[0].data)} → ${krotko(k[k.length - 1].data)} · ${k.length} zdj., co ${FM.co} dni` : typ;
}
$("fmPi").onclick = async () => {
  const k = plan().kl;
  if(!k.length){ $("fmStatus").textContent = "Najpierw wybierz zdjęcia do filmu."; return; }
  $("fmPi").disabled = true;
  try{ await post(API + "/render", {film:FM, ids:k.map(z => z.id), opis:opisFilmu(), geo:Object.fromEntries(k.map(z => [z.id, dopasowanie(z)]).filter(([, d]) => d).map(([id, d]) => [id, [d.s, d.tx, d.ty]]))}); $("fmStatus").textContent = "Zlecono render na Raspberry ✓ Film pojawi się na liście poniżej, możesz zamknąć stronę."; }
  catch(e){ $("fmStatus").textContent = "Nie udało się zlecić renderu: " + e.message; }
  $("fmPi").disabled = false; listaFilmow();
};
const BLOBY = {};
let pollFilmow = null;
async function listaFilmow(){
  const box = $("fmFilmy"); if(!box) return;
  let lista = [];
  try{ lista = await (await fetch(API + "/filmy", {cache:"no-store"})).json(); }catch(e){ box.innerHTML = ""; box.append(el("p", {class:"err small", text:"Nie udało się wczytać listy filmów."})); return; }
  box.innerHTML = "";
  if(!lista.length) box.append(el("p", {class:"muted small", text:"Jeszcze nie ma filmów. Ustaw film powyżej i kliknij „Renderuj na Raspberry”."}));
  lista.forEach(m => {
    const url = `${API}/film/${m.id}.mp4`, nazwa = `progres-${m.utworzono.slice(0, 10)}-${m.id.slice(0, 6)}.mp4`;
    const stan = {oczekuje:["q", "w kolejce"], renderuje:["run", `renderuje ${m.postep || 0}%`], gotowe:["ok", "gotowe"], blad:["err", "błąd"]}[m.status] || ["q", m.status];
    const d = new Date(m.utworzono), kiedy = `${d.getDate()} ${MIES[d.getMonth()]}, ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    const info = [kiedy]; if(m.rozmiar) info.push((m.rozmiar / 1e6).toFixed(1).replace(".", ",") + " MB"); if(m.czas_renderu) info.push(`render ${m.czas_renderu} s`);
    const wiersz = el("div", {class:"film"}, el("div", {class:"t"}, m.opis || "Film", el("span", {class:"stan " + stan[0], text:stan[1]})), el("div", {class:"m", text:info.join(" · ")}));
    if(m.status === "renderuje") wiersz.append(el("div", {class:"pasek"}, el("i", {style:`width:${m.postep || 0}%`})));
    if(m.status === "blad") wiersz.append(el("div", {class:"m err", text:m.blad || ""}));
    const akcje = el("div", {class:"row", style:"margin-top:6px"});
    if(m.status === "gotowe"){
      akcje.append(el("button", {class:"btn", text:"▶ Obejrzyj", onclick:() => { const b = $("modalBox"); b.innerHTML = ""; $("modal").hidden = false;
        b.append(el("video", {src:url, controls:"", playsinline:"", autoplay:""}), el("div", {class:"row", style:"justify-content:center"}, el("button", {class:"btn", text:"Zamknij", onclick:zamknij}))); }}),
        el("a", {class:"btn primary", href:url, download:nazwa, text:"⬇ Pobierz"}));
      if(navigator.canShare){
        const ud = el("button", {class:"btn", text:"📤 Udostępnij / Zapisz w Zdjęciach"});
        ud.onclick = async () => {
          // iOS wymaga, żeby udostępnienie było bezpośrednio po dotknięciu: najpierw pobieramy film, potem drugie dotknięcie udostępnia
          if(!BLOBY[m.id]){ ud.disabled = true; ud.textContent = "Przygotowuję…";
            try{ const bl = await (await fetch(url)).blob(); BLOBY[m.id] = new File([bl], nazwa, {type:"video/mp4"}); }catch(e){}
            ud.disabled = false; ud.textContent = "📤 Dotknij jeszcze raz, żeby udostępnić"; return; }
          if(navigator.canShare({files:[BLOBY[m.id]]})) navigator.share({files:[BLOBY[m.id]], title:"Progres"}).catch(() => {});
        };
        akcje.append(ud);
      }
    }
    if(m.status !== "renderuje") akcje.append(el("button", {class:"btn bad", text:"Usuń", onclick:async () => { if(!confirm("Usunąć ten film?")) return; await post(`${API}/film/${m.id}`, {usun:true}); listaFilmow(); }}));
    wiersz.append(akcje); box.append(wiersz);
  });
  clearTimeout(pollFilmow);
  if(lista.some(m => m.status === "oczekuje" || m.status === "renderuje")) pollFilmow = setTimeout(() => { if(!$("film").hidden) listaFilmow(); }, 3000);
}

/* rysuje chwilę s filmu (do testów porównujących z renderem na Pi) */
async function rysujChwile(s){
  synchCEL(); const P = plan(), k = P.kl; if(!k.length) return;
  const imgs = await Promise.all(k.map(obraz)), c = $("fmCanvas"), g = c.getContext("2d"), W = c.width, H = c.height, rk = ramkaKoncowa(k, W, H), st = P.stan(Math.min(s, P.dl - 1e-6));
  g.fillStyle = "#000"; g.fillRect(0, 0, W, H);
  wRamce(g, rk, W, () => { rysujKlatke(g, imgs[st.a], k[st.a], W, H); if(st.b != null && st.w > 0) rysujKlatke(g, imgs[st.b], k[st.b], W, H, st.w); });
  napis(g, st.napis.map(i => k[i]), W, H);
}
window.__progres = {pokazKlatke, klatki, plan, ramkaKoncowa, geom, rysujChwile, wzor, dopasowanie, FM:() => FM};   // do testów automatycznych

/* ---------- start ---------- */
(async () => {
  try{ await wczytaj(); }catch(e){ document.querySelector("main .wrap").prepend(el("p", {class:"err", text:"Nie udało się wczytać danych z Raspberry (" + e.message + ")."})); }
  ustawFormularz(dzis());
  let z = null; try{ z = localStorage.getItem("progres:zakladka"); }catch(e){}
  if(z && document.getElementById(z)) pokaz(z);
})();
