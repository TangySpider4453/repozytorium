/* Dioda stanu serwera: doklejana przez portal do każdej strony (przed </body>).
   Zielona = wszystko w porządku, żółta = coś do sprawdzenia (bez pośpiechu albo problem, który już minął i czeka
   na „Przejrzane”), czerwona = trzeba zareagować. Liczba w środku = ile rzeczy czeka. Kliknięcie: /strony/zdrowie/. */
(function(){
  if(window.__dioda) return; window.__dioda = true;
  const KOLOR = {ok:"#22c55e", warn:"#facc15", crit:"#ef4444"}, TEKST = {ok:"#0b3d1c", warn:"#111111", crit:"#ffffff"};
  const OPIS = {ok:"Serwer: wszystko w porządku", warn:"Serwer: coś do sprawdzenia", crit:"Serwer: wymaga uwagi teraz"};
  const st = document.createElement("style");
  st.textContent = `.dioda-srv{display:inline-flex;align-items:center;justify-content:center;box-sizing:border-box;width:22px;height:22px;border-radius:50%;
    border:1.5px solid rgba(120,128,138,.95);margin-left:.35em;position:relative;top:-.55em;font:700 12px/1 system-ui,-apple-system,"Segoe UI",sans-serif;
    text-decoration:none;cursor:pointer;vertical-align:middle;letter-spacing:-.02em;background:#9aa3ad;transition:background-color .3s}
    .dioda-srv.plywa{position:fixed;top:calc(10px + env(safe-area-inset-top,0px));right:12px;z-index:9999;margin:0}
    .dioda-srv:focus-visible{outline:3px solid #4DB7C9;outline-offset:2px}`;
  document.head.appendChild(st);
  const d = document.createElement("a");
  d.className = "dioda-srv"; d.href = "/strony/zdrowie/"; d.title = "Stan serwera: sprawdzam…"; d.setAttribute("aria-label", d.title);
  const cel = document.getElementById("h-title") || document.querySelector("header h1") || document.querySelector("h1");
  if(cel) cel.appendChild(d); else { d.classList.add("plywa"); document.body.appendChild(d); }
  async function odswiez(){
    try{
      const r = await fetch("/api/zdrowie", {cache:"no-store"}); if(!r.ok) throw new Error(r.status);
      const z = await r.json(), s = KOLOR[z.stan] ? z.stan : "warn";
      d.style.backgroundColor = KOLOR[s]; d.style.color = TEKST[s];
      d.textContent = z.liczba > 0 ? (z.liczba > 99 ? "99+" : String(z.liczba)) : "";
      const lista = [...z.aktywne.map(i => "• " + i.tytul), ...z.do_przejrzenia.slice(0, 5).map(i => "• (minęło) " + i.tytul)];
      d.title = OPIS[s] + (lista.length ? "\n" + lista.join("\n") : "");
      d.setAttribute("aria-label", OPIS[s] + (z.liczba ? `, ${z.liczba} do sprawdzenia` : ""));
    }catch(e){
      d.style.backgroundColor = "#9aa3ad"; d.style.color = "#111"; d.textContent = "?"; d.title = "Nie udało się sprawdzić stanu serwera";
    }
  }
  odswiez(); setInterval(odswiez, 30000);
  document.addEventListener("visibilitychange", () => { if(!document.hidden) odswiez(); });
})();
