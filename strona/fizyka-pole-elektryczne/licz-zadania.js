/* Zadania rachunkowe: siły, pole i napięcie elektryczne. Tematy jak w T: 1 siły, 2 pole, 3 napięcie. */
(function(){
  const k = 9e9, e = 1.6e-19, me = 9.11e-31;
  const R = (a, b) => a + Math.floor(Math.random() * (b - a + 1));
  const pick = a => a[Math.floor(Math.random() * a.length)];
  const f = Licz.fmt;
  const typy = [
    {id:"coulomb", temat:1, nazwa:"Prawo Coulomba", gen(){
      const q1 = R(1, 9), q2 = R(1, 9), r = pick([2, 3, 4, 5, 6, 10, 15, 20, 30]), F = k * q1e(q1) * q1e(q2) / (r / 100) ** 2;
      return {tresc:`Dwa ładunki punktowe q₁ = ${q1} µC i q₂ = ${q2} µC są odległe o r = ${r} cm (w powietrzu). Oblicz wartość siły, z jaką na siebie działają.`,
        pola:[{etykieta:"F =", jednostka:"N", odp:F}],
        rozw:[`Zamiana na jednostki SI: q₁ = ${q1}·10⁻⁶ C, q₂ = ${q2}·10⁻⁶ C, r = ${f(r / 100)} m.`,
              `F = k·q₁·q₂ / r² = 9·10⁹ · ${q1}·10⁻⁶ · ${q2}·10⁻⁶ / ${f(r / 100)}²`,
              `Licznik: 9·10⁹ · ${q1 * q2}·10⁻¹² = ${f(k * q1 * q2 * 1e-12)}; mianownik: ${f((r / 100) ** 2)} m².`,
              `F = <b>${f(F)} N</b>.`]};
    }},
    {id:"coulomb-zmiana", temat:1, nazwa:"Jak zmieni się siła?", gen(){
      const a = pick([2, 3, 4]), b = pick([1, 2, 3]), dalej = Math.random() < 0.5;
      const ratio = dalej ? b / (a * a) : b * a * a;
      const zm = b === 1 ? "Ładunki się nie zmieniają" : `Jeden z ładunków zwiększamy ${b} razy`;
      return {tresc:`${zm}, a odległość między ładunkami ${dalej ? "zwiększamy" : "zmniejszamy"} ${a} razy. Ile razy zmieni się siła? Podaj F'/F (np. 0,25 albo 1/4 albo 9).`,
        pola:[{etykieta:"F'/F =", odp:ratio, tol:0.01}],
        rozw:[`F ~ q₁·q₂ / r².`, `Ładunek: ×${b}. Odległość ${dalej ? "×" : "÷"}${a}, więc r² ${dalej ? "×" : "÷"}${a * a}, a siła ${dalej ? "÷" : "×"}${a * a}.`,
              `F'/F = ${b} ${dalej ? "/" : "·"} ${a * a} = <b>${f(ratio, 4)}</b>${dalej && b < a * a ? ` (= ${b}/${a * a})` : ""}.`]};
    }},
    {id:"elektrony", temat:1, nazwa:"Ile elektronów?", gen(){
      const q = R(1, 50) * pick([1, 10]), n = q * 1e-9 / e;
      return {tresc:`Kulka naelektryzowała się ujemnie ładunkiem o wartości ${q} nC. Ile nadmiarowych elektronów na niej jest?`,
        pola:[{etykieta:"n =", odp:n}],
        rozw:[`q = n·e, więc n = q / e.`, `n = ${q}·10⁻⁹ C / 1,6·10⁻¹⁹ C = <b>${f(n)}</b> elektronów.`]};
    }},
    {id:"r-z-sily", temat:1, nazwa:"Odległość z siły", gen(){
      const q1 = R(1, 9), q2 = R(1, 9), r = pick([3, 5, 6, 10, 12, 15, 20, 30]) / 100, F = k * q1e(q1) * q1e(q2) / r ** 2;
      return {tresc:`Ładunki q₁ = ${q1} µC i q₂ = ${q2} µC odpychają się siłą F = ${f(F)} N. W jakiej odległości od siebie są? Podaj w cm.`,
        pola:[{etykieta:"r =", jednostka:"cm", odp:r * 100}],
        rozw:[`Z prawa Coulomba: r² = k·q₁·q₂ / F, więc r = √(k·q₁·q₂ / F).`,
              `r² = 9·10⁹ · ${q1}·10⁻⁶ · ${q2}·10⁻⁶ / ${f(F)} = ${f(r * r)} m².`,
              `r = ${f(r)} m = <b>${f(r * 100)} cm</b>.`]};
    }},
    {id:"pole-punkt", temat:2, nazwa:"Natężenie pola ładunku", gen(){
      const Q = R(1, 20), r = pick([5, 10, 15, 20, 25, 30, 40, 50]), E = k * Q * 1e-9 / (r / 100) ** 2;
      return {tresc:`Oblicz natężenie pola elektrycznego w odległości ${r} cm od ładunku punktowego Q = ${Q} nC.`,
        pola:[{etykieta:"E =", jednostka:"N/C", odp:E}],
        rozw:[`E = k·Q / r², Q = ${Q}·10⁻⁹ C, r = ${f(r / 100)} m.`, `k·Q = 9·10⁹ · ${Q}·10⁻⁹ = ${f(k * Q * 1e-9)}; r² = ${f((r / 100) ** 2)}.`,
              `E = <b>${f(E)} N/C</b>.`]};
    }},
    {id:"sila-w-polu", temat:2, nazwa:"Siła w polu", gen(){
      const q = R(1, 10), E = pick([500, 800, 1000, 2000, 2500, 5000, 20000, 40000]), F = q * 1e-6 * E;
      return {tresc:`Ładunek q = ${q} µC umieszczono w polu o natężeniu E = ${E} N/C. Jaka siła na niego działa?`,
        pola:[{etykieta:"F =", jednostka:"N", odp:F}],
        rozw:[`F = q·E.`, `F = ${q}·10⁻⁶ C · ${E} N/C = <b>${f(F)} N</b>.`]};
    }},
    {id:"E-z-sily", temat:2, nazwa:"Natężenie z siły", gen(){
      const q = R(1, 10), E = pick([200, 400, 500, 1000, 2000, 4000, 5000, 10000]), F = q * 1e-6 * E;
      return {tresc:`Na ładunek ${q} µC działa w polu elektrycznym siła ${f(F)} N. Oblicz natężenie pola.`,
        pola:[{etykieta:"E =", jednostka:"N/C", odp:E}],
        rozw:[`E = F / q.`, `E = ${f(F)} N / ${q}·10⁻⁶ C = <b>${f(E)} N/C</b>.`]};
    }},
    {id:"pole-jednorodne", temat:3, nazwa:"Pole między płytami (E = U/d)", gen(){
      const U = R(5, 50) * 10, d = R(2, 20), E = U / (d / 1000);
      return {tresc:`Między płytami kondensatora odległymi o d = ${d} mm jest napięcie U = ${U} V. Oblicz natężenie pola między płytami.`,
        pola:[{etykieta:"E =", jednostka:"V/m", odp:E}],
        rozw:[`W polu jednorodnym E = U / d.`, `d = ${d} mm = ${f(d / 1000)} m.`, `E = ${U} / ${f(d / 1000)} = <b>${f(E)} V/m</b>.`]};
    }},
    {id:"U-z-pola", temat:3, nazwa:"Napięcie z natężenia (U = E·d)", gen(){
      const E = pick([1000, 2000, 5000, 10000, 20000, 50000]), d = R(2, 30), U = E * d / 1000;
      return {tresc:`Pole jednorodne ma natężenie E = ${E} V/m. Jakie jest napięcie między punktami odległymi o ${d} mm wzdłuż linii pola?`,
        pola:[{etykieta:"U =", jednostka:"V", odp:U}],
        rozw:[`U = E·d, d = ${f(d / 1000)} m.`, `U = ${E} · ${f(d / 1000)} = <b>${f(U)} V</b>.`]};
    }},
    {id:"praca", temat:3, nazwa:"Praca w polu (W = q·U)", gen(){
      const q = R(1, 20), U = pick([12, 24, 50, 100, 230, 400, 1000]), W = q * 1e-6 * U;
      return {tresc:`Jaką pracę wykonują siły pola, przenosząc ładunek ${q} µC między punktami o napięciu ${U} V?`,
        pola:[{etykieta:"W =", jednostka:"J", odp:W}],
        rozw:[`W = q·U.`, `W = ${q}·10⁻⁶ C · ${U} V = <b>${f(W)} J</b>.`]};
    }},
    {id:"elektron-przysp", temat:3, nazwa:"Elektron przyspieszony napięciem", gen(){
      const U = pick([10, 20, 50, 100, 200, 500, 1000]), Ek = e * U, v = Math.sqrt(2 * e * U / me);
      return {tresc:`Elektron (startuje z prędkością 0) przyspieszono napięciem U = ${U} V. Oblicz jego energię kinetyczną w dżulach i prędkość końcową. (e = 1,6·10⁻¹⁹ C, mₑ = 9,11·10⁻³¹ kg)`,
        pola:[{etykieta:"Eₖ =", jednostka:"J", odp:Ek}, {etykieta:"v =", jednostka:"m/s", odp:v, tol:0.03}],
        rozw:[`Eₖ = e·U = ${U} eV = 1,6·10⁻¹⁹ · ${U} = <b>${f(Ek)} J</b>.`, `½·m·v² = e·U, więc v = √(2·e·U / m).`,
              `v = √(2 · ${f(Ek)} / 9,11·10⁻³¹) = √(${f(2 * Ek / me)}) ≈ <b>${f(v)} m/s</b>.`]};
    }},
    {id:"potencjal", temat:3, nazwa:"Potencjał (V = kQ/r)", gen(){
      const Q = R(1, 20), r = pick([10, 20, 30, 40, 50, 60]), V = k * Q * 1e-9 / (r / 100);
      return {tresc:`Oblicz potencjał pola ładunku Q = ${Q} nC w odległości ${r} cm od niego.`,
        pola:[{etykieta:"V =", jednostka:"V", odp:V}],
        rozw:[`V = k·Q / r (bez kwadratu!).`, `V = 9·10⁹ · ${Q}·10⁻⁹ / ${f(r / 100)} = ${f(k * Q * 1e-9)} / ${f(r / 100)} = <b>${f(V)} V</b>.`]};
    }}
  ];
  function q1e(x){ return x * 1e-6; }
  Licz.init({el:document.getElementById("liczBox"), typy, kolor:n => C(n)});
})();
