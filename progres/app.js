/* Progres sylwetki: pomiary z wagi, zdjęcia z typem (przód / bok / biceps / tył), wykresy i film z postępu.
   Dane: /api/progres (Raspberry Pi). Rozpoznawanie sylwetki: MediaPipe Pose (pliki w ./mp/, działa w przeglądarce).
   Wyrównanie: z barków i bioder liczymy środek tułowia (cx, cy) i jego długość (s, ułamek wysokości zdjęcia);
   w filmie każda klatka jest skalowana i przesuwana tak, żeby tułów był zawsze w tym samym miejscu i tej samej wielkości. */

const TYPY = [["przod", "Przód"], ["bok", "Bok"], ["biceps", "Przód + biceps"], ["tyl", "Tył"], ["inne", "Inne"]];
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
    return {cx:+((sh.x + hp.x) / 2 / W).toFixed(4), cy:+((sh.y + hp.y) / 2 / H).toFixed(4), s:+(tul / H).toFixed(4), ok};
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
function ustawFormularz(data){
  $("fData").value = data;
  const w = DANE.wpisy[data];
  $("fMasa").value = w && w.masa != null ? pl(w.masa) : "";
  $("fFat").value = w && w.fat != null ? pl(w.fat) : "";
  $("fMuscle").value = w && w.muscle != null ? pl(w.muscle) : "";
  $("fNotatka").value = w && w.notatka || "";
  const ile = DANE.zdjecia.filter(z => z.data === data).length;
  $("fIstnieje").hidden = !(w || ile);
  $("fIstnieje").textContent = `Dla ${krotko(data)} są już zapisane ${w ? "wyniki z wagi" : ""}${w && ile ? " i " : ""}${ile ? ile + " zdj." : ""}. Zapis podmieni wyniki, a zdjęcia dopisze.`;
  NOWE.forEach(n => { if(!n.wlasnaData) n.data = data; rysujNowe(n); });
}
$("fData").onchange = () => ustawFormularz($("fData").value || dzis());

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
      n.pose = await wykryj(n.duzy);
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
  if(n.exif && n.exif !== n.data) prawa.append(el("button", {class:"btn small", style:"margin-top:6px;padding:6px 10px", text:`Użyj daty ze zdjęcia: ${krotko(n.exif)}`, onclick:() => { n.data = n.exif; n.wlasnaData = true; rysujNowe(n); }}));
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
      fd.append("data", n.data); fd.append("typ", n.typ); fd.append("pose", JSON.stringify(n.pose || null));
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
function wykres(tytul, serie, jedn){
  // serie: [{nazwa, kolor, pkt:[[data, wartosc]]}] - jedna oś y, wspólna jednostka
  const all = serie.flatMap(s => s.pkt);
  const box = el("div", {class:"chart"}, el("h3", {text:tytul}));
  if(new Set(all.map(p => p[0])).size < 2){ box.append(el("p", {class:"muted small", text:"Wykres pojawi się po pomiarach z co najmniej dwóch dni."})); return box; }
  const W = Math.max(300, Math.round(($("wykresy").clientWidth || 600) - 34)), H = 190, L = 40, R = serie.length > 1 ? 100 : 64, T = 10, B = 24;
  const xs = all.map(p => pd(p[0]).getTime()), ys = all.map(p => p[1]);
  let x0 = Math.min(...xs), x1 = Math.max(...xs); if(x1 === x0) x1 = x0 + 864e5;
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
  serie.forEach(s => {
    if(!s.pkt.length) return;
    const d = s.pkt.map((p, i) => (i ? "L" : "M") + X(pd(p[0]).getTime()).toFixed(1) + "," + Y(p[1]).toFixed(1)).join("");
    svg.append(S("path", {d, fill:"none", stroke:s.kolor, "stroke-width":2, "stroke-linejoin":"round", "stroke-linecap":"round"}));
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
function rysujHistorie(){
  const wpisy = Object.entries(DANE.wpisy).sort((a, b) => a[0].localeCompare(b[0]));
  const ser = k => wpisy.filter(([, w]) => w[k] != null).map(([d, w]) => [d, w[k]]);
  const cs = getComputedStyle(document.documentElement), s1 = cs.getPropertyValue("--s1").trim(), s2 = cs.getPropertyValue("--s2").trim();
  $("wykresy").innerHTML = ""; $("wykresy").append(el("h2", {text:"Wykresy"}),
    wykres("Masa ciała (kg)", [{nazwa:"masa", kolor:s1, pkt:ser("masa")}], " kg"),
    wykres("Skład ciała (%)", [{nazwa:"tłuszcz", kolor:s1, pkt:ser("fat")}, {nazwa:"mięśnie", kolor:s2, pkt:ser("muscle")}], "%"));
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
const CEL = {y:0.44, s:0.26};   // środek tułowia na 44% wysokości kadru, tułów = 26% wysokości kadru
function rysujKlatke(g, img, z, W, H, alfa = 1){
  const iw = img.naturalWidth || img.width, ih = img.naturalHeight || img.height;
  const r = z.reczne || {}, p = z.pose;
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
  g.globalAlpha = alfa; g.drawImage(img, ox, oy, iw * k, ih * k); g.globalAlpha = 1;
}
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
  Object.assign(FM, DANE.ustawienia.film || {});
  const box = $("modalBox"); box.innerHTML = ""; $("modal").hidden = false;
  const [Wf, Hf] = formatWH();
  const c = el("canvas", {width:Wf / 2, height:Hf / 2}), g = c.getContext("2d");
  const r = Object.assign({dx:0, dy:0, z:1}, z.reczne || {});
  const poprz = DANE.zdjecia.filter(q => q.typ === z.typ && q.id !== z.id && q.data <= z.data).sort((a, b) => b.data.localeCompare(a.data))[0];
  const img = await obraz(z), img2 = poprz ? await obraz(poprz) : null;
  const duch = el("input", {type:"range", min:0, max:0.8, step:0.05, value:img2 ? 0.4 : 0});
  const rys = () => { g.fillStyle = "#000"; g.fillRect(0, 0, c.width, c.height);
    rysujKlatke(g, img, Object.assign({}, z, {reczne:r}), c.width, c.height);
    if(img2 && +duch.value) rysujKlatke(g, img2, poprz, c.width, c.height, +duch.value);
    g.strokeStyle = "rgba(52,199,89,.7)"; g.setLineDash([6, 6]); g.beginPath(); g.moveTo(c.width / 2, 0); g.lineTo(c.width / 2, c.height);
    const y = CEL.y * c.height; g.moveTo(0, y); g.lineTo(c.width, y); g.stroke(); g.setLineDash([]); };
  duch.oninput = rys;
  const krok = (k, v) => () => { r[k] = +(r[k] + v).toFixed(3); rys(); };
  let drag = null;
  c.onpointerdown = e => { drag = {x:e.clientX, y:e.clientY, dx:r.dx, dy:r.dy}; c.setPointerCapture(e.pointerId); };
  c.onpointermove = e => { if(!drag) return; const sc = c.getBoundingClientRect().height * CEL.s; r.dx = +(drag.dx + (e.clientX - drag.x) / sc).toFixed(3); r.dy = +(drag.dy + (e.clientY - drag.y) / sc).toFixed(3); rys(); };
  c.onpointerup = () => drag = null;
  const zapisz = async () => { const reczne = (r.dx || r.dy || r.z !== 1) ? r : null; DANE = await post(`${API}/zdjecie/${z.id}`, {reczne}); if(poZapisie) poZapisie(); else rysujHistorie(); zamknij(); };
  const wykryjPon = async () => { status.textContent = "Rozpoznaję…"; const cc = naCanvas(img, 1800); const pose = await wykryj(cc);
    if(!pose){ status.textContent = "Nie udało się rozpoznać sylwetki. Ustaw kadr ręcznie."; return; }
    DANE = await post(`${API}/zdjecie/${z.id}`, {pose}); z.pose = pose; status.textContent = "✓ rozpoznano"; rys(); };
  const status = el("p", {class:"small muted", text:z.pose ? "Sylwetka rozpoznana automatycznie. Popraw, jeśli trzeba." : "Sylwetka nierozpoznana: przesuń i przybliż ręcznie."});
  box.append(el("h2", {text:`Kadrowanie: ${NAZWA[z.typ]}, ${krotko(z.data)}`}), status,
    el("div", {class:"stage"}, c),
    el("p", {class:"small muted", style:"margin:0", text:"Przeciągnij zdjęcie palcem. Zielone linie to miejsce tułowia. " + (img2 ? "Półprzezroczyste jest poprzednie zdjęcie tego typu." : "")}),
    img2 ? el("label", {class:"f small", style:"margin:6px 0"}, `Poprzednie zdjęcie (${krotko(poprz.data)}) – przezroczystość`, duch) : null,
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
let FM = {typ:"przod", od:"", do:"", co:7, sek:0.5, format:"4:5", przejscie:0.25, napisy:true};
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
function filmUstaw(){
  Object.assign(FM, DANE.ustawienia.film || {});
  const ch = $("fmTyp"); ch.innerHTML = "";
  TYPY.forEach(([k, n]) => { const ile = DANE.zdjecia.filter(z => z.typ === k).length; if(!ile && k !== FM.typ) return;
    ch.append(el("button", {"aria-pressed":String(FM.typ === k), text:`${n} (${ile})`, onclick:() => { FM.typ = k; zapiszFM(); filmUstaw(); }})); });
  $("fmOd").value = FM.od; $("fmDo").value = FM.do; $("fmCo").value = FM.co; $("fmSek").value = String(FM.sek).replace(".", ",");
  $("fmFormat").value = FM.format; $("fmPrzejscie").value = String(FM.przejscie); $("fmNapisy").checked = !!FM.napisy;
  const [W, H] = formatWH(); const c = $("fmCanvas"); if(c.width !== W || c.height !== H){ c.width = W; c.height = H; }
  const k = klatki(), sek = Math.max(0.1, FM.sek);
  $("fmInfo").textContent = k.length ? `${k.length} klatek (${krotko(k[0].data)} → ${krotko(k[k.length - 1].data)}), film ok. ${pl(k.length * sek, 1)} s.` : "Brak zdjęć tego rodzaju w wybranym zakresie.";
  const kl = $("fmKlatki"); kl.innerHTML = "";
  k.forEach(z => kl.append(el("button", {class:z.pose || z.reczne ? "" : "bez", onclick:() => kadruj(z, filmUstaw)}, el("img", {src:plik(z, true), alt:"", loading:"lazy"}), krotko(z.data).replace(/ \d{4}$/, ""))));
  if(k.length) pokazKlatke(0);
}
function zapiszFM(){ post(API + "/ustawienia", {film:FM}).catch(() => {}); DANE.ustawienia.film = Object.assign({}, FM); }
["fmOd", "fmDo", "fmCo", "fmSek", "fmFormat", "fmPrzejscie", "fmNapisy"].forEach(id => $(id).onchange = () => {
  FM.od = $("fmOd").value; FM.do = $("fmDo").value; FM.co = Math.max(1, parseInt($("fmCo").value) || 1);
  const s = num($("fmSek").value); FM.sek = Number.isFinite(s) && s > 0 ? Math.min(s, 10) : 0.5;
  FM.format = $("fmFormat").value; FM.przejscie = +$("fmPrzejscie").value; FM.napisy = $("fmNapisy").checked;
  zapiszFM(); filmUstaw();
});
function napis(g, z, W, H){
  if(!FM.napisy) return;
  const w = DANE.wpisy[z.data] || {}, czesci = [krotko(z.data)];
  if(w.masa != null) czesci.push(pl(w.masa) + " kg"); if(w.fat != null) czesci.push(pl(w.fat) + "% tł."); if(w.muscle != null) czesci.push(pl(w.muscle) + "% mięśni");
  const t = czesci.join("  ·  "), fs = Math.round(W * 0.038);
  g.font = `700 ${fs}px "Alegreya Sans", sans-serif`; g.textAlign = "center"; g.textBaseline = "middle";
  const tw = g.measureText(t).width, y = H - fs * 1.6;
  g.fillStyle = "rgba(0,0,0,.55)"; g.beginPath(); g.roundRect ? g.roundRect(W / 2 - tw / 2 - fs * 0.7, y - fs * 0.85, tw + fs * 1.4, fs * 1.7, fs * 0.5) : g.rect(W / 2 - tw / 2 - fs * 0.7, y - fs * 0.85, tw + fs * 1.4, fs * 1.7); g.fill();
  g.fillStyle = "#fff"; g.fillText(t, W / 2, y);
}
async function pokazKlatke(i){
  const k = klatki(); if(!k[i]) return; const c = $("fmCanvas"), g = c.getContext("2d");
  const img = await obraz(k[i]); g.fillStyle = "#000"; g.fillRect(0, 0, c.width, c.height); rysujKlatke(g, img, k[i], c.width, c.height); napis(g, k[i], c.width, c.height);
}
/* odtwarzanie w czasie rzeczywistym (podgląd i nagrywanie używają tego samego) */
async function odtworz(onKoniec){
  const k = klatki(); if(!k.length) return;
  $("fmStatus").textContent = "Wczytuję zdjęcia…";
  const imgs = await Promise.all(k.map(obraz));
  const c = $("fmCanvas"), g = c.getContext("2d"), W = c.width, H = c.height, sek = Math.max(0.1, FM.sek), fade = Math.min(FM.przejscie, sek / 2);
  const total = k.length * sek + 0.6; let start = null;
  $("fmStatus").textContent = "";
  return new Promise(res => {
    const krok = t => {
      if(start == null) start = t;
      const el_ = (t - start) / 1000, i = Math.min(Math.floor(el_ / sek), k.length - 1), wKlatce = el_ - i * sek;
      g.fillStyle = "#000"; g.fillRect(0, 0, W, H);
      rysujKlatke(g, imgs[i], k[i], W, H);
      if(fade > 0 && i + 1 < k.length && wKlatce > sek - fade) rysujKlatke(g, imgs[i + 1], k[i + 1], W, H, (wKlatce - (sek - fade)) / fade);
      napis(g, k[i], W, H);
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
  const nazwa = `progres-${FM.typ}-${(klatki()[0] || {}).data || ""}.${ext}`;
  $("fmPobierz").innerHTML = ""; $("fmPobierz").append(el("a", {class:"btn primary", href:url, download:nazwa, text:"⬇ Zapisz film (" + (blob.size / 1e6).toFixed(1).replace(".", ",") + " MB)"}));
  $("fmStatus").textContent = "Gotowe. Na iPhonie/iPadzie możesz też przytrzymać film i wybrać „Zapisz”.";
  $("fmNagraj").disabled = $("fmPlay").disabled = false;
};

window.__progres = {pokazKlatke, klatki};   // do testów automatycznych

/* ---------- start ---------- */
(async () => {
  try{ await wczytaj(); }catch(e){ document.querySelector("main .wrap").prepend(el("p", {class:"err", text:"Nie udało się wczytać danych z Raspberry (" + e.message + ")."})); }
  ustawFormularz(dzis());
  let z = null; try{ z = localStorage.getItem("progres:zakladka"); }catch(e){}
  if(z && document.getElementById(z)) pokaz(z);
})();
