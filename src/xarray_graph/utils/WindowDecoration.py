
from qtpy.QtCore import QPoint


def windowDecorationOffset() -> QPoint:
    from qtpy.QtCore import QRect
    from qtpy.QtWidgets import QWidget

    window = QWidget()
    window.show()
    frame: QRect = window.frameGeometry()
    geo: QRect = window.geometry()
    window.close()
    return QPoint(frame.x() - geo.x(), frame.y() - geo.y())