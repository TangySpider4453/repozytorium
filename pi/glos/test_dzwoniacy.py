# Test usługi telefonu na samym Pi (bez Linphone): uruchom telefon.py z SIP_DOMENA=lokalnie, potem:
#   python3 test_dzwoniacy.py pytanie.wav nagranie.wav 90
# Test: „Antek” dzwoni do telefonu serwerka na 127.0.0.1:5070, mówi pytanie (plik WAV), nagrywa odpowiedź.
import sys, time
import pjsua2 as pj
pytanie, nagranie, czekaj = sys.argv[1], sys.argv[2], float(sys.argv[3])
ep = pj.Endpoint(); ep.libCreate(); c = pj.EpConfig(); c.uaConfig.threadCnt = 0; c.uaConfig.mainThreadOnly = True
c.medConfig.clockRate = 16000; c.logConfig.consoleLevel = 1; c.logConfig.level = 5; c.logConfig.filename = "/tmp/dzwoniacy-sip.log"; ep.libInit(c)
t = pj.TransportConfig(); t.port = 5080; ep.transportCreate(pj.PJSIP_TRANSPORT_UDP, t); ep.transportCreate(pj.PJSIP_TRANSPORT_TCP, t); ep.libStart(); ep.audDevManager().setNullDev()
ac = pj.AccountConfig(); ac.idUri = "sip:antek@127.0.0.1:5080"; acc = pj.Account(); acc.create(ac)
stan = {"media": None, "koniec": False}
class P(pj.Call):
    def onCallState(self, prm):
        ci = self.getInfo(); print(time.strftime("%H:%M:%S"), "stan:", ci.stateText, flush=True)
        if ci.state == pj.PJSIP_INV_STATE_DISCONNECTED: stan["koniec"] = True
    def onCallMediaState(self, prm):
      try:
        ci = self.getInfo()
        for mi in ci.media:
            print("media:", mi.type, mi.status, flush=True)
            if mi.type == pj.PJMEDIA_TYPE_AUDIO and mi.status == pj.PJSUA_CALL_MEDIA_ACTIVE and stan["media"] is None:
                stan["media"] = self.getAudioMedia(mi.index)
                stan["rec"] = pj.AudioMediaRecorder(); stan["rec"].createRecorder(nagranie); stan["media"].startTransmit(stan["rec"])
      except Exception as ex:
        import traceback; traceback.print_exc()
p = P(acc); p.makeCall("sip:pi@127.0.0.1:5070", pj.CallOpParam(True))
t0 = time.time(); zagrane = False
while time.time() - t0 < czekaj and not stan["koniec"]:
    ep.libHandleEvents(20)
    if stan.get("media") is None and time.time() - t0 > 1:
        if int(time.time()*10) % 20 == 0: print("info:", [(m.index, m.type, m.status) for m in p.getInfo().media], pj.PJMEDIA_TYPE_AUDIO, pj.PJSUA_CALL_MEDIA_ACTIVE, flush=True)
        ci2 = p.getInfo()
        for mi in ci2.media:
            if mi.type == pj.PJMEDIA_TYPE_AUDIO and mi.status == pj.PJSUA_CALL_MEDIA_ACTIVE:
                stan["media"] = p.getAudioMedia(mi.index); print("media aktywne (odpytane)", flush=True)
                stan["rec"] = pj.AudioMediaRecorder(); stan["rec"].createRecorder(nagranie); stan["media"].startTransmit(stan["rec"])
    if stan["media"] is not None and not zagrane and time.time() - t0 > 6:
        g = pj.AudioMediaPlayer(); g.createPlayer(pytanie, pj.PJMEDIA_FILE_NO_LOOP); g.startTransmit(stan["media"]); zagrane = True
        print(time.strftime("%H:%M:%S"), "mówię pytanie", flush=True)
if not stan["koniec"]:
    p.hangup(pj.CallOpParam())
    for _ in range(50): ep.libHandleEvents(20)
stan.clear(); del p
ep.libDestroy()
