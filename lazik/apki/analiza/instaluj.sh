#!/bin/bash
# Instalacja aplikacji "Łazik: analiza wideo" na Pi 5 (uruchamiać jako rpi z ~/lazik/analiza).
# Wymaga aplikacji "Łazik: wizja" w ~/lazik/wizja (modele YOLO, głębia, wspólny kod).
set -e
cd "$(dirname "$0")"
sudo apt-get install -y python3-flask python3-qrcode python3-opencv python3-pyqt5
mkdir -p modele filmy raporty
[ -f modele/yunet.onnx ] || curl -fsSL -o modele/yunet.onnx \
  https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
[ -f modele/sface.onnx ] || curl -fsSL -o modele/sface.onnx \
  https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx
chmod +x uruchom.sh analizator.py serwer_wideo.py
sudo cp lazik-wideo.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lazik-wideo.service
cp lazik-analiza.desktop ~/Desktop/ && cp lazik-analiza.desktop ~/.local/share/applications/ && chmod +x ~/Desktop/lazik-analiza.desktop
echo "Gotowe. Opis AI wymaga Ollamy z modelem gemma3:4b:"
echo "  curl -fsSL https://ollama.com/install.sh | sh && ollama pull gemma3:4b"
