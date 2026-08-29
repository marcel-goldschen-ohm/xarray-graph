""" LinearRegionItem with context menu, optional text label, and style dialog.
"""
from __future__ import annotations
from typing import Any, cast
from qtpy.QtCore import Qt, QPoint
from qtpy.QtGui import QColor, QPen, QMouseEvent, QFont
from qtpy.QtWidgets import QMenu, QWidget
from pyqtgraph import InfiniteLine, InfLineLabel, mkPen


class InfLine(InfiniteLine):
    """ InfiniteLine with context menu, optional text label, and style dialog.
    
    sigDragged(self)
    sigPositionChangeFinished(self)
    sigPositionChanged(self)
    sigClicked(self, ev)
    """

    def __init__(self, *args, **kwargs):
        if 'angle' not in kwargs:
            kwargs['angle'] = 90
        if 'pen' not in kwargs:
            kwargs['pen'] = mkPen(QColor(237, 135, 131), width=1)
        if 'hoverPen' not in kwargs:
            kwargs['hoverPen'] = mkPen(QColor(255, 0, 0), width=2)
        super().__init__(*args, **kwargs)

        self._textLabelItem = InfiniteLineLabel(self, text='', movable=True, position=1, anchors=[(0,0), (0,0)])
        self._textLabelItem.setVisible(False)
        self.setFontColor(QColor.fromRgbF(0.15, 0.15, 0.15))
    
    def state(self) -> dict[str, Any]:
        """ Return hashable dict for saving and restoring state.
        """
        return {
            'position': self.position(),
            'text': self.text(),
            'movable': self.movable,
            'format': self.format()
        }

    def setState(self, state: dict[str, Any]):
        """ Restore state from hashable dict.
        """
        for key, value in state.items():
            key = key.lower()
            if key == 'position':
                self.setPosition(value)
            elif key == 'text':
                self.setText(value)
            elif key == 'movable':
                self.setMovable(value)
            elif key == 'format':
                self.setFormat(value)
    
    def format(self) -> dict[str, Any]:
        """ Return hashable dict for saving and restoring state.
        """
        from xarray_graph.utils.color import toColorStr
        return {
            'color': toColorStr(self.color()),
            'width': self.width(),
            'hovercolor': toColorStr(self.hoverColor()),
            'hoverwidth': self.hoverWidth(),
            'font': self.font().toString(),
            'fontsize': self.fontSize(),
            'fontcolor': toColorStr(self.fontColor()),
        }
    
    def setFormat(self, state: dict[str, Any]):
        """ Restore state from hashable dict.
        """
        from xarray_graph.utils.color import toQColor
        for key, value in state.items():
            key = key.lower()
            if key == 'color':
                self.setColor(toQColor(value))
            elif key == 'width':
                self.setWidth(value)
            elif key == 'hovercolor':
                self.setHoverColor(toQColor(value))
            elif key == 'hoverwidth':
                self.setHoverWidth(value)
            elif key == 'font':
                font = QFont()
                font.fromString(value)
                self.setFont(font)
            elif key == 'fontsize':
                self.setFontSize(value)
            elif key == 'fontcolor':
                self.setFontColor(toQColor(value))

    def position(self):
        return self.value()

    def setPosition(self, position):
        self.setValue(position)
    
    # movable: bool is an existing attribute
    # setMovable(bool) is an existing method

    # pen: QPen is an existing attribute
    # setPen(QPen) is an existing method
    
    def color(self) -> QColor:
        return self.pen.color()
    
    def setColor(self, color: QColor):
        self.pen.setColor(color)
    
    def width(self) -> int:
        return self.pen.width()
    
    def setWidth(self, width: int):
        self.pen.setWidth(width)

    # hoverPen: QPen is an existing attribute
    # setHoverPen(QPen) is an existing method
    
    def hoverColor(self) -> QColor:
        return self.hoverPen.color()
    
    def setHoverColor(self, color: QColor):
        self.hoverPen.setColor(color)
    
    def hoverWidth(self) -> int:
        return self.hoverPen.width()
    
    def setHoverWidth(self, width: int):
        self.hoverPen.setWidth(width)

    def text(self) -> str:
        try:
            return self._textLabelItem.format
        except:
            return ''

    def setText(self, text: str):
        self._textLabelItem.setFormat(text)
        self._textLabelItem.setVisible(text != '')
    
    def font(self) -> QFont:
        return self._textLabelItem.textItem.font()
    
    def setFont(self, font: QFont):
        self._textLabelItem.setFont(font)
    
    def fontSize(self) -> int:
        return self._textLabelItem.textItem.font().pointSize()
    
    def setFontSize(self, size):
        font = self._textLabelItem.textItem.font()
        font.setPointSize(size)
        self._textLabelItem.setFont(font)
    
    def fontColor(self) -> QColor:
        return self._textLabelItem.color
    
    def setFontColor(self, color: QColor):
        self._textLabelItem.setColor(color)
    
    def mouseClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.RightButton:
            bbox = self.boundingRect()
            if bbox and bbox.contains(event.pos()):
                if self.raiseContextMenu(event):
                    event.accept()
    
    # def mouseDragEvent(self, event: MouseDragEvent):
    #     """ Handle mouse drags.
        
    #     Emits new signal for when drag is finished.
    #     """
    #     if not self.movable or event.button() != Qt.MouseButton.LeftButton:
    #         return
    #     event.accept()
        
    #     if event.isStart():
    #         bdpos = event.buttonDownPos()
    #         lpos = self.getPos()
    #         self.cursorOffset = lpos - bdpos
    #         self.startPosition = lpos
    #         self.moving = True
            
    #     if not self.moving:
    #         return
            
    #     self.blockLineSignal = True  # only want to update once
    #     self.setPos(self.cursorOffset + event.pos())
    #     self.prepareGeometryChange()
    #     self.blockLineSignal = False
        
    #     if event.isFinish():
    #         self.moving = False
    #         self.sigPositionChangeFinished.emit(self)
    #         self.sigDragFinished.emit(self)
    #     else:
    #         self.sigPositionChanged.emit(self)
        
    def raiseContextMenu(self, event: QMouseEvent) -> bool:
        menu: QMenu = self.getContextMenus(event)
        pos = event.screenPos()
        menu.popup(QPoint(int(pos.x()), int(pos.y())))
        return True
    
    def getContextMenus(self, event=None):
        self.menu = QMenu()

        self.menu.addAction('Edit', lambda: self.editDialog())
        # self.menu.addSeparator()
        # self.menu.addAction('Delete', lambda: self.sigRequestDeletion.emit(self))

        # Let the scene add on to the end of our context menu (this is optional)
        self.menu.addSection('View')
        from pyqtgraph.GraphicsScene import GraphicsScene
        scene = cast(GraphicsScene, self.scene())
        self.menu = scene.addParentContextMenus(self, self.menu, event)
        return self.menu
    
    def editDialog(self, parent: QWidget = None):
        editInfLine(self, parent=parent)
        self.sigPositionChangeFinished.emit(self)


class InfiniteLineLabel(InfLineLabel):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def updatePosition(self):
        # constrain label position to be visible within the viewbox (0.0 to 1.0)
        self.orthoPos = min(max(self.orthoPos, 0.0), 1.0)
        super().updatePosition()
        # ensure label is anchored to the top or bottom of the viewbox depending on its position so it is always visible
        self.setAnchor((0, int(1 - self.orthoPos)))


class VLine(InfLine):
    """ Vertical InfiniteLine. """

    def __init__(self, *args, **kwargs):
        kwargs['angle'] = 90
        InfLine.__init__(self, *args, **kwargs)


class HLine(InfLine):
    """ Horizontal InfiniteLine. """

    def __init__(self, *args, **kwargs):
        kwargs['angle'] = 0
        InfLine.__init__(self, *args, **kwargs)


class InfLinePanel(QWidget):
    """ Widget for editing InfLine properties.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        from qtpy.QtWidgets import QFormLayout, QLineEdit, QCheckBox, QTextEdit, QVBoxLayout, QFrame

        form = QFormLayout()
        form.setContentsMargins(5, 5, 5, 5)
        form.setSpacing(5)
        form.setHorizontalSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self._positionEdit = QLineEdit()
        form.addRow('Position', self._positionEdit)

        self._movableCheckBox = QCheckBox()
        form.addRow('Movable', self._movableCheckBox)

        self._textEdit = QTextEdit()
        form.addRow('Text', self._textEdit)

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)
        vbox.addLayout(form)

        hline = QFrame()
        hline.setFrameShape(QFrame.Shape.HLine)
        hline.setFrameShadow(QFrame.Shadow.Sunken)

        self._format_panel = InfLineFormatPanel()

        vbox.addWidget(hline)
        vbox.addWidget(self._format_panel)

        vbox.addStretch()

        # default settings
        self.setState(InfLine().state())
    
    def state(self) -> dict[str, Any]:
        state: dict[str, Any] = {}

        if self._positionEdit.text() != '':
            try:
                state['position'] = float(self._positionEdit.text())
            except:
                pass

        if self._movableCheckBox.checkState() != Qt.CheckState.PartiallyChecked:
            state['movable'] = self._movableCheckBox.isChecked()
        
        state['text'] = self._textEdit.toPlainText()

        if hasattr(self, '_format_panel'):
            state['format'] = self._format_panel.format()

        return state

    def setState(self, state: dict[str, Any]):
        for key, value in state.items():
            key = key.lower()
            if key == 'position':
                self._positionEdit.setText(f'{value:.6f}')
            elif key == 'movable':
                self._movableCheckBox.setChecked(value)
            elif key == 'text':
                self._textEdit.setPlainText(value)
            elif key == 'format' and hasattr(self, '_format_panel'):
                self._format_panel.setFormat(value)
        self._state = state

    def editedState(self) -> dict[str, Any]:
        """ Return the state of the widget, but only include values that have changed from the original state.
        """
        current_state = self.state()
        edited_state = {}
        for key, value in current_state.items():
            if key == 'format' and hasattr(self, '_format_panel'):
                edited_format = self._format_panel.editedFormat()
                if edited_format:
                    edited_state[key] = edited_format
            elif key not in self._state or self._state[key] != value:
                edited_state[key] = value
        return edited_state


class InfLineFormatPanel(QWidget):
    """ Widget for editing AxisRegion format properties.
    """

    def __init__(self, *args, **kwargs):
        QWidget.__init__(self, *args, **kwargs)

        from qtpy.QtWidgets import QFormLayout, QVBoxLayout, QHBoxLayout, QSpinBox, QSpacerItem
        from xarray_graph.widgets.ColorButton import ColorButton

        self._colorButton = ColorButton()
        self._widthSpinBox = QSpinBox()

        self._hoverColorButton = ColorButton()
        self._hoverWidthSpinBox = QSpinBox()

        self._fontColorButton = ColorButton()
        self._fontSizeSpinBox = QSpinBox()

        self._leftColumn = QFormLayout()
        self._leftColumn.setContentsMargins(5, 5, 5, 5)
        self._leftColumn.setSpacing(5)
        self._leftColumn.addRow('Color', self._colorButton)
        self._leftColumn.addRow('Width', self._widthSpinBox)
        self._leftColumn.addItem(QSpacerItem(20, 10))
        self._leftColumn.addRow('Font Color', self._fontColorButton)
        self._leftColumn.addRow('Font Size', self._fontSizeSpinBox)

        self._rightColumn = QFormLayout()
        self._rightColumn.setContentsMargins(5, 5, 5, 5)
        self._rightColumn.setSpacing(5)
        self._rightColumn.addRow('Hover Color', self._hoverColorButton)
        self._rightColumn.addRow('Hover Width', self._hoverWidthSpinBox)

        self._hoverLayoutWrapper = QVBoxLayout()
        self._hoverLayoutWrapper.addLayout(self._rightColumn)
        self._hoverLayoutWrapper.addStretch()

        self._formatLayoutWrapper = QHBoxLayout()
        self._formatLayoutWrapper.addLayout(self._leftColumn)
        self._formatLayoutWrapper.addLayout(self._hoverLayoutWrapper)

        self.setLayout(self._formatLayoutWrapper)

        # default settings
        self.setFormat(InfLine().format())
    
    def format(self) -> dict[str, Any]:
        from xarray_graph.utils.color import toColorStr

        fmt = {}

        color = self._colorButton.color()
        width = self._widthSpinBox.value()
        fontSize = self._fontSizeSpinBox.value()
        fontColor = self._fontColorButton.color()
        hoverColor = self._hoverColorButton.color()
        hoverWidth = self._hoverWidthSpinBox.value()

        if color is not None:
            fmt['color'] = toColorStr(color)
        if width > 0:
            fmt['width'] = width
        if fontSize > 0:
            fmt['fontsize'] = fontSize
        if fontColor is not None:
            fmt['fontcolor'] = toColorStr(fontColor)
        if hoverColor is not None:
            fmt['hovercolor'] = toColorStr(hoverColor)
        if hoverWidth > 0:
            fmt['hoverwidth'] = hoverWidth

        return fmt

    def setFormat(self, format: dict[str, Any]):
        from xarray_graph.utils.color import toQColor

        for key, value in format.items():
            key = key.lower()
            if key == 'color':
                self._colorButton.setColor(toQColor(value))
            elif key == 'width':
                self._widthSpinBox.setValue(value)
            elif key == 'hovercolor':
                self._hoverColorButton.setColor(toQColor(value))
            elif key == 'hoverwidth':
                self._hoverWidthSpinBox.setValue(value)
            elif key == 'fontsize':
                self._fontSizeSpinBox.setValue(value)
            elif key == 'fontcolor':
                self._fontColorButton.setColor(toQColor(value))
        self._format = format

    def editedFormat(self) -> dict[str, Any]:
        """ Return the format of the widget, but only include values that have changed from the original format.
        """
        current_format = self.format()
        edited_format = {}
        for key, value in current_format.items():
            if key not in self._format or self._format[key] != value:
                edited_format[key] = value
        return edited_format


def editInfLine(line: InfLine = None, *args, **kwargs) -> dict[str, Any] | None:
    title: str = kwargs.pop('title', None)

    if line is None:
        line = InfLine()

    from qtpy.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox
    
    panel = InfLinePanel()
    panel.setState(line.state())

    dlg = QDialog(*args, **kwargs)
    vbox = QVBoxLayout(dlg)
    vbox.addWidget(panel)

    btns = QDialogButtonBox()
    btns.setStandardButtons(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)
    vbox.addWidget(btns)
    vbox.addStretch()

    if title:
        dlg.setWindowTitle(title)
    dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
    
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return

    edited_state = panel.editedState()
    line.setState(edited_state)
    return edited_state


def test_live():
    from qtpy.QtWidgets import QApplication
    app = QApplication()

    from pyqtgraph import PlotWidget
    ui = PlotWidget()
    line = InfLine(pos=0.5, pen=mkPen('r', width=2), hoverPen=mkPen('g', width=3))
    ui.addItem(line)
    ui.show()

    app.exec()

if __name__ == '__main__':
    test_live()