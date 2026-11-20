# -*- coding: utf-8 -*-
"""Добавляет PicoPlayer в «Открыть с помощью», в меню правой кнопки
и в «Приложения по умолчанию» Windows. Только для текущего пользователя,
права администратора не нужны.

    python register_windows.py            — установить
    python register_windows.py --uninstall — убрать
"""
import os
import sys
import winreg

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "picoplayer.py")
ICON = os.path.join(HERE, "picoplayer.ico")
PROGID = "PicoPlayer.Media"
APP = "PicoPlayer"
CAPS = r"Software\PicoPlayer\Capabilities"

IMAGE = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tif', '.tiff', '.webp', '.ico',
         '.svg', '.jfif', '.heic', '.heif', '.avif']
VIDEO = ['.mp4', '.m4v', '.wmv', '.avi', '.mov', '.mkv', '.webm', '.mpg', '.mpeg',
         '.3gp', '.ts', '.m2ts', '.flv']
AUDIO = ['.mp3', '.flac', '.wma', '.aac', '.m4a', '.ogg', '.opus', '.wav']
EXTS = IMAGE + VIDEO + AUDIO

HKCU = winreg.HKEY_CURRENT_USER


def classes(path):
    return r"Software\Classes" + ("\\" + path if path else "")


def set_value(path, name, value, kind=winreg.REG_SZ):
    with winreg.CreateKeyEx(HKCU, path, 0, winreg.KEY_WRITE) as k:
        winreg.SetValueEx(k, name, 0, kind, value)


def delete_tree(path):
    try:
        with winreg.OpenKey(HKCU, path, 0, winreg.KEY_ALL_ACCESS) as k:
            while True:
                try:
                    sub = winreg.EnumKey(k, 0)
                except OSError:
                    break
                delete_tree(path + "\\" + sub)
        winreg.DeleteKey(HKCU, path)
    except FileNotFoundError:
        pass


def delete_value(path, name):
    try:
        with winreg.OpenKey(HKCU, path, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, name)
    except FileNotFoundError:
        pass


def pythonw_path():
    d = os.path.dirname(sys.executable)
    for name in ("pythonw.exe", "pyw.exe"):
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return sys.executable


def refresh_explorer():
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
    except Exception:
        pass


def install():
    if not os.path.isfile(SCRIPT):
        print("Не найден picoplayer.py рядом с этим файлом.")
        return 1
    cmd = f'"{pythonw_path()}" "{SCRIPT}" "%1"'
    icon = f"{ICON},0" if os.path.isfile(ICON) else pythonw_path() + ",0"

    # Тип файла «PicoPlayer»
    set_value(classes(PROGID), "", "Медиафайл (PicoPlayer)")
    set_value(classes(PROGID + r"\DefaultIcon"), "", icon)
    set_value(classes(PROGID + r"\shell\open"), "FriendlyAppName", APP)
    set_value(classes(PROGID + r"\shell\open\command"), "", cmd)
    set_value(classes(PROGID + r"\Application"), "ApplicationName", APP)
    set_value(classes(PROGID + r"\Application"), "ApplicationIcon", icon)

    for ext in EXTS:
        # «Открыть с помощью» → PicoPlayer
        set_value(classes(ext + r"\OpenWithProgids"), PROGID, b"", winreg.REG_NONE)
        # правая кнопка → «Открыть в PicoPlayer»
        base = classes(rf"SystemFileAssociations\{ext}\shell\PicoPlayer")
        set_value(base, "", "Открыть в PicoPlayer")
        set_value(base, "Icon", icon)
        set_value(base + r"\command", "", cmd)

    # правая кнопка на папке → «Открыть в PicoPlayer»
    base = classes(r"Directory\shell\PicoPlayer")
    set_value(base, "", "Открыть в PicoPlayer")
    set_value(base, "Icon", icon)
    set_value(base + r"\command", "", cmd)

    # «Параметры → Приложения по умолчанию»
    set_value(CAPS, "ApplicationName", APP)
    set_value(CAPS, "ApplicationDescription", "Просмотр фото, видео и музыки")
    set_value(CAPS, "ApplicationIcon", icon)
    for ext in EXTS:
        set_value(CAPS + r"\FileAssociations", ext, PROGID)
    set_value(r"Software\RegisteredApplications", APP, CAPS)

    refresh_explorer()
    print("Готово! PicoPlayer добавлен:")
    print("  • в «Открыть с помощью» (правая кнопка по файлу);")
    print("  • в меню правой кнопки: «Открыть в PicoPlayer» (и для папок);")
    print("  • в «Параметры → Приложения → Приложения по умолчанию».")
    print()
    print("Чтобы видео/фото ВСЕГДА открывались в PicoPlayer:")
    print("  правая кнопка по файлу → Открыть с помощью → Выбрать другое приложение →")
    print("  PicoPlayer → «Всегда» (или галочка «Всегда использовать это приложение»).")
    print()
    print("Если перенесёте папку с плеером — запустите этот установщик ещё раз.")
    return 0


def uninstall():
    delete_tree(classes(PROGID))
    for ext in EXTS:
        delete_value(classes(ext + r"\OpenWithProgids"), PROGID)
        delete_tree(classes(rf"SystemFileAssociations\{ext}\shell\PicoPlayer"))
    delete_tree(classes(r"Directory\shell\PicoPlayer"))
    delete_value(r"Software\RegisteredApplications", APP)
    delete_tree(r"Software\PicoPlayer")
    refresh_explorer()
    print("PicoPlayer убран из «Открыть с помощью» и меню правой кнопки.")
    return 0


if __name__ == "__main__":
    sys.exit(uninstall() if "--uninstall" in sys.argv else install())
