"""Диагностика PicoPlayer: открывает картинку и проверяет, что она отрисовалась.

Запуск:  python diagnose_player.py [путь_к_картинке]
Если путь не указан, создаётся временная тестовая картинка.
"""
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QColor, QPainter
from PySide6.QtWidgets import QApplication

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from picoplayer import MediaPlayer  # noqa: E402


def make_test_image(path):
    img = QImage(800, 500, QImage.Format.Format_ARGB32)
    img.fill(QColor("#4060a0"))
    p = QPainter(img)
    p.setPen(QColor("white"))
    p.drawText(img.rect(), Qt.AlignCenter, "PicoPlayer test")
    p.end()
    img.save(path)


app = QApplication(["picoplayer-diagnostic"])

if len(sys.argv) > 1:
    test_path = os.path.abspath(sys.argv[1])
else:
    test_path = os.path.join(HERE, "test_image.png")
    if not os.path.isfile(test_path):
        make_test_image(test_path)

window = MediaPlayer([test_path])
window.resize(1100, 720)
window.show()
app.processEvents()

view = window.image_view
viewport = view.viewport()
image = viewport.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)

nontransparent = 0
transparent = 0
bg = QColor("#1e1e2e").rgb()
non_bg = 0
for y in range(image.height()):
    for x in range(image.width()):
        px = image.pixel(x, y)
        if (px >> 24) & 0xFF:
            nontransparent += 1
        else:
            transparent += 1
        if (px | 0xFF000000) != bg:
            non_bg += 1

out_png = os.path.join(HERE, "player_diagnostic.png")
image.save(out_png)

print("test_file", test_path)
print("visible", window.isVisible())
print("image_view_visible", view.isVisible())
print("image_view_has_image", view.has_image())
print("scene_items", len(view.scene().items()))
print("scene_rect", view.scene().sceneRect().getRect())
print("viewport_size", viewport.width(), viewport.height())
print("transform", view.transform().m11(), view.transform().m22())
print("item_bounds", view.item.boundingRect().getRect() if view.item else None)
print("viewport_nontransparent_pixels", nontransparent)
print("viewport_transparent_pixels", transparent)
print("viewport_non_background_pixels", non_bg)
print("screenshot", out_png)

window.close()
app.quit()
