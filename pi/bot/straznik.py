#!/usr/bin/env python3
"""
Strażnik poleceń Claude w bocie (hook PreToolUse dla Bash, podpięty przez --settings w serwerek_bot.py).
Claude może uruchamiać dowolne polecenia jako tonyg (potoki, skrypty, edycja plików), blokowane są tylko:
  - sudo i inne podnoszenie uprawnień: zamiast tego znacznik [[SUDO: polecenie]], a bot pyta Antka (Claude i tak działa
    z flagą no_new_privs, więc sudo by nie zadziałało; strażnik tylko podpowiada, jak poprosić),
  - odczyt sekretów (tokeny, hasła, klucze, zmienne środowiska),
  - wyłączanie/restart Pi i niszczenie dysków lub systemu,
  - odcinanie dostępu (Tailscale, SSH) i restart samego bota (przerwałby odpowiedź).
Wyjście 2 = polecenie zablokowane, powód idzie do Claude na stderr.
"""
import json
import re
import sys

ZASADY = [
    (r"(^|[;&|(\s`'\"])(sudo|su|pkexec|doas|run0)(\s|$)|\bcrontab\b|(^|[;&|(\s])at\s|\bsystemd-run\b|systemctl\s+--user|\.config/systemd",
     "sudo nie uruchamiaj sam: dopisz na końcu odpowiedzi [[SUDO: polecenie]] (jedno polecenie, może być z potokiem), "
     "bot zapyta Antka i po jego „Tak” uruchomi je jako root; crontab/at/systemd-run też są zablokowane"),
    (r"/home/tonyg/(bot|glos|portal)/[^ ]*\.py\b[^\n]*(>|\btee\b|\bsed\s+-i)|(>|\btee\b|\bsed\s+-i|\bmv\b|\bcp\b)[^\n]*(serwerek_bot|telefon|straznik|app)\.py"
     r"|uprawnienia\.json|chattr",
     "kodu bota, telefonu, portalu i strażnika nie zmieniaj (robi to sesja Claude Code w chmurze)"),
    (r"/etc/serwerek-bot|token\.env|claude\.env|nas-credentials|/proc/[^ ]*/environ|\.ssh/|\.claude/\.credentials"
     r"|dostep\.json|/var/lib/tailscale|/playit/|/etc/shadow|CLAUDE_CODE_OAUTH_TOKEN|TELEGRAM_TOKEN|SIP_HASLO|POCZTA_|MOBI_|INTERVALS_|mobi\.env|poczta\.env|intervals\.env|google_cookies",
     "to plik albo zmienna z hasłem/tokenem: nie czytaj ani nie ujawniaj sekretów"),
    (r"(^|[;&|(\s])(sudo\s+)?(env|printenv|export\s+-p|set)\s*($|[;&|)])", "wypisanie zmiennych środowiska ujawniłoby token"),
    (r"(^|[;&|(\s])(sudo\s+)?(reboot|shutdown|poweroff|halt|raspiproszewylaczsie)\b|systemctl\s+(reboot|poweroff|halt|kexec)"
     r"|\binit\s+[06]\b",
     "wyłączenie/restart Pi robi tylko Antek (komenda raspiproszewylaczsie albo sudo reboot w terminalu)"),
    (r"\bmkfs|\bwipefs|\bfdisk|\bparted|\bsfdisk|\bdd\b[^\n]*\bof=/dev/|>\s*/dev/(sd|mmcblk|nvme)",
     "operacje na dyskach są zablokowane"),
    (r"\brm\s+(-\S*\s+)*(/|/\*|~|~/|/home|/home/tonyg|/home/tonyg/|/etc|/usr|/boot|/var|/bin|/lib|/mnt/nas|/mnt/nas/Raspberry)/?(\s|$)",
     "usuwanie całego katalogu systemowego/domowego/NAS jest zablokowane"),
    (r"\bchmod\s+-R\s+\S+\s+/(\s|$)|\bchown\s+-R\s+\S+\s+/(\s|$)", "rekurencyjna zmiana uprawnień całego systemu jest zablokowana"),
    (r"\btailscale\s+(down|logout|set|up)\b|systemctl\s+(stop|disable|mask|restart)\s+[^\n]*\b(tailscaled|ssh|sshd)\b",
     "to odcięłoby zdalny dostęp do Pi"),
    (r"systemctl\s+(stop|restart|disable|mask|kill)\s+[^\n]*\bserwerek-(bot|telefon)\b|\bpkill\b[^\n]*serwerek|\bkill(all)?\b[^\n]*serwerek",
     "restart bota przerwałby tę odpowiedź: napisz Antkowi, żeby kliknął Restart albo zrobił to w terminalu"),
    (r"\b(passwd|userdel|usermod|deluser|visudo)\b|/etc/sudoers", "zmiany kont i sudo są zablokowane"),
    (r"\bnft\s+flush\s+ruleset|\biptables\s+-F", "czyszczenie zapory jest zablokowane"),
]


def main():
    try:
        d = json.load(sys.stdin)
    except ValueError:
        return 0
    if d.get("tool_name") != "Bash":
        return 0
    cmd = (d.get("tool_input") or {}).get("command") or ""
    for wzor, powod in ZASADY:
        if re.search(wzor, cmd):
            print(f"Zablokowane przez strażnika Pi: {powod}.", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
