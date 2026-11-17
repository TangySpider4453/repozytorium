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


def tempo(mps):
    if not mps:
        return None
    s = 1000 / mps
    return f"{int(s // 60)}:{int(s % 60):02d}/km"


def dni_wstecz(n, od=None):
    od = od or date.today()
    return [(od - timedelta(days=i)).isoformat() for i in range(n)]
