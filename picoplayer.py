#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PicoPlayer 2 — удобный просмотрщик фото и проигрыватель видео/музыки (PySide6).

Главное:
  • Открыли один файл — в списке сразу вся папка, листайте стрелками.
  • Фото: масштаб, поворот, слайд-шоу, анимированные GIF/WebP,
    автоповорот снимков с телефона (по EXIF).
  • Видео/музыка: перемотка кликом по полосе, скорость, громкость,
    повтор, клик по видео — пауза, двойной клик — во весь экран.
  • Удаление — в Корзину (можно восстановить).
  • Запоминает громкость, размер окна, последнюю папку.
  • F1 — список всех горячих клавиш.
"""

import json
import os
import re
import sys
import tempfile
import time
import traceback

APP_NAME = "PicoPlayer"
HERE = os.path.dirname(os.path.abspath(__file__))


def _write_error_log(text):
    candidates = [os.path.join(HERE, "picoplayer_error.log")]
    try:
        candidates.append(os.path.join(tempfile.gettempdir(), "picoplayer_error.log"))
    except Exception:
        pass
    for log_path in candidates:
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(time.strftime("\n=== %Y-%m-%d %H:%M:%S ===\n") + text)
            return log_path
        except OSError:
            continue
    return candidates[0]


def install_error_handler():
    """pythonw не показывает ошибки — покажем их в окне и запишем в лог."""
    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        log_path = _write_error_log(text)
        msg = f"Произошла ошибка:\n\n{exc}\n\nПодробности: {log_path}"
        shown = False
        try:
            if "QApplication" in globals() and QApplication.instance() is not None:
                QMessageBox.critical(None, APP_NAME + " — ошибка", msg)
                shown = True
        except Exception:
            pass
        if not shown and sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, msg, APP_NAME + " — ошибка", 0x10)
                shown = True
            except Exception:
                pass
        if not shown:
            sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = hook


if __name__ == "__main__":
    install_error_handler()

from PySide6.QtCore import (Qt, QUrl, QTimer, QSize, QSettings, QFile, Signal,
                            QPointF, QRect, QEvent, QVariantAnimation, QSizeF)
from PySide6.QtGui import (QKeySequence, QPixmap, QImageReader, QIcon, QPainter,
                           QColor, QShortcut, QCursor, QMovie, QPolygonF)
from PySide6.QtWidgets import (QApplication, QMainWindow, QLabel, QWidget,
                               QVBoxLayout, QHBoxLayout, QSlider, QToolButton,
                               QFileDialog, QMessageBox, QFrame, QGraphicsView,
                               QGraphicsScene, QSplitter, QListWidget,
                               QListWidgetItem, QStatusBar, QStackedWidget,
                               QMenu, QStyle, QPushButton, QAbstractButton,
                               QGraphicsOpacityEffect)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtNetwork import QLocalServer, QLocalSocket

ICON_PATH = os.path.join(HERE, "picoplayer.ico")
SERVER_NAME = "PicoPlayer-" + (os.environ.get("USERNAME") or os.environ.get("USER") or "user")

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tif', '.tiff', '.webp',
              '.ico', '.svg', '.jfif', '.pbm', '.pgm', '.ppm', '.xbm', '.xpm',
              '.heic', '.heif', '.avif'}
VIDEO_EXTS = {'.mp4', '.m4v', '.wmv', '.avi', '.mov', '.mkv', '.webm', '.mpg',
              '.mpeg', '.3gp', '.ts', '.m2ts', '.flv'}
AUDIO_EXTS = {'.mp3', '.flac', '.wma', '.aac', '.m4a', '.ogg', '.opus', '.wav'}
ALL_EXTS = IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS

COLOR_BG = "#1e1e2e"
COLOR_BG2 = "#252537"
COLOR_BG3 = "#2f2f45"
COLOR_BORDER = "#3a3a55"
COLOR_ACCENT = "#cba6f7"
COLOR_TEXT = "#e6e6f0"
COLOR_DIM = "#9a9ab0"

REPEAT_MODES = [  # (текст, подсказка)
    ("➡ Дальше", "После окончания — следующий файл"),
    ("🔂 Повтор", "Повторять текущий файл"),
    ("⏹ Стоп", "После окончания — остановиться"),
]
SPEEDS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0]

HELP_TEXT = """
<h3>Горячие клавиши</h3>
<table cellspacing=4>
<tr><td><b>← / →</b>, PgUp / PgDn</td><td>предыдущий / следующий файл</td></tr>
<tr><td><b>Home / End</b></td><td>первый / последний файл</td></tr>
<tr><td><b>Пробел</b></td><td>пауза / воспроизведение</td></tr>
<tr><td><b>Ctrl + ← / →</b></td><td>перемотка на 5 секунд</td></tr>
<tr><td><b>Shift + ← / →</b></td><td>перемотка на 30 секунд</td></tr>
<tr><td><b>↑ / ↓</b></td><td>громкость</td></tr>
<tr><td><b>M</b></td><td>выключить / включить звук</td></tr>
<tr><td><b>[ / ]</b>, Backspace</td><td>медленнее / быстрее, обычная скорость</td></tr>
<tr><td><b>+ / −</b>, Ctrl + колесо</td><td>увеличить / уменьшить фото</td></tr>
<tr><td><b>0</b> / <b>1</b></td><td>фото по размеру окна / 100%</td></tr>
<tr><td><b>R</b> / <b>Shift+R</b></td><td>повернуть фото вправо / влево</td></tr>
<tr><td><b>C</b> / <b>Ctrl+2</b></td><td>сравнить 2 фото рядом / выбрать второе фото</td></tr>
<tr><td><b>S</b></td><td>слайд-шоу</td></tr>
<tr><td><b>F</b>, F11, двойной клик</td><td>во весь экран</td></tr>
<tr><td><b>Esc</b></td><td>выйти из полноэкранного режима</td></tr>
<tr><td><b>L</b></td><td>показать / скрыть список файлов</td></tr>
<tr><td><b>Ctrl+O</b> / <b>Ctrl+Shift+O</b></td><td>открыть файлы / папку</td></tr>
<tr><td><b>Delete</b></td><td>удалить файл в Корзину</td></tr>
<tr><td><b>F1</b></td><td>эта справка</td></tr>
</table>
<p>Колесо мыши над фото листает файлы (если фото целиком в окне),
над видео — меняет громкость.</p>
"""


def natural_key(path):
    """Сортировка как в Проводнике: img2 раньше img10."""
    name = os.path.basename(path).lower()
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', name)]


def ext_of(path):
    return os.path.splitext(path)[1].lower()


def human_size(n):
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if n < 1024 or unit == "ГБ":
            return f"{n:.0f} {unit}" if unit == "Б" else f"{n:.1f} {unit}"
        n /= 1024


def fmt_time(ms):
    s = max(0, int(ms)) // 1000
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


# ====================================================================
#  Виджеты
# ====================================================================

class ImageView(QGraphicsView):
    """Просмотр фото: зум, перетаскивание, поворот."""
    stepRequested = Signal(int)
    zoomChanged = Signal(float)
    viewChanged = Signal()
    doubleClicked = Signal()
    activated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.item = None
        self._zoom = 1.0
        self._fit = True
        self._rotation = 0
        self._internal_update = False
        self.setBackgroundBrush(QColor(COLOR_BG))
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setFrameShape(QFrame.NoFrame)
        self.setFocusPolicy(Qt.NoFocus)
        # перетаскивание файлов обрабатывает главное окно
        self.setAcceptDrops(False)
        self.viewport().setAcceptDrops(False)
        self.horizontalScrollBar().valueChanged.connect(self._on_scroll)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def _on_scroll(self, _value):
        if not self._internal_update and self.item is not None:
            self.viewChanged.emit()

    def set_image(self, pixmap):
        self._internal_update = True
        try:
            self._scene.clear()
            self.item = self._scene.addPixmap(pixmap)
            self.item.setTransformationMode(Qt.SmoothTransformation)
            self.item.setTransformOriginPoint(self.item.boundingRect().center())
            self._scene.setSceneRect(self.item.sceneBoundingRect())
            self._rotation = 0
            self._fit = True
            self._apply_fit()
        finally:
            self._internal_update = False

    def update_frame(self, pixmap):
        """Новый кадр анимации — без сброса масштаба."""
        if self.item is not None:
            self.item.setPixmap(pixmap)

    def clear_image(self):
        self._scene.clear()
        self.item = None

    def has_image(self):
        return self.item is not None

    def fit_scale(self):
        if not self.item:
            return 1.0
        rect = self.item.sceneBoundingRect()
        s = min(self.viewport().width() / max(1, rect.width()),
                self.viewport().height() / max(1, rect.height()))
        return max(min(s, 1.0), 0.01)  # маленькие фото не растягиваем

    def get_view_state(self):
        if not self.item:
            return None
        rect = self.item.sceneBoundingRect()
        center = self.mapToScene(self.viewport().rect().center())
        nx = (center.x() - rect.left()) / max(1.0, rect.width())
        ny = (center.y() - rect.top()) / max(1.0, rect.height())
        rel = self._zoom / max(0.01, self.fit_scale())
        return (self._fit, rel, nx, ny)

    def apply_view_state(self, state):
        if not self.item or state is None:
            return
        fit, rel, nx, ny = state
        self._internal_update = True
        try:
            if fit:
                self._fit = True
                self._apply_fit()
            else:
                self._fit = False
                new_zoom = max(0.02, min(20.0, rel * self.fit_scale()))
                self._zoom = new_zoom
                self.resetTransform()
                self.scale(new_zoom, new_zoom)
                rect = self.item.sceneBoundingRect()
                self.centerOn(rect.left() + nx * rect.width(),
                              rect.top() + ny * rect.height())
                self.zoomChanged.emit(self._zoom)
        finally:
            self._internal_update = False

    def _set_zoom(self, new_zoom):
        new_zoom = max(0.02, min(20.0, new_zoom))
        factor = new_zoom / self._zoom
        self._zoom = new_zoom
        prev = self._internal_update
        self._internal_update = True
        try:
            self.scale(factor, factor)
            self.zoomChanged.emit(self._zoom)
        finally:
            self._internal_update = prev
        if not self._internal_update:
            self.viewChanged.emit()

    def _apply_fit(self):
        if not self.item or not self._fit:
            return
        prev = self._internal_update
        self._internal_update = True
        try:
            self.resetTransform()
            rect = self.item.sceneBoundingRect()
            s = self.fit_scale()
            self._zoom = s
            self.scale(s, s)
            self.centerOn(rect.center())
            self.zoomChanged.emit(self._zoom)
        finally:
            self._internal_update = prev

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._fit and self.item:
            self._apply_fit()

    def wheelEvent(self, e):
        if not self.item:
            return
        delta = e.angleDelta().y()
        if delta == 0:
            return
        if e.modifiers() & Qt.ControlModifier:
            self._fit = False
            self._set_zoom(self._zoom * (1.15 if delta > 0 else 1 / 1.15))
        elif e.modifiers() & Qt.ShiftModifier:
            sb = self.horizontalScrollBar()
            sb.setValue(sb.value() - delta)
        else:
            sb = self.verticalScrollBar()
            if sb.maximum() <= 0:
                self.stepRequested.emit(1 if delta < 0 else -1)
            else:
                sb.setValue(sb.value() - delta)

    def zoom_in(self):
        if self.item:
            self._fit = False
            self._set_zoom(self._zoom * 1.25)

    def zoom_out(self):
        if self.item:
            self._fit = False
            self._set_zoom(self._zoom / 1.25)

    def zoom_fit(self):
        if self.item:
            self._fit = True
            self._apply_fit()
            self.viewChanged.emit()

    def zoom_100(self):
        if self.item:
            prev = self._internal_update
            self._internal_update = True
            try:
                self._fit = False
                self._zoom = 1.0
                self.resetTransform()
                self.centerOn(self.item.sceneBoundingRect().center())
                self.zoomChanged.emit(1.0)
            finally:
                self._internal_update = prev
            self.viewChanged.emit()

    def rotate(self, deg):
        if not self.item:
            return
        prev = self._internal_update
        self._internal_update = True
        try:
            self._rotation = (self._rotation + deg) % 360
            self.item.setRotation(self._rotation)
            self._scene.setSceneRect(self.item.sceneBoundingRect())
            if self._fit:
                self._apply_fit()
            else:
                self.centerOn(self.item.sceneBoundingRect().center())
        finally:
            self._internal_update = prev

    def mousePressEvent(self, e):
        self.activated.emit()
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.doubleClicked.emit()
        else:
            super().mouseDoubleClickEvent(e)


class VideoSurface(QGraphicsView):
    """Видео (через QGraphicsVideoItem — поверх него видны кнопки).
    Клик — пауза, двойной клик — полный экран, колесо — громкость."""
    clicked = Signal()
    doubleClicked = Signal()
    wheel = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.video_item = QGraphicsVideoItem()
        self.video_item.setAspectRatioMode(Qt.KeepAspectRatio)
        self._scene.addItem(self.video_item)
        self.setBackgroundBrush(QColor("#000000"))
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setRenderHints(QPainter.SmoothPixmapTransform)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAcceptDrops(False)
        self.viewport().setAcceptDrops(False)
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self.clicked.emit)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        vp = self.viewport().size()
        self.video_item.setSize(QSizeF(vp))
        self._scene.setSceneRect(0, 0, vp.width(), vp.height())

    def mousePressEvent(self, e):
        e.accept()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._click_timer.start(QApplication.doubleClickInterval())

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._click_timer.stop()
            self.doubleClicked.emit()

    def wheelEvent(self, e):
        d = e.angleDelta().y()
        if d:
            self.wheel.emit(5 if d > 0 else -5)


class OverlayButton(QAbstractButton):
    """Большая круглая полупрозрачная кнопка поверх фото/видео."""

    def __init__(self, kind, size, tip, parent):
        super().__init__(parent)
        self.kind = kind  # play / pause / prev / next
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setToolTip(tip)
        self.setAttribute(Qt.WA_Hover)
        self.effect = QGraphicsOpacityEffect(self)
        self.effect.setOpacity(0.0)
        self.setGraphicsEffect(self.effect)

    def set_kind(self, kind):
        if kind != self.kind:
            self.kind = kind
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        alpha = 200 if self.isDown() else (165 if self.underMouse() else 115)
        p.setPen(QColor(255, 255, 255, 70))
        p.setBrush(QColor(0, 0, 0, alpha))
        p.drawEllipse(self.rect().adjusted(1, 1, -1, -1))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 240))
        w = self.width()
        c = w / 2
        r = w * 0.2
        if self.kind == "play":
            p.drawPolygon(QPolygonF([QPointF(c - r * 0.65, c - r), QPointF(c - r * 0.65, c + r),
                                     QPointF(c + r * 1.0, c)]))
        elif self.kind == "pause":
            bw, gap = r * 0.55, r * 0.35
            p.drawRoundedRect(int(c - gap - bw), int(c - r), int(bw), int(2 * r), 2, 2)
            p.drawRoundedRect(int(c + gap), int(c - r), int(bw), int(2 * r), 2, 2)
        else:
            sgn = -1 if self.kind == "prev" else 1
            # треугольник + полоска (⏮ / ⏭)
            tip_x = c + sgn * r * 0.55
            base_x = c - sgn * r * 0.75
            p.drawPolygon(QPolygonF([QPointF(base_x, c - r * 0.9), QPointF(base_x, c + r * 0.9),
                                     QPointF(tip_x, c)]))
            bar_w = r * 0.28
            bx = tip_x if sgn > 0 else tip_x - bar_w
            p.drawRoundedRect(int(bx), int(c - r * 0.9), max(2, int(bar_w)), int(1.8 * r), 1, 1)
        p.end()


class SeekSlider(QSlider):
    """Полоса перемотки: клик в любое место — сразу туда."""
    seekRequested = Signal(int)

    def __init__(self):
        super().__init__(Qt.Horizontal)
        self.setRange(0, 1000)
        self.setFocusPolicy(Qt.NoFocus)
        self.sliderMoved.connect(self.seekRequested.emit)
        self.sliderReleased.connect(lambda: self.seekRequested.emit(self.value()))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.isEnabled():
            val = QStyle.sliderValueFromPosition(
                self.minimum(), self.maximum(), int(e.position().x()), self.width())
            self.setValue(val)
            self.seekRequested.emit(val)
        super().mousePressEvent(e)


class FileList(QListWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("FileList")
        self.setFocusPolicy(Qt.NoFocus)
        self.setIconSize(QSize(40, 40))
        self.setUniformItemSizes(True)
        self.setAcceptDrops(False)
        self.viewport().setAcceptDrops(False)


# ====================================================================
#  Главное окно
# ====================================================================

class MediaPlayer(QMainWindow):

    def __init__(self, files=None):
        super().__init__()
        self.settings = QSettings("Picoclaw", APP_NAME)
        self.setWindowTitle(APP_NAME)
        self.setAcceptDrops(True)

        self.files = []
        self.index = -1
        self.player = None
        self.audio_output = None
        self.movie = None
        self.compare_movie = None
        self._compare_mode = False
        self._compare_path = None
        self._compare_files = []
        self._compare_size = None
        self._compare_active = "left"
        self._compare_sync = True
        self._syncing_views = False
        self._fullscreen = False
        self._was_maximized = False
        self._closing = False
        self._server = None
        self._repeat = int(self.settings.value("repeat", 0))
        self.slideshow_interval = int(self.settings.value("slideshow_ms", 5000))
        self._slideshow_active = False
        self._thumb_queue = []
        self._last_cursor = None
        self._idle_ms = 0

        self.slideshow_timer = QTimer(self)
        self.slideshow_timer.timeout.connect(self._slideshow_next)
        self.thumb_timer = QTimer(self)
        self.thumb_timer.setInterval(15)
        self.thumb_timer.timeout.connect(self._thumb_tick)
        # «сторож» воспроизведения: если плеер пишет «играю», а время стоит — перезапускаем
        self._autoplay = False
        self._autoplay_source = None
        self._setting_source = False
        self._stall_pos = -1
        self._stall_tries = 0
        self.stall_timer = QTimer(self)
        self.stall_timer.setInterval(700)
        self.stall_timer.timeout.connect(self._stall_check)
        self.cursor_timer = QTimer(self)
        self.cursor_timer.setInterval(250)
        self.cursor_timer.timeout.connect(self._cursor_tick)

        self._setup_ui()
        self._setup_shortcuts()
        self._apply_theme()
        self._restore_settings()
        self._update_controls()

        if files:
            self.open_files(files)

    # ---------- UI ----------
    def _btn(self, text, tip, slot=None, icon=None, checkable=False, obj_name="ToolBtn"):
        b = QToolButton()
        if icon is not None:
            b.setIcon(self.style().standardIcon(icon))
            b.setIconSize(QSize(18, 18))
        if text:
            b.setText(text)
        b.setToolTip(tip)
        b.setObjectName(obj_name)
        b.setCursor(Qt.PointingHandCursor)
        b.setFocusPolicy(Qt.NoFocus)
        b.setCheckable(checkable)
        if slot:
            b.clicked.connect(slot)
        return b

    def _sep(self):
        f = QFrame()
        f.setFixedWidth(1)
        f.setStyleSheet(f"background:{COLOR_BORDER};")
        return f

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.image_view = ImageView()
        self.image_view.stepRequested.connect(
            lambda d: self.step_image(d) if self._compare_mode else self.step_file(d))
        self.image_view.zoomChanged.connect(lambda z: self._update_status())
        self.image_view.viewChanged.connect(lambda: self._sync_views(self.image_view, self.compare_view))
        self.image_view.doubleClicked.connect(self.toggle_fullscreen)
        self.image_view.activated.connect(lambda: self._set_compare_active("left"))

        self.compare_view = ImageView()
        self.compare_view.stepRequested.connect(self._step_compare_image)
        self.compare_view.zoomChanged.connect(lambda z: self._update_status())
        self.compare_view.viewChanged.connect(lambda: self._sync_views(self.compare_view, self.image_view))
        self.compare_view.doubleClicked.connect(self.toggle_fullscreen)
        self.compare_view.activated.connect(lambda: self._set_compare_active("right"))

        # ----- верхняя панель -----
        self.top_bar = QFrame()
        self.top_bar.setObjectName("TopBar")
        tl = QHBoxLayout(self.top_bar)
        tl.setContentsMargins(8, 6, 8, 6)
        tl.setSpacing(4)

        tl.addWidget(self._btn("📂 Открыть", "Открыть файлы (Ctrl+O)", self.open_dialog))
        tl.addWidget(self._btn("📁 Папка", "Открыть всю папку (Ctrl+Shift+O)", self.open_folder_dialog))
        tl.addWidget(self._sep())

        self.btn_zoom_out = self._btn("−", "Уменьшить (−)", self._img_zoom_out)
        self.btn_zoom_in = self._btn("+", "Увеличить (+)", self._img_zoom_in)
        self.btn_fit = self._btn("По окну", "Вписать в окно (0)", self._img_zoom_fit)
        self.btn_100 = self._btn("1:1", "Реальный размер (1)", self._img_zoom_100)
        self.btn_rot_l = self._btn("↺", "Повернуть влево (Shift+R)", lambda: self._img_rotate(-90))
        self.btn_rot_r = self._btn("↻", "Повернуть вправо (R)", lambda: self._img_rotate(90))
        self.btn_compare = self._btn("◫ Сравнить", "Сравнить 2 фото на одном экране (C)",
                                     self.toggle_compare, checkable=True)
        self.image_tools = [self.btn_zoom_out, self.btn_zoom_in, self.btn_fit,
                            self.btn_100, self.btn_rot_l, self.btn_rot_r, self.btn_compare]
        for b in self.image_tools:
            tl.addWidget(b)

        self.btn_slideshow = self._btn("▷ Слайд-шоу", "Слайд-шоу (S). Стрелка — выбрать интервал",
                                       self.toggle_slideshow)
        self.btn_slideshow.setPopupMode(QToolButton.MenuButtonPopup)
        m = QMenu(self.btn_slideshow)
        for sec in (2, 3, 5, 10, 20):
            a = m.addAction(f"Каждые {sec} сек")
            a.triggered.connect(lambda _=False, s=sec: self._set_slideshow_interval(s))
        self.btn_slideshow.setMenu(m)
        tl.addWidget(self.btn_slideshow)

        tl.addStretch(1)
        self.btn_list = self._btn("☰ Список", "Показать / скрыть список файлов (L)",
                                  lambda: self._set_list_visible(self.btn_list.isChecked()),
                                  checkable=True)
        self.btn_list.setChecked(True)
        tl.addWidget(self.btn_list)
        tl.addWidget(self._btn("⤢ Экран", "Во весь экран (F)", self.toggle_fullscreen))
        tl.addWidget(self._btn("?", "Горячие клавиши (F1)", self.show_help))
        root.addWidget(self.top_bar)

        # ----- центр -----
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)

        self.stack = QStackedWidget()
        # страница 0 — приветствие
        hint = QWidget()
        hl = QVBoxLayout(hint)
        hl.addStretch(1)
        self.hint_label = QLabel("Перетащите сюда фото, видео или музыку")
        self.hint_label.setAlignment(Qt.AlignCenter)
        self.hint_label.setStyleSheet(f"color:{COLOR_DIM}; font-size:18px;")
        hl.addWidget(self.hint_label)
        row = QHBoxLayout()
        row.addStretch(1)
        for text, slot in (("Открыть файлы", self.open_dialog), ("Открыть папку", self.open_folder_dialog)):
            pb = QPushButton(text)
            pb.setObjectName("BigBtn")
            pb.setCursor(Qt.PointingHandCursor)
            pb.setFocusPolicy(Qt.NoFocus)
            pb.clicked.connect(slot)
            row.addWidget(pb)
        row.addStretch(1)
        hl.addLayout(row)
        tip = QLabel("F1 — горячие клавиши")
        tip.setAlignment(Qt.AlignCenter)
        tip.setStyleSheet(f"color:{COLOR_DIM}; font-size:12px; margin-top:12px;")
        hl.addWidget(tip)
        hl.addStretch(1)
        self.stack.addWidget(hint)                    # 0

        # страница 1 — фото (обычный режим или сравнение 2 фото рядом)
        self.image_splitter = QSplitter(Qt.Horizontal)
        self.image_splitter.setChildrenCollapsible(False)

        self.left_pane = QWidget()
        lpl = QVBoxLayout(self.left_pane)
        lpl.setContentsMargins(0, 0, 0, 0)
        lpl.setSpacing(0)
        self.left_header = QFrame()
        self.left_header.setObjectName("CompareHeader")
        lhl = QHBoxLayout(self.left_header)
        lhl.setContentsMargins(8, 4, 8, 4)
        lhl.setSpacing(4)
        self.left_title = QLabel("Фото 1")
        self.left_title.setStyleSheet(f"color:{COLOR_TEXT}; font-size:12px; background:transparent;")
        lhl.addWidget(self.left_title, 1)
        lhl.addWidget(self._btn("◀", "Предыдущее фото слева", lambda: self.step_image(-1), obj_name="MiniBtn"))
        lhl.addWidget(self._btn("▶", "Следующее фото слева", lambda: self.step_image(1), obj_name="MiniBtn"))
        self.left_header.hide()
        lpl.addWidget(self.left_header)
        lpl.addWidget(self.image_view, 1)
        self.image_splitter.addWidget(self.left_pane)

        self.right_pane = QWidget()
        rpl = QVBoxLayout(self.right_pane)
        rpl.setContentsMargins(0, 0, 0, 0)
        rpl.setSpacing(0)
        self.right_header = QFrame()
        self.right_header.setObjectName("CompareHeader")
        rhl = QHBoxLayout(self.right_header)
        rhl.setContentsMargins(8, 4, 8, 4)
        rhl.setSpacing(4)
        self.right_title = QLabel("Выберите второе фото")
        self.right_title.setStyleSheet(f"color:{COLOR_DIM}; font-size:12px; background:transparent;")
        rhl.addWidget(self.right_title, 1)
        rhl.addWidget(self._btn("◀", "Предыдущее фото справа", lambda: self._step_compare_image(-1), obj_name="MiniBtn"))
        rhl.addWidget(self._btn("▶", "Следующее фото справа", lambda: self._step_compare_image(1), obj_name="MiniBtn"))
        rhl.addWidget(self._btn("📂 Выбрать", "Выбрать второе фото с диска (Ctrl+2)",
                                self.choose_compare_image, obj_name="MiniBtn"))
        rhl.addWidget(self._btn("⇄", "Поменять фото местами", self._swap_compare_images, obj_name="MiniBtn"))
        self.btn_sync = self._btn("🔗 Синхр.", "Синхронизировать масштаб и перемещение двух фото",
                                  lambda: self._set_compare_sync(self.btn_sync.isChecked()),
                                  checkable=True, obj_name="MiniBtn")
        self.btn_sync.setChecked(True)
        rhl.addWidget(self.btn_sync)
        rhl.addWidget(self._btn("✕", "Закрыть сравнение (C)", lambda: self._set_compare_mode(False), obj_name="MiniBtn"))
        rpl.addWidget(self.right_header)

        self.compare_stack = QStackedWidget()
        self.compare_placeholder = QWidget()
        cpl = QVBoxLayout(self.compare_placeholder)
        cpl.addStretch(1)
        self.compare_hint = QLabel("Выберите второе фото для сравнения")
        self.compare_hint.setAlignment(Qt.AlignCenter)
        self.compare_hint.setWordWrap(True)
        self.compare_hint.setStyleSheet(f"color:{COLOR_DIM}; font-size:16px;")
        cpl.addWidget(self.compare_hint)
        cprow = QHBoxLayout()
        cprow.addStretch(1)
        pb_pick = QPushButton("📂 Выбрать второе фото")
        pb_pick.setObjectName("BigBtn")
        pb_pick.setCursor(Qt.PointingHandCursor)
        pb_pick.setFocusPolicy(Qt.NoFocus)
        pb_pick.clicked.connect(self.choose_compare_image)
        cprow.addWidget(pb_pick)
        cprow.addStretch(1)
        cpl.addLayout(cprow)
        cptip = QLabel("Или кликните по фото в списке справа,\nили перетащите файл прямо сюда")
        cptip.setAlignment(Qt.AlignCenter)
        cptip.setStyleSheet(f"color:{COLOR_DIM}; font-size:12px; margin-top:8px;")
        cpl.addWidget(cptip)
        cpl.addStretch(1)
        self.compare_stack.addWidget(self.compare_placeholder)  # 0
        self.compare_stack.addWidget(self.compare_view)         # 1
        rpl.addWidget(self.compare_stack, 1)

        self.right_pane.hide()
        self.image_splitter.addWidget(self.right_pane)
        self.image_splitter.setStretchFactor(0, 1)
        self.image_splitter.setStretchFactor(1, 1)
        self.stack.addWidget(self.image_splitter)     # 1

        self.video_widget = VideoSurface()
        self.video_widget.clicked.connect(self.toggle_play)
        self.video_widget.doubleClicked.connect(self.toggle_fullscreen)
        self.video_widget.wheel.connect(self._volume_step)
        self.stack.addWidget(self.video_widget)       # 2
        self.audio_label = QLabel()
        self.audio_label.setAlignment(Qt.AlignCenter)
        self.audio_label.setWordWrap(True)
        self.audio_label.setStyleSheet(f"color:{COLOR_TEXT}; font-size:20px;")
        self.stack.addWidget(self.audio_label)        # 3
        # область просмотра + большие кнопки поверх
        self.view_area = QWidget()
        va = QVBoxLayout(self.view_area)
        va.setContentsMargins(0, 0, 0, 0)
        va.addWidget(self.stack)
        self.ov_prev = OverlayButton("prev", 64, "Предыдущий файл (←)", self.view_area)
        self.ov_play = OverlayButton("play", 92, "Пауза / воспроизведение (Пробел)", self.view_area)
        self.ov_next = OverlayButton("next", 64, "Следующий файл (→)", self.view_area)
        self.ov_prev.clicked.connect(lambda: self.step_file(-1))
        self.ov_next.clicked.connect(lambda: self.step_file(1))
        self.ov_play.clicked.connect(self._overlay_play_clicked)
        self.overlay_buttons = [self.ov_prev, self.ov_play, self.ov_next]
        for b in self.overlay_buttons:
            b.hide()
        self.view_area.installEventFilter(self)
        self.left_header.installEventFilter(self)
        self.right_header.installEventFilter(self)
        self.compare_placeholder.installEventFilter(self)
        self._ov_opacity = 0.0
        self._ov_anim = QVariantAnimation(self)
        self._ov_anim.setDuration(180)
        self._ov_anim.valueChanged.connect(self._set_overlay_opacity)
        self._ov_last_pos = None
        self._ov_idle = 0
        self.overlay_timer = QTimer(self)
        self.overlay_timer.setInterval(120)
        self.overlay_timer.timeout.connect(self._overlay_tick)
        self.overlay_timer.start()
        self.splitter.addWidget(self.view_area)

        self.side = QWidget()
        sl = QVBoxLayout(self.side)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        self.list_title = QLabel("Файлов нет")
        self.list_title.setStyleSheet(f"color:{COLOR_DIM}; background:{COLOR_BG2}; padding:6px 8px; font-size:12px;")
        sl.addWidget(self.list_title)
        self.file_list = FileList()
        self.file_list.itemClicked.connect(self._list_open)
        self.file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self._list_context_menu)
        sl.addWidget(self.file_list)
        self.side.setMinimumWidth(160)
        self.splitter.addWidget(self.side)
        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([860, 260])
        root.addWidget(self.splitter, 1)

        # ----- нижняя панель -----
        self.bottom_bar = QFrame()
        self.bottom_bar.setObjectName("BottomBar")
        bl = QHBoxLayout(self.bottom_bar)
        bl.setContentsMargins(8, 6, 8, 6)
        bl.setSpacing(6)

        bl.addWidget(self._btn("", "Предыдущий файл (←)", lambda: self.step_file(-1),
                               icon=QStyle.SP_MediaSkipBackward))
        self.btn_play = self._btn("", "Пауза / воспроизведение (Пробел)", self.toggle_play,
                                  icon=QStyle.SP_MediaPlay)
        bl.addWidget(self.btn_play)
        bl.addWidget(self._btn("", "Следующий файл (→)", lambda: self.step_file(1),
                               icon=QStyle.SP_MediaSkipForward))

        self.pos_label = QLabel("0:00")
        self.pos_label.setObjectName("TimeLabel")
        bl.addWidget(self.pos_label)
        self.seek_slider = SeekSlider()
        self.seek_slider.seekRequested.connect(self._seek_to)
        bl.addWidget(self.seek_slider, 1)
        self.dur_label = QLabel("0:00")
        self.dur_label.setObjectName("TimeLabel")
        bl.addWidget(self.dur_label)

        self.btn_repeat = self._btn("", "", self._cycle_repeat)
        bl.addWidget(self.btn_repeat)

        self.btn_speed = self._btn("1×", "Скорость воспроизведения ([ и ])")
        self.btn_speed.setPopupMode(QToolButton.InstantPopup)
        sm = QMenu(self.btn_speed)
        for sp in SPEEDS:
            a = sm.addAction(f"{sp:g}×")
            a.triggered.connect(lambda _=False, v=sp: self._set_speed(v))
        self.btn_speed.setMenu(sm)
        bl.addWidget(self.btn_speed)

        self.btn_mute = self._btn("", "Звук вкл/выкл (M)", self.toggle_mute,
                                  icon=QStyle.SP_MediaVolume)
        bl.addWidget(self.btn_mute)
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setFixedWidth(110)
        self.vol_slider.setFocusPolicy(Qt.NoFocus)
        self.vol_slider.setToolTip("Громкость (↑ / ↓)")
        self.vol_slider.valueChanged.connect(self._set_volume)
        bl.addWidget(self.vol_slider)
        self.vol_label = QLabel("80%")
        self.vol_label.setObjectName("TimeLabel")
        self.vol_label.setFixedWidth(36)
        bl.addWidget(self.vol_label)
        root.addWidget(self.bottom_bar)

        self.media_controls = [self.btn_play, self.seek_slider, self.btn_speed]

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self._update_repeat_btn()

    def _apply_theme(self):
        self.setStyleSheet(f"""
            QWidget {{ background: {COLOR_BG}; color: {COLOR_TEXT}; font-size: 13px; }}
            QFrame#TopBar, QFrame#BottomBar {{ background: {COLOR_BG2}; }}
            QFrame#CompareHeader {{
                background: {COLOR_BG2};
                border-top: 2px solid transparent;
                border-bottom: 1px solid {COLOR_BORDER};
            }}
            QFrame#CompareHeader[active="true"] {{
                border-top: 2px solid {COLOR_ACCENT};
            }}
            QToolButton#ToolBtn {{
                background: {COLOR_BG3}; color: {COLOR_TEXT};
                border: 1px solid {COLOR_BORDER}; border-radius: 6px;
                padding: 5px 9px; font-size: 13px;
            }}
            QToolButton#ToolBtn:hover {{ background: #3d3d5c; }}
            QToolButton#ToolBtn:pressed, QToolButton#ToolBtn:checked {{ background: #4a4a70; }}
            QToolButton#ToolBtn:disabled {{ color: #5a5a75; background: {COLOR_BG2}; }}
            QToolButton#ToolBtn[popupMode="1"] {{ padding-right: 20px; }}
            QToolButton#MiniBtn {{
                background: {COLOR_BG3}; color: {COLOR_TEXT};
                border: 1px solid {COLOR_BORDER}; border-radius: 5px;
                padding: 3px 7px; font-size: 12px;
            }}
            QToolButton#MiniBtn:hover {{ background: #3d3d5c; }}
            QToolButton#MiniBtn:pressed, QToolButton#MiniBtn:checked {{ background: #4a4a70; border-color: {COLOR_ACCENT}; }}
            QPushButton#BigBtn {{
                background: {COLOR_ACCENT}; color: #1e1e2e; border: none;
                border-radius: 8px; padding: 10px 22px; font-size: 14px; font-weight: 600;
                margin: 10px 6px;
            }}
            QPushButton#BigBtn:hover {{ background: #d9bdfb; }}
            QLabel#TimeLabel {{ color: {COLOR_DIM}; font-size: 12px; background: transparent; }}
            QListWidget#FileList {{
                background: {COLOR_BG2}; border: none; padding: 4px; font-size: 12px;
            }}
            QListWidget#FileList::item {{ padding: 3px 6px; border-radius: 4px; }}
            QListWidget#FileList::item:selected {{ background: {COLOR_ACCENT}; color: #1e1e2e; }}
            QListWidget#FileList::item:hover:!selected {{ background: {COLOR_BORDER}; }}
            QSlider {{ background: transparent; }}
            QSlider::groove:horizontal {{ height: 6px; background: {COLOR_BORDER}; border-radius: 3px; }}
            QSlider::handle:horizontal {{
                width: 14px; margin: -4px 0; border-radius: 7px; background: {COLOR_ACCENT};
            }}
            QSlider::sub-page:horizontal {{ background: {COLOR_ACCENT}; border-radius: 3px; }}
            QSlider::handle:horizontal:disabled {{ background: #5a5a75; }}
            QSlider::sub-page:horizontal:disabled {{ background: {COLOR_BORDER}; }}
            QStatusBar {{ background: {COLOR_BG2}; color: {COLOR_DIM}; border-top: 1px solid {COLOR_BORDER}; }}
            QMenu {{ background: {COLOR_BG2}; border: 1px solid {COLOR_BORDER}; }}
            QMenu::item {{ padding: 5px 18px; }}
            QMenu::item:selected {{ background: {COLOR_ACCENT}; color: #1e1e2e; }}
            QToolTip {{ background: {COLOR_BG3}; color: {COLOR_TEXT}; border: 1px solid {COLOR_BORDER}; }}
            QSplitter::handle {{ background: {COLOR_BORDER}; width: 2px; }}
        """)

    # ---------- Настройки ----------
    def _restore_settings(self):
        geo = self.settings.value("geometry")
        if geo is None or not self.restoreGeometry(geo):
            self.resize(1180, 760)
        if self.windowState() & Qt.WindowMinimized:
            self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        screens = QApplication.screens()
        if screens and not any(s.availableGeometry().intersects(self.frameGeometry()) for s in screens):
            self.resize(1180, 760)
            primary = QApplication.primaryScreen() or screens[0]
            rect = primary.availableGeometry()
            self.move(rect.center() - self.rect().center())
        vol = int(self.settings.value("volume", 80))
        self.vol_slider.setValue(vol)
        self._set_volume(vol)
        self._muted = self.settings.value("muted", "false") in (True, "true")
        self._update_mute_btn()
        show_list = self.settings.value("show_list", "true") in (True, "true")
        self.btn_list.setChecked(show_list)
        self.side.setVisible(show_list)

    def _save_settings(self):
        if self._fullscreen:
            self.exit_fullscreen()
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("volume", self.vol_slider.value())
        self.settings.setValue("muted", "true" if self._muted else "false")
        self.settings.setValue("show_list", "true" if self.btn_list.isChecked() else "false")
        self.settings.setValue("repeat", self._repeat)
        self.settings.setValue("slideshow_ms", self.slideshow_interval)

    # ---------- Горячие клавиши ----------
    def _setup_shortcuts(self):
        def sc(seq, fn):
            QShortcut(QKeySequence(seq), self, activated=fn)

        sc("Space", self.toggle_play)
        sc("Right", lambda: self.step_file(1))
        sc("Left", lambda: self.step_file(-1))
        sc("PgDown", lambda: self.step_file(1))
        sc("PgUp", lambda: self.step_file(-1))
        sc("Home", lambda: self.go_to(0))
        sc("End", lambda: self.go_to(len(self.files) - 1))
        sc("Ctrl+Right", lambda: self._seek_rel(5000))
        sc("Ctrl+Left", lambda: self._seek_rel(-5000))
        sc("Shift+Right", lambda: self._seek_rel(30000))
        sc("Shift+Left", lambda: self._seek_rel(-30000))
        sc("Up", lambda: self._volume_step(5))
        sc("Down", lambda: self._volume_step(-5))
        sc("M", self.toggle_mute)
        sc("]", lambda: self._speed_step(1))
        sc("[", lambda: self._speed_step(-1))
        sc("Backspace", lambda: self._set_speed(1.0))
        sc("+", self._img_zoom_in)
        sc("=", self._img_zoom_in)
        sc("-", self._img_zoom_out)
        sc("0", self._img_zoom_fit)
        sc("1", self._img_zoom_100)
        sc("R", lambda: self._img_rotate(90))
        sc("Shift+R", lambda: self._img_rotate(-90))
        sc("C", self.toggle_compare)
        sc("Ctrl+2", self.choose_compare_image)
        sc("S", self.toggle_slideshow)
        sc("F", self.toggle_fullscreen)
        sc("F11", self.toggle_fullscreen)
        sc("Return", self.toggle_fullscreen)
        sc("Escape", self.exit_fullscreen)
        sc("L", self.toggle_list)
        sc("Ctrl+O", self.open_dialog)
        sc("Ctrl+Shift+O", self.open_folder_dialog)
        sc("Delete", self.delete_current)
        sc("F1", self.show_help)

    # ---------- Открытие ----------
    def _scan_dir(self, d):
        try:
            names = os.listdir(d)
        except OSError as e:
            self.status.showMessage(f"Не удалось прочитать папку: {e}", 5000)
            return []
        out = [os.path.join(d, n) for n in names if ext_of(n) in ALL_EXTS]
        return sorted((p for p in out if os.path.isfile(p)), key=natural_key)

    def open_files(self, paths):
        """Один файл — открываем всю его папку. Несколько — только их. Папку — её содержимое."""
        paths = [os.path.abspath(p) for p in paths if p]
        start = None
        if len(paths) == 1 and os.path.isfile(paths[0]):
            start = os.path.normcase(paths[0])
            media = self._scan_dir(os.path.dirname(paths[0]))
            if not any(os.path.normcase(p) == start for p in media):
                media = [paths[0]] + media  # файл с необычным расширением
        else:
            media = []
            for p in paths:
                if os.path.isdir(p):
                    media.extend(self._scan_dir(p))
                elif os.path.isfile(p):
                    media.append(p)
        if not media:
            self.status.showMessage("Нет поддерживаемых файлов", 4000)
            return
        self.files = media
        self.index = 0
        if start:
            for i, p in enumerate(media):
                if os.path.normcase(p) == start:
                    self.index = i
                    break
        self.settings.setValue("last_dir", os.path.dirname(media[self.index]))
        self._populate_list()
        self._load_current()

    def _last_dir(self):
        d = self.settings.value("last_dir", "")
        return d if d and os.path.isdir(d) else os.path.expanduser("~")

    def open_dialog(self):
        exts = " ".join("*" + e for e in sorted(ALL_EXTS))
        filters = (f"Все медиафайлы ({exts});;"
                   f"Фото ({' '.join('*' + e for e in sorted(IMAGE_EXTS))});;"
                   f"Видео ({' '.join('*' + e for e in sorted(VIDEO_EXTS))});;"
                   f"Музыка ({' '.join('*' + e for e in sorted(AUDIO_EXTS))});;"
                   "Все файлы (*)")
        paths, _ = QFileDialog.getOpenFileNames(self, "Открыть файлы", self._last_dir(), filters)
        if paths:
            self.open_files(paths)

    def open_folder_dialog(self):
        d = QFileDialog.getExistingDirectory(self, "Открыть папку", self._last_dir())
        if d:
            self.open_files([d])

    # ---------- Список ----------
    def _populate_list(self):
        self.thumb_timer.stop()
        self._thumb_queue = []
        self.file_list.clear()
        for i, f in enumerate(self.files):
            ext = ext_of(f)
            name = os.path.basename(f)
            if ext in VIDEO_EXTS:
                name = "🎬 " + name
            elif ext in AUDIO_EXTS:
                name = "🎵 " + name
            else:
                self._thumb_queue.append(i)
            it = QListWidgetItem(name)
            it.setData(Qt.UserRole, i)
            it.setToolTip(f)
            self.file_list.addItem(it)
        self._update_list_title()
        if self._thumb_queue:
            self.thumb_timer.start()

    def _update_list_title(self):
        n = len(self.files)
        if not n:
            self.list_title.setText("Файлов нет")
        else:
            folder = os.path.basename(os.path.dirname(self.files[0])) or self.files[0]
            self.list_title.setText(f"{folder}  ·  {n} шт.")

    def _thumb_tick(self):
        """Миниатюры грузим понемногу, чтобы окно не подвисало (важно для Google Диска)."""
        if self._closing:
            self.thumb_timer.stop()
            return
        deadline = time.monotonic() + 0.015
        while self._thumb_queue and time.monotonic() < deadline:
            i = self._thumb_queue.pop(0)
            item = self.file_list.item(i)
            if item is None or i >= len(self.files):
                continue
            reader = QImageReader(self.files[i])
            reader.setAutoTransform(True)
            size = reader.size()
            if size.isValid():
                size.scale(40, 40, Qt.KeepAspectRatio)
                reader.setScaledSize(size)
            img = reader.read()
            if not img.isNull():
                item.setIcon(QIcon(QPixmap.fromImage(img)))
        if not self._thumb_queue:
            self.thumb_timer.stop()

    def _list_open(self, item):
        i = item.data(Qt.UserRole)
        if i is None or not (0 <= i < len(self.files)):
            return
        if self._compare_mode and self._compare_active == "right" and ext_of(self.files[i]) in IMAGE_EXTS:
            self._load_compare_image(self.files[i])
            return
        if i != self.index:
            self.index = i
            self._load_current()

    def _list_context_menu(self, pos):
        item = self.file_list.itemAt(pos)
        if item is None:
            return
        i = item.data(Qt.UserRole)
        if i is None or not (0 <= i < len(self.files)):
            return
        path = self.files[i]
        if ext_of(path) not in IMAGE_EXTS:
            return
        menu = QMenu(self)
        a_right = menu.addAction("◫ Сравнить с этим фото (справа)")
        a_left = menu.addAction("Открыть слева")
        chosen = menu.exec(self.file_list.viewport().mapToGlobal(pos))
        if chosen is a_right:
            self._open_in_compare_right(path)
        elif chosen is a_left:
            self._set_compare_active("left")
            if i != self.index:
                self.index = i
                self._load_current()

    def toggle_list(self):
        self._set_list_visible(not self.btn_list.isChecked())

    def _set_list_visible(self, vis):
        self.btn_list.setChecked(vis)
        if not self._fullscreen:
            self.side.setVisible(vis)

    # ---------- Навигация ----------
    def step_file(self, d):
        if self._compare_mode:
            if self._compare_active == "right":
                self._step_compare_image(d)
            else:
                self.step_image(d)
            return
        if self.files:
            self.index = (self.index + d) % len(self.files)
            self._load_current()

    def go_to(self, i):
        if self.files and 0 <= i < len(self.files) and i != self.index:
            self.index = i
            self._load_current()

    def step_image(self, d):
        img_idx = [i for i, f in enumerate(self.files) if ext_of(f) in IMAGE_EXTS]
        if not img_idx:
            return
        if self.index in img_idx:
            self.index = img_idx[(img_idx.index(self.index) + d) % len(img_idx)]
        else:
            after = [i for i in img_idx if i > self.index]
            before = [i for i in img_idx if i < self.index]
            if d > 0:
                self.index = after[0] if after else img_idx[0]
            else:
                self.index = before[-1] if before else img_idx[-1]
        self._load_current()

    # ---------- Загрузка ----------
    def current_kind(self):
        if not (0 <= self.index < len(self.files)):
            return None
        ext = ext_of(self.files[self.index])
        if ext in VIDEO_EXTS:
            return "video"
        if ext in AUDIO_EXTS:
            return "audio"
        return "image"

    def _load_current(self):
        if not (0 <= self.index < len(self.files)):
            return
        path = self.files[self.index]
        self._stop_media()
        self.file_list.setCurrentRow(self.index)
        self.file_list.scrollToItem(self.file_list.currentItem())
        self.setWindowTitle(f"{os.path.basename(path)} — {APP_NAME}")
        kind = self.current_kind()
        if kind != "image" and self._compare_mode:
            self._set_compare_mode(False)
        if kind == "image":
            self._load_image(path)
        elif kind == "video":
            self._load_media(path, video=True)
        else:
            self._load_media(path, video=False)
        self._update_controls()
        self._update_compare_headers()
        self._update_status()

    def _load_image(self, path):
        self.stack.setCurrentIndex(1)
        reader = QImageReader(path)
        reader.setAutoTransform(True)  # поворот фото с телефона по EXIF
        animated = reader.supportsAnimation() and reader.imageCount() > 1
        img = reader.read()
        if img.isNull():
            self.image_view.clear_image()
            self._image_size = None
            self.hint_label.setText(f"Не удалось открыть:\n{os.path.basename(path)}\n({reader.errorString()})")
            self.stack.setCurrentIndex(0)
            return
        self.image_view.set_image(QPixmap.fromImage(img))
        self._image_size = img.size()
        if animated:
            self.movie = QMovie(path, parent=self)
            self.movie.frameChanged.connect(
                lambda _: self.image_view.update_frame(self.movie.currentPixmap()))
            self.movie.start()
        if self._compare_mode and self._compare_sync and self.compare_view.has_image() and not self.compare_view._fit:
            self._sync_views(self.compare_view, self.image_view)

    # ---------- Сравнение двух фото ----------
    def toggle_compare(self):
        self._set_compare_mode(not self._compare_mode)

    def _set_compare_mode(self, enabled):
        if enabled and self.current_kind() != "image":
            self.btn_compare.blockSignals(True)
            self.btn_compare.setChecked(False)
            self.btn_compare.blockSignals(False)
            self.status.showMessage("Сравнение доступно при просмотре фото", 3000)
            return
        self._compare_mode = bool(enabled)
        self.btn_compare.blockSignals(True)
        self.btn_compare.setChecked(self._compare_mode)
        self.btn_compare.blockSignals(False)
        self.left_header.setVisible(self._compare_mode)
        self.right_pane.setVisible(self._compare_mode)
        if self._compare_mode:
            if self._compare_path and not os.path.isfile(self._compare_path):
                self._clear_compare_image()
            if self._slideshow_active:
                self._stop_slideshow()
            self._set_compare_active("right" if self._compare_path is None else self._compare_active)
            QTimer.singleShot(0, self._equalize_compare_split)
        else:
            self._set_compare_active("left")
            if self.image_view.has_image() and self.image_view._fit:
                QTimer.singleShot(0, self.image_view._apply_fit)
        self._update_compare_headers()
        self._update_status()

    def _equalize_compare_split(self):
        if not self._compare_mode:
            return
        w = max(200, self.image_splitter.width())
        self.image_splitter.setSizes([w // 2, w - w // 2])
        if self.image_view.has_image() and self.image_view._fit:
            self.image_view._apply_fit()
        if self.compare_view.has_image() and self.compare_view._fit:
            self.compare_view._apply_fit()

    def _set_compare_active(self, side):
        self._compare_active = "right" if side == "right" else "left"
        for hdr, is_act in ((self.left_header, self._compare_active == "left"),
                            (self.right_header, self._compare_active == "right")):
            hdr.setProperty("active", "true" if (self._compare_mode and is_act) else "false")
            hdr.style().unpolish(hdr)
            hdr.style().polish(hdr)

    def _set_compare_sync(self, enabled):
        self._compare_sync = bool(enabled)
        if self._compare_sync and self._compare_mode:
            src = self.compare_view if self._compare_active == "right" else self.image_view
            dst = self.image_view if src is self.compare_view else self.compare_view
            self._sync_views(src, dst)

    def _sync_views(self, src, dst):
        if not self._compare_mode or not self._compare_sync or self._syncing_views:
            return
        if not src.has_image() or not dst.has_image():
            return
        self._syncing_views = True
        try:
            dst.apply_view_state(src.get_view_state())
        finally:
            self._syncing_views = False
        self._update_status()

    def _active_image_view(self):
        if self._compare_mode and self._compare_active == "right" and self.compare_view.has_image():
            return self.compare_view
        return self.image_view

    def _img_zoom_in(self):
        self._active_image_view().zoom_in()

    def _img_zoom_out(self):
        self._active_image_view().zoom_out()

    def _img_zoom_fit(self):
        self._active_image_view().zoom_fit()

    def _img_zoom_100(self):
        self._active_image_view().zoom_100()

    def _img_rotate(self, deg):
        if self._compare_mode and self._compare_sync and self.compare_view.has_image():
            self.image_view.rotate(deg)
            self.compare_view.rotate(deg)
        else:
            self._active_image_view().rotate(deg)
        self._update_status()

    def choose_compare_image(self):
        if self.current_kind() != "image":
            self.status.showMessage("Сначала откройте первое фото", 3000)
            return
        start_dir = (os.path.dirname(self._compare_path)
                     if self._compare_path and os.path.isdir(os.path.dirname(self._compare_path))
                     else self._last_dir())
        filters = (f"Фото ({' '.join('*' + e for e in sorted(IMAGE_EXTS))});;"
                   "Все файлы (*)")
        path, _ = QFileDialog.getOpenFileName(self, "Выбрать второе фото для сравнения", start_dir, filters)
        if path:
            self._open_in_compare_right(path)

    def _open_in_compare_right(self, path):
        if self.current_kind() != "image":
            return
        if not self._compare_mode:
            self._set_compare_mode(True)
        self._load_compare_image(path)
        self._set_compare_active("right")

    def _stop_compare_movie(self):
        if self.compare_movie is not None:
            self.compare_movie.stop()
            self.compare_movie.deleteLater()
            self.compare_movie = None

    def _load_compare_image(self, path):
        self._stop_compare_movie()
        path = os.path.abspath(path)
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        animated = reader.supportsAnimation() and reader.imageCount() > 1
        img = reader.read()
        if img.isNull():
            self.compare_view.clear_image()
            self._compare_path = None
            self._compare_size = None
            self.compare_hint.setText(f"Не удалось открыть:\n{os.path.basename(path)}\n({reader.errorString()})")
            self.compare_stack.setCurrentIndex(0)
            self._update_compare_headers()
            self._update_status()
            return
        self._compare_path = path
        self._compare_size = img.size()
        norm = os.path.normcase(path)
        siblings = [p for p in self._scan_dir(os.path.dirname(path)) if ext_of(p) in IMAGE_EXTS]
        if not any(os.path.normcase(p) == norm for p in siblings):
            siblings = [path] + siblings
        self._compare_files = siblings
        self.compare_stack.setCurrentIndex(1)
        self.compare_view.set_image(QPixmap.fromImage(img))
        if animated:
            self.compare_movie = QMovie(path, parent=self)
            self.compare_movie.frameChanged.connect(
                lambda _: self.compare_view.update_frame(self.compare_movie.currentPixmap()))
            self.compare_movie.start()
        if self._compare_sync and self.image_view.has_image() and not self.image_view._fit:
            self._sync_views(self.image_view, self.compare_view)
        self._update_compare_headers()
        self._update_status()

    def _clear_compare_image(self):
        self._stop_compare_movie()
        self.compare_view.clear_image()
        self._compare_path = None
        self._compare_files = []
        self._compare_size = None
        self.compare_hint.setText("Выберите второе фото для сравнения")
        self.compare_stack.setCurrentIndex(0)
        self._update_compare_headers()

    def _step_compare_image(self, d):
        if self._compare_path and self._compare_files:
            norm = os.path.normcase(self._compare_path)
            idx = next((i for i, p in enumerate(self._compare_files) if os.path.normcase(p) == norm), 0)
            nxt = self._compare_files[(idx + d) % len(self._compare_files)]
            self._load_compare_image(nxt)
            return
        img_paths = [f for f in self.files if ext_of(f) in IMAGE_EXTS]
        if not img_paths:
            return
        cur = self.files[self.index] if 0 <= self.index < len(self.files) else None
        if cur in img_paths:
            idx = (img_paths.index(cur) + d) % len(img_paths)
        else:
            idx = 0 if d > 0 else len(img_paths) - 1
        self._load_compare_image(img_paths[idx])

    def _swap_compare_images(self):
        if not self._compare_path or not (0 <= self.index < len(self.files)):
            return
        old_left = self.files[self.index]
        old_right = self._compare_path
        norm_right = os.path.normcase(old_right)
        match = next((i for i, p in enumerate(self.files) if os.path.normcase(p) == norm_right), None)
        if match is not None:
            self.index = match
            self._load_current()
        else:
            self.open_files([old_right])
        self._load_compare_image(old_left)

    def _update_compare_headers(self):
        if 0 <= self.index < len(self.files):
            lp = self.files[self.index]
            ls = getattr(self, "_image_size", None)
            ltxt = os.path.basename(lp)
            if ls is not None:
                ltxt += f"  ·  {ls.width()}×{ls.height()}"
            self.left_title.setText(f"1: {ltxt}")
            self.left_title.setToolTip(lp)
        else:
            self.left_title.setText("1: Фото")
            self.left_title.setToolTip("")

        if self._compare_path:
            rtxt = os.path.basename(self._compare_path)
            if self._compare_size is not None:
                rtxt += f"  ·  {self._compare_size.width()}×{self._compare_size.height()}"
            self.right_title.setText(f"2: {rtxt}")
            self.right_title.setToolTip(self._compare_path)
            self.right_title.setStyleSheet(f"color:{COLOR_TEXT}; font-size:12px; background:transparent;")
        else:
            self.right_title.setText("2: Выберите второе фото")
            self.right_title.setToolTip("")
            self.right_title.setStyleSheet(f"color:{COLOR_DIM}; font-size:12px; background:transparent;")

    def _ensure_player(self):
        if self.player is not None:
            return
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(self.vol_slider.value() / 100.0)
        self.audio_output.setMuted(self._muted)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget.video_item)
        self.player.positionChanged.connect(self._position_changed)
        self.player.durationChanged.connect(self._duration_changed)
        self.player.playbackStateChanged.connect(self._state_changed)
        self.player.errorOccurred.connect(self._media_error)
        self.player.mediaStatusChanged.connect(self._media_status)

    def _load_media(self, path, video):
        self._ensure_player()
        if video:
            self.stack.setCurrentIndex(2)
        else:
            self.audio_label.setText(f"<div style='font-size:72px'>🎵</div><br>{os.path.basename(path)}")
            self.stack.setCurrentIndex(3)
        self.player.setPlaybackRate(1.0)
        self.btn_speed.setText("1×")
        # play() вызываем только когда файл загрузится (см. _media_status).
        # Если вызвать сразу после setSource, на Windows видео может «застыть»:
        # плеер считает, что играет, а картинка стоит.
        # Во время setSource Qt может прислать устаревший сигнал «загружено»
        # от прошлого файла — его игнорируем (флаг _setting_source).
        url = QUrl.fromLocalFile(path)
        self._autoplay = False
        self._setting_source = True
        if self.player.source() == url:
            self.player.setSource(QUrl())
        self.player.setSource(url)
        self._setting_source = False
        self._autoplay = True
        self._autoplay_source = self.player.source()
        # запасной вариант, если сигнал о загрузке так и не придёт
        QTimer.singleShot(1500, self._autoplay_fallback)

    def _autoplay_fallback(self):
        MS = QMediaPlayer.MediaStatus
        if (self._autoplay and self.player is not None
                and self.player.source() == self._autoplay_source
                and self.player.mediaStatus() in (MS.LoadedMedia, MS.BufferedMedia, MS.EndOfMedia)):
            if self.player.mediaStatus() == MS.EndOfMedia:
                self.player.setPosition(0)
            self._start_playback()

    def _start_playback(self):
        self._autoplay = False
        self.player.play()
        self._watch_playback()

    def _watch_playback(self):
        self._stall_pos = self.player.position()
        self._stall_tries = 0
        self.stall_timer.start()

    def _stall_check(self):
        if (self.player is None or self.current_kind() not in ("video", "audio")
                or self.player.playbackState() != QMediaPlayer.PlayingState):
            self.stall_timer.stop()
            return
        pos = self.player.position()
        if pos != self._stall_pos:
            self.stall_timer.stop()  # время идёт — всё в порядке
            return
        if self._stall_tries >= 3:
            self.stall_timer.stop()
            return
        # застряло — то же самое, что «пауза + пуск» вручную
        self._stall_tries += 1
        self.player.pause()
        self.player.play()

    def _stop_media(self, release=False, keep_player=False):
        self.stall_timer.stop()
        self._autoplay = False
        if self.movie is not None:
            self.movie.stop()
            self.movie.deleteLater()
            self.movie = None
        if self.player is not None and not keep_player:
            self.player.stop()
            if release:
                self.player.setSource(QUrl())
        self.seek_slider.blockSignals(True)
        self.seek_slider.setValue(0)
        self.seek_slider.blockSignals(False)
        self.pos_label.setText("0:00")
        self.dur_label.setText("0:00")

    # ---------- Большие кнопки поверх просмотра ----------
    def eventFilter(self, obj, e):
        if obj is getattr(self, "view_area", None) and e.type() == QEvent.Resize:
            self._place_overlay()
        elif e.type() == QEvent.MouseButtonPress:
            if obj is getattr(self, "left_header", None):
                self._set_compare_active("left")
            elif obj in (getattr(self, "right_header", None), getattr(self, "compare_placeholder", None)):
                self._set_compare_active("right")
        return super().eventFilter(obj, e)

    def _place_overlay(self):
        w, h = self.view_area.width(), self.view_area.height()
        m = 24
        self.ov_play.move((w - self.ov_play.width()) // 2, (h - self.ov_play.height()) // 2)
        self.ov_prev.move(m, (h - self.ov_prev.height()) // 2)
        self.ov_next.move(w - m - self.ov_next.width(), (h - self.ov_next.height()) // 2)

    def _overlay_wanted(self):
        """Какие большие кнопки нужны для текущего файла."""
        if self._compare_mode:
            return []
        kind = self.current_kind()
        if kind is None or self.stack.currentIndex() == 0:
            return []
        many = len(self.files) > 1
        side = [self.ov_prev, self.ov_next] if many else []
        if kind in ("video", "audio"):
            return side + [self.ov_play]
        if self.movie is not None:  # анимированный GIF — тоже можно поставить на паузу
            return side + [self.ov_play]
        return side

    def _update_overlay_kind(self):
        playing = False
        if self.current_kind() in ("video", "audio") and self.player is not None:
            playing = self.player.playbackState() == QMediaPlayer.PlayingState or self._autoplay
        elif self.movie is not None:
            playing = self.movie.state() == QMovie.Running
        self.ov_play.set_kind("pause" if playing else "play")

    def _overlay_play_clicked(self):
        self.toggle_play()
        self._update_overlay_kind()

    def _overlay_tick(self):
        """Показываем кнопки, когда мышь двигается над просмотром; прячем через 2 сек покоя."""
        pos = QCursor.pos()
        area = QRect(self.view_area.mapToGlobal(self.view_area.rect().topLeft()), self.view_area.size())
        inside = self.isActiveWindow() and area.contains(pos) and self.view_area.isVisible()
        over_btn = any(b.isVisible() and b.underMouse() for b in self.overlay_buttons)
        if pos != self._ov_last_pos:
            self._ov_last_pos = pos
            self._ov_idle = 0
        else:
            self._ov_idle += self.overlay_timer.interval()
        wanted = self._overlay_wanted()
        for b in self.overlay_buttons:
            b.setVisible(b in wanted)
        show = bool(wanted) and inside and (self._ov_idle < 2000 or over_btn)
        target = 1.0 if show else 0.0
        if self._ov_anim.endValue() != target or (
                self._ov_anim.state() != QVariantAnimation.Running and self._ov_opacity != target):
            self._ov_anim.stop()
            self._ov_anim.setStartValue(self._ov_opacity)
            self._ov_anim.setEndValue(target)
            self._ov_anim.start()
        if show:
            self._update_overlay_kind()

    def _set_overlay_opacity(self, v):
        self._ov_opacity = float(v)
        for b in self.overlay_buttons:
            b.effect.setOpacity(self._ov_opacity)
            # прозрачные кнопки не должны мешать кликам по видео/фото
            b.setAttribute(Qt.WA_TransparentForMouseEvents, self._ov_opacity < 0.05)
        for b in self.overlay_buttons:
            b.raise_()

    def _update_controls(self):
        kind = self.current_kind()
        for w in self.image_tools:
            w.setEnabled(kind == "image")
        for w in self.media_controls:
            w.setEnabled(kind in ("video", "audio"))

    def _update_status(self):
        if not (0 <= self.index < len(self.files)):
            self.status.clearMessage()
            return
        path = self.files[self.index]
        if self._compare_mode and self.current_kind() == "image":
            left_info = os.path.basename(path)
            if self.image_view.has_image():
                left_info += f" ({self.image_view._zoom * 100:.0f}%)"
            if self._compare_path:
                right_info = os.path.basename(self._compare_path)
                if self.compare_view.has_image():
                    right_info += f" ({self.compare_view._zoom * 100:.0f}%)"
            else:
                right_info = "не выбрано"
            sync_txt = "синхр." if self._compare_sync else "независимо"
            self.status.showMessage(f"Сравнение ({sync_txt})   ·   1: {left_info}   |   2: {right_info}")
            return
        parts = [f"{self.index + 1} / {len(self.files)}", os.path.basename(path)]
        if self.current_kind() == "image" and self.image_view.has_image():
            s = getattr(self, "_image_size", None)
            if s is not None:
                parts.append(f"{s.width()}×{s.height()}")
            parts.append(f"{self.image_view._zoom * 100:.0f}%")
        try:
            parts.append(human_size(os.path.getsize(path)))
        except OSError:
            pass
        if self._slideshow_active:
            parts.append(f"слайд-шоу {self.slideshow_interval // 1000} сек")
        self.status.showMessage("   ·   ".join(parts))

    # ---------- Плеер ----------
    def toggle_play(self):
        kind = self.current_kind()
        if kind == "image":
            if self.movie is not None:
                self.movie.setPaused(self.movie.state() == QMovie.Running)
            return
        if self.player is None:
            return
        if self._autoplay:
            return  # файл ещё загружается и запустится сам
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            if self.stall_timer.isActive() and self.player.position() == self._stall_pos:
                # плеер «думает», что играет, но время стоит — перезапускаем, а не ставим паузу
                self.player.pause()
                self.player.play()
                return
            self.player.pause()
        else:
            if self.player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia:
                self.player.setPosition(0)
            self.player.play()
            self._watch_playback()

    def _position_changed(self, pos):
        dur = self.player.duration()
        if dur > 0 and not self.seek_slider.isSliderDown():
            self.seek_slider.blockSignals(True)
            self.seek_slider.setValue(int(pos * 1000 / dur))
            self.seek_slider.blockSignals(False)
        self.pos_label.setText(fmt_time(pos))

    def _duration_changed(self, dur):
        self.dur_label.setText(fmt_time(dur))

    def _seek_to(self, val):
        if self.player is not None and self.player.duration() > 0:
            self.player.setPosition(int(val * self.player.duration() / 1000))

    def _seek_rel(self, ms):
        if self.player is not None and self.current_kind() in ("video", "audio"):
            dur = self.player.duration()
            pos = max(0, self.player.position() + ms)
            if dur > 0:
                pos = min(pos, dur - 500)
            self.player.setPosition(pos)
            self.status.showMessage(f"{'⏩' if ms > 0 else '⏪'} {fmt_time(pos)}", 1200)

    def _set_volume(self, val):
        self.vol_label.setText(f"{val}%")
        if self.audio_output is not None:
            self.audio_output.setVolume(val / 100.0)
        if val > 0 and getattr(self, "_muted", False):
            self.toggle_mute()

    def _volume_step(self, d):
        self.vol_slider.setValue(max(0, min(100, self.vol_slider.value() + d)))

    def toggle_mute(self):
        self._muted = not getattr(self, "_muted", False)
        if self.audio_output is not None:
            self.audio_output.setMuted(self._muted)
        self._update_mute_btn()

    def _update_mute_btn(self):
        icon = QStyle.SP_MediaVolumeMuted if self._muted else QStyle.SP_MediaVolume
        self.btn_mute.setIcon(self.style().standardIcon(icon))

    def _set_speed(self, sp):
        if self.player is None or self.current_kind() not in ("video", "audio"):
            return
        self.player.setPlaybackRate(sp)
        self.btn_speed.setText(f"{sp:g}×")
        self.status.showMessage(f"Скорость {sp:g}×", 1500)

    def _speed_step(self, d):
        if self.player is None:
            return
        cur = self.player.playbackRate()
        idx = min(range(len(SPEEDS)), key=lambda i: abs(SPEEDS[i] - cur))
        self._set_speed(SPEEDS[max(0, min(len(SPEEDS) - 1, idx + d))])

    def _cycle_repeat(self):
        self._repeat = (self._repeat + 1) % len(REPEAT_MODES)
        self._update_repeat_btn()

    def _update_repeat_btn(self):
        text, tip = REPEAT_MODES[self._repeat]
        self.btn_repeat.setText(text)
        self.btn_repeat.setToolTip(tip + " (нажмите, чтобы сменить)")

    def _state_changed(self, state):
        playing = state == QMediaPlayer.PlayingState
        icon = QStyle.SP_MediaPause if playing else QStyle.SP_MediaPlay
        self.btn_play.setIcon(self.style().standardIcon(icon))
        self._update_overlay_kind()

    def _media_error(self, error, msg):
        name = os.path.basename(self.files[self.index]) if 0 <= self.index < len(self.files) else ""
        self.status.showMessage(f"Не удалось воспроизвести {name}: {msg}", 8000)

    def _media_status(self, status):
        MS = QMediaPlayer.MediaStatus
        if self._setting_source:
            return  # устаревший сигнал от предыдущего файла
        if self._autoplay and status in (MS.LoadedMedia, MS.BufferedMedia):
            self._start_playback()
            return
        if status == MS.InvalidMedia:
            self._autoplay = False
            return
        if status != MS.EndOfMedia:
            return
        if self._repeat == 1:
            self.player.setPosition(0)
            self.player.play()
            self._watch_playback()
        elif self._repeat == 0:
            if self._slideshow_active:
                self._slideshow_next()
            elif self.index < len(self.files) - 1:
                self.step_file(1)

    # ---------- Слайд-шоу ----------
    def toggle_slideshow(self):
        if self._slideshow_active:
            self._stop_slideshow()
        else:
            self._start_slideshow()

    def _set_slideshow_interval(self, sec):
        self.slideshow_interval = sec * 1000
        if self._slideshow_active:
            self.slideshow_timer.start(self.slideshow_interval)
        else:
            self._start_slideshow()

    def _start_slideshow(self):
        if not any(ext_of(f) in IMAGE_EXTS for f in self.files):
            self.status.showMessage("Для слайд-шоу нужны фото", 3000)
            return
        self._slideshow_active = True
        self.slideshow_timer.start(self.slideshow_interval)
        self.btn_slideshow.setText("■ Стоп")
        if self.current_kind() != "image":
            self.step_image(1)
        self._update_status()

    def _stop_slideshow(self):
        self._slideshow_active = False
        self.slideshow_timer.stop()
        self.btn_slideshow.setText("▷ Слайд-шоу")
        self._update_status()

    def _slideshow_next(self):
        self.step_image(1)

    # ---------- Полный экран ----------
    def toggle_fullscreen(self):
        if self._fullscreen:
            self.exit_fullscreen()
        else:
            self.enter_fullscreen()

    def enter_fullscreen(self):
        if self._fullscreen:
            return
        self._fullscreen = True
        self._was_maximized = self.isMaximized()
        self.top_bar.hide()
        self.side.hide()
        self.status.hide()
        self.showFullScreen()
        self._idle_ms = 0
        self._last_cursor = QCursor.pos()
        self.cursor_timer.start()

    def exit_fullscreen(self):
        if not self._fullscreen:
            return
        self._fullscreen = False
        self.cursor_timer.stop()
        self.centralWidget().unsetCursor()
        self.top_bar.show()
        self.bottom_bar.show()
        self.status.show()
        self.side.setVisible(self.btn_list.isChecked())
        if self._was_maximized:
            self.showMaximized()
        else:
            self.showNormal()

    def _cursor_tick(self):
        """В полноэкранном режиме прячем панель и курсор, если мышь не двигается."""
        pos = QCursor.pos()
        near_bottom = pos.y() > self.geometry().bottom() - 90
        if pos != self._last_cursor or near_bottom:
            self._last_cursor = pos
            self._idle_ms = 0
            if not self.bottom_bar.isVisible():
                self.bottom_bar.show()
                self.centralWidget().unsetCursor()
        else:
            self._idle_ms += self.cursor_timer.interval()
            if self._idle_ms >= 2500 and self.bottom_bar.isVisible():
                self.bottom_bar.hide()
                self.centralWidget().setCursor(Qt.BlankCursor)

    # ---------- Прочее ----------
    def show_help(self):
        QMessageBox.information(self, "Справка — " + APP_NAME, HELP_TEXT)

    def delete_current(self):
        if not (0 <= self.index < len(self.files)):
            return
        path = self.files[self.index]
        ret = QMessageBox.question(self, "Удалить файл?",
                                   f"Переместить «{os.path.basename(path)}» в Корзину?",
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if ret != QMessageBox.Yes:
            return
        self._stop_media(release=True)  # иначе Windows не даст удалить открытый файл
        self.image_view.clear_image()
        if self._compare_path and os.path.normcase(self._compare_path) == os.path.normcase(path):
            self._clear_compare_image()
        ok = QFile.moveToTrash(path)
        if isinstance(ok, tuple):
            ok = ok[0]
        if not ok:
            ret = QMessageBox.question(self, "Корзина недоступна",
                                       "Не удалось переместить файл в Корзину "
                                       "(например, на сетевом или облачном диске).\n"
                                       "Удалить безвозвратно?",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ret != QMessageBox.Yes:
                self._load_current()
                return
            try:
                os.remove(path)
            except OSError as e:
                QMessageBox.warning(self, "Ошибка", f"Не удалось удалить: {e}")
                self._load_current()
                return
        self.files.pop(self.index)
        if not self.files:
            self.index = -1
            if self._compare_mode:
                self._set_compare_mode(False)
            self._populate_list()
            self.hint_label.setText("Перетащите сюда фото, видео или музыку")
            self.stack.setCurrentIndex(0)
            self.setWindowTitle(APP_NAME)
            self._update_controls()
            self.status.showMessage("Файл удалён", 3000)
            return
        self.index = min(self.index, len(self.files) - 1)
        self._populate_list()
        self._load_current()
        self.status.showMessage("Файл перемещён в Корзину", 3000)

    # ---------- Drag & drop ----------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            if (self._compare_mode and self.right_pane.isVisible()
                    and len(paths) == 1 and os.path.isfile(paths[0])
                    and ext_of(paths[0]) in IMAGE_EXTS):
                pos_in_right = self.right_pane.mapFrom(self, e.position().toPoint())
                if self.right_pane.rect().contains(pos_in_right):
                    self._load_compare_image(paths[0])
                    self._set_compare_active("right")
                    self.activateWindow()
                    e.acceptProposedAction()
                    return
            self.open_files(paths)
            self.activateWindow()
        e.acceptProposedAction()

    def closeEvent(self, e):
        self._closing = True
        if self._server is not None:
            self._server.close()
            self._server = None
        self.overlay_timer.stop()
        self.thumb_timer.stop()
        self.cursor_timer.stop()
        self.stall_timer.stop()
        self._ov_anim.stop()
        self._save_settings()
        self._stop_slideshow()
        self._stop_compare_movie()
        self._stop_media(release=True)
        if self.player is not None:
            self.player.setVideoOutput(None)
            self.player.setAudioOutput(None)
        super().closeEvent(e)


# ====================================================================

def _bring_to_front(w):
    """Поднять окно на передний план (в том числе поверх Проводника в Windows)."""
    if w.isMinimized():
        w.setWindowState(w.windowState() & ~Qt.WindowMinimized)
    w.show()
    w.raise_()
    w.activateWindow()
    if sys.platform == "win32":
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = int(w.winId())
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
        except Exception:
            pass


def _send_to_running_instance(files, timeout_connect=400, timeout_ack=1500):
    """Передать файлы уже запущенному плееру. Возвращает True только после
    подтверждения OK от живого окна — если старый процесс закрывается или завис,
    откроется новое окно вместо молчаливого выхода."""
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if not sock.waitForConnected(timeout_connect):
        return False
    if sys.platform == "win32":
        try:
            import ctypes
            # Передаём уже открытому окну право выйти на передний план
            ctypes.windll.user32.AllowSetForegroundWindow(0xFFFFFFFF)
        except Exception:
            pass
    payload = (json.dumps(files, ensure_ascii=False) + "\n").encode("utf-8")
    sock.write(payload)
    sock.flush()
    if not sock.waitForBytesWritten(1000):
        sock.abort()
        return False
    ack = bytearray()
    deadline = time.monotonic() + (timeout_ack / 1000.0)
    while b"\n" not in ack:
        remaining = int((deadline - time.monotonic()) * 1000)
        if remaining <= 0:
            break
        if sock.bytesAvailable() > 0 or sock.waitForReadyRead(remaining):
            ack.extend(bytes(sock.readAll()))
        else:
            break
    sock.disconnectFromServer()
    if sock.state() != QLocalSocket.UnconnectedState:
        sock.waitForDisconnected(200)
    return ack.strip() == b"OK"


def main():
    install_error_handler()
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("Picoclaw")
    QImageReader.setAllocationLimit(1024)  # большие фото (до ~1 ГБ в памяти)

    # Защита от экранированной кавычки при открытии корня диска (например "D:\")
    files = [os.path.abspath(a.rstrip('"')) for a in sys.argv[1:] if a and a.strip('"')]

    # Уже открыт живой плеер? Тогда отдаём ему файлы, ждём OK и выходим (одно окно на всё).
    if _send_to_running_instance(files):
        return

    if os.path.isfile(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))

    # Запускаем сервер сразу (до сканирования папки), чтобы параллельные запуски
    # из «Открыть с помощью» находили это окно без гонок.
    server = QLocalServer()
    if not server.listen(SERVER_NAME):
        if _send_to_running_instance(files):
            return
        QLocalServer.removeServer(SERVER_NAME)
        server.listen(SERVER_NAME)

    w = MediaPlayer()
    w._server = server
    app.aboutToQuit.connect(server.close)
    w.show()
    _bring_to_front(w)

    group = {"paths": list(files), "time": time.monotonic() if files else 0.0}
    open_timer = QTimer(w)
    open_timer.setSingleShot(True)
    open_timer.timeout.connect(
        lambda: (not w._closing) and bool(group["paths"]) and w.open_files(list(group["paths"])))
    if files:
        open_timer.start(0)

    def handle_client(conn):
        buf = bytearray()
        state = {"done": False}

        def finish(raw_bytes):
            if state["done"]:
                return
            state["done"] = True
            try:
                paths = json.loads(raw_bytes.decode("utf-8"))
            except ValueError:
                paths = None
            if w._closing:
                conn.write(b"CLOSING\n")
                conn.flush()
                return
            _bring_to_front(w)
            conn.write(b"OK\n")
            conn.flush()
            if isinstance(paths, list):
                paths = [p for p in paths if p]
                if paths:
                    # Windows при «Открыть с помощью» на нескольких файлах запускает плеер
                    # для каждого файла отдельно — собираем пришедшие подряд в одну подборку.
                    now = time.monotonic()
                    if now - group["time"] < 0.6:
                        group["paths"] += [p for p in paths if p not in group["paths"]]
                    else:
                        group["paths"] = list(paths)
                    group["time"] = now
                    open_timer.start(0)

        def on_read():
            if state["done"]:
                return
            buf.extend(bytes(conn.readAll()))
            nl = buf.find(b"\n")
            if nl != -1:
                finish(bytes(buf[:nl]))

        def on_disconnected():
            if not state["done"]:
                buf.extend(bytes(conn.readAll()))
                if buf.strip():
                    finish(bytes(buf))
                else:
                    state["done"] = True
            conn.deleteLater()

        conn.readyRead.connect(on_read)
        conn.disconnected.connect(on_disconnected)
        # Страховка на случай, если клиент завис и не закрыл соединение
        guard = QTimer(conn)
        guard.setSingleShot(True)
        guard.timeout.connect(conn.disconnectFromServer)
        guard.start(5000)
        # Данные могли уже прийти или клиент уже отключился до подключения сигналов
        on_read()
        if conn.state() == QLocalSocket.UnconnectedState:
            on_disconnected()

    def on_connection():
        while server.hasPendingConnections():
            conn = server.nextPendingConnection()
            if conn is not None:
                handle_client(conn)

    server.newConnection.connect(on_connection)
    on_connection()
    code = app.exec()
    server.close()
    sys.exit(code)


if __name__ == "__main__":
    main()
