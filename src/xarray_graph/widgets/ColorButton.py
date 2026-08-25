""" PySide/PyQt button for selecting and displaying a color.
"""

from qtpy.QtCore import Signal  # type: ignore
from qtpy.QtGui import QColor
from qtpy.QtWidgets import QToolButton
from xarray_graph.utils.color import ColorType


class ColorButton(QToolButton):
    """ Button for selecting and displaying a color.
    """

    colorChanged = Signal(QColor)
    
    def __init__(self, color = None):
        QToolButton.__init__(self)
        self.setColor(color)
        self.clicked.connect(self.pickColor)
    
    def color(self) -> QColor | None:
        return self._color

    def setColor(self, color: ColorType):
        from qtpy.QtGui import QIcon
        from xarray_graph.utils.color import toQColor
        color = toQColor(color)
        self.setStyleSheet(f'background-color: rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()}); border: 1px solid black;')
        if color == QColor():
            from qtawesome import icon as qta_icon
            self.setIcon(qta_icon('ri.question-mark'))
        else:
            self.setIcon(QIcon())
        self._color = color
        self.colorChanged.emit(color)
    
    def pickColor(self):
        color = self.color()
        from qtpy.QtWidgets import QColorDialog
        color = QColorDialog.getColor(color, self, "Select Color", options=QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if color.isValid():
            self.setColor(color)


def test_live():
    from qtpy.QtWidgets import QApplication, QWidget, QVBoxLayout

    app = QApplication()

    redButton = ColorButton('red')
    transparentGreenButton = ColorButton([0, 255, 0, 64])
    blueButton = ColorButton([0.0, 0.0, 1.0])
    noColorButton = ColorButton()

    redButton.colorChanged.connect(print)
    transparentGreenButton.colorChanged.connect(print)
    blueButton.colorChanged.connect(print)
    noColorButton.colorChanged.connect(print)

    ui = QWidget()
    vbox = QVBoxLayout(ui)
    vbox.addWidget(redButton)
    vbox.addWidget(transparentGreenButton)
    vbox.addWidget(blueButton)
    vbox.addWidget(noColorButton)
    ui.show()

    app.exec()

    print('Final color selections:')
    print(f'red -> {redButton.color()}')
    print(f'transparentGreen -> {transparentGreenButton.color()}')
    print(f'blue -> {blueButton.color()}')
    print(f'noColor -> {noColorButton.color()}')


if __name__ == '__main__':
    test_live()
