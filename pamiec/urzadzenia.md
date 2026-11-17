# Urządzenia i sieć

| Urządzenie | Rola | Tailscale | Inne |
|---|---|---|---|
| **Raspberry Pi 4B 8 GB** | serwer domowy: portal, bot, telefon, NAS-kopie, Minecraft | `raspberrypi` 100.108.241.58 | LAN eth0 172.23.0.20, wlan0 .24; Debian 13 aarch64, user `tonyg`, sudo bez hasła, karta 58 GB |
| **Raspberry Pi 5 8 GB + AI HAT+ Hailo-8** | mózg łazika | `rpi-5-1` 100.64.96.61 | LAN 172.23.0.15, user `rpi`, ekran HDMI 1024×600 |
| Pi Zero 2W **a1** | stacja LoRa | `rpi-zero2w-a1` | user `rpi` |
| Pi Zero 2W **a2** | satelita LoRa | `rpi-zero2w-a2` | user `rpi` |
| **NAS Synology DSM 7** | kopie, zdjęcia, logi | — | 172.23.0.28, udział `Tony-Folder` → `/mnt/nas` na Pi 4 (960 GB, 16% zajęte 17.11) |
| iPhone 14 Pro, iPad, PC Windows | Antek | `iphone-14-pro`, `ipad157`, `desktop-lgevlh8` | |
| `pc-antek` | komputer Antka (Windows) | `pc-antek` | |
| `claude-cloud` | sesja Claude w chmurze | efemeryczny | |

Łazik — sprzęt (kamera C170, L298N, MPU6050, BME280, LoRa DX-LR03): `lazik/LAZIK.md` na gałęzi `lazik-mapa`.
