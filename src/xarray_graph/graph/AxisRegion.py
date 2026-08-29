""" LinearRegionItem with context menu, optional text label, and style dialog.
"""

from __future__ import annotations
from typing import Any, cast
from qtpy.QtCore import Qt, QPoint
from qtpy.QtGui import QColor, QPen, QFont, QMouseEvent
from qtpy.QtWidgets import QMenu, QWidget
from pyqtgraph import LinearRegionItem, InfLineLabel, mkPen, mkBrush
# from pyqtgraph.GraphicsScene.mouseEvents import MouseDragEvent


class AxisRegion(LinearRegionItem):
    """ LinearRegionItem with context menu, optional text label, and style dialog.

    sigRegionChangeFinished(self) emitted when the user has finished dragging the region (or one of its lines) and when the region is changed programatically.
    
    sigRegionChanged(self) emitted while the user is dragging the region (or one of its lines) and when the region is changed programatically.
    """

    def __init__(self, *args, **kwargs):
        if 'orientation' not in kwargs:
            kwargs['orientation'] = 'vertical'
        if 'brush' not in kwargs:
            kwargs['brush'] = mkBrush(QColor(237, 135, 131, 51))
        if 'hoverBrush' not in kwargs:
            kwargs['hoverBrush'] = mkBrush(QColor(237, 135, 131, 128))
        if 'pen' not in kwargs:
            kwargs['pen'] = mkPen(QColor(237, 135, 131), width=1)
        if 'hoverPen' not in kwargs:
            kwargs['hoverPen'] = mkPen(QColor(255, 0, 0), width=2)
        if 'swapMode' not in kwargs:
            kwargs['swapMode'] = 'push'  # keeps label on left side
        super().__init__(*args, **kwargs)

        self._textLabelItem = AxisRegionLabel(self.lines[0], text='', movable=True, position=1, anchors=[(0,0), (0,0)])
        self._textLabelItem.setVisible(False)
        self.setFontColor(QColor.fromRgbF(0.15, 0.15, 0.15))

        self.lines[0].sigClicked.connect(self.onEdgeClicked)
        self.lines[1].sigClicked.connect(self.onEdgeClicked)
    
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
            'facecolor': toColorStr(self.faceColor()),
            'edgecolor': toColorStr(self.edgeColor()),
            'edgewidth': self.edgeWidth(),
            'facehovercolor': toColorStr(self.faceHoverColor()),
            'edgehovercolor': toColorStr(self.edgeHoverColor()),
            'edgehoverwidth': self.edgeHoverWidth(),
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
            if key == 'facecolor':
                self.setFaceColor(toQColor(value))
            elif key == 'edgecolor':
                self.setEdgeColor(toQColor(value))
            elif key == 'edgewidth':
                self.setEdgeWidth(value)
            elif key == 'facehovercolor':
                self.setFaceHoverColor(toQColor(value))
            elif key == 'edgehovercolor':
                self.setEdgeHoverColor(toQColor(value))
            elif key == 'edgehoverwidth':
                self.setEdgeHoverWidth(value)
            elif key == 'font':
                font = QFont()
                font.fromString(value)
                self.setFont(font)
            elif key == 'fontsize':
                self.setFontSize(value)
            elif key == 'fontcolor':
                self.setFontColor(toQColor(value))

    def position(self):
        return self.getRegion()

    def setPosition(self, position):
        self.setRegion(position)

    # movable: bool is an existing attribute
    # setMovable(bool) is an existing method
    
    def faceColor(self) -> QColor:
        return self.brush.color()
    
    def setFaceColor(self, color: QColor):
        self.brush.setColor(color)
    
    def edgePen(self) -> QPen:
        return self.lines[0].pen
    
    def setEdgePen(self, pen: QPen):
        self.lines[0].pen = pen
        self.lines[1].pen = pen
    
    def edgeColor(self) -> QColor:
        return self.lines[0].pen.color()
    
    def setEdgeColor(self, color: QColor):
        self.lines[0].pen.setColor(color)
        self.lines[1].pen.setColor(color)
    
    def edgeWidth(self) -> int:
        return self.lines[0].pen.width()
    
    def setEdgeWidth(self, width: int):
        self.lines[0].pen.setWidth(width)
        self.lines[1].pen.setWidth(width)
    
    def faceHoverColor(self) -> QColor:
        return self.hoverBrush.color()
    
    def setFaceHoverColor(self, color: QColor):
        self.hoverBrush.setColor(color)
    
    def edgeHoverPen(self) -> QPen:
        return self.lines[0].hoverPen
    
    def setEdgeHoverPen(self, pen: QPen):
        self.lines[0].hoverPen = pen
        self.lines[1].hoverPen = pen
    
    def edgeHoverColor(self) -> QColor:
        return self.lines[0].hoverPen.color()
    
    def setEdgeHoverColor(self, color: QColor):
        self.lines[0].hoverPen.setColor(color)
        self.lines[1].hoverPen.setColor(color)
    
    def edgeHoverWidth(self) -> int:
        return self.lines[0].hoverPen.width()
    
    def setEdgeHoverWidth(self, width: int):
        self.lines[0].hoverPen.setWidth(width)
        self.lines[1].hoverPen.setWidth(width)

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
    
    def onEdgeClicked(self, line, event: QMouseEvent):
        if event.button() == Qt.MouseButton.RightButton:
            if self.raiseContextMenu(event):
                event.accept()
    
    def mouseClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.RightButton:
            if self.boundingRect().contains(event.pos()):
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
    #         bdp = event.buttonDownPos()
    #         self.cursorOffsets = [l.pos() - bdp for l in self.lines]
    #         self.startPositions = [l.pos() for l in self.lines]
    #         self.moving = True
            
    #     if not self.moving:
    #         return
            
    #     self.blockLineSignal = True  # only want to update once
    #     for i, l in enumerate(self.lines):
    #         l.setPos(self.cursorOffsets[i] + event.pos())
    #     self.prepareGeometryChange()
    #     self.blockLineSignal = False
        
    #     if event.isFinish():
    #         self.moving = False
    #         self.sigRegionChangeFinished.emit(self)
    #         self.sigDragFinished.emit(self)
    #     else:
    #         self.sigRegionChanged.emit(self)
        
    def raiseContextMenu(self, event: QMouseEvent) -> bool:
        menu: QMenu = self.getContextMenus(event)
        pos = event.screenPos()
        menu.popup(QPoint(int(pos.x()), int(pos.y())))
        return True
    
    def getContextMenus(self, event=None):
        self.menu = QMenu()

        self.menu.addAction('Edit', lambda: self.editDialog())

        # Let the scene add on to the end of our context menu (this is optional)
        self.menu.addSection('View')
        from pyqtgraph.GraphicsScene import GraphicsScene
        scene = cast(GraphicsScene, self.scene())
        self.menu = scene.addParentContextMenus(self, self.menu, event)
        return self.menu
    
    def editDialog(self, parent: QWidget = None):
        editAxisRegion(self, parent=parent)
        self.sigRegionChangeFinished.emit(self)


class AxisRegionLabel(InfLineLabel):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def updatePosition(self):
        # constrain label position to be visible within the viewbox (0.0 to 1.0)
        self.orthoPos = min(max(self.orthoPos, 0.0), 1.0)
        super().updatePosition()
        # ensure label is anchored to the top or bottom of the viewbox depending on its position so it is always visible
        self.setAnchor((0, int(1 - self.orthoPos)))


class XAxisRegion(AxisRegion):
    """ Vertical AxisRegionItem for x-axis ROI. """

    def __init__(self, *args, **kwargs):
        kwargs['orientation'] = 'vertical'
        AxisRegion.__init__(self, *args, **kwargs)


class YAxisRegion(AxisRegion):
    """ Horizontal AxisRegionItem for y-axis ROI. """

    def __init__(self, *args, **kwargs):
        kwargs['orientation'] = 'horizontal'
        AxisRegion.__init__(self, *args, **kwargs)


class AxisRegionPanel(QWidget):
    """ Widget for editing AxisRegion properties.
    """

    def __init__(self, *args, **kwargs):
        include_format: bool = kwargs.pop('include_format', True)
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

        if include_format:
            hline = QFrame()
            hline.setFrameShape(QFrame.Shape.HLine)
            hline.setFrameShadow(QFrame.Shadow.Sunken)

            self._format_panel = AxisRegionFormatPanel()

            vbox.addWidget(hline)
            vbox.addWidget(self._format_panel)

        vbox.addStretch()

        # default settings
        self.setState(AxisRegion().state())
    
    def state(self) -> dict[str, Any]:
        state: dict[str, Any] = {}

        if self._positionEdit.text() != '':
            try:
                min_val, max_val = map(float, self._positionEdit.text().split(','))
                state['position'] = (min_val, max_val)
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
                self._positionEdit.setText(f'{value[0]:.6f}, {value[1]:.6f}')
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


class AxisRegionFormatPanel(QWidget):
    """ Widget for editing AxisRegion format properties.
    """

    def __init__(self, *args, **kwargs):
        QWidget.__init__(self, *args, **kwargs)

        from qtpy.QtWidgets import QFormLayout, QVBoxLayout, QHBoxLayout, QSpinBox, QSpacerItem
        from xarray_graph.widgets.ColorButton import ColorButton

        self._faceColorButton = ColorButton()
        self._edgeColorButton = ColorButton()
        self._edgeWidthSpinBox = QSpinBox()

        self._faceHoverColorButton = ColorButton()
        self._edgeHoverColorButton = ColorButton()
        self._edgeHoverWidthSpinBox = QSpinBox()

        self._fontColorButton = ColorButton()
        self._fontSizeSpinBox = QSpinBox()

        self._leftColumn = QFormLayout()
        self._leftColumn.setContentsMargins(5, 5, 5, 5)
        self._leftColumn.setSpacing(5)
        self._leftColumn.addRow('Face Color', self._faceColorButton)
        self._leftColumn.addRow('Edge Color', self._edgeColorButton)
        self._leftColumn.addRow('Edge Width', self._edgeWidthSpinBox)
        self._leftColumn.addItem(QSpacerItem(20, 10))
        self._leftColumn.addRow('Font Color', self._fontColorButton)
        self._leftColumn.addRow('Font Size', self._fontSizeSpinBox)

        self._rightColumn = QFormLayout()
        self._rightColumn.setContentsMargins(5, 5, 5, 5)
        self._rightColumn.setSpacing(5)
        self._rightColumn.addRow('Face Hover Color', self._faceHoverColorButton)
        self._rightColumn.addRow('Edge Hover Color', self._edgeHoverColorButton)
        self._rightColumn.addRow('Edge Hover Width', self._edgeHoverWidthSpinBox)

        self._hoverLayoutWrapper = QVBoxLayout()
        self._hoverLayoutWrapper.addLayout(self._rightColumn)
        self._hoverLayoutWrapper.addStretch()

        self._formatLayoutWrapper = QHBoxLayout()
        self._formatLayoutWrapper.addLayout(self._leftColumn)
        self._formatLayoutWrapper.addLayout(self._hoverLayoutWrapper)

        self.setLayout(self._formatLayoutWrapper)

        # default settings
        self.setFormat(AxisRegion().format())
    
    def format(self) -> dict[str, Any]:
        from xarray_graph.utils.color import toColorStr

        fmt = {}

        faceColor = self._faceColorButton.color()
        edgeColor = self._edgeColorButton.color()
        edgeWidth = self._edgeWidthSpinBox.value()
        fontSize = self._fontSizeSpinBox.value()
        fontColor = self._fontColorButton.color()
        faceHoverColor = self._faceHoverColorButton.color()
        edgeHoverColor = self._edgeHoverColorButton.color()
        edgeHoverWidth = self._edgeHoverWidthSpinBox.value()

        if faceColor is not None:
            fmt['facecolor'] = toColorStr(faceColor)
        if edgeColor is not None:
            fmt['edgecolor'] = toColorStr(edgeColor)
        if edgeWidth > 0:
            fmt['edgewidth'] = edgeWidth
        if fontSize > 0:
            fmt['fontsize'] = fontSize
        if fontColor is not None:
            fmt['fontcolor'] = toColorStr(fontColor)
        if faceHoverColor is not None:
            fmt['facehovercolor'] = toColorStr(faceHoverColor)
        if edgeHoverColor is not None:
            fmt['edgehovercolor'] = toColorStr(edgeHoverColor)
        if edgeHoverWidth > 0:
            fmt['edgehoverwidth'] = edgeHoverWidth

        return fmt

    def setFormat(self, format: dict[str, Any]):
        from xarray_graph.utils.color import toQColor

        for key, value in format.items():
            key = key.lower()
            if key == 'facecolor':
                self._faceColorButton.setColor(toQColor(value))
            elif key == 'edgecolor':
                self._edgeColorButton.setColor(toQColor(value))
            elif key == 'edgewidth':
                self._edgeWidthSpinBox.setValue(value)
            elif key == 'facehovercolor':
                self._faceHoverColorButton.setColor(toQColor(value))
            elif key == 'edgehovercolor':
                self._edgeHoverColorButton.setColor(toQColor(value))
            elif key == 'edgehoverwidth':
                self._edgeHoverWidthSpinBox.setValue(value)
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


def editAxisRegion(region: AxisRegion = None, *args, **kwargs) -> dict[str, Any] | None:
    include_format: bool = kwargs.pop('include_format', True)
    title: str = kwargs.pop('title', None)

    if region is None:
        region = AxisRegion()

    from qtpy.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox
    
    panel = AxisRegionPanel(include_format=include_format)
    panel.setState(region.state())

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
    region.setState(edited_state)
    return edited_state


def test_live():
    from qtpy.QtWidgets import QApplication
    app = QApplication()

    ui = AxisRegionPanel()
    from pyqtgraph import PlotWidget
    ui = PlotWidget()
    region = XAxisRegion()
    region.setRegion((0.2, 0.8))
    ui.addItem(region)
    ui.show()

    app.exec()


if __name__ == '__main__':
    test_live()