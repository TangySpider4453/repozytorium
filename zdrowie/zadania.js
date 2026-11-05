/* Wysuwany panel „Kopie zapasowe i zadania w tle” (dane z /api/zadania): kopia systemu na NAS, render filmów, zdjęcia na NAS,
   logi, połączenie z NAS, aktualizacje. Używany na stronie głównej portalu i na /strony/zdrowie/.
   Zadania.panel(dane) zwraca gotowy element; Zadania.trwa(dane) mówi, czy odświeżać częściej.
   Zwinięty pokazuje tylko „!” (błąd, NAS niedostępny) i procent tego, co trwa; stan rozwinięcia pamięta przeglądarka. */
(function(){
  const st = document.createElement("style");
  st.textContent = `.zd-det>summary{cursor:pointer;list-style:none;display:flex;align-items:center;gap:8px 10px;flex-wrap:wrap;font-weight:700}
    .zd-det>summary::-webkit-details-marker{display:none}
    .zd-det>summary::before{content:"▸";display:inline-block;width:1em;transition:transform .2s;color:var(--muted,#56606e)}
    .zd-det[open]>summary::before{transform:rotate(90deg)}
    .zd-det[open]>.zd-lista{margin-top:10px}
    .zd-tyt{font-size:19px} .zd-pod{font-weight:400;font-size:14px;color:var(--muted,#56606e)}
    .zd-wykrz{display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:50%;background:#ef4444;color:#fff;
      font:800 14px/1 system-ui,-apple-system,sans-serif;border:1.5px solid rgba(120,128,138,.95)}
    .zd-pill{font-size:13.5px;font-weight:700;border-radius:999px;padding:1px 10px;background:#2563eb;color:#fff;font-variant-numeric:tabular-nums}
    .zd-lista{display:flex;flex-direction:column}
    .zd-wiersz{display:grid;grid-template-columns:14px minmax(0,1fr);gap:10px;padding:10px 0;border-top:1px solid var(--line,#d5dbe3)}
    .zd-wiersz:first-child{border-top:0;padding-top:2px}
    .zd-kr{width:14px;height:14px;border-radius:50%;border:1.5px solid rgba(120,128,138,.95);margin-top:5px;background:#22c55e}
    .zd-kr.trwa{background:#3b82f6;animation:zd-puls 1.6s ease-in-out infinite} .zd-kr.zle{background:#ef4444} .zd-kr.brak{background:#9aa3ad}
    @keyframes zd-puls{50%{opacity:.45}}
    @media (prefers-reduced-motion:reduce){.zd-kr.trwa{animation:none}}
    .zd-gora{display:flex;flex-wrap:wrap;justify-content:space-between;gap:2px 12px;align-items:baseline}
    .zd-n{font-weight:700} .zd-s{font-weight:700;font-variant-numeric:tabular-nums}
    .zd-s.trwa{color:#2563eb} .zd-s.zle{color:var(--bad,#c03442)}
    .zd-pas{height:8px;background:var(--soft,rgba(128,128,128,.22));border-radius:4px;overflow:hidden;margin:6px 0 2px}
    .zd-pas i{display:block;height:100%;background:#3b82f6;transition:width .6s}
    .zd-o{font-size:14px;color:var(--muted,#56606e);overflow-wrap:anywhere}
    .zd-nas{font-size:14px;color:var(--muted,#56606e);margin:0 0 6px}`;
  document.head.appendChild(st);

  const MIES = ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"];
  function kiedy(s){
    if(!s) return "–";
    const d = new Date(s), dzis = new Date(); dzis.setHours(0, 0, 0, 0);
    const dz = Math.round((new Date(d.getFullYear(), d.getMonth(), d.getDate()) - dzis) / 864e5);
    const g = String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
    return (dz === 0 ? "dziś" : dz === -1 ? "wczoraj" : dz === 1 ? "jutro" : `${d.getDate()} ${MIES[d.getMonth()]}`) + " " + g;
  }
  function ile(s){
    s = Math.max(0, Math.round(s));
    return s < 60 ? `${s} s` : s < 3600 ? `${Math.round(s / 60)} min` : `${Math.floor(s / 3600)} h ${Math.round(s % 3600 / 60)} min`;
  }
  // stan jednego zadania: {klasa: trwa|ok|zle|brak, tekst, procent, szczegoly}
  function stan(z){
    if(z.id === "nas-bufor" && z.czeka && !z.trwa) return {klasa:"zle", tekst:`${z.czeka} plików czeka na Pi`, szczegoly:"NAS niedostępny: przeniosą się same, gdy wróci"};
    if(z.trwa){
      const p = z.procent, sz = [];
      let tekst = (z.faza || "trwa") + (p != null ? ` · ${p}%` : "");
      if(z.szacunek) sz.push("procent szacunkowy");
      if(z.pliki) sz.push(`pliki ${z.pliki.replace("/", " z ")}`);
      if(z.czeka) tekst = `przenoszę ${z.czeka} plików`;
      if(z.start){
        const up = (Date.now() - new Date(z.start)) / 1000;
        sz.push(`trwa ${ile(up)}`);
        if(p >= 3 && p < 100) sz.push(`zostało ok. ${ile(up * (100 - p) / p)}`);
      }
      if(z.cel) sz.push(z.cel);
      if(z.kolejka) sz.push(`w kolejce jeszcze ${z.kolejka}`);
      return {klasa:"trwa", tekst, procent:p, szczegoly:sz.join(" · ")};
    }
    if(z.id === "kopia-pi"){
      if(z.ostatni && z.ostatni.wynik === "blad") return {klasa:"zle", tekst:"ostatnia nie udała się", szczegoly:`próba ${kiedy(z.ostatni.czas)}`};
      if(z.udana) return {klasa:"ok", tekst:`ostatnia udana: ${kiedy(z.udana.czas)}`, szczegoly:`trwała ${ile(z.udana.sekundy)}`};
      return {klasa:"brak", tekst:"jeszcze nie było kopii"};
    }
    if(z.id === "nas-bufor") return {klasa:"ok", tekst:"wszystko na NAS"};
    if(z.id === "render"){
      if(z.kolejka) return {klasa:"trwa", tekst:`w kolejce: ${z.kolejka}`};
      return {klasa:z.wynik === "blad" ? "zle" : "ok", tekst:z.wynik === "blad" ? "ostatni film: błąd" : "nic do zrobienia"};
    }
    const BLAD = {"exit-code":"zakończone błędem", "timeout":"przekroczony czas", "signal":"przerwane", "core-dump":"awaria programu"};
    if(z.wynik && z.wynik !== "success") return {klasa:"zle", tekst:`ostatnio: ${BLAD[z.wynik] || "błąd (" + z.wynik + ")"}`};
    return {klasa:"ok", tekst:z.ostatnio ? "ostatnio OK" : "czeka"};
  }
  const el = (t, k, tekst) => { const e = document.createElement(t); if(k) e.className = k; if(tekst != null) e.textContent = tekst; return e; };
  let otwarte = false;
  try{ otwarte = localStorage.getItem("zadania:otwarte") === "1"; }catch(e){}
  const KROTKO = {"kopia-pi":"Kopia", "render":"Render", "nas-bufor":"Zdjęcia na NAS", "logi-na-nas":"Logi", "mc-autoupdate":"Aktualizacja MC", "apt-daily-upgrade":"Aktualizacje"};
  function panel(d){
    const det = el("details", "zd-det"), sum = el("summary"), box = el("div", "zd-lista");
    det.open = otwarte;
    det.addEventListener("toggle", () => { otwarte = det.open; try{ localStorage.setItem("zadania:otwarte", det.open ? "1" : "0"); }catch(e){} });
    sum.append(el("span", "zd-tyt", "Kopie zapasowe i zadania w tle"));
    const stany = d.zadania.map(z => [z, stan(z)]), zle = stany.filter(([, s]) => s.klasa === "zle");
    if(zle.length || (d.nas && !d.nas.ok)){
      const w = el("span", "zd-wykrz", "!");
      w.title = [d.nas && !d.nas.ok ? "NAS niedostępny" : null, ...zle.map(([z, s]) => `${z.nazwa}: ${s.tekst}`)].filter(Boolean).join("\n");
      w.setAttribute("aria-label", w.title); sum.append(w);
    }
    for(const [z, s] of stany) if(z.trwa) sum.append(el("span", "zd-pill", (KROTKO[z.id] || z.nazwa) + (s.procent != null ? ` ${s.procent}%` : "…")));
    const kopia = d.zadania.find(z => z.id === "kopia-pi");
    if(kopia && !kopia.trwa) sum.append(el("span", "zd-pod", kopia.udana ? `ostatnia kopia: ${kiedy(kopia.udana.czas)}` : "kopii jeszcze nie było"));
    det.append(sum, box);
    if(d.nas) box.append(el("p", "zd-nas", d.nas.ok
      ? `NAS połączony${d.nas.wolne_gb != null ? ` · wolne ${d.nas.wolne_gb} z ${d.nas.razem_gb} GB` : ""}`
      : "NAS niedostępny: zdjęcia i logi zapisują się na Pi, kopia systemu się nie zrobi"));
    for(const z of d.zadania){
      const s = stan(z), w = el("div", "zd-wiersz"), prawa = el("div");
      const gora = el("div", "zd-gora");
      gora.append(el("span", "zd-n", z.nazwa), el("span", "zd-s " + s.klasa, s.tekst));
      prawa.append(gora);
      if(s.klasa === "trwa" && s.procent != null){
        const pas = el("div", "zd-pas"), i = el("i"); i.style.width = Math.min(100, Math.max(2, s.procent)) + "%";
        pas.append(i); pas.setAttribute("role", "progressbar"); pas.setAttribute("aria-valuenow", s.procent); prawa.append(pas);
      }
      const o = [s.szczegoly, z.opis];
      if(!z.trwa && z.ostatnio && z.id !== "kopia-pi") o.push(`ostatnio ${kiedy(z.ostatnio)}`);
      if(z.nastepnie) o.push(`następnie ${kiedy(z.nastepnie)}`);
      prawa.append(el("div", "zd-o", o.filter(Boolean).join(" · ")));
      w.append(el("span", "zd-kr " + s.klasa), prawa);
      box.append(w);
    }
    return det;
  }
  window.Zadania = {panel, stan, trwa: d => d.zadania.some(z => z.trwa)};
})();
