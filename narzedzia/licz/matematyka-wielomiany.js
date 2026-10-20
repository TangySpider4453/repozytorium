/* Zadania rachunkowe: wielomiany. Tematy jak w T: 1 działania, 2 dzielenie, 3 rozkład i pierwiastki, 4 równania. */
(function(){
  const R = (a, b) => a + Math.floor(Math.random() * (b - a + 1));
  const Rnz = (a, b) => { let x; do x = R(a, b); while(x === 0); return x; };
  const pick = a => a[Math.floor(Math.random() * a.length)];
  const SUP = ["", "", "²", "³", "⁴", "⁵", "⁶"];
  const m = x => x < 0 ? "−" + (-x) : String(x);              // liczba z prawdziwym minusem
  const par = x => x < 0 ? "(" + m(x) + ")" : String(x);       // w nawiasie, gdy ujemna
  /* współczynniki od najwyższej potęgi -> "2x³ − 3x² + x − 5" */
  function P(c){
    const n = c.length - 1; let s = "";
    c.forEach((a, i) => {
      const p = n - i; if(a === 0) return;
      const abs = Math.abs(a), znak = a < 0 ? (s ? " − " : "−") : (s ? " + " : "");
      const wsp = (abs === 1 && p > 0) ? "" : String(abs);
      s += znak + wsp + (p > 0 ? "x" + SUP[p] : "");
    });
    return s || "0";
  }
  const val = (c, x) => c.reduce((acc, a) => acc * x + a, 0);
  function mul(a, b){ const r = Array(a.length + b.length - 1).fill(0); a.forEach((x, i) => b.forEach((y, j) => r[i + j] += x * y)); return r; }
  const fromRoots = rs => rs.reduce((acc, r) => mul(acc, [1, -r]), [1]);
  const xa = a => a >= 0 ? `(x − ${a})` : `(x + ${-a})`;
  function horner(c, a){ const q = [c[0]]; for(let i = 1; i < c.length; i++) q.push(q[i - 1] * a + c[i]); return q; } // ostatni = reszta
  function hornerTab(c, a){
    const q = horner(c, a);
    return `<div class="tablewrap" style="margin:6px 0"><table style="min-width:0"><tr><th></th>${c.map(x => `<th>${m(x)}</th>`).join("")}</tr>` +
      `<tr><td>a = ${m(a)}</td>${q.map((x, i) => `<td>${i === 0 ? m(x) : `${m(q[i - 1])}·${par(a)} + ${par(c[i])} = <b>${m(x)}</b>`}</td>`).join("")}</tr></table></div>`;
  }
  const dzielniki = n => { n = Math.abs(n); const d = []; for(let i = 1; i <= n; i++) if(n % i === 0) d.push(i, -i); return d; };

  const typy = [
    {id:"wartosc", temat:1, nazwa:"Wartość wielomianu W(a)", gen(){
      const c = [Rnz(-4, 4), R(-5, 5), R(-6, 6), R(-9, 9)], a = Rnz(-3, 3), w = val(c, a);
      return {tresc:`Dany jest wielomian W(x) = ${P(c)}. Oblicz W(${m(a)}).`,
        pola:[{etykieta:`W(${m(a)}) =`, odp:w, tol:0}],
        rozw:[`Podstaw x = ${m(a)}: W(${m(a)}) = ${c.map((x, i) => `${par(x)}·${par(a)}${SUP[3 - i]}`).slice(0, 3).join(" + ")} + ${par(c[3])}.`,
              `${par(a)}³ = ${m(a ** 3)}, ${par(a)}² = ${m(a ** 2)}.`,
              `W(${m(a)}) = ${m(c[0] * a ** 3)} + ${par(c[1] * a ** 2)} + ${par(c[2] * a)} + ${par(c[3])} = <b>${m(w)}</b>.`]};
    }},
    {id:"iloczyn", temat:1, nazwa:"Mnożenie wielomianów", gen(){
      const A = [Rnz(-3, 3), R(-4, 4), Rnz(-5, 5)], B = [Rnz(-3, 3), Rnz(-5, 5)], W = mul(A, B);
      return {tresc:`Oblicz iloczyn (${P(A)})·(${P(B)}). Podaj stopień wyniku oraz współczynniki przy x² i przy x.`,
        pola:[{etykieta:"stopień =", odp:3, tol:0}, {etykieta:"przy x²:", odp:W[1], tol:0}, {etykieta:"przy x:", odp:W[2], tol:0}],
        rozw:[`Stopień iloczynu = suma stopni: 2 + 1 = 3.`,
              `Mnożymy każdy wyraz przez każdy: ${P(A)} razy ${P(B)}.`,
              `x²: ${par(A[0])}·${par(B[1])} + ${par(A[1])}·${par(B[0])} = ${m(W[1])}; x: ${par(A[1])}·${par(B[1])} + ${par(A[2])}·${par(B[0])} = ${m(W[2])}.`,
              `Wynik: <b>${P(W)}</b>.`]};
    }},
    {id:"reszta", temat:2, nazwa:"Reszta z dzielenia (tw. o reszcie)", gen(){
      const st = pick([3, 4]), c = [Rnz(-3, 3)].concat(Array.from({length:st}, () => R(-6, 6))), a = Rnz(-3, 3), r = val(c, a);
      return {tresc:`Oblicz resztę z dzielenia wielomianu W(x) = ${P(c)} przez ${xa(a)}.`,
        pola:[{etykieta:"reszta =", odp:r, tol:0}],
        rozw:[`Twierdzenie o reszcie: reszta z dzielenia przez (x − a) to W(a). Tu a = ${m(a)}${a < 0 ? `, bo x + ${-a} = x − (${m(a)})` : ""}.`,
              `W(${m(a)}) = ${c.map((x, i) => `${par(x)}·${par(a)}${SUP[st - i]}`).slice(0, st).join(" + ")} + ${par(c[st])} = <b>${m(r)}</b>.`]};
    }},
    {id:"horner", temat:2, nazwa:"Schemat Hornera", gen(){
      const c = [Rnz(-3, 3), R(-6, 6), R(-6, 6), R(-9, 9)], a = Rnz(-3, 3), q = horner(c, a);
      return {tresc:`Podziel W(x) = ${P(c)} przez ${xa(a)} schematem Hornera. Iloraz ma postać ax² + bx + c. Podaj a, b, c i resztę.`,
        pola:[{etykieta:"a =", odp:q[0], tol:0}, {etykieta:"b =", odp:q[1], tol:0}, {etykieta:"c =", odp:q[2], tol:0}, {etykieta:"reszta =", odp:q[3], tol:0}],
        rozw:[`Dzielnik ${xa(a)}, więc w schemacie a = ${m(a)}. Wypisz współczynniki: ${c.map(m).join(", ")}.`,
              `Pierwszy przepisz, każdy kolejny: poprzedni wynik · a + współczynnik.` + hornerTab(c, a),
              `Iloraz: <b>${P(q.slice(0, 3))}</b>, reszta: <b>${m(q[3])}</b>.`]};
    }},
    {id:"parametr", temat:2, nazwa:"Parametr m (tw. Bézouta)", gen(){
      const a = Rnz(-3, 3), mm = R(-5, 5), b = R(-6, 6), c = -(a ** 3 + mm * a * a + b * a);
      const ogon = P([b, c]), tail = ogon === "0" ? "" : ogon.startsWith("−") ? " − " + ogon.slice(1) : " + " + ogon;
      return {tresc:`Dla jakiej wartości m wielomian W(x) = x³ + mx²${tail} jest podzielny przez ${xa(a)}?`,
        pola:[{etykieta:"m =", odp:mm, tol:0}],
        rozw:[`Bézout: W(x) dzieli się przez (x − a) ⇔ W(a) = 0. Tu a = ${m(a)}.`,
              `W(${m(a)}) = ${par(a)}³ + m·${par(a)}² + ${par(b)}·${par(a)} + ${par(c)} = ${m(a ** 3)} + ${a * a}m + ${par(b * a)} + ${par(c)}.`,
              `${a * a}m + ${par(a ** 3 + b * a + c)} = 0, więc m = ${m(-(a ** 3 + b * a + c))} / ${a * a} = <b>${m(mm)}</b>.`]};
    }},
    {id:"wspolczynniki", temat:1, nazwa:"Suma współczynników i wyraz wolny", gen(){
      const p = Rnz(-3, 3), q = Rnz(-3, 3), n = pick([2, 3]), r = Rnz(-2, 2), s = Rnz(-4, 4);
      const W = mul(Array(n).fill([p, q]).reduce((acc, x) => mul(acc, x), [1]), [r, s]);
      return {tresc:`Dany jest wielomian W(x) = (${P([p, q])})${SUP[n]}·(${P([r, s])}). Oblicz sumę jego współczynników i wyraz wolny (bez wymnażania!).`,
        pola:[{etykieta:"suma współczynników =", odp:val(W, 1), tol:0}, {etykieta:"wyraz wolny =", odp:val(W, 0), tol:0}],
        rozw:[`Suma współczynników = W(1), wyraz wolny = W(0).`,
              `W(1) = (${m(p)} + ${par(q)})${SUP[n]}·(${m(r)} + ${par(s)}) = ${par(p + q)}${SUP[n]}·${par(r + s)} = <b>${m(val(W, 1))}</b>.`,
              `W(0) = ${par(q)}${SUP[n]}·${par(s)} = <b>${m(val(W, 0))}</b>.`]};
    }},
    {id:"pierwiastki", temat:3, nazwa:"Pierwiastki całkowite (Horner)", gen(){
      let rs; do rs = [R(-4, 4), R(-4, 4), R(-4, 4)]; while(new Set(rs).size < 3 || rs.includes(0));
      const c = fromRoots(rs), d = dzielniki(c[3]), r0 = d.find(x => val(c, x) === 0), q = horner(c, r0);
      const reszta = rs.filter(x => x !== r0), D = q[1] * q[1] - 4 * q[0] * q[2];
      return {tresc:`Rozwiąż równanie ${P(c)} = 0. Wpisz wszystkie rozwiązania oddzielone średnikami.`,
        pola:[{etykieta:"x ∈", odp:rs, rodzaj:"zbior"}],
        rozw:[`Pierwiastków całkowitych szukamy wśród dzielników wyrazu wolnego ${m(c[3])}: ${d.map(m).join(", ")}.`,
              `Sprawdzamy: W(${m(r0)}) = 0, więc x = ${m(r0)} jest pierwiastkiem i W dzieli się przez ${xa(r0)}.`,
              `Horner:` + hornerTab(c, r0) + `Iloraz: ${P(q.slice(0, 3))}.`,
              `Δ = ${par(q[1])}² − 4·${par(q[0])}·${par(q[2])} = ${m(D)}, √Δ = ${Math.sqrt(D)}; x = ${m(reszta[0])} lub x = ${m(reszta[1])}.`,
              `Odpowiedź: <b>x ∈ {${rs.slice().sort((a, b) => a - b).map(m).join("; ")}}</b>.`]};
    }},
    {id:"grupowanie", temat:4, nazwa:"Równanie przez grupowanie", gen(){
      let a, kk; do{ a = Rnz(-5, 5); kk = R(1, 5); } while(Math.abs(a) === kk);
      const c = [1, a, -kk * kk, -a * kk * kk];
      return {tresc:`Rozwiąż równanie ${P(c)} = 0 (wskazówka: pogrupuj wyrazy). Wpisz rozwiązania oddzielone średnikami.`,
        pola:[{etykieta:"x ∈", odp:[-a, kk, -kk], rodzaj:"zbior"}],
        rozw:[`Grupujemy: x²(x ${a < 0 ? "− " + (-a) : "+ " + a}) ${kk * kk === 1 ? "−" : "− " + kk * kk}(x ${a < 0 ? "− " + (-a) : "+ " + a}) = 0.`,
              `(x ${a < 0 ? "− " + (-a) : "+ " + a})(x² − ${kk * kk}) = 0, a x² − ${kk * kk} = (x − ${kk})(x + ${kk}).`,
              `Odpowiedź: <b>x ∈ {${[-a, kk, -kk].sort((p, q) => p - q).map(m).join("; ")}}</b>.`]};
    }},
    {id:"wylacz-x", temat:4, nazwa:"Równanie: wyłącz x przed nawias", gen(){
      let r1, r2; do{ r1 = Rnz(-5, 5); r2 = Rnz(-5, 5); } while(r1 === r2);
      const a = pick([1, 2]), c = [a, -a * (r1 + r2), a * r1 * r2, 0];
      return {tresc:`Rozwiąż równanie ${P(c)} = 0. Wpisz rozwiązania oddzielone średnikami.`,
        pola:[{etykieta:"x ∈", odp:[0, r1, r2], rodzaj:"zbior"}],
        rozw:[`Nie dziel przez x! Wyłącz x przed nawias: x(${P(c.slice(0, 3))}) = 0.`,
              `x = 0 albo ${P(c.slice(0, 3))} = 0. Δ = ${m(c[1] * c[1] - 4 * c[0] * c[2])}, pierwiastki ${m(r1)} i ${m(r2)}.`,
              `Odpowiedź: <b>x ∈ {${[0, r1, r2].sort((p, q) => p - q).map(m).join("; ")}}</b>.`]};
    }},
    {id:"krotnosc", temat:3, nazwa:"Krotność pierwiastka", gen(){
      let a, b; do{ a = Rnz(-4, 4); b = Rnz(-4, 4); } while(a === b);
      const k1 = pick([2, 3]);
      return {tresc:`Wielomian W(x) = ${xa(a)}${SUP[k1]}·${xa(b)}. Podaj krotność pierwiastka x = ${m(a)} oraz stopień wielomianu.`,
        pola:[{etykieta:`krotność ${m(a)}:`, odp:k1, tol:0}, {etykieta:"stopień:", odp:k1 + 1, tol:0}],
        rozw:[`Krotność = wykładnik potęgi czynnika ${xa(a)}: <b>${k1}</b>.`, `Stopień = suma wykładników: ${k1} + 1 = <b>${k1 + 1}</b>.`]};
    }}
  ];
  Licz.init({el:document.getElementById("liczBox"), typy, kolor:n => C(n)});
})();
