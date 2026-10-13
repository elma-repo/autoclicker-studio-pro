```markdown
# AutoClicker Studio Pro

## 1. Identidad del proyecto
- App de escritorio **solo Windows** (usa `pywin32`, `ctypes.windll`, `os.startfile`).
- Python 3 + **CustomTkinter >= 5.2** (GUI), `pynput` (teclado/ratón global), `pyautogui` + `opencv-python` + `Pillow` (visión por imagen), `pystray` (bandeja), `pyinstaller` (build).
- Punto de entrada: `main.py` (clase `AutoClickerVisionPro`). Tema oscuro, acento violeta.
- Idioma de la interfaz y de los comentarios: **español**.
- Versión actual: `1.0.0 · Studio` (chip en `tab_about.APP_VERSION` y `APP_CODENAME`).
- Lanzador: `AutoClicker_Studio.exe` (C#, fuentes en `launcher/`, ~6 KB) ejecuta `main.py` con el Python del equipo, con permisos de administrador y consola oculta.

## 2. Convenciones de código
- **Estructura**: lógica de motores en módulos planos (`clicker.py`, `macro_engine.py`, `vision.py`, `black_souls.py`); una pestaña por archivo `tab_*.py`; componentes reutilizables y paleta en `ui_components.py`; rutas y perfiles en `config.py`. Los perfiles se guardan como un archivo por perfil en `perfiles/<nombre>.json`.
- **Pestañas**: clase que hereda `ctk.CTkFrame`, constructor `(master, app_ref)`, UI en `_build_ui()` con métodos `_build_*_card()`. Usar `Card`, `COLORS`, `FONT` y las fábricas `styled_*`, `primary_button`, `ghost_button` de `ui_components.py`. No usar colores ni fuentes sueltas.
- **API que main.py espera de una pestaña** (cuando aplique): `on_engine_started()`, `refresh_hotkey_label()`, `on_show()`.
- **Estado de los motores**: los workers publican texto y color en `app_ref.lbl_status`; cada pestaña lo escucha con `lbl_status.add_listener(...)` y traduce el mensaje a su cabecera. Colores: verde `#22C55E`, violeta `#A855F7`/`#9333EA`/`#C084FC`, azul `#3B82F6`, amarillo `#EAB308`, rojo `#EF4444`.
- **Workers**: corren en un hilo daemon, comprueban `stop_event` en cada iteración y usan esperas interrumpibles (`stop_event.wait`; en `black_souls.py`, `_esperar`). Se lanzan solo desde `toggle_engine(modo)` con los modos `principal`, `macro`, `vision`, `blacksouls`; `toggle_engine` no limpia `stop_event` hasta que el worker anterior haya terminado (`_launch_when_free`).
- **Black Souls**: la ruta de farmeo se define una sola vez en `black_souls.RUTA_DEFECTO`; la pestaña construye `bs_pasos_vars` a partir de ella y el worker recibe esos tiempos (`lista_pasos`).
- **Flujos**: la pestaña (`TabFlujos`) es compacta; el editor vive en una ventana flotante (`FlowEditorWindow`) que se oculta (no se destruye) al cerrarla. El lienzo es `FlowCanvas` (tk.Canvas, no CTk). El motor vive en `logic_engine/`. Al ejecutar, `target_hwnd` limita la búsqueda de imágenes a la ventana objetivo elegida.
- **Rutas**: siempre con `ruta_recurso(...)`, nunca relativas. Assets en `assets/`, identidad en `assets/app/`, flujos en `flujos/`.
- **Nombres**: funciones y variables de dominio en español (`cargar_perfiles`, `ruta_recurso`); clases de UI y helpers genéricos en inglés (`Card`, `StatusDot`). Atajos remapeables: `key_main` F6, `key_macro` F7, `key_vision` F8, `key_bs` F9, `key_record` F10; parada de emergencia fija: Shift + Esc.

## 3. Comandos frecuentes
- Instalar dependencias: `pip install -r requirements.txt`
- Ejecutar: `python main.py`
- Compilar el lanzador (pequeño, requiere Python instalado): `build_launcher.bat`
- Compilar el .exe autónomo: `build_exe.bat` (resultado en `dist/`)
- Comprobar sintaxis sin abrir la GUI: `python -m py_compile main.py tab_*.py flow_canvas.py vision.py`
- No hay tests automatizados ni deploy: la distribución es el .exe.

## 4. Restricciones importantes
- **No renombrar** atributos que usan `main.py`, `clicker.py` y los perfiles JSON: `entry_h/m/s/ms`, `combo_btn`, `combo_type`, `repeat_mode`, `entry_repeats`, `pos_mode`, `entry_x/y`, `bs_pasos_vars`, `img_bs_combate`, `img_open_path`, `vision_*`, `step_cards`, `macro_scroll`, `macro_speed`, `macro_repeat_mode`, `entry_macro_repeats`, `btn_hk_record`, `check_topmost/tray/countdown`, `btn_hk_main/macro/vision/bs`, `combo_profiles`, `entry_profile_name`, etc. Si hay que cambiarlos, actualizar también `_save_profile` y `_load_selected_profile`.
- **No tocar widgets desde hilos de worker**, salvo `lbl_status` (`StatusLabel` ya delega al hilo de Tk). Cualquier otra actualización de UI va con `app_ref.after(0, ...)`.
- **No usar `bind_all` sin `add="+"`** (rompe la rueda del ratón de otras pestañas).
- **No modificar** los PNG de `assets/` ni el formato de los perfiles (`perfiles/*.json`) sin migrar los existentes. El nombre del perfil es el del archivo: siempre pasa por `nombre_valido`.
- **No modificar** el formato de los flujos (`flujos/*.json`) sin migración; `flow_model.FLOW_VERSION` lo controla.
- **No añadir librerías** distintas de las de `requirements.txt` sin avisar; nada de red ni telemetría.
- **No cambiar** la parada de emergencia Shift + Esc ni su lógica en `on_key_press`.
- Los cambios de UI deben mantener el tamaño mínimo de ventana (940x700) y el del editor flotante (940x600).
- El motor de flujos usa `logic_engine/` sin `eval()` ni código arbitrario: `condition_evaluator` solo admite operadores de una lista blanca.

## 5. Contexto de negocio
AutoClicker Studio Pro automatiza clics, secuencias grabadas de ratón y teclado y rutinas guiadas por imagen. Incluye módulos dedicados para el juego War of Genesis (traslado de ítems entre pestañas del almacén), Black Souls (farmeo por ruta y consumo de almas) y un editor visual de flujos para encadenar acciones y condiciones.

## Deuda conocida (no asumir que funciona)
- `StepCard` (en `ui_components.py`) sigue con widgets `tk`/`ttk` del estilo antiguo.
- `TIEMPO_RESPAWN_CICLO` y `VUELTAS_PARA_ALMAS` (Black Souls) son constantes de `black_souls.py`, no se editan desde la interfaz.
- En `vision.py`, el respaldo global de `buscar_y_clicar` (multimonitor) hace clic sin comprobar que esté dentro de la ventana del juego.
- `pyautogui.locate` se envuelve en `try/except` y cualquier error se trata como «no encontrado».
- `toggle_engine` espera hasta ~5 s a que muera el worker anterior; si no muere, avisa y no arranca el nuevo.
- Los flujos no guardan las imágenes que usan: se referencian por ruta. Al compartir un flujo, hay que compartir también los PNG.