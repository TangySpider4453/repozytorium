// zakladka: Wpisz
/* Ćwiczenie wpisywania form: czasowniki nieregularne 1–23 (podręcznik s. 130), bez Präteritum.
   Tematy jak w T: 1 ge-…-en, 2 bez ge-, 3 mieszane. */
(function(){
  const V = [
    [1,"backen","gebacken","hat","piec",1],[2,"befehlen","befohlen","hat","rozkazywać",2],[3,"beginnen","begonnen","hat","zaczynać",2],
    [4,"beißen","gebissen","hat","gryźć",1],[5,"besitzen","besessen","hat","posiadać",2],[6,"betrügen","betrogen","hat","oszukiwać",2],
    [7,"biegen","gebogen","hat","giąć",1],[7,"biegen","gebogen","ist","skręcać (w kierunku)",1],[8,"bieten","geboten","hat","ofiarowywać, oferować",1],
    [9,"binden","gebunden","hat","wiązać",1],[10,"bitten","gebeten","hat","prosić",1],[11,"bleiben","geblieben","ist","zostawać",1],
    [12,"braten","gebraten","hat","smażyć",1],[13,"brechen","gebrochen","hat","łamać",1],[14,"brennen","gebrannt","hat","palić się, płonąć",3],
    [15,"bringen","gebracht","hat","przynosić",3],[16,"denken","gedacht","hat","myśleć",3],[17,"dürfen","gedurft","hat","móc, mieć pozwolenie",3],
    [18,"empfangen","empfangen","hat","przyjmować",2],[19,"empfehlen","empfohlen","hat","polecać",2],[20,"empfinden","empfunden","hat","czuć, odczuwać",2],
    [21,"erschrecken","erschrocken","ist","przestraszyć się",2],[22,"essen","gegessen","hat","jeść",1],[23,"fahren","gefahren","ist","jechać",1],
    [23,"fahren","gefahren","hat","wieźć",1]
  ];
  const GR = {1:"ge- + rdzeń + -en", 2:"bez ge-, bo przedrostek be-/emp-/er- jest nieakcentowany", 3:"czasownik mieszany: ge- + zmieniony rdzeń + -t"};
  const pick = a => a[Math.floor(Math.random() * a.length)];
  const uniq = [...new Map(V.map(v => [v[1], v])).values()];
  const wiersz = v => `${v[0]}. <b>${v[1]}</b> – ${v[3]} ${v[2]} – ${v[4]}`;
  const typy = [
    {id:"partizip", temat:0, nazwa:"Partizip Perfekt", gen(){
      const v = pick(uniq);
      return {tresc:`Podaj Partizip Perfekt: <b lang="de">${v[1]}</b> (${v[4]})`,
        pola:[{etykieta:"Partizip:", odp:[v[2]], rodzaj:"tekst"}],
        rozw:[wiersz(v), `Grupa: ${GR[v[5]]}.`]};
    }},
    {id:"perfekt", temat:0, nazwa:"Perfekt z hat / ist", gen(){
      const v = pick(V);
      return {tresc:`Uzupełnij w Perfekt (er/sie/es): <b lang="de">${v[1]}</b> = ${v[4]}<br>er ___`,
        pola:[{etykieta:"er", odp:[`${v[3]} ${v[2]}`], rodzaj:"tekst"}],
        rozw:[wiersz(v), v[3] === "ist" ? "Z <b>sein</b>: ruch, zmiana stanu albo bleiben." : "Z <b>haben</b> (większość czasowników)."]};
    }},
    {id:"z-polskiego", temat:0, nazwa:"Z polskiego: bezokolicznik + Partizip", gen(){
      const v = pick(V);
      return {tresc:`Przetłumacz na niemiecki i podaj Partizip Perfekt z hat/ist: <b>${v[4]}</b>`,
        pola:[{etykieta:"Infinitiv:", odp:[v[1]], rodzaj:"tekst"}, {etykieta:"Perfekt:", odp:[`${v[3]} ${v[2]}`], rodzaj:"tekst"}],
        rozw:[wiersz(v)]};
    }},
    {id:"bezokolicznik", temat:0, nazwa:"Bezokolicznik z Partizip", gen(){
      const v = pick(uniq);
      return {tresc:`Od jakiego czasownika jest forma <b lang="de">${v[2]}</b>? Podaj bezokolicznik.`,
        pola:[{etykieta:"Infinitiv:", odp:[v[1]], rodzaj:"tekst"}],
        rozw:[wiersz(v)]};
    }}
  ];
  Licz.init({el:document.getElementById("liczBox"), typy, kolor:() => "var(--nav)", lang:"de", nazwa:"Wpisz",
    intro:"Wpisz formę z pamięci (wielkość liter nie ma znaczenia, ale umlauty i ß tak: ü, ö, ä, ß). Seria ma 10 zadań i zapisuje się w wynikach."});
})();
