#!/bin/bash
# Łączy sesję Claude w chmurze z tailnetem, żeby był dostęp SSH do Raspberry Pi (patrz PLAN.md, sekcja 4).
# Wymaga sekretu środowiska TS_AUTHKEY (klucz Tailscale wielokrotnego użytku, najlepiej efemeryczny).
set -uo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

log() { echo "[session-start] $*" >&2; }

# 1. Binarki Tailscale (statyczne, z pkgs.tailscale.com)
if ! command -v tailscaled >/dev/null 2>&1; then
  tmp=$(mktemp -d)
  if curl -fsSL -m 180 -o "$tmp/ts.tgz" https://pkgs.tailscale.com/stable/tailscale_latest_amd64.tgz \
     && tar xzf "$tmp/ts.tgz" -C "$tmp" --strip-components=1; then
    install -m 755 "$tmp/tailscale" "$tmp/tailscaled" /usr/local/bin/
  else
    log "Nie udało się pobrać Tailscale."
  fi
  rm -rf "$tmp"
fi

# 2. Klient SSH
if ! command -v ssh >/dev/null 2>&1; then
  apt-get install -y -qq openssh-client >/dev/null 2>&1 \
    || { apt-get update -qq >/dev/null 2>&1 && apt-get install -y -qq openssh-client >/dev/null 2>&1; } \
    || log "Nie udało się zainstalować openssh-client."
fi

# 3. Konfiguracja SSH: alias "pi" (tonyg@raspberrypi przez Tailscale, trwałe połączenie)
mkdir -p ~/.ssh && chmod 700 ~/.ssh
cat > ~/.ssh/config <<'CFG'
Host pi
  HostName raspberrypi
  User tonyg
  ProxyCommand tailscale nc %h %p
  StrictHostKeyChecking accept-new
  ControlMaster auto
  ControlPath ~/.ssh/cm-%r@%h
  ControlPersist 8h
  ServerAliveInterval 30
CFG

# 4. Demon i logowanie do tailnetu
command -v tailscaled >/dev/null 2>&1 || exit 0
mkdir -p /var/run/tailscale
if ! tailscale status >/dev/null 2>&1; then
  nohup tailscaled --tun=userspace-networking --state=/var/lib/tailscale-claude.state \
    --socket=/var/run/tailscale/tailscaled.sock >/tmp/tailscaled.log 2>&1 &
  for _ in $(seq 1 20); do [ -S /var/run/tailscale/tailscaled.sock ] && break; sleep 0.5; done
fi

# 5. Wiadomość dla Claude (stdout trafia do kontekstu sesji)
echo "=== Mózg: zacznij od pamiec/MAPA.md (potem pamiec/zasady.md) ==="
if tailscale status >/dev/null 2>&1; then
  echo "Tailscale: połączony. Test: ssh pi hostname"
elif [ -n "${TS_AUTHKEY:-}" ]; then
  if timeout 60 tailscale up --authkey="$TS_AUTHKEY" --hostname=claude-cloud --accept-dns=false >/dev/null 2>&1; then
    echo "Tailscale: połączony kluczem TS_AUTHKEY. Test: ssh pi hostname"
  else
    log "tailscale up z kluczem nie powiodło się (zły lub wygasły klucz?)."
    echo "Tailscale: klucz TS_AUTHKEY nie zadziałał. Uruchom: timeout 20 tailscale up --hostname=claude-cloud --accept-dns=false i daj użytkownikowi link."
  fi
else
  url=$(timeout 20 tailscale up --hostname=claude-cloud --accept-dns=false 2>&1 | grep -o 'https://login.tailscale.com/a/[a-z0-9]*' | head -1)
  echo "Tailscale: brak TS_AUTHKEY. Daj użytkownikowi od razu link do zatwierdzenia: ${url:-(uruchom tailscale up ręcznie)}"
fi
exit 0
