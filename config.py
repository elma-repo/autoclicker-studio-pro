import os
import re
import sys
import ctypes
import json

# Forzar DPI-Aware para multimonitor
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

TARGET_GAME_IDENTIFIER = "War of Genesis Idle Loot"

def ruta_recurso(ruta_relativa):
    """Resuelve la ruta correcta en modo script o dentro del .exe compilado."""
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, ruta_relativa)

# Cada perfil es un archivo perfiles/<nombre>.json
PROFILES_DIR = ruta_recurso("perfiles")
# Formato anterior (todos los perfiles en un solo JSON suelto). Se migra solo la primera vez.
LEGACY_PROFILES_FILE = ruta_recurso("clicker_profiles_vision_pro.json")

NOMBRE_POR_DEFECTO = "Perfil por defecto"
_RESERVADOS = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
               *(f"LPT{i}" for i in range(1, 10))}


def nombre_valido(nombre):
    """Convierte un nombre escrito por el usuario en uno seguro como nombre de archivo."""
    limpio = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(nombre or "")).strip().rstrip(". ")
    limpio = limpio[:60].rstrip(". ")
    if not limpio:
        return NOMBRE_POR_DEFECTO
    if limpio.split(".")[0].upper() in _RESERVADOS:
        limpio = f"_{limpio}"
    return limpio


def _ruta_perfil(nombre):
    return os.path.join(PROFILES_DIR, nombre_valido(nombre) + ".json")


def guardar_perfil(nombre, datos):
    """Guarda un perfil en perfiles/<nombre>.json (escritura atómica). Devuelve la ruta."""
    os.makedirs(PROFILES_DIR, exist_ok=True)
    destino = _ruta_perfil(nombre)
    temporal = destino + ".tmp"
    with open(temporal, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)
    os.replace(temporal, destino)
    return destino


def guardar_perfiles(datos):
    """Guarda todos los perfiles del diccionario {nombre: configuración}."""
    for nombre, cfg in datos.items():
        guardar_perfil(nombre, cfg)


def _migrar_perfiles_antiguos():
    """Pasa clicker_profiles_vision_pro.json a la carpeta perfiles/ (una sola vez).

    El archivo original no se borra: queda como .bak junto a la carpeta.
    """
    if not os.path.isfile(LEGACY_PROFILES_FILE):
        return
    try:
        with open(LEGACY_PROFILES_FILE, "r", encoding="utf-8") as f:
            viejos = json.load(f)
        if not isinstance(viejos, dict):
            return
        os.makedirs(PROFILES_DIR, exist_ok=True)
        for nombre, cfg in viejos.items():
            if not isinstance(cfg, dict):
                continue
            base = nombre_valido(nombre)
            candidato, n = base, 2
            while os.path.exists(_ruta_perfil(candidato)):   # nunca pisa un perfil existente
                candidato, n = f"{base} ({n})", n + 1
            guardar_perfil(candidato, cfg)

        respaldo, n = LEGACY_PROFILES_FILE + ".bak", 2
        while os.path.exists(respaldo):
            respaldo, n = f"{LEGACY_PROFILES_FILE}.bak{n}", n + 1
        os.replace(LEGACY_PROFILES_FILE, respaldo)
    except Exception:
        pass   # si algo falla, el archivo original queda intacto y se reintenta al abrir


def cargar_perfiles():
    """Devuelve {nombre: configuración} con todos los perfiles de la carpeta perfiles/."""
    _migrar_perfiles_antiguos()
    perfiles = {}
    if os.path.isdir(PROFILES_DIR):
        for archivo in sorted(os.listdir(PROFILES_DIR), key=str.lower):
            if not archivo.lower().endswith(".json"):
                continue
            try:
                with open(os.path.join(PROFILES_DIR, archivo), "r", encoding="utf-8") as f:
                    datos = json.load(f)
            except Exception:
                continue
            if isinstance(datos, dict):
                perfiles[os.path.splitext(archivo)[0]] = datos
    return perfiles
