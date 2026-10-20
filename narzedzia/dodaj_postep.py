# Podłącza stronę sprawdzianu do wspólnego zapisu postępów (strona/postep.js + API portalu na Pi):
# fiszki zapamiętują „umiem / jeszcze nie”, quiz zapisuje wyniki i błędne pytania.
# Do tego wznawianie: przerwany quiz i otwarta zakładka wracają po przeładowaniu strony (localStorage).
# Użycie: python3 narzedzia/dodaj_postep.py <id> [<id> ...]   (uruchamiać z katalogu repozytorium)
import re, sys

CSS = """
/* postępy */
.fcopt{margin:0 0 10px}
.chk{display:flex;align-items:center;gap:6px;font-size:15px;cursor:pointer}
.chk input{width:18px;height:18px}
.qhist{display:grid;gap:8px;margin:0 0 14px}
.qh{font-size:14px;color:var(--muted)}
.qh b{color:var(--ink)}
.qh span{display:block}
"""
HELPERS = r"""
/* ---------- zapis postępów (../postep.js, dane na Raspberry Pi) ---------- */
var qPowt;
function fcKey(c){return c[0]+"|"+c[1]}
function fcStatDraw(){
  const e=document.getElementById("fcStat");if(!e||typeof FC==="undefined")return;
  const all=FC.filter(c=>fcFilter==="all"||c[0]==fcFilter);
  const k=all.filter(c=>Postep.stan(fcKey(c))===1).length,n=all.filter(c=>Postep.stan(fcKey(c))===0).length;
  e.textContent=`umiesz ${k} z ${all.length}`+(n?`, do powtórki ${n}`:"");
}
function qLabel(f){return f==="all"?"wszystko":(T[f]?f+". "+T[f]:f)}
function qHistDraw(){
  const box=document.getElementById("qHist");if(!box)return;box.innerHTML="";
  const bl=Postep.bledne().filter(t=>Q.some(q=>q[1]===t));
  if(bl.length){const b=document.createElement("button");b.className="btn badb";b.textContent=`Powtórz pytania, w których się myliłeś (${bl.length})`;b.onclick=()=>startQuiz(Q.filter(q=>bl.includes(q[1])),true);box.append(b)}
  const hist=Postep.quizy().slice(-5).reverse();
  if(hist.length){
    const h=document.createElement("div");h.className="qh";const t=document.createElement("b");t.textContent="Ostatnie wyniki";h.append(t);
    hist.forEach(r=>{const d=new Date(r.czas),s=document.createElement("span"),p=r.wszystkie?Math.round(r.dobre/r.wszystkie*100):0;
      s.textContent=`${p}% (${r.dobre}/${r.wszystkie}) · ${d.getDate()}.${String(d.getMonth()+1).padStart(2,"0")} ${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")} · ${qLabel(r.filtr)}`;h.append(s)});
    box.append(h);
  }
}
(function(){
  const sk=document.getElementById("fcSkip"),rs=document.getElementById("fcReset");
  if(sk)sk.addEventListener("change",()=>buildDeck(fcFilter));
  if(rs)rs.addEventListener("click",()=>{if(confirm("Wyzerować zapamiętane fiszki? Wszystkie karty wrócą do nauki."))Postep.zerujFiszki().then(()=>buildDeck(fcFilter))});
  Postep.ready.then(()=>{qHistDraw();Postep.ile(typeof FC!=="undefined"?{fiszki:FC.length,quiz:Q.length}:{quiz:Q.length})});
})();
"""
FC_ROW = '\n  <div class="row fcopt"><label class="chk"><input type="checkbox" id="fcSkip" checked> Pomiń karty, które już umiem</label><button class="btn" id="fcReset">Wyzeruj fiszki</button><span class="counter" id="fcStat"></span></div>'

RESUME = r"""
/* ---------- wznawianie: przerwany quiz i ostatnia zakładka po przeładowaniu ---------- */
function qLS(){return "nauka:"+document.documentElement.dataset.nauka+":quiz_w_toku"}
function tabLS(){return "nauka:"+document.documentElement.dataset.nauka+":zakladka"}
function qSave(ans){try{localStorage.setItem(qLS(),JSON.stringify({qs:qs.map(q=>({n:q.n,t:q.t,o:q.o,a:q.a,e:q.e,i:Q.indexOf(q.src)})),qi,score,wrong:wrong.map(w=>Q.indexOf(w)),qFilter,qPowt:!!qPowt,ans:ans==null?null:ans}))}catch(e){}}
function qClear(){try{localStorage.removeItem(qLS())}catch(e){}const r=document.getElementById("qResume");if(r)r.remove()}
function qRestore(){
  let s=null;try{s=JSON.parse(localStorage.getItem(qLS())||"null")}catch(e){}
  if(!s||!Array.isArray(s.qs)||!s.qs.length||s.qi>=s.qs.length||(s.qi===0&&s.ans==null))return false;
  if(s.qs.some(q=>!Q[q.i]||Q[q.i][1]!==q.t)){qClear();return false}
  qs=s.qs.map(q=>({n:q.n,t:q.t,o:q.o,a:q.a,e:q.e,src:Q[q.i]}));qi=s.qi;score=s.score;wrong=s.wrong.map(i=>Q[i]).filter(Boolean);qFilter=s.qFilter;qPowt=s.qPowt;
  document.querySelectorAll("#qFilters button").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.t===String(qFilter))));
  drawQ();if(s.ans!=null)answer(s.ans,true);
  const r=document.createElement("div");r.id="qResume";r.className="expl";r.style.margin="0 0 12px";
  r.append(`Wróciłeś do przerwanego quizu: pytanie ${Math.min(qi+1,qs.length)} z ${qs.length}, dobrze ${score}. `);
  const b=document.createElement("button");b.className="btn";b.textContent="Zacznij od nowa";b.onclick=()=>startQuiz(filtered());r.append(b);
  document.getElementById("qArea").before(r);
  return true;
}
(function(){
  let t=null;try{t=JSON.parse(localStorage.getItem(tabLS())||"null")}catch(e){}
  if(t&&Date.now()-t.czas<3*3600*1000&&document.getElementById(t.id))showTab(t.id);
})();
"""

def resume(pid, s):
    if "function qRestore" in s:
        return s
    def rep(a, b):
        nonlocal s
        assert s.count(a) == 1, (pid, a[:60], s.count(a))
        s = s.replace(a, b)
    rep("var qPowt=false;\n", "var qPowt;\n")
    rep("function showTab(id){", 'function showTab(id){try{localStorage.setItem(tabLS(),JSON.stringify({id,czas:Date.now()}))}catch(e){}')
    rep("function startQuiz(list,powt){qPowt=!!powt;", 'function startQuiz(list,powt){qPowt=!!powt;const r=document.getElementById("qResume");if(r)r.remove();')
    rep("  if(qi>=qs.length){\n", "  if(qi>=qs.length){\n    qClear();\n")
    rep("  const q=qs[qi];\n  A.innerHTML=", "  const q=qs[qi];qSave(null);\n  A.innerHTML=")
    rep("function answer(i){", "function answer(i,odtw){")
    rep('if(i===q.a)score++;else{btns[i].classList.add("wrong");wrong.push(q.src)}',
        'if(i===q.a){if(!odtw)score++}else{btns[i].classList.add("wrong");if(!odtw)wrong.push(q.src)}')
    rep('  document.getElementById("qNext").focus();\n', '  document.getElementById("qNext").focus();\n  if(!odtw)qSave(i);\n')
    rep("\nstartQuiz(filtered());\n", "\nif(!qRestore())startQuiz(filtered());\n")
    i = s.rfind("</script>")
    return s[:i] + RESUME + s[i:]

def patch(pid):
    p = f"strona/{pid}/index.html"
    s = open(p, encoding="utf-8").read()
    if "postep.js" in s:
        s2 = resume(pid, s)
        if s2 != s:
            open(p, "w", encoding="utf-8").write(s2); print(pid, "dodano wznawianie")
        else:
            print(pid, "już podłączona")
        return
    def rep(a, b, count=1):
        nonlocal s
        assert s.count(a) == count, (pid, a[:60], s.count(a))
        s = s.replace(a, b)
    rep('<html lang="pl">', f'<html lang="pl" data-nauka="{pid}">')
    rep("</style>", CSS + "</style>")
    rep("</head>", '<script src="../postep.js"></script>\n</head>')
    # quiz
    rep('<div class="filters" id="qFilters"></div>', '<div class="filters" id="qFilters"></div>\n  <div class="qhist" id="qHist"></div>')
    rep("function startQuiz(list){", "function startQuiz(list,powt){qPowt=!!powt;")
    rep("if(rw) rw.onclick=()=>startQuiz(wrong);", "if(rw) rw.onclick=()=>startQuiz(wrong,true);")
    rep("    const pct=Math.round(score/qs.length*100);\n",
        "    const pct=Math.round(score/qs.length*100);\n"
        "    if(qs.length)Postep.quiz({filtr:qPowt?\"błędne\":qFilter,dobre:score,wszystkie:qs.length},wrong.map(q=>q[1]),qs.filter(q=>!wrong.includes(q.src)).map(q=>q.t)).then(qHistDraw);\n")
    # fiszki (nie każda strona je ma)
    if "function buildDeck(f)" in s:
        rep('<div class="filters" id="fcFilters"></div>', '<div class="filters" id="fcFilters"></div>' + FC_ROW)
        s, n = re.subn(r"function buildDeck\(f\)\{[^\n]*\}",
            lambda m: 'function buildDeck(f){const all=FC.filter(c=>f==="all"||c[0]==f),st=c=>Postep.stan(fcKey(c)),skip=document.getElementById("fcSkip").checked;'
                      'deck=[...shuffle(all.filter(c=>st(c)===0)),...shuffle(all.filter(c=>st(c)===undefined)),...(skip?[]:shuffle(all.filter(c=>st(c)===1)))];fcIdx=0;known=0;drawFC();fcStatDraw();}', s)
        assert n == 1, (pid, "buildDeck")
        rep('document.getElementById("fcYes").addEventListener("click",()=>{if(!deck.length)return;deck.shift();known++;drawFC();});',
            'document.getElementById("fcYes").addEventListener("click",()=>{if(!deck.length)return;Postep.fiszka(fcKey(deck[0]),true);deck.shift();known++;drawFC();fcStatDraw();});')
        rep('document.getElementById("fcNo").addEventListener("click",()=>{if(!deck.length)return;deck.push(deck.shift());drawFC();});',
            'document.getElementById("fcNo").addEventListener("click",()=>{if(!deck.length)return;Postep.fiszka(fcKey(deck[0]),false);deck.push(deck.shift());drawFC();fcStatDraw();});')
        rep('makeFilters(document.getElementById("fcFilters"),f=>{fcFilter=f;buildDeck(f)}); buildDeck("all");',
            'makeFilters(document.getElementById("fcFilters"),f=>{fcFilter=f;buildDeck(f)}); Postep.ready.then(()=>buildDeck(fcFilter));')
    # „Sprawdź się” na stronie z wierszem
    if "best=saveBest(pct);" in s:
        rep("const pct=Math.round(good/items.length*100), best=saveBest(pct);",
            "const pct=Math.round(good/items.length*100), best=saveBest(pct);\n"
            "    Postep.quiz({filtr:\"Sprawdź się: \"+(chkS===\"all\"?\"cały wiersz\":\"strofa \"+chkS),dobre:good,wszystkie:items.length},[],[]).then(qHistDraw);")
    i = s.rfind("</script>")
    s = s[:i] + HELPERS + s[i:]
    s = resume(pid, s)
    open(p, "w", encoding="utf-8").write(s)
    print(pid, "ok")

for pid in sys.argv[1:]:
    patch(pid)
