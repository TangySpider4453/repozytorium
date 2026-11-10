/* Panel „⚙️ Ustawienia” na dole stron automatyzacji (Mobidziennik, zadania, budziki, komunikacja, Automatyczne).
   Użycie: <div data-ustawienia="mobi"></div> (kilka modułów: "zadania,sprawdziany") i
   <script src="/strony/wspolne/ustawienia.js" defer></script>. Schemat i wartości z GET /api/automaty,
   każda zmiana zapisuje się od razu (POST /api/automaty/<moduł>). Bot na Pi stosuje je w ciągu ok. 30 s. */
(() => {
  const css = `
.ust{margin:18px 0 8px;background:var(--surface,#fff);border:1px solid var(--line,#ccd);border-radius:14px;padding:14px 16px}
.ust h2{font-size:20px;margin:0 0 2px;display:flex;align-items:center;gap:8px}
.ust .ust-opis{color:var(--muted,#667);font-size:14px;margin:0 0 10px}
.ust .ust-mod{border-top:1px solid var(--line,#ccd);padding-top:10px;margin-top:10px}
.ust .ust-mod:first-of-type{border-top:0;margin-top:0;padding-top:0}
.ust h3{font-size:16px;margin:0 0 6px}
.ust .ust-pole{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:7px 0;font-size:15px;min-height:40px}
.ust .ust-pole.wyl{opacity:.45}
.ust .ust-pole label{flex:1;min-width:0}
.ust select,.ust input[type=time],.ust input[type=number]{font:inherit;font-size:16px;padding:6px 8px;border:1px solid var(--line,#ccd);border-radius:8px;background:var(--bg,#fff);color:var(--ink,#123)}
.ust .ust-pole select,.ust .ust-pole input{flex:none;width:auto;max-width:9em;margin:0}
.ust .ust-pole input[type=number]{width:5.5em}
.ust .ust-pole input[type=time]{width:8em}
.ust .przel{position:relative;width:50px;height:30px;flex:none;border-radius:99px;border:0;background:var(--line,#ccd);cursor:pointer;padding:0}
.ust .przel::after{content:"";position:absolute;top:3px;left:3px;width:24px;height:24px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.3);transition:left .15s}
.ust .przel[aria-checked=true]{background:var(--ok,#1f8a4c)}
.ust .przel[aria-checked=true]::after{left:23px}
.ust .ust-stan{font-size:13px;color:var(--muted,#667);min-height:1.2em;margin-top:4px}
.ust .ust-stan.blad{color:var(--bad,#c03442)}`;
  const el = (t, a = {}, ...k) => { const e = document.createElement(t); for(const [n, v] of Object.entries(a)){ if(v == null) continue;
    if(n === "text") e.textContent = v; else if(n.startsWith("on")) e.addEventListener(n.slice(2), v); else e.setAttribute(n, v); }
    e.append(...k.filter(x => x != null)); return e; };
  const pojemniki = [...document.querySelectorAll("[data-ustawienia]")];
  if(!pojemniki.length) return;
  document.head.append(el("style", {text:css}));
  fetch("/api/automaty", {cache:"no-store"}).then(r => { if(!r.ok) throw new Error(r.status); return r.json(); }).then(d => {
    for(const box of pojemniki){
      const moduly = box.dataset.ustawienia.split(",").map(x => x.trim()).filter(m => d.schemat[m]);
      const stan = el("div", {class:"ust-stan", role:"status"});
      const karta = el("section", {class:"ust", "aria-label":"Ustawienia"},
        el("h2", {}, el("span", {"aria-hidden":"true", text:"⚙️"}), "Ustawienia"),
        el("p", {class:"ust-opis", text:"Zmiany zapisują się od razu. Pi stosuje je w ciągu pół minuty."}));
      for(const m of moduly){
        const sch = d.schemat[m], w = d.wartosci[m], wiersze = [];
        const mod = el("div", {class:"ust-mod"}, moduly.length > 1 || box.dataset.tytul ? el("h3", {text:sch.nazwa}) : null);
        const glowny = sch.pola[0].typ === "bool" ? sch.pola[0].pole : null;      // pierwszy włącznik = cały moduł
        const odswiez = () => wiersze.forEach(([p, r]) => r.classList.toggle("wyl", !!glowny && p !== glowny && !w[glowny]));
        const zapisz = async (pole, v) => {
          stan.className = "ust-stan"; stan.textContent = "Zapisuję…";
          try{
            const r = await fetch("/api/automaty/" + m, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({[pole]:v})});
            if(!r.ok) throw new Error("serwer odpowiedział " + r.status);
            Object.assign(w, await r.json()); odswiez();
            stan.textContent = "Zapisano ✓";
          }catch(e){ stan.className = "ust-stan blad"; stan.textContent = "Nie udało się zapisać: " + e.message; }
        };
        for(const f of sch.pola){
          const id = `ust-${m}-${f.pole}`;
          let pole;
          if(f.typ === "bool"){
            pole = el("button", {type:"button", class:"przel", role:"switch", id, "aria-checked":String(!!w[f.pole]), "aria-label":f.etykieta});
            pole.onclick = () => { const v = pole.getAttribute("aria-checked") !== "true"; pole.setAttribute("aria-checked", String(v)); zapisz(f.pole, v); };
          } else if(f.typ === "godzina"){
            pole = el("input", {type:"time", id, value:w[f.pole], step:60});
            pole.onchange = () => pole.value && zapisz(f.pole, pole.value);
          } else if(f.typ === "wybor"){
            pole = el("select", {id}, ...f.opcje.map(o => el("option", {value:String(o), text:String(o), ...(o === w[f.pole] ? {selected:""} : {})})));
            pole.onchange = () => zapisz(f.pole, f.opcje.find(o => String(o) === pole.value));
          } else {
            pole = el("input", {type:"number", id, value:w[f.pole], min:f.opcje[0], max:f.opcje[1], step:1, inputmode:"numeric"});
            pole.onchange = () => { const v = parseInt(pole.value); if(v >= f.opcje[0] && v <= f.opcje[1]) zapisz(f.pole, v); else { pole.value = w[f.pole]; } };
          }
          const r = el("div", {class:"ust-pole"}, el("label", {for:id, text:f.etykieta}), pole);
          wiersze.push([f.pole, r]); mod.append(r);
        }
        odswiez(); karta.append(mod);
      }
      karta.append(stan);
      box.replaceChildren(karta);
    }
  }).catch(e => pojemniki.forEach(b => b.replaceChildren(el("p", {class:"ust-stan blad", text:"Ustawienia: nie udało się wczytać (" + e.message + ")."}))));
})();
