""" Data interface and widgets for storing/editing the style of a graph.

Style is stored in hashable dict.
"""
from __future__ import annotations

from qtpy.QtCore import Qt

import typing
if typing.TYPE_CHECKING:
    from qtpy.QtGui import QPen, QBrush


class PlotCurveStyle(dict):
    """ Hashable style dict for graph data.

    'color': str
    'linestyle': str
    'linewidth': float
    'marker': str
    'markersize': float
    'markeredgestyle': str
    'markeredgewidth': float
    'markeredgecolor': str
    'markerfacecolor': str
    """

    # alternate key names
    keymap = {
        'c': 'color',
        'ls': 'linestyle',
        'lw': 'linewidth',
        'symbol': 'marker',
        'm': 'marker',
        'ms': 'markersize',
        'mes': 'markeredgestyle',
        'mew': 'markeredgewidth',
        'mec': 'markeredgecolor',
        'mfc': 'markerfacecolor',
    }

    # lines
    penStyles = [Qt.PenStyle.NoPen, Qt.PenStyle.SolidLine, Qt.PenStyle.DashLine, Qt.PenStyle.DotLine, Qt.PenStyle.DashDotLine, Qt.PenStyle.DashDotDotLine]
    penStyleLabels = ['No Line', 'Solid Line', 'Dash Line', 'Dot Line', 'Dash Dot Line', 'Dash Dot Dot Line']
    lineStyles = ['none', 'solid', 'dashed', 'dotted', 'dashdot', 'dashdotdot']
    lineStyleSymbols = ['', '-', '--', ':', '-.', '-..']

    # {label: marker key}
    pyqtgraphMarkers = {
        'None': 'none',
        'Circle': 'o',
        'Square': 's',
        'Triangle': 't',
        'Diamond': 'd',
        'Plus': '+',
        'Triangle Up': 't1',
        'Triangle Right': 't2',
        'Triangle Left': 't3',
        'Pentagon': 'p',
        'Hexagon': 'h',
        'Star': 'star',
        'Vertical Line': '|',
        'Horizontal Line': '_',
        'Cross': 'x',
        'Arrow Up': 'arrow_up',
        'Arrow Right': 'arrow_right',
        'Arrow Down': 'arrow_down',
        'Arrow Left': 'arrow_left',
        'Crosshair': 'crosshair'
    }

    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)

        # default values
        self._defaults = {
            'linestyle': '-',
            'linewidth': 1,
            'marker': 'none',
            'markersize': 10,
            'markeredgestyle': '-',
            'markeredgewidth': 1,
        }
    
    def __getitem__(self, key: str):
        key = self.getKey(key)
        if key in self:
            return dict.__getitem__(self, key)
        # key not found...
        if key == 'markeredgewidth':
            if 'linewidth' in self:
                return self['linewidth']
        elif key == 'markeredgecolor':
            if 'color' in self:
                return self['color']
        elif key == 'markerfacecolor':
            if 'markeredgecolor' in self:
                return self['markeredgecolor']
            elif 'color' in self:
                return self['color']
        if key in self._defaults:
            return self._defaults[key]
    
    def __setitem__(self, key: str, value):
        key = self.getKey(key)
        if key.endswith('color'):
            if value is not None:
                from xarray_graph.utils.color import toColorStr
                value = toColorStr(value)
        elif key in ['linestyle', 'markeredgestyle']:
            if value is None:
                value = 'none'
            elif isinstance(value, (int, Qt.PenStyle)):
                value = PlotCurveStyle.lineStyles[value]
            elif isinstance(value, str):
                if value == '.-':
                    value = '-.'
                elif value == '..-' or value == '.-.':
                    value = '-..'
        elif key == 'linewidth':
            if value is not None:
                value = max(0, value)
        elif key == 'marker':
            if value is None:
                value = 'none'
        elif key == 'markersize':
            if value is not None:
                value = max(0, value)
        elif key == 'markeredgewidth':
            if value is not None:
                value = max(0, value)
        if value is None:
            del self[key]
            return
        dict.__setitem__(self, key, value)
    
    def __delitem__(self, key: str):
        key = self.getKey(key)
        if key in self:
            dict.__delitem__(self, key)
    
    @staticmethod
    def getKey(key: str) -> str:
        key = key.lower()
        if key in PlotCurveStyle.keymap:
            key = PlotCurveStyle.keymap[key]
        return key

    def penStyle(self, linestyle: str) -> Qt.PenStyle:
        if linestyle in self.lineStyles:
            return self.penStyles[self.lineStyles.index(linestyle)]
        if linestyle in self.lineStyleSymbols:
            return self.penStyles[self.lineStyleSymbols.index(linestyle)]

    def linePen(self) -> QPen:
        color = self['color']
        linestyle = self['linestyle']
        penstyle = self.penStyle(linestyle)
        linewidth = self['linewidth']
        from pyqtgraph import mkPen
        return mkPen(color=color, style=penstyle, width=linewidth)

    def markerPen(self) -> QPen:
        color = self['markeredgecolor']
        linestyle = self['markeredgestyle']
        penstyle = self.penStyle(linestyle)
        linewidth = self['markeredgewidth']
        from pyqtgraph import mkPen
        return mkPen(color=color, style=penstyle, width=linewidth)

    def markerBrush(self) -> QBrush:
        color = self['markerfacecolor']
        from pyqtgraph import mkBrush
        return mkBrush(color=color)

    # def createWidget(self, key: str) -> QWidget:
    #     key = self.getKey(key)
    #     if key in ['color', 'markeredgecolor', 'markerfacecolor']:
    #         widget = ColorButton()
    #         widget.setColor(self[key])
    #         return widget
    #     elif key in ['linestyle', 'markeredgestyle']:
    #         widget = QComboBox()
    #         widget.addItems(PlotCurveStyle.penStyleLabels)
    #         widget.setCurrentIndex(PlotCurveStyle.penStyleKeys.index(self[key]))
    #         return widget
    #     elif key in ['linewidth', 'markersize', 'markeredgewidth']:
    #         widget = QDoubleSpinBox()
    #         widget.setMinimum(0)
    #         widget.setValue(self[key])
    #         return widget
    #     elif key == 'marker':
    #         widget = QComboBox()
    #         marker_labels = list(PlotCurveStyle.pyqtgraphMarkers.keys())
    #         marker_keys = list(PlotCurveStyle.pyqtgraphMarkers.values())
    #         widget.addItems(marker_labels)
    #         marker = self[key]
    #         if marker is None:
    #             marker = 'None'
    #         elif marker in marker_keys:
    #             marker = marker_labels[marker_keys.index(marker)]
    #         widget.setCurrentIndex(marker_labels.index(marker))
    #         return widget

    # def updateWidget(self, key: str, widget: QWidget) -> None:
    #     key = self.getKey(key)
    #     if key in ['color', 'markeredgecolor', 'markerfacecolor']:
    #         widget.setColor(self[key])
    #     elif key in ['linestyle', 'markeredgestyle']:
    #         widget.setCurrentIndex(PlotCurveStyle.penStyleKeys.index(self[key]))
    #     elif key in ['linewidth', 'markersize', 'markeredgewidth']:
    #         widget.setValue(self[key])
    #     elif key == 'marker':
    #         marker_labels = list(PlotCurveStyle.pyqtgraphMarkers.keys())
    #         marker_keys = list(PlotCurveStyle.pyqtgraphMarkers.values())
    #         marker = self[key]
    #         if marker is None:
    #             marker = 'None'
    #         elif marker in marker_keys:
    #             marker = marker_labels[marker_keys.index(marker)]
    #         widget.setCurrentIndex(marker_labels.index(marker))

    # def updateFromWidget(self, key: str, widget: QWidget) -> None:
    #     key = self.getKey(key)
    #     if key in ['color', 'markeredgecolor', 'markerfacecolor']:
    #         self[key] = widget.color()
    #     elif key in ['linestyle', 'markeredgestyle']:
    #         self[key] = PlotCurveStyle.penStyleKeys[widget.currentIndex()]
    #     elif key in ['linewidth', 'markersize', 'markeredgewidth']:
    #         self[key] = widget.value()
    #     elif key == 'marker':
    #         self[key] = widget.currentText()


# class GraphStylePanel(QWidget):

#     def __init__(self, styles: list[str] = None, *args, **kwargs):
#         QWidget.__init__(self, *args, **kwargs)

#         if styles is None:
#             styles = ['color', 'linestyle', 'linewidth', 'marker', 'markersize', 'markeredgestyle', 'markeredgewidth', 'markeredgecolor', 'markerfacecolor']
#         styles = [PlotCurveStyle.getKey(key) for key in styles]

#         self._widgets: dict[str, QWidget] = {key: PlotCurveStyle().createWidget(key) for key in styles}

#         vbox = QVBoxLayout(self)
#         vbox.setContentsMargins(10, 10, 10, 10)
#         vbox.setSpacing(10)

#         sections = [
#             [
#                 'Line',
#                 ['color', 'linestyle', 'linewidth'],
#                 ['Color', 'Style', 'Width']
#             ],
#             [
#                 'Marker',
#                 ['marker', 'markersize', 'markeredgestyle', 'markeredgewidth', 'markeredgecolor', 'markerfacecolor'],
#                 ['Marker', 'Size', 'Edge Style', 'Edge Width', 'Edge Color', 'Face Color']
#             ],
#         ]
#         for section in sections:
#             title, keys, labels = section
#             if set(keys).intersection(styles):
#                 # sectionWidget = CollapsibleSection(title=title)
#                 sectionWidget = QGroupBox(title=title)
#                 form = QFormLayout(sectionWidget)
#                 form.setContentsMargins(0, 0, 0, 0)
#                 form.setSpacing(6)
#                 form.setHorizontalSpacing(10)
#                 for key, label in zip(keys, labels):
#                     if key in styles:
#                         form.addRow(label, self._widgets[key])
#                 # sectionWidget.setContentLayout(form)
#                 vbox.addWidget(sectionWidget)
        
#         # # expand 1st section
#         # if vbox.count() > 0:
#         #     vbox.itemAt(0).widget().expand()
        
#         vbox.addStretch()
    
#     def graphStyle(self) -> PlotCurveStyle:
#         graphStyle = PlotCurveStyle()
#         for key, widget in self._widgets.items():
#             graphStyle.updateFromWidget(key, widget)
#         return graphStyle
    
#     def setGraphStyle(self, graphStyle: PlotCurveStyle):
#         for key, widget in self._widgets.items():
#             graphStyle.updateWidget(key, widget)


# def editGraphStyle(graphStyle: PlotCurveStyle, styles: list[str] = None, parent: QWidget = None, title: str = None) -> PlotCurveStyle | None:
#     panel = GraphStylePanel(styles)
#     panel.layout().setContentsMargins(0, 0, 0, 0)
#     panel.setGraphStyle(graphStyle)

#     dlg = QDialog(parent)
#     vbox = QVBoxLayout(dlg)
#     vbox.addWidget(panel)

#     btns = QDialogButtonBox()
#     btns.setStandardButtons(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
#     btns.accepted.connect(dlg.accept)
#     btns.rejected.connect(dlg.reject)
#     vbox.addWidget(btns)
#     vbox.addStretch()

#     if title is not None:
#         dlg.setWindowTitle(title)
#     dlg.setWindowModality(Qt.ApplicationModal)
#     if dlg.exec() == QDialog.Accepted:
#         return panel.graphStyle()


def test():
    style = PlotCurveStyle()
    pen = style.linePen()
    print(pen)


# def test_live():
#     app = QApplication()
#     ui = GraphStylePanel()
#     ui.show()
#     # QTimer.singleShot(1000, lambda: print(editGraphStyle(GraphStyle())))
#     app.exec()


if __name__ == '__main__':
    test()
    # test_live()
