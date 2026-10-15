"""Munay Cotizador - ventana de escritorio que muestra la interfaz de ui/index.html.

Los datos (insumos, productos, historial y ajustes) se guardan en
%APPDATA%\\Munay Cotizador\\datos.json
"""
import base64
import ctypes
import os
import sys
import tempfile
import time
import webbrowser
from ctypes import wintypes
from urllib.parse import quote

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


# ---------- WhatsApp de escritorio ----------
# Un link de WhatsApp solo puede llevar texto. Para mandar también la imagen se abre el chat
# con whatsapp://send, se pone la imagen en el portapapeles como archivo y se simula Ctrl+V y Enter.
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

CF_UNICODETEXT, CF_HDROP = 13, 15
VK_CONTROL, VK_V, VK_RETURN = 0x11, 0x56, 0x0D


def _portapapeles(formatos):
    """formatos: lista de (formato, bytes)."""
    for _ in range(20):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("No se pudo abrir el portapapeles")
    try:
        user32.EmptyClipboard()
        for formato, datos in formatos:
            h = kernel32.GlobalAlloc(0x0002, len(datos))  # GMEM_MOVEABLE
            ctypes.memmove(kernel32.GlobalLock(h), datos, len(datos))
            kernel32.GlobalUnlock(h)
            user32.SetClipboardData(formato, h)
    finally:
        user32.CloseClipboard()


def _copiar_texto(texto):
    _portapapeles([(CF_UNICODETEXT, (texto + "\0").encode("utf-16-le"))])


def _copiar_archivo(ruta, png):
    # DROPFILES: offset a la lista, punto, fNC, fWide=1; después las rutas en UTF-16 terminadas en doble nulo
    cabecera = (20).to_bytes(4, "little") + bytes(12) + (1).to_bytes(4, "little")
    lista = (ruta + "\0\0").encode("utf-16-le")
    _portapapeles([
        (CF_HDROP, cabecera + lista),
        (user32.RegisterClipboardFormatW("PNG"), png),
    ])


def _es_whatsapp(hwnd):
    if not hwnd:
        return False
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    proceso = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not proceso:
        return False
    try:
        buf, largo = ctypes.create_unicode_buffer(1024), wintypes.DWORD(1024)
        kernel32.QueryFullProcessImageNameW(proceso, 0, buf, ctypes.byref(largo))
        return "whatsapp" in buf.value.lower()
    finally:
        kernel32.CloseHandle(proceso)


def _whatsapp_abierto():
    encontrado = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def revisar(hwnd, _):
        if user32.IsWindowVisible(hwnd) and _es_whatsapp(hwnd):
            encontrado.append(hwnd)
        return True

    user32.EnumWindows(revisar, 0)
    return bool(encontrado)


def _teclas(*vks):
    for vk in vks:
        user32.keybd_event(vk, 0, 0, 0)
    for vk in reversed(vks):
        user32.keybd_event(vk, 0, 2, 0)  # KEYEVENTF_KEYUP
    time.sleep(0.15)


def _esperar_whatsapp(segundos):
    limite = time.time() + segundos
    while time.time() < limite:
        if _es_whatsapp(user32.GetForegroundWindow()):
            return True
        time.sleep(0.2)
    return False


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

    def logo(self):
        # Se pasa como data URI porque una imagen cargada desde file:// no deja exportar el canvas
        with open(ruta_recurso(os.path.join("ui", "logo.jpg")), "rb") as f:
            return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode("ascii")

    def abrir_url(self, url):
        # Abre WhatsApp (o el navegador) fuera de la ventana de la app
        if url.startswith(("https://", "whatsapp://")):
            webbrowser.open(url)
        return True

    def enviar_whatsapp(self, data_url, telefono, texto, enviar=True):
        """Abre el chat del número, manda el texto y después la imagen.
        Devuelve "ok", "sin-ventana" (WhatsApp no apareció) o "foco" (se cambió de ventana a mitad)."""
        png = base64.b64decode(data_url.split(",", 1)[1])
        ruta = os.path.join(tempfile.gettempdir(), "Presupuesto Munay.png")
        with open(ruta, "wb") as f:
            f.write(png)

        ya_abierto = _whatsapp_abierto()
        os.startfile("whatsapp://send?phone=%s&text=%s" % (telefono, quote(texto)))
        if not _esperar_whatsapp(10 if ya_abierto else 25):
            return "sin-ventana"
        time.sleep(2.5 if ya_abierto else 7)  # que termine de cargar el chat

        # Antes de cada tecla se confirma que WhatsApp siga adelante, para no escribir en otra ventana
        if enviar:
            if not _es_whatsapp(user32.GetForegroundWindow()):
                return "foco"
            _teclas(VK_RETURN)  # manda el texto que ya quedó escrito
            time.sleep(1)
        _copiar_archivo(ruta, png)
        if not _es_whatsapp(user32.GetForegroundWindow()):
            return "foco"
        _teclas(VK_CONTROL, VK_V)
        time.sleep(3)  # vista previa de la imagen
        if enviar:
            if not _es_whatsapp(user32.GetForegroundWindow()):
                return "foco"
            _teclas(VK_RETURN)
        return "ok"

    def guardar_imagen(self, data_url, nombre="presupuesto.png"):
        destino = ventana.create_file_dialog(
            _dialogo("SAVE"),
            save_filename=nombre,
            file_types=("Imagen PNG (*.png)",),
        )
        if not destino:
            return None
        if not isinstance(destino, str):
            destino = destino[0]
        with open(destino, "wb") as f:
            f.write(base64.b64decode(data_url.split(",", 1)[1]))
        return destino


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
