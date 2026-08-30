""" Plot curve with context menu and style dialog.
"""
from __future__ import annotations

from typing import cast, Any
from qtpy.QtCore import Signal  # type: ignore
from qtpy.QtCore import Qt, QPoint, QRectF
from qtpy.QtGui import QColor, QPainterPath, QMouseEvent, QPen, QBrush
from qtpy.QtWidgets import QMenu, QWidget
from pyqtgraph import AxisItem, PlotDataItem, mkPen, mkBrush


class PlotData(PlotDataItem):
    """ Plot curve and/or scatter points with context menu and style dialog.
    """

    sigNameChanged = Signal(str)

    def __init__(self, *args, **kwargs):
        # default style is first MATLAB line color
        if 'pen' not in kwargs:
            kwargs['pen'] = mkPen(QColor(0, 114, 189), width=1)
        if 'symbolPen' not in kwargs:
            kwargs['symbolPen'] = mkPen(QColor(0, 114, 189), width=1)
        if 'symbolBrush' not in kwargs:
            kwargs['symbolBrush'] = mkBrush(QColor(0, 114, 189, 0))
        if 'symbol' not in kwargs:
            kwargs['symbol'] = None
        super().__init__(*args, **kwargs)

    def hasLine(self):
        pen = mkPen(self.opts['pen'])
        return pen.style() != Qt.PenStyle.NoPen
    
    def hasMarker(self):
        return 'symbol' in self.opts and self.opts['symbol'] is not None
    
    def shape(self) -> QPainterPath:
        if self.hasLine():
            return self.curve.shape()
        elif self.hasMarker():
            return self.scatter.shape()
        raise RuntimeError("No curve or symbol available to compute shape.")

    def boundingRect(self) -> QRectF:
        return self.shape().boundingRect()
    
    def mouseClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.RightButton:
            if self.hasLine():
                if self.curve.mouseShape().contains(event.pos()):
                    if self.raiseContextMenu(event):
                        event.accept()
                        return
            if self.hasMarker():
                if len(self.scatter.pointsAt(event.pos())) > 0:
                    if self.raiseContextMenu(event):
                        event.accept()
                        return
    
    def raiseContextMenu(self, event: QMouseEvent):
        menu: QMenu = self.getContextMenus(event)
        pos = event.screenPos()
        menu.popup(QPoint(int(pos.x()), int(pos.y())))
        return True
    
    def getContextMenus(self, event=None) -> QMenu:
        from qtpy.QtGui import QAction  # type: ignore

        self.menu = QMenu()

        name = self.name()
        if name is None:
            name = self.__class__.__name__
        this_menu = QMenu(name)
        this_menu.addAction('Data Table', self.dataDialog)
        this_menu.addSeparator()
        this_menu.addAction('Style', self.styleDialog)
        self.menu.addMenu(this_menu)

        # Let the scene add on to the end of our context menu (this is optional)
        self.menu.addSection('View')
        from pyqtgraph.GraphicsScene import GraphicsScene
        scene = cast(GraphicsScene, self.scene())
        self.menu = scene.addParentContextMenus(self, self.menu, event)
        return self.menu
    
    def name(self) -> str | None:
        return self.opts.get('Name', None)
    
    def setName(self, name: str | None) -> None:
        if name is None:
            del self.opts['Name']
        else:
            self.opts['Name'] = name
        self.sigNameChanged.emit(name)

    def color(self) -> QColor:
        pen = mkPen(self.opts['pen'])
        return pen.color()

    def setColor(self, color: QColor) -> None:
        pen = mkPen(self.opts['pen'])
        pen.setColor(color)
        self.setPen(pen)

    def lineStyle(self) -> Qt.PenStyle:
        pen = mkPen(self.opts['pen'])
        return pen.style()

    def setLineStyle(self, style: Qt.PenStyle) -> None:
        pen = mkPen(self.opts['pen'])
        pen.setStyle(style)
        self.setPen(pen)

    def lineWidth(self) -> float:
        pen = mkPen(self.opts['pen'])
        return pen.widthF()

    def setLineWidth(self, width: float) -> None:
        pen = mkPen(self.opts['pen'])
        pen.setWidthF(width)
        self.setPen(pen)

    def linePen(self) -> QPen:
        pen = mkPen(self.opts['pen'])
        return pen

    def setLinePen(self, pen: QPen) -> None:
        self.setPen(pen)

    def marker(self) -> str:
        return self.opts.get('symbol', 'none')

    def setMarker(self, marker: str | None) -> None:
        if marker == 'none':
            marker = None
        self.setSymbol(marker)

    def markerSize(self) -> float:
        return self.opts.get('symbolSize', 8.0)

    def setMarkerSize(self, size: float) -> None:
        self.setSymbolSize(size)

    def markerEdgeStyle(self) -> Qt.PenStyle:
        symbolPen = mkPen(self.opts['symbolPen'])
        return symbolPen.style()

    def setMarkerEdgeStyle(self, style: Qt.PenStyle) -> None:
        symbolPen = mkPen(self.opts['symbolPen'])
        symbolPen.setStyle(style)
        self.setSymbolPen(symbolPen)

    def markerEdgeWidth(self) -> float:
        symbolPen = mkPen(self.opts['symbolPen'])
        return symbolPen.widthF()

    def setMarkerEdgeWidth(self, width: float) -> None:
        symbolPen = mkPen(self.opts['symbolPen'])
        symbolPen.setWidthF(width)
        self.setSymbolPen(symbolPen)

    def markerEdgeColor(self) -> QColor:
        symbolPen = mkPen(self.opts['symbolPen'])
        return symbolPen.color()

    def setMarkerEdgeColor(self, color: QColor) -> None:
        symbolPen = mkPen(self.opts['symbolPen'])
        symbolPen.setColor(color)
        self.setSymbolPen(symbolPen)

    def markerFaceColor(self) -> QColor:
        symbolBrush = mkBrush(self.opts['symbolBrush'])
        return symbolBrush.color()

    def setMarkerFaceColor(self, color: QColor) -> None:
        symbolBrush = mkBrush(self.opts['symbolBrush'])
        symbolBrush.setColor(color)
        self.setSymbolBrush(symbolBrush)

    def markerPen(self) -> QPen:
        symbolPen = mkPen(self.opts['symbolPen'])
        return symbolPen

    def setMarkerPen(self, pen: QPen) -> None:
        self.setSymbolPen(pen)

    def markerBrush(self) -> QBrush:
        symbolBrush = mkBrush(self.opts['symbolBrush'])
        return symbolBrush

    def setMarkerBrush(self, brush: QBrush) -> None:
        self.setSymbolBrush(brush)

    @staticmethod
    def penStyleStr(pen_style: Qt.PenStyle) -> str:
        style_map = {
            Qt.PenStyle.NoPen: "none",
            Qt.PenStyle.SolidLine: "solid",
            Qt.PenStyle.DashLine: "dashed",
            Qt.PenStyle.DotLine: "dotted",
            Qt.PenStyle.DashDotLine: "dashdot",
            Qt.PenStyle.DashDotDotLine: "dashdotdot",
        }
        return style_map.get(pen_style, "solid")

    @staticmethod
    def toPenStyle(style: Any) -> Qt.PenStyle:
        if isinstance(style, Qt.PenStyle):
            return style
        style_map = {
            "none": Qt.PenStyle.NoPen,
            "solid": Qt.PenStyle.SolidLine,
            "dashed": Qt.PenStyle.DashLine,
            "dotted": Qt.PenStyle.DotLine,
            "dashdot": Qt.PenStyle.DashDotLine,
            "dashdotdot": Qt.PenStyle.DashDotDotLine,
        }
        return style_map.get(str(style).lower(), Qt.PenStyle.SolidLine)
    
    def style(self) -> dict[str, Any]:
        """ Return hashable dict for saving and restoring style.
        """
        from xarray_graph.utils.color import toColorStr

        style: dict[str, Any] = {}

        pen = mkPen(self.opts['pen'])
        symbolPen = mkPen(self.opts['symbolPen'])
        symbolBrush = mkBrush(self.opts['symbolBrush'])

        style['color'] = toColorStr(pen.color())
        style['linestyle'] = PlotData.penStyleStr(pen.style())
        style['linewidth'] = pen.widthF()
        style['marker'] = self.marker()
        style['markersize'] = self.markerSize()
        style['markeredgestyle'] = PlotData.penStyleStr(symbolPen.style())
        style['markeredgewidth'] = symbolPen.widthF()
        style['markeredgecolor'] = toColorStr(symbolPen.color())
        style['markerfacecolor'] = toColorStr(symbolBrush.color())

        return style
    
    def setStyle(self, style: dict[str, Any]) -> None:
        """ Restore style from hashable dict.
        """
        from xarray_graph.utils.color import toQColor

        for key, value in style.items():
            key = key.lower()
            if key == 'color':
                self.setColor(toQColor(value))
            elif key == 'linestyle':
                penStyle = PlotData.toPenStyle(value)
                self.setLineStyle(penStyle)
            elif key == 'linewidth':
                self.setLineWidth(value)
            elif key == 'marker':
                self.setMarker(value)
            elif key == 'markersize':
                self.setSymbolSize(value)
            elif key == 'markeredgestyle':
                penStyle = PlotData.toPenStyle(value)
                self.setMarkerEdgeStyle(penStyle)
            elif key == 'markeredgewidth':
                self.setMarkerEdgeWidth(value)
            elif key == 'markeredgecolor':
                self.setMarkerEdgeColor(toQColor(value))
            elif key == 'markerfacecolor':
                self.setMarkerFaceColor(toQColor(value))
    
    def styleDialog(self):
        from qtpy.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox

        name = self.name()
        if name is None:
            name = self.__class__.__name__
        
        panel = PlotDataStylePanel()
        panel.setStyle(self.style())

        dlg = QDialog(parent=self.getViewWidget())
        dlg.setWindowTitle(name)
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        vbox = QVBoxLayout(dlg)
        vbox.setContentsMargins(5, 5, 5, 5)
        vbox.addWidget(panel)

        btns = QDialogButtonBox()
        btns.setStandardButtons(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        vbox.addWidget(btns)
        vbox.addStretch()
        
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        edited_style = panel.editedStyle()
        if edited_style:
            self.setStyle(edited_style)
    
    def dataDialog(self):
        import numpy as np
        from qtpy.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox
        from xarray_graph.table.ArrayTableModel import ArrayTableModel
        from xarray_graph.table.ArrayTableView import ArrayTableView

        name = self.name()
        if name is None:
            name = self.__class__.__name__

        dlg = QDialog()
        dlg.setWindowTitle(name)
        vbox = QVBoxLayout(dlg)
        vbox.setContentsMargins(5, 5, 5, 5)
        vbox.setSpacing(0)

        xdata, ydata = self.getOriginalDataset()
        if not isinstance(xdata, np.ndarray) or not isinstance(ydata, np.ndarray):
            return

        xy = np.column_stack((xdata, ydata))
        model = ArrayTableModel(xy)
        view = ArrayTableView()
        view.setModel(model)
        vbox.addWidget(view)

        colum_labels = ['X', 'Y']
        from pyqtgraph.graphicsItems.ViewBox import ViewBox
        vb = self.getViewBox()
        if isinstance(vb, ViewBox):
            from pyqtgraph import PlotWidget
            plot = vb.parentWidget()
            if isinstance(plot, PlotWidget):
                from pyqtgraph.graphicsItems.AxisItem import AxisItem
                xaxis: AxisItem = plot.getAxis('bottom')
                yaxis: AxisItem = plot.getAxis('left')
                xlabel = xaxis.labelText
                if xaxis.labelUnits:
                    xlabel += f' ({xaxis.labelUnits})'
                ylabel = yaxis.labelText
                if yaxis.labelUnits:
                    ylabel += f' ({yaxis.labelUnits})'
                colum_labels = [xlabel, ylabel]
        model.setColumnLabels(colum_labels)

        btns = QDialogButtonBox()
        btns.setStandardButtons(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        vbox.addWidget(btns)
        
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        xdata = xy[:, 0]
        ydata = xy[:, 1]
        self.setData(xdata, ydata)


class PlotDataStylePanel(QWidget):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        from xarray_graph.widgets.ColorButton import ColorButton
        from qtpy.QtWidgets import QLabel, QComboBox, QDoubleSpinBox, QCheckBox, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox

        self._linestyles: list[str] = ['No Line', 'Solid Line', 'Dash Line', 'Dot Line', 'Dash Dot Line', 'Dash Dot Dot Line']
        self._penstyles: list[Qt.PenStyle] = [Qt.PenStyle.NoPen, Qt.PenStyle.SolidLine, Qt.PenStyle.DashLine, Qt.PenStyle.DotLine, Qt.PenStyle.DashDotLine, Qt.PenStyle.DashDotDotLine]

        self._color_label = QLabel('Color')
        self._color_button = ColorButton()
        self._color_button.colorChanged.connect(self._on_color_changed)

        self._linestyle_label = QLabel('Style')
        self._linestyle_combobox = QComboBox()
        self._linestyle_combobox.addItems(self._linestyles)
        self._linestyle_combobox.setCurrentIndex(1)

        self._linewidth_label = QLabel('Width')
        self._linewidth_spinbox = QDoubleSpinBox()
        self._linewidth_spinbox.setMinimum(0)
        self._linewidth_spinbox.setValue(1)

        self._marker_label = QLabel('Marker')
        self._marker_combobox = QComboBox()
        self._marker_combobox.addItems(['None', 'Circle', 'Square', 'Triangle', 'Diamond', 'Plus', 'Triangle Up', 'Triangle Right', 'Triangle Left', 'Pentagon', 'Hexagon', 'Star', 'Vertical Line', 'Horizontal Line', 'Cross', 'Arrow Up', 'Arrow Right', 'Arrow Down', 'Arrow Left', 'Crosshair'])
        self._marker_combobox.setCurrentIndex(0)
        self._pyqtgraph_symbols = ['none', 'o', 's', 't', 'd', '+', 't1', 't2', 't3', 'p', 'h', 'star', '|', '_', 'x', 'arrow_up', 'arrow_right', 'arrow_down', 'arrow_left', 'crosshair']

        self._markersize_label = QLabel('Size')
        self._markersize_spinbox = QDoubleSpinBox()
        self._markersize_spinbox.setMinimum(0)
        self._markersize_spinbox.setValue(8)

        self._markeredgestyle_label = QLabel('Edge Style')
        self._markeredgestyle_combobox = QComboBox()
        self._markeredgestyle_combobox.addItems(self._linestyles)
        self._markeredgestyle_combobox.setCurrentIndex(1)

        self._markeredgewidth_label = QLabel('Edge Width')
        self._markeredgewidth_spinbox = QDoubleSpinBox()
        self._markeredgewidth_spinbox.setMinimum(0)
        self._markeredgewidth_spinbox.setValue(1)

        self._markeredgecolor_label = QLabel('Edge Color')
        self._markeredgecolor_button = ColorButton()

        self._markerfacecolor_label = QLabel('Face Color')
        self._markerfacecolor_button = ColorButton()

        self._default_color_checkbox = QCheckBox('Dynamic')
        self._default_color_checkbox.setToolTip('Let app choose color.')
        self._default_color_checkbox.stateChanged.connect(self._on_default_color_changed)

        self._default_markeredgecolor_checkbox = QCheckBox('Use Color')
        self._default_markeredgecolor_checkbox.stateChanged.connect(self._on_default_markeredgecolor_changed)

        self._default_markerfacecolor_checkbox = QCheckBox('Use Color')
        self._default_markerfacecolor_checkbox.stateChanged.connect(self._on_default_markerfacecolor_changed)

        self._markerfacecolor_nofill_checkbox = QCheckBox('No Fill')
        self._markerfacecolor_nofill_checkbox.stateChanged.connect(self._on_markerfacecolor_nofill_changed)
        self._markerfacecolor_nofill_checkbox.setStyleSheet("QCheckBox { padding-right: 10px; }") # QCheckBox doesn't correctly account for margins?

        self._widgets: dict[str, QWidget] = {
            'color': self._color_button,
            'linestyle': self._linestyle_combobox,
            'linewidth': self._linewidth_spinbox,
            'marker': self._marker_combobox,
            'markersize': self._markersize_spinbox,
            'markeredgestyle': self._markeredgestyle_combobox,
            'markeredgewidth': self._markeredgewidth_spinbox,
            'markeredgecolor': self._markeredgecolor_button,
            'markerfacecolor': self._markerfacecolor_button,
        }
    
        def _get_hbox_container() -> tuple[QWidget, QHBoxLayout]:
            container = QWidget()
            hbox = QHBoxLayout(container)
            hbox.setContentsMargins(0, 0, 0, 0)
            hbox.setSpacing(10)
            return container, hbox
        
        color_widget, hbox = _get_hbox_container()
        hbox.addWidget(self._color_button)
        hbox.addWidget(self._default_color_checkbox)

        markeredgecolor_widget, hbox = _get_hbox_container()
        hbox.addWidget(self._markeredgecolor_button)
        hbox.addWidget(self._default_markeredgecolor_checkbox)

        markerfacecolor_widget, hbox = _get_hbox_container()
        hbox.addWidget(self._markerfacecolor_button)
        hbox.addWidget(self._default_markerfacecolor_checkbox)
        hbox.addWidget(self._markerfacecolor_nofill_checkbox)

        line_group = QGroupBox('Line')
        form = QFormLayout(line_group)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(6)
        form.setHorizontalSpacing(10)
        form.addRow(self._color_label, color_widget)
        form.addRow(self._linestyle_label, self._linestyle_combobox)
        form.addRow(self._linewidth_label, self._linewidth_spinbox)

        marker_group = QGroupBox('Marker')
        form = QFormLayout(marker_group)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(6)
        form.setHorizontalSpacing(10)
        form.addRow(self._marker_label, self._marker_combobox)
        form.addRow(self._markersize_label, self._markersize_spinbox)
        form.addRow(self._markeredgestyle_label, self._markeredgestyle_combobox)
        form.addRow(self._markeredgewidth_label, self._markeredgewidth_spinbox)
        form.addRow(self._markeredgecolor_label, markeredgecolor_widget)
        form.addRow(self._markerfacecolor_label, markerfacecolor_widget)

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(10, 10, 10, 10)
        vbox.setSpacing(10)
        vbox.addWidget(line_group)
        vbox.addWidget(marker_group)
        vbox.addStretch()
        
        # self._default_color_checkbox.setChecked(True)
        # self._default_markeredgecolor_checkbox.setChecked(True)
        # self._default_markerfacecolor_checkbox.setChecked(True)
    
    def _color(self) -> QColor:
        if self._default_color_checkbox.isChecked():
            return QColor()
        return self._color_button.color() or QColor()

    def _on_color_changed(self, color: QColor):
        if self._default_markeredgecolor_checkbox.isChecked():
            self._markeredgecolor_button.setColor(color)
        if self._default_markerfacecolor_checkbox.isChecked():
            self._markerfacecolor_button.setColor(color)

    def _on_default_color_changed(self, state: int):
        if state:
            self._color_button.setColor(QColor())
        self._color_button.setEnabled(not state)

    def _on_default_markeredgecolor_changed(self, state: int):
        if state:
            self._markeredgecolor_button.setColor(self._color_button.color())
        self._markeredgecolor_button.setEnabled(not state)

    def _on_default_markerfacecolor_changed(self, state: int):
        if state:
            self._markerfacecolor_nofill_checkbox.setChecked(False)
            self._markerfacecolor_button.setColor(self._color_button.color())
        self._markerfacecolor_button.setEnabled(not state)

    def _on_markerfacecolor_nofill_changed(self, state: int):
        if state:
            self._default_markerfacecolor_checkbox.setChecked(False)
            self._markerfacecolor_button.setColor(QColor())
        self._markerfacecolor_button.setEnabled(not state)

    def style(self) -> dict[str, Any]:
        from qtpy.QtWidgets import QComboBox, QDoubleSpinBox
        from xarray_graph.widgets.ColorButton import ColorButton
        from xarray_graph.utils.color import toColorStr

        style: dict[str, Any] = {}
        for key, widget in self._widgets.items():
            if key in ['color', 'markeredgecolor', 'markerfacecolor']:
                widget = cast(ColorButton, widget)
                style[key] = toColorStr(widget.color())
            elif key in ['linestyle', 'markeredgestyle']:
                widget = cast(QComboBox, widget)
                index = widget.currentIndex()
                penstyle = self._penstyles[index]
                style[key] = PlotData.penStyleStr(penstyle)
            elif key in ['linewidth', 'markersize', 'markeredgewidth']:
                widget = cast(QDoubleSpinBox, widget)
                style[key] = widget.value()
            elif key == 'marker':
                widget = cast(QComboBox, widget)
                index = widget.currentIndex()
                style[key] = self._pyqtgraph_symbols[index]
        return style
    
    def setStyle(self, style: dict[str, Any]):
        from xarray_graph.utils.color import toQColor

        for key, value in style.items():
            key = key.lower()
            if key == 'color':
                color = toQColor(value)
                self._color_button.setColor(color)
                self._default_color_checkbox.setChecked(False)
            elif key == 'linestyle':
                penstyle = PlotData.toPenStyle(value)
                index = self._penstyles.index(penstyle)
                self._linestyle_combobox.setCurrentIndex(index)
            elif key == 'linewidth':
                value = max(0, value)
                self._linewidth_spinbox.setValue(value)
            elif key == 'marker':
                try:
                    index = self._pyqtgraph_symbols.index(value)
                    self._marker_combobox.setCurrentIndex(index)
                except ValueError:
                    continue
            elif key == 'markersize':
                value = max(0, value)
                self._markersize_spinbox.setValue(value)
            elif key == 'markeredgestyle':
                penstyle = PlotData.toPenStyle(value)
                index = self._penstyles.index(penstyle)
                self._markeredgestyle_combobox.setCurrentIndex(index)
            elif key == 'markeredgewidth':
                value = max(0, value)
                self._markeredgewidth_spinbox.setValue(value)
            elif key == 'markeredgecolor':
                color = toQColor(value)
                self._markeredgecolor_button.setColor(color)
                self._default_markeredgecolor_checkbox.setChecked(False)
            elif key == 'markerfacecolor':
                color = toQColor(value)
                self._markerfacecolor_button.setColor(color)
                self._default_markerfacecolor_checkbox.setChecked(False)
                self._markerfacecolor_nofill_checkbox.setChecked(color == QColor())

        from copy import deepcopy
        self._style = deepcopy(style)

    def editedStyle(self) -> dict[str, Any]:
            """ Return the style of the widget, but only include values that have changed from the original style.
            """
            current_style = self.style()
            edited_style = {}
            for key, value in current_style.items():
                if key not in self._style or self._style[key] != value:
                    edited_style[key] = value
            return edited_style


def test_live():
    from qtpy.QtWidgets import QApplication
    app = QApplication()

    import numpy as np
    data = PlotData(y=np.random.random(100))
    data.setName('Test')
    data.setToolTip(data.name() or '')

    from pyqtgraph import PlotWidget
    plot = PlotWidget()
    plot.addItem(data)
    plot.show()

    app.exec()


if __name__ == '__main__':
    test_live()