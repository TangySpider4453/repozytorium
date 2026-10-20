/* Wspólny zapis postępów nauki: fiszki (umiem / jeszcze nie), wyniki quizów i pytania, w których był błąd.
   Dane są na Raspberry Pi (/api/nauka/postep/<id>), więc telefon, iPad i komputer widzą to samo.
   Kopia w localStorage służy tylko na wypadek, gdyby serwer chwilowo nie odpowiadał.
   Strona podaje swój id w <html data-nauka="...">. */
(function(){
  const ID = document.documentElement.dataset.nauka;
  const API = "/api/nauka/postep/" + ID;
  const LS = "nauka:" + ID + ":postep";
  const pusty = () => ({fiszki:{}, quizy:[], bledne:{}, ile:{}});
  let st = pusty(), online = false;
  try{ const c = JSON.parse(localStorage.getItem(LS) || "null"); if(c) st = Object.assign(pusty(), c); }catch(e){}
  const zapiszLokalnie = () => { try{ localStorage.setItem(LS, JSON.stringify(st)); }catch(e){} };
  function wyslij(body){
    return fetch(API, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)})
      .then(r => { if(!r.ok) throw new Error(r.status); return r.json(); })
      .then(d => { st = Object.assign(pusty(), d); online = true; zapiszLokalnie(); })
      .catch(() => { online = false; });
  }
  const ready = fetch(API, {cache:"no-store"})
    .then(r => { if(!r.ok) throw new Error(r.status); return r.json(); })
    .then(d => { st = Object.assign(pusty(), d); online = true; zapiszLokalnie(); })
    .catch(() => { online = false; });

  window.Postep = {
    ready,
    get online(){ return online; },
    /* fiszki: 1 = umiem, 0 = jeszcze nie, undefined = jeszcze nieoceniona */
    stan: k => st.fiszki[k],
    fiszka(k, umiem){ st.fiszki[k] = umiem ? 1 : 0; zapiszLokalnie(); return wyslij({op:"fiszka", klucz:k, umiem:!!umiem}); },
    zerujFiszki(){ st.fiszki = {}; zapiszLokalnie(); return wyslij({op:"zeruj_fiszki"}); },
    /* quiz: wynik {filtr, dobre, wszystkie}; bledne/poprawne to teksty pytań */
    quiz(wynik, bledne, poprawne){
      st.quizy.push(Object.assign({czas:new Date().toISOString().slice(0,19)}, wynik));
      poprawne.forEach(k => delete st.bledne[k]);
      bledne.forEach(k => st.bledne[k] = (st.bledne[k] || 0) + 1);
      zapiszLokalnie();
      return wyslij({op:"quiz", wynik, bledne, poprawne});
    },
    quizy: () => st.quizy.slice(),
    bledne: () => Object.keys(st.bledne),
    ile(o){ if(JSON.stringify(st.ile) !== JSON.stringify(o)) wyslij({op:"ile", ile:o}); }
  };
})();
