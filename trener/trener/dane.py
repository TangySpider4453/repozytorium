"""Wyliczanie wartości dnia z surowych odpowiedzi Garmina (odporne na brakujące pola i stare formaty)."""
import json
from datetime import date, datetime, timedelta

from . import baza


def szukaj(obj, klucz):
    """pierwsza wartość klucza w zagnieżdżonym JSON (dict/list)"""
    if isinstance(obj, dict):
        if klucz in obj and obj[klucz] is not None:
            return obj[klucz]
        for v in obj.values():
            w = szukaj(v, klucz)
            if w is not None:
                return w
    elif isinstance(obj, list):
        for v in obj:
            w = szukaj(v, klucz)
            if w is not None:
                return w
    return None


def _godz(ms):
    if not ms:
        return None
    return datetime.utcfromtimestamp(ms / 1000).strftime("%H:%M")      # *Local = już czas lokalny jako „UTC”


def _r(x, n=1):
    return None if x is None else round(x, n)


def przytnij_sen(s):
    """z ~200 KB zostawiamy podsumowanie i hipnogram"""
    if not isinstance(s, dict):
        return s
    zostaw = ("dailySleepDTO", "sleepLevels", "restlessMomentsCount", "avgOvernightHrv", "hrvStatus",
              "bodyBatteryChange", "restingHeartRate", "avgSleepStress")
    return {k: s[k] for k in zostaw if k in s}


def wylicz(db, d):
    w = {}
    sen = baza.surowe(db, "sen", d)
    s = (sen or {}).get("dailySleepDTO") or {}
    if s.get("sleepTimeSeconds"):
        w.update(sen_h=_r(s["sleepTimeSeconds"] / 3600, 2), sen_gleboki_h=_r((s.get("deepSleepSeconds") or 0) / 3600, 2),
                 sen_lekki_h=_r((s.get("lightSleepSeconds") or 0) / 3600, 2), sen_rem_h=_r((s.get("remSleepSeconds") or 0) / 3600, 2),
                 sen_czuwanie_min=round((s.get("awakeSleepSeconds") or 0) / 60), sen_wybudzenia=s.get("awakeCount"),
                 sen_wynik=((s.get("sleepScores") or {}).get("overall") or {}).get("value"),
                 sen_stres=s.get("avgSleepStress"), sen_tetno=s.get("avgHeartRate"),
                 sen_oddech=s.get("averageRespirationValue"), sen_spo2=s.get("averageSpO2Value"),
                 sen_od=_godz(s.get("sleepStartTimestampLocal")), sen_do=_godz(s.get("sleepEndTimestampLocal")),
                 sen_uwagi=[x for x in (s.get("sleepScoreFeedback"), s.get("sleepScoreInsight")) if x and x != "NONE"])
    h = (baza.surowe(db, "hrv", d) or {}).get("hrvSummary") or {}
    if h:
        w.update(hrv=h.get("lastNightAvg"), hrv_7d=h.get("weeklyAvg"), hrv_status=h.get("status"),
                 hrv_norma=[(h.get("baseline") or {}).get("balancedLow"), (h.get("baseline") or {}).get("balancedUpper")])
    u = baza.surowe(db, "sum", d) or {}
    if u:
        w.update(tetno_spocz=u.get("restingHeartRate"), stres=u.get("averageStressLevel"),
                 bb_max=u.get("bodyBatteryHighestValue"), bb_min=u.get("bodyBatteryLowestValue"),
                 bb_rano=u.get("bodyBatteryAtWakeTime"), kroki=u.get("totalSteps"),
                 kcal_akt=u.get("activeKilocalories"),
                 min_intens=(u.get("moderateIntensityMinutes") or 0) + 2 * (u.get("vigorousIntensityMinutes") or 0))
    g = baza.surowe(db, "gotowosc", d)
    if isinstance(g, list) and g:
        o = max(g, key=lambda x: x.get("timestamp") or "")
        w.update(gotowosc=o.get("score"), gotowosc_poziom=o.get("level"), regeneracja_h=_r((o.get("recoveryTime") or 0) / 60),
                 obc_ostre=o.get("acuteLoad"), gotowosc_uwaga=o.get("feedbackShort"))
    st = baza.surowe(db, "status", d)
    if st:
        vo = (st.get("mostRecentVO2Max") or {})
        w.update(vo2_bieg=(vo.get("generic") or {}).get("vo2MaxPreciseValue"),
                 vo2_rower=(vo.get("cycling") or {}).get("vo2MaxPreciseValue"))
        ts = st.get("mostRecentTrainingStatus") or {}
        dane = next(iter((ts.get("latestTrainingStatusData") or {}).values()), None) or {}
        acwr = dane.get("acuteTrainingLoadDTO") or {}
        w.update(status=dane.get("trainingStatusFeedbackPhrase") or dane.get("trainingStatus"),
                 obc_ostre=w.get("obc_ostre") or acwr.get("dailyTrainingLoadAcute"),
                 obc_przewlekle=acwr.get("dailyTrainingLoadChronic"), acwr=acwr.get("dailyAcuteChronicWorkloadRatio"))
        lb = next(iter(((st.get("mostRecentTrainingLoadBalance") or {}).get("metricsTrainingLoadBalanceDTOMap") or {}).values()), None)
        if lb:
            w.update(balans=lb.get("trainingBalanceFeedbackPhrase"))
    akt = [dict(r) for r in db.execute("SELECT typ, nazwa, dane FROM aktywnosci WHERE dzien=?", (d,))]
    if akt:
        lista = []
        for a in akt:
            j = baza.rozpakuj(a["dane"]) or {}
            lista.append({"typ": a["typ"], "nazwa": a["nazwa"], "min": round((j.get("duration") or 0) / 60),
                          "km": _r((j.get("distance") or 0) / 1000), "obc": _r(j.get("activityTrainingLoad"), 0)})
        w.update(treningi=lista, trening_min=sum(x["min"] for x in lista),
                 trening_obc=round(sum(x["obc"] or 0 for x in lista)))
    w = {k: v for k, v in w.items() if v not in (None, [], "")}
    if w:
        db.execute("INSERT OR REPLACE INTO dni VALUES (?,?)", (d, json.dumps(w, ensure_ascii=False)))
    return w


def streszczenie_aktywnosci(j):
    """najważniejsze liczby z podsumowania aktywności (lista Garmina)"""
    typ = (j.get("activityType") or {}).get("typeKey")
    w = {"id": j.get("activityId"), "start": (j.get("startTimeLocal") or "")[:16], "typ": typ, "nazwa": j.get("activityName"),
         "min": round((j.get("duration") or 0) / 60), "km": _r((j.get("distance") or 0) / 1000, 2),
         "tetno": _r(j.get("averageHR"), 0), "tetno_max": _r(j.get("maxHR"), 0),
         "obc": _r(j.get("activityTrainingLoad"), 0), "te_aer": j.get("aerobicTrainingEffect"),
         "te_anaer": j.get("anaerobicTrainingEffect"), "efekt": j.get("trainingEffectLabel"),
         "przewyzszenie": _r(j.get("elevationGain"), 0), "kcal": _r(j.get("calories"), 0)}
    if j.get("avgPower"):
        w.update(moc=_r(j["avgPower"], 0), moc_np=_r(j.get("normPower"), 0), moc_max=_r(j.get("maxPower"), 0),
                 kadencja=_r(j.get("averageBikingCadenceInRevPerMinute"), 0), tss=_r(j.get("trainingStressScore"), 0),
                 if_=_r(j.get("intensityFactor"), 2))
    if typ and ("run" in typ or typ == "walking") and j.get("averageSpeed"):
        w["tempo"] = tempo(j["averageSpeed"])
    elif j.get("averageSpeed"):
        w["kmh"] = _r(j["averageSpeed"] * 3.6)
    strefy = [j.get(f"hrTimeInZone_{i}") for i in range(1, 6)]
    if any(strefy):
        w["strefy_min"] = [round((x or 0) / 60) for x in strefy]
    if j.get("totalSets"):
        w.update(serie=j.get("totalSets"), powt=j.get("totalReps"))
    return {k: v for k, v in w.items() if v not in (None, 0, [], "")}


def statystyki_pelne(j):
    """wszystko, co ciekawe z podsumowania Garmina — do ekranu treningu (grupy [nazwa, [[etykieta, wartość], …]])"""
    def mm(s):
        s = round(s or 0)
        return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"
    def r(k, n=0, mn=1):
        v = j.get(k)
        return None if v in (None, 0) else (round(v * mn) if n == 0 else round(v * mn, n))
    typ = (j.get("activityType") or {}).get("typeKey") or ""
    bieg = "run" in typ or typ == "walking"
    g = [
        ["Czas", [["całkowity", mm(j.get("elapsedDuration")) if j.get("elapsedDuration") else None],
                  ["w ruchu", mm(j.get("movingDuration")) if j.get("movingDuration") else None],
                  ["na stojąco", mm(j.get("standingTime")) if j.get("standingTime") else None]]],
        ["Tętno", [["średnie", r("averageHR")], ["max", r("maxHR")], ["min", r("minHR")]]],
        ["Moc", [["średnia", r("avgPower")], ["NP", r("normPower")], ["max", r("maxPower")],
                 ["max 20 min", r("max20MinPower")], ["IF", r("intensityFactor", 2)], ["TSS", r("trainingStressScore")],
                 ["praca kJ", round((j.get("avgPower") or 0) * (j.get("duration") or 0) / 1000) or None],
                 ["balans L/P", f"{j['avgLeftBalance']:.0f}/{100 - j['avgLeftBalance']:.0f}" if j.get("avgLeftBalance") else None],
                 ["śr. siedząc", r("avgSeatedPower")], ["śr. na stojąco", r("avgStandingPower")]]],
        ["Prędkość", [["średnia", (f"{1000 / j['averageSpeed'] // 60:.0f}:{1000 / j['averageSpeed'] % 60:02.0f}/km" if bieg
                                    else f"{j['averageSpeed'] * 3.6:.1f} km/h") if j.get("averageSpeed") else None],
                      ["max", f"{j['maxSpeed'] * 3.6:.1f} km/h" if j.get("maxSpeed") else None],
                      ["dystans", f"{j['distance'] / 1000:.2f} km" if j.get("distance") else None]]],
        ["Kadencja", [["średnia", r("averageBikingCadenceInRevPerMinute") or r("averageRunningCadenceInStepsPerMinute")],
                      ["max", r("maxBikingCadenceInRevPerMinute") or r("maxRunningCadenceInStepsPerMinute")],
                      ["długość kroku", f"{j['avgStrideLength'] / 100:.2f} m" if j.get("avgStrideLength") else None],
                      ["kontakt z podłożem", f"{j['avgGroundContactTime']:.0f} ms" if j.get("avgGroundContactTime") else None],
                      ["oscylacja pionowa", f"{j['avgVerticalOscillation']:.1f} cm" if j.get("avgVerticalOscillation") else None]]],
        ["Teren", [["przewyższenie", r("elevationGain")], ["spadek", r("elevationLoss")],
                   ["wysokość min–max", f"{j['minElevation']:.0f}–{j['maxElevation']:.0f} m" if j.get("maxElevation") else None],
                   ["temperatura", f"{j['minTemperature']:.0f}–{j['maxTemperature']:.0f} °C" if j.get("maxTemperature") is not None and j.get("minTemperature") is not None else None],
                   ["grit (MTB)", r("grit", 1)], ["flow (MTB)", r("avgFlow", 1)], ["skoki", r("jumpCount")]]],
        ["Efekt", [["tlenowy", r("aerobicTrainingEffect", 1)], ["beztlenowy", r("anaerobicTrainingEffect", 1)],
                   ["obciążenie", r("activityTrainingLoad")], ["VO2max", r("vO2MaxValue")],
                   ["Body Battery", f"{j['differenceBodyBattery']:+d}" if j.get("differenceBodyBattery") else None],
                   ["min. intensywne", (j.get("moderateIntensityMinutes") or 0) + 2 * (j.get("vigorousIntensityMinutes") or 0) or None]]],
        ["Ciało", [["kcal", r("calories")], ["w tym spoczynkowe", r("bmrCalories")], ["pot (szac.)", f"{j['waterEstimated']:.0f} ml" if j.get("waterEstimated") else None],
                   ["oddech śr.", f"{j['avgRespirationRate']:.0f}/min" if j.get("avgRespirationRate") else None],
                   ["oddech max", f"{j['maxRespirationRate']:.0f}/min" if j.get("maxRespirationRate") else None]]],
        ["Siłka", [["serie", r("totalSets")], ["powtórzenia", r("totalReps")]]],
    ]
    jedn = {"Tętno": " bpm", "Moc": " W", "Teren": " m", "Kadencja": " rpm"}
    wyn = []
    for nazwa, pola in g:
        p = [[e, str(v) if isinstance(v, str) or e in ("IF", "TSS", "praca kJ", "balans L/P", "wysokość min–max", "temperatura",
                                                   "grit (MTB)", "flow (MTB)", "skoki")
              else f"{v}{jedn.get(nazwa, '')}"] for e, v in pola if v not in (None, "", 0)]
        p = [[e, v.replace(".", ",")] for e, v in p]          # polski przecinek dziesiętny
        if p:
            wyn.append([nazwa, p])
    krzywa = [[s, j[f"maxAvgPower_{s}"]] for s in (1, 2, 5, 10, 20, 30, 60, 120, 300, 600, 1200, 1800, 3600, 5400, 7200)
              if j.get(f"maxAvgPower_{s}")]
    strefy_mocy = [round((j.get(f"powerTimeInZone_{i}") or 0) / 60, 1) for i in range(1, 8)]
    return {"grupy": wyn, "krzywa_mocy": krzywa, "strefy_mocy": strefy_mocy if any(strefy_mocy) else None}


def tempo(mps):
    if not mps:
        return None
    s = 1000 / mps
    return f"{int(s // 60)}:{int(s % 60):02d}/km"


def dni_wstecz(n, od=None):
    od = od or date.today()
    return [(od - timedelta(days=i)).isoformat() for i in range(n)]
