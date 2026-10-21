/* Zakładka „Licz”: zadania rachunkowe z losowymi liczbami, sprawdzanie wyniku i rozwiązanie krok po kroku.
   Strona woła Licz.init({el, typy, kolor}), gdzie typy = [{id, temat, nazwa, gen}] i gen() zwraca:
     {tresc: "HTML", pola: [{etykieta, jednostka, odp, tol, rodzaj}], rozw: ["krok HTML", ...]}
   rodzaj: "liczba" (domyślnie; tol = względna tolerancja, np. 0.02), "zbior" (liczby całkowite w dowolnej kolejności)
   albo "tekst" (odp = lista poprawnych napisów; wielkość liter, nadmiarowe spacje i kropki nie mają znaczenia).
   Opcjonalnie cfg.intro zastępuje tekst wprowadzenia.
   Seria 10 zadań zapisuje się w wynikach (Postep.quiz, filtr „Licz: …”), a przerwana seria wraca po przeładowaniu. */
(function(){
  const SUP = {"⁰":"0","¹":"1","²":"2","³":"3","⁴":"4","⁵":"5","⁶":"6","⁷":"7","⁸":"8","⁹":"9","⁻":"-","⁺":"+"};
  const SERIA = 10;

  /* "1,8·10⁻³", "1.8e-3", "1,8*10^-3", "−4", "3/4" -> liczba */
  function parse(txt){
    if(txt == null) return NaN;
    let s = String(txt).trim().replace(/\s+/g, "").replace(/[−–]/g, "-").replace(/,/g, ".");
    s = s.replace(/[⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺]+/g, m => "^" + [...m].map(c => SUP[c]).join(""));
    s = s.replace(/(?:[·*x×]10\^?|e)([+-]?\d+)/i, "e$1");
    if(/^[+-]?\d+\/\d+$/.test(s)){ const [a, b] = s.split("/").map(Number); return b ? a / b : NaN; }
    return /^[+-]?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$/i.test(s) ? Number(s) : NaN;
  }
  function parseZbior(txt){
    const parts = String(txt).replace(/[−–]/g, "-").split(/[;,\s]+/).filter(Boolean);
    const nums = parts.map(Number);
    return nums.some(n => !Number.isFinite(n)) ? null : nums.sort((a, b) => a - b);
  }
  const norm = t => String(t).toLowerCase().replace(/[.,!?;:]/g, " ").replace(/\s+/g, " ").trim();
  function ok(pole, txt){
    if(pole.rodzaj === "tekst") return pole.odp.some(w => norm(w) === norm(txt));
    if(pole.rodzaj === "zbior"){
      const z = parseZbior(txt), w = pole.odp.slice().sort((a, b) => a - b);
      return !!z && z.length === w.length && z.every((v, i) => v === w[i]);
    }
    const v = parse(txt), w = pole.odp, tol = pole.tol == null ? 0.02 : pole.tol;
    if(!Number.isFinite(v)) return false;
    if(w === 0) return Math.abs(v) < 1e-9;
    return Math.abs(v - w) <= Math.abs(w) * tol + 1e-12;
  }

  /* liczba po polsku: 3 cyfry znaczące, przecinek, notacja 10ⁿ dla bardzo małych/dużych */
  const SUPW = {"0":"⁰","1":"¹","2":"²","3":"³","4":"⁴","5":"⁵","6":"⁶","7":"⁷","8":"⁸","9":"⁹","-":"⁻"};
  function fmt(x, sig){
    return fmt0(x, sig).replace(/^-/, "−");
  }
  function fmt0(x, sig){
    sig = sig || 3;
    if(!Number.isFinite(x)) return "?";
    if(x === 0) return "0";
    const a = Math.abs(x);
    if(a >= 1e-3 && a < 1e6){
      const r = Number(x.toPrecision(sig));
      return String(r).replace(".", ",");
    }
    let [m, e] = x.toExponential(sig - 1).split("e");
    m = String(Number(m)).replace(".", ",");
    return m + "·10" + String(Number(e)).split("").map(c => SUPW[c]).join("");
  }

  const Licz = { parse, fmt, ok };
  Licz.init = function(cfg){
    const root = cfg.el, typy = cfg.typy, KEY = "nauka:" + document.documentElement.dataset.nauka + ":licz_w_toku";
    let wybor = "all", zad = null, sprawdzone = false, dobre = 0, ile = 0;

    const zapisz = () => { try{ localStorage.setItem(KEY, JSON.stringify({wybor, zad, sprawdzone, dobre, ile})); }catch(e){} };
    const wczytaj = () => { try{ return JSON.parse(localStorage.getItem(KEY) || "null"); }catch(e){ return null; } };
    const czysc = () => { try{ localStorage.removeItem(KEY); }catch(e){} };
    const etykieta = () => wybor === "all" ? "wszystko" : (typy.find(t => t.id === wybor) || {}).nazwa;

    root.innerHTML = `<p class="intro">${cfg.intro || `Za każdym razem inne liczby. Wpisz wynik (przecinek albo kropka; potęgi jako 1,8·10⁻³, 1,8e-3 albo 1,8*10^-3). Seria ma ${SERIA} zadań i zapisuje się w wynikach.`}</p>
      <details class="lz-wybor"><summary>Rodzaj zadań: <b class="lz-akt"></b> <span>(zmień)</span></summary><div class="filters lz-typy"></div></details><div class="lz-licznik"></div><div class="lz-karta"></div>`;
    const fBox = root.querySelector(".lz-typy"), licznik = root.querySelector(".lz-licznik"), karta = root.querySelector(".lz-karta");

    const btn = (t, cls, fn) => { const b = document.createElement("button"); b.className = "btn " + (cls || ""); b.textContent = t; b.onclick = fn; return b; };
    function filtry(){
      fBox.innerHTML = ""; root.querySelector(".lz-akt").textContent = wybor === "all" ? "wszystkie (losowo)" : etykieta();
      const mk = (id, nazwa, c) => { const b = document.createElement("button"); b.dataset.t = id; b.textContent = nazwa; if(c) b.style.setProperty("--c", c);
        b.setAttribute("aria-pressed", String(id === wybor)); b.onclick = () => { root.querySelector(".lz-wybor").open = false; if(id === wybor) return; wybor = id; dobre = 0; ile = 0; filtry(); nowe(); }; fBox.append(b); };
      mk("all", "Wszystko (losowo)");
      typy.forEach(t => mk(t.id, t.nazwa, cfg.kolor ? cfg.kolor(t.temat) : null));
    }
    const nr = () => Math.min(sprawdzone ? ile : ile + 1, SERIA);
    function pokazLicznik(){ licznik.innerHTML = `<div class="lz-pasek"><span>Seria: zadanie <b>${nr()}</b> z ${SERIA}</span><span>dobrze <b>${dobre}</b></span></div>`; }
    function nowe(){
      const pula = wybor === "all" ? typy : typy.filter(t => t.id === wybor);
      const t = pula[Math.floor(Math.random() * pula.length)];
      const z = t.gen(); z.typ = t.id; z.nazwa = t.nazwa; z.temat = t.temat;
      zad = z; sprawdzone = false; zapisz(); rysuj();
    }
    function rysuj(wpisane, wynikiPol){
      pokazLicznik();
      const c = cfg.kolor ? cfg.kolor(zad.temat) : "var(--nav)";
      karta.innerHTML = "";
      const k = document.createElement("div"); k.className = "qcard lz"; k.style.setProperty("--c", c);
      k.innerHTML = `<div class="qmeta"><span>${zad.nazwa}</span><span>${nr()} / ${SERIA}</span></div><div class="lz-tresc">${zad.tresc}</div>`;
      const inputs = zad.pola.map((p, i) => {
        const row = document.createElement("label"); row.className = "lz-pole";
        const lab = document.createElement("span"); lab.innerHTML = p.etykieta; row.append(lab);
        const inp = document.createElement("input"); inp.type = "text"; inp.inputMode = p.rodzaj === "zbior" || p.rodzaj === "tekst" ? "text" : "decimal"; inp.autocomplete = "off";
        if(p.rodzaj === "tekst"){ inp.autocapitalize = "off"; inp.spellcheck = false; inp.setAttribute("autocorrect", "off"); inp.lang = cfg.lang || ""; }
        inp.placeholder = p.rodzaj === "zbior" ? "np. -2; 1; 3" : p.rodzaj === "tekst" ? "wpisz" : "wynik"; if(wpisane) inp.value = wpisane[i] || "";
        inp.addEventListener("keydown", e => { if(e.key === "Enter"){ e.preventDefault(); sprawdz(false); } });
        row.append(inp);
        if(p.jednostka){ const u = document.createElement("span"); u.className = "lz-j"; u.innerHTML = p.jednostka; row.append(u); }
        if(wynikiPol){ row.classList.add(wynikiPol[i] ? "lz-ok" : "lz-zle"); inp.disabled = true; }
        k.append(row); return inp;
      });
      const akcje = document.createElement("div"); akcje.className = "row"; akcje.style.marginTop = "12px";
      const out = document.createElement("div");
      if(!sprawdzone){
        akcje.append(btn("Sprawdź", "primary", () => sprawdz(false)), btn("Nie wiem, pokaż rozwiązanie", "", () => sprawdz(true)));
      } else {
        const wszystkie = wynikiPol && wynikiPol.every(Boolean);
        out.innerHTML = `<div class="expl"><b>${wynikiPol ? (wszystkie ? "Dobrze!" : "Źle.") : "Rozwiązanie"}</b> Poprawnie: ${zad.pola.map(p => (p.rodzaj === "tekst" ? p.odp[0] : p.rodzaj === "zbior" ? p.odp.slice().sort((a,b)=>a-b).map(v => fmt(v)).join("; ") : fmt(p.odp, 4)) + (p.jednostka ? " " + p.jednostka : "")).join(" · ")}
          <ol class="lz-kroki">${zad.rozw.map(x => "<li>" + x + "</li>").join("")}</ol></div>`;
        akcje.append(btn(ile >= SERIA ? "Nowa seria" : "Następne zadanie", "primary", dalej));
      }
      k.append(out, akcje); karta.append(k);
      if(!sprawdzone && inputs[0] && document.activeElement && root.contains(document.activeElement)) inputs[0].focus();
      function sprawdz(poddaj){
        const vals = inputs.map(i => i.value);
        if(!poddaj && vals.every(v => !v.trim())){ inputs[0].focus(); return; }
        const wyn = zad.pola.map((p, i) => !poddaj && ok(p, vals[i]));
        const dobrze = wyn.every(Boolean);
        sprawdzone = true; ile++; if(dobrze) dobre++;
        zad.wpisane = vals; zad.wyniki = poddaj ? null : wyn;
        if(ile >= SERIA){
          if(window.Postep) Postep.quiz({filtr:(cfg.nazwa || "Licz") + ": " + etykieta(), dobre, wszystkie:ile}, [], []).then(() => { if(typeof window.qHistDraw === "function") window.qHistDraw(); });
        }
        zapisz(); rysuj(vals, poddaj ? null : wyn);
      }
    }
    function dalej(){
      if(ile >= SERIA){
        const pct = Math.round(dobre / ile * 100);
        karta.innerHTML = `<div class="qcard result" style="--c:var(--nav)"><div class="big">${dobre}/${ile}</div><h3 style="margin-top:10px">${pct}%</h3><p>Seria zapisana w wynikach (zakładka Quiz → Ostatnie wyniki).</p></div>`;
        const r = document.createElement("div"); r.className = "row"; r.style.justifyContent = "center"; r.style.marginTop = "12px";
        r.append(btn("Nowa seria", "primary", () => { dobre = 0; ile = 0; nowe(); }));
        karta.append(r); licznik.innerHTML = ""; czysc(); return;
      }
      nowe();
    }

    const s = wczytaj();
    filtry();
    if(s && s.zad && s.ile < SERIA + 1){
      wybor = s.wybor; dobre = s.dobre; ile = s.ile; zad = s.zad; sprawdzone = s.sprawdzone; filtry();
      rysuj(zad.wpisane, sprawdzone ? zad.wyniki : undefined);
    } else nowe();
  };
  window.Licz = Licz;
})();
