import os
from urllib.request import urlretrieve

URL = "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8x.pt"
WEIGHTS = "yolov8x.pt"

if os.path.exists(WEIGHTS):
    print(f"Arquivo '{WEIGHTS}' ja existe. Nenhum download necessario.")
else:
    print(f"Baixando modelo de {URL} ...")
    urlretrieve(URL, WEIGHTS)
    print("Download concluido.")