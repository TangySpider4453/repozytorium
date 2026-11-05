/* Wysuwany „Raport obciążenia” (dane z /api/obciazenie): każdy przedział, w którym CPU > 60 %, temperatura > 55 °C
   albo RAM > 60 %, z maksimum, średnią i procesami, które najwięcej zjadały. Zwinięty pokazuje tylko „!”, gdy coś
   trwa teraz. Używany na stronie głównej portalu i na /strony/zdrowie/; stan rozwinięcia i filtr pamięta przeglądarka. */
(function(){
  const st = document.createElement("style");
  st.textContent = `.ob-det>summary{cursor:pointer;list-style:none;display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-weight:700}
    .ob-det>summary::-webkit-details-marker{display:none}
    .ob-det>summary::before{content:"▸";display:inline-block;width:1em;transition:transform .2s;color:var(--muted,#56606e)}
    .ob-det[open]>summary::before{transform:rotate(90deg)}
    .ob-tyt{font-size:19px} .ob-pod{font-weight:400;font-size:14px;color:var(--muted,#56606e)}
    .ob-wykrz{display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:50%;background:#ef4444;color:#fff;
      font:800 14px/1 system-ui,-apple-system,sans-serif;border:1.5px solid rgba(120,128,138,.95)}
    .ob-wykrz.warn{background:#facc15;color:#111}
    .ob-in{margin-top:10px;display:flex;flex-direction:column;gap:12px}
    .ob-teraz{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:15px}
    .ob-teraz b{font-variant-numeric:tabular-nums} .ob-ponad{color:var(--bad,#c03442)}
    .ob-trwa{border:1.5px solid #ef4444;border-radius:10px;padding:8px 12px}
    .ob-trwa .t{font-weight:700;color:var(--bad,#c03442)}
    .ob-doba{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
    .ob-doba>div{background:var(--soft,rgba(128,128,128,.16));border-radius:10px;padding:8px 10px;min-width:0}
    .ob-doba .k{font-size:13px;color:var(--muted,#56606e)} .ob-doba .v{font-weight:700;font-variant-numeric:tabular-nums}
    @media (max-width:480px){.ob-doba{grid-template-columns:1fr}}
    .ob-filtr{display:flex;flex-wrap:wrap;gap:6px}
    .ob-filtr button{font:inherit;font-size:14px;font-weight:700;border-radius:999px;padding:3px 12px;border:1.5px solid var(--line,#d5dbe3);
      background:transparent;color:inherit;cursor:pointer}
    .ob-filtr button.on{background:#2563eb;border-color:#2563eb;color:#fff}
    .ob-lista{display:flex;flex-direction:column}
    .ob-p{border-top:1px solid var(--line,#d5dbe3);padding:8px 0;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:2px 10px}
    .ob-p:first-child{border-top:0}
    .ob-p .k{font-weight:700} .ob-p .m{font-weight:700;font-variant-numeric:tabular-nums;text-align:right}
    .ob-p .o{grid-column:1/-1;font-size:14px;color:var(--muted,#56606e);overflow-wrap:anywhere}
    .ob-uw{font-size:13.5px;color:var(--muted,#56606e);margin:0}`;
  document.head.appendChild(st);

  const TYP = {cpu:["Procesor", "%"], temp:["Temperatura", " °C"], ram:["RAM", "%"]};
  const MIES = ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"];
  const pam = (k, v) => { try{ if(v === undefined) return localStorage.getItem("obciazenie:" + k); localStorage.setItem("obciazenie:" + k, v); }catch(e){ return null; } };
  let otwarte = pam("otwarte") === "1", filtr = pam("filtr") || "wszystko";
  const g = s => s.slice(11, 16);
  function kiedy(s){
    const d = new Date(s), dzis = new Date(); dzis.setHours(0, 0, 0, 0);
    const dz = Math.round((new Date(d.getFullYear(), d.getMonth(), d.getDate()) - dzis) / 864e5);
    return (dz === 0 ? "dziś" : dz === -1 ? "wczoraj" : `${d.getDate()} ${MIES[d.getMonth()]}`) + " " + g(s);
  }
  function ile(s){ s = Math.round(s); return s < 60 ? `${s} s` : s < 3600 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${Math.floor(s / 3600)} h ${Math.round(s % 3600 / 60)} min`; }
  const liczba = (v, typ) => v == null ? "–" : String(Math.round(v)) + TYP[typ][1];
  const top = t => (t || []).map(x => x.mb != null ? `${x.nazwa} ${x.mb} MB` : `${x.nazwa} ${x.cpu}%`).join(", ") || "–";
  const el = (t, k, tekst) => { const e = document.createElement(t); if(k) e.className = k; if(tekst != null) e.textContent = tekst; return e; };

  function panel(d){
    const p = d.progi, det = el("details", "ob-det");
    det.open = otwarte;
    det.addEventListener("toggle", () => { otwarte = det.open; pam("otwarte", det.open ? "1" : "0"); });
    const sum = el("summary");
    sum.append(el("span", "ob-tyt", "Raport obciążenia"));
    if(d.trwa.length){
      const w = el("span", "ob-wykrz" + (d.trwa.every(t => t.typ === "ram") ? " warn" : ""), "!");
      w.title = "Teraz: " + d.trwa.map(t => `${TYP[t.typ][0]} ponad ${t.prog}${TYP[t.typ][1]}`).join(", ");
      w.setAttribute("aria-label", w.title);
      sum.append(w);
    }
    sum.append(el("span", "ob-pod", `CPU > ${p.cpu}%, temperatura > ${p.temp} °C, RAM > ${p.ram}%`));
    det.append(sum);
    const wn = el("div", "ob-in");

    const tz = d.teraz || {}, rz = el("div", "ob-teraz");
    rz.append(el("span", "", "Teraz:"));
    for(const typ of ["cpu", "temp", "ram"]){
      const s = el("span", "", TYP[typ][0] + " "), b = el("b", tz[typ] > p[typ] ? "ob-ponad" : "", liczba(tz[typ], typ));
      s.append(b); rz.append(s);
    }
    wn.append(rz);

    for(const t of d.trwa){
      const box = el("div", "ob-trwa");
      box.append(el("div", "t", `Trwa: ${TYP[t.typ][0]} ponad ${t.prog}${TYP[t.typ][1]} od ${g(t.od)} (${ile(t.sek)})`),
        el("div", "", `max ${liczba(t.max, t.typ)} o ${t.max_czas ? g(t.max_czas) : "–"}, średnio ${liczba(t.srednia, t.typ)}`),
        el("div", "ob-uw", "Najwięcej zjada: " + top(t.top)));
      wn.append(box);
    }

    const doba = el("div", "ob-doba");
    for(const typ of ["cpu", "temp", "ram"]){
      const x = d.doba[typ], k = el("div");
      k.append(el("div", "k", `${TYP[typ][0]}: ostatnie 24 h`),
        el("div", "v", x.ile ? `${x.ile}× · razem ${ile(x.sek)}` : "ani razu"),
        el("div", "k", x.max != null ? `najwięcej ${liczba(x.max, typ)}` : `próg ${p[typ]}${TYP[typ][1]}`));
      doba.append(k);
    }
    wn.append(doba);

    const fl = el("div", "ob-filtr"), lista = el("div", "ob-lista");
    const rysuj = () => {
      lista.replaceChildren();
      const pr = d.przedzialy.filter(x => filtr === "wszystko" || x.typ === filtr);
      if(!pr.length) lista.append(el("p", "ob-uw", "Jeszcze nie było takich przedziałów."));
      for(const x of pr.slice(0, 60)){
        const w = el("div", "ob-p");
        w.append(el("div", "k", `${TYP[x.typ][0]} · ${kiedy(x.od)}–${g(x.do)}`), el("div", "m", `max ${liczba(x.max, x.typ)}`),
          el("div", "o", `${ile(x.sek)}, średnio ${liczba(x.srednia, x.typ)}, szczyt o ${x.max_czas ? g(x.max_czas) : "–"} · ${x.typ === "ram" ? "najwięcej RAM" : "najwięcej CPU"}: ${top(x.top)}`));
        lista.append(w);
      }
      fl.querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.f === filtr));
    };
    for(const [f, n] of [["wszystko", "Wszystko"], ["cpu", "Procesor"], ["temp", "Temperatura"], ["ram", "RAM"]]){
      const b = el("button", "", n); b.type = "button"; b.dataset.f = f;
      b.onclick = () => { filtr = f; pam("filtr", f); rysuj(); };
      fl.append(b);
    }
    rysuj();
    wn.append(fl, lista, el("p", "ob-uw", "Procesy: 100% = jeden pełny rdzeń (Pi ma 4). Pełne logi: NAS → Raspberry/Logi/cpu.log, temperatura.log, ram.log."));
    det.append(wn);
    return det;
  }
  window.Obciazenie = {panel};
})();
