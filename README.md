# autoclicker-studio-pro
Es una plataforma avanzada de automatización y ejecutor de macros construida en Python con la interfaz gráfica `CustomTkinter`. Diseñada con una arquitectura modular y un motor multihilo, permite automatizar desde clics repetitivos e interacciones con teclado hasta flujos de trabajo basados en reconocimiento visual (*Computer Vision*) y árboles de lógica condicional editables visualmente.

**Versión actual:** `1.0.0 · Studio`

## Características Principales

* **Clicker Principal**
  * Clics sencillos o dobles con soporte para botón izquierdo, derecho o central.
  * Intervalos personalizables en milisegundos, segundos, minutos u horas.
  * Posición del cursor: actual o fija (X, Y capturados con el ratón).

* **Editor de Secuencias y Macros**
  * Grabación en tiempo real de entradas físicas (ratón y teclado).
  * Editor visual para reordenar, duplicar, modificar retrasos o insertar pasos manualmente.
  * Ajustes de velocidad de reproducción (0.5× a 3×) y repetición cíclica o fija.
  * Exportación e importación de secuencias en formato JSON.

* **Auto-Inventario (War of Genesis)**
  * Detección visual del almacén abierto/cerrado y del botón «Mover».
  * Traslado automático de ítems entre pestañas (hasta 6).
  * Bucle configurable en horas, minutos y segundos.

* **Black Souls**
  * Farmeo automático por ruta configurable (calibración de pasos y tiempos).
  * Detección de combate por imagen y resolución automática de peleas.
  * Consumo automático de almas cada N vueltas.

* **Motor de Flujos (Flow Engine)**
  * Editor visual en ventana flotante: arrastra bloques desde la paleta al lienzo.
  * Conexión de bloques con dos clics o arrastrando desde los puertos.
  * Zoom, paneo con botón central y desplazamiento con la rueda.
  * Ventana objetivo seleccionable: las imágenes se buscan solo dentro de esa ventana y los clics se calculan respecto a su origen.
  * Importar y exportar flujos como JSON.
  * Acciones basadas en imagen, coordenadas, teclas, retardos, variables y condicionales.

* **Gestión de Perfiles y Sistema**
  * Almacenamiento de configuraciones por perfil en formato JSON dentro de `perfiles/`.
  * Hotkeys globales para iniciar y detener procesos (F6–F10).
  * Parada de emergencia global (`Shift + Esc`).
  * Minimización a la bandeja del sistema (*System Tray*).

## Requisitos e Instalación

### Requisitos

* **Python 3.10** o superior.
* **Windows 10/11** (usa `pywin32`, `ctypes.windll`, `os.startfile`).
* Permisos de administrador recomendados para simular eventos sobre ventanas elevadas.

### Instalación

1. Descarga o clona este repositorio.
2. En la raíz del proyecto:

```bash
- Instalar dependencias: `pip install -r requirements.txt`
- Ejecutar: `python main.py`
- Compilar el lanzador (pequeño, requiere Python instalado): `build_launcher.bat`
- Compilar el .exe autónomo: `build_exe.bat` (resultado en `dist/`) (Eliminado)
- Comprobar sintaxis sin abrir la GUI: `python -m py_compile main.py tab_*.py flow_canvas.py vision.py`
- No hay tests automatizados ni deploy: la distribución es el .exe.