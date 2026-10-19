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

# 4. Demon i logowanie do tailnetu (stan w pamięci = węzeł efemeryczny, znika po sesji)
command -v tailscaled >/dev/null 2>&1 || exit 0
if [ -z "${TS_AUTHKEY:-}" ]; then
  log "Brak sekretu TS_AUTHKEY: Tailscale zainstalowany, ale niepołączony."
  exit 0
fi
mkdir -p /var/run/tailscale
if ! tailscale status >/dev/null 2>&1; then
  nohup tailscaled --tun=userspace-networking --state=mem: \
    --socket=/var/run/tailscale/tailscaled.sock >/tmp/tailscaled.log 2>&1 &
  for _ in $(seq 1 20); do [ -S /var/run/tailscale/tailscaled.sock ] && break; sleep 0.5; done
  timeout 60 tailscale up --authkey="$TS_AUTHKEY" --hostname=claude-cloud --accept-dns=false >/dev/null 2>&1 \
    || log "tailscale up nie powiodło się (zły lub wygasły klucz?)."
fi
exit 0
