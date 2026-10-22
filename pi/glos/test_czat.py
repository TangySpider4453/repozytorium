# Test czatu usługi telefonu na samym Pi (telefon.py z SIP_DOMENA=lokalnie): wysyła wiadomości jako „antek”,
# wypisuje odpowiedzi.   python3 test_czat.py "stan" "Ile jest wolnego miejsca na karcie?" "PLIK:https://…/nagranie.wav"
import sys, time
import pjsua2 as pj
ep = pj.Endpoint(); ep.libCreate(); c = pj.EpConfig(); c.uaConfig.threadCnt = 0; c.uaConfig.mainThreadOnly = True
c.logConfig.consoleLevel = 1; ep.libInit(c)
t = pj.TransportConfig(); t.port = 5081; ep.transportCreate(pj.PJSIP_TRANSPORT_UDP, t); ep.transportCreate(pj.PJSIP_TRANSPORT_TCP, t)
ep.libStart(); ep.audDevManager().setNullDev()
class K(pj.Account):
    def onInstantMessage(self, prm):
        print(time.strftime("%H:%M:%S"), "ODPOWIEDŹ", f"[{prm.contentType}]:", prm.msgBody.replace("\n", " | ")[:400], flush=True)
ac = pj.AccountConfig(); ac.idUri = "sip:antek@127.0.0.1:5081"; k = K(); k.create(ac)
bc = pj.BuddyConfig(); bc.uri = "sip:pi@127.0.0.1:5070"; b = pj.Buddy(); b.create(k, bc)
for tekst in sys.argv[1:]:
    p = pj.SendInstantMessageParam()
    if tekst.startswith("PLIK:"):         # głosówka: adres pliku na serwerze Linphone
        p.contentType = "application/vnd.gsma.rcs-ft-http+xml"
        p.content = ('<?xml version="1.0" encoding="UTF-8"?><file xmlns="urn:gsma:params:xml:ns:rcs:rcs:fthttp"><file-info type="file">'
                     f'<content-type>audio/wav;voice-recording=yes</content-type><data url="{tekst[5:]}"/></file-info></file>')
    else:
        p.content = tekst; p.contentType = "text/plain"
    b.sendInstantMessage(p)
    print(time.strftime("%H:%M:%S"), "WYSŁANO:", tekst, flush=True)
    t0 = time.time()
    while time.time() - t0 < 60:
        ep.libHandleEvents(50)
del b, k
ep.libDestroy()
