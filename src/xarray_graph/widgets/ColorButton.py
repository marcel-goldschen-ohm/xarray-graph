""" PySide/PyQt button for selecting and displaying a color.
"""

from qtpy.QtCore import Signal
from qtpy.QtGui import QColor, QIcon
from qtpy.QtWidgets import QToolButton, QColorDialog
import qtawesome as qta
from xarray_graph.utils.color import ColorType, toQColor


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
        if color is None:
            color: QColor = QColor('transparent')
            self.setStyleSheet(f'background-color: rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()}); border: 1px solid black;')
            self.setIcon(qta.icon('ri.question-mark'))
            self._color = None
            return
        color: QColor = toQColor(color)
        self.setStyleSheet(f'background-color: rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()}); border: 1px solid black;')
        self.setIcon(QIcon())
        self._color = color
        self.colorChanged.emit(color)
    
    def pickColor(self):
        color: QColor = self.color()
        if color is None:
            color = QColor('white')
        color = QColorDialog.getColor(color, self, "Select Color", options=QColorDialog.ShowAlphaChannel)
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
