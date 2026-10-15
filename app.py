"""Munay Cotizador - ventana de escritorio que muestra la interfaz de ui/index.html.

Los datos (insumos, productos, historial y ajustes) se guardan en
%APPDATA%\\Munay Cotizador\\datos.json
"""
import os
import sys

import webview

APP_NOMBRE = "Munay Cotizador"


def ruta_recurso(relativa):
    """Devuelve la ruta de un archivo empaquetado (funciona en el .exe y en desarrollo)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relativa)


def carpeta_datos():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    carpeta = os.path.join(base, APP_NOMBRE)
    os.makedirs(carpeta, exist_ok=True)
    return carpeta


ARCHIVO_DATOS = os.path.join(carpeta_datos(), "datos.json")
ventana = None


def _dialogo(tipo):
    # pywebview 5 usa webview.SAVE_DIALOG / OPEN_DIALOG; pywebview 6 usa webview.FileDialog
    enum = getattr(webview, "FileDialog", None)
    if enum is not None:
        return getattr(enum, tipo)
    return getattr(webview, tipo + "_DIALOG")


class Api:
    def cargar(self):
        if not os.path.exists(ARCHIVO_DATOS):
            return None
        with open(ARCHIVO_DATOS, "r", encoding="utf-8") as f:
            return f.read()

    def guardar(self, texto):
        # Escritura atómica: si se corta la luz a mitad de camino no se pierde el archivo anterior
        temporal = ARCHIVO_DATOS + ".tmp"
        with open(temporal, "w", encoding="utf-8") as f:
            f.write(texto)
        os.replace(temporal, ARCHIVO_DATOS)
        return True

    def exportar(self, texto, nombre="munay-backup.json"):
        destino = ventana.create_file_dialog(
            _dialogo("SAVE"),
            save_filename=nombre,
            file_types=("Backup JSON (*.json)",),
        )
        if not destino:
            return None
        if not isinstance(destino, str):
            destino = destino[0]
        with open(destino, "w", encoding="utf-8") as f:
            f.write(texto)
        return destino

    def importar(self):
        origen = ventana.create_file_dialog(
            _dialogo("OPEN"), file_types=("Backup JSON (*.json)",)
        )
        if not origen:
            return None
        with open(origen[0], "r", encoding="utf-8") as f:
            return f.read()


def main():
    global ventana
    ventana = webview.create_window(
        APP_NOMBRE,
        ruta_recurso(os.path.join("ui", "index.html")),
        js_api=Api(),
        width=1280,
        height=820,
        min_size=(960, 620),
    )
    webview.start()


if __name__ == "__main__":
    main()
