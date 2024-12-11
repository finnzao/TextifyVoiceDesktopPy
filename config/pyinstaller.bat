#!/bin/bash


echo "Iniciando o processo de build com PyInstaller..."

pyinstaller --windowed --hidden-import=whisper --icon="./bin/icon.ico" --add-data="ffmpeg.exe" --add-data="config.json;." main.py
pyinstaller --windowed --add-data "bin/icon.ico;bin" textifyVoiceModelDownload.py
pyinstaller --windowed --add-data "./bin/icon.ico;bin" textifyVoiceModelDownload.py
pyinstaller --windowed --hidden-import=whisper --icon="bin/icon.ico" --add-data="config.json;." main.py
pyinstaller --windowed --hidden-import=whisper --icon="bin/icon.ico" --add-data="config.json;." --add-data="ffmpeg.exe" main.py

if [ $? -eq 0 ]; then
    echo "Build concluído com sucesso!"
else
    echo "Ocorreu um erro durante o build."
fi

read -p "Pressione qualquer tecla para continuar..."

