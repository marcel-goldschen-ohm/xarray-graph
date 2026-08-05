""" Data interface and widgets for storing/editing the style of a graph.

Style is stored in hashable dict.
"""
from __future__ import annotations

from qtpy.QtCore import Qt
from qtpy.QtGui import QColor
from qtpy.QtWidgets import QWidget

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
    lineStyles = {
        'pens': [Qt.PenStyle.NoPen, Qt.PenStyle.SolidLine, Qt.PenStyle.DashLine, Qt.PenStyle.DotLine, Qt.PenStyle.DashDotLine, Qt.PenStyle.DashDotDotLine],
        'labels': ['No Line', 'Solid Line', 'Dash Line', 'Dot Line', 'Dash Dot Line', 'Dash Dot Dot Line'],
        'symbols': ['', '-', '--', ':', '-.', '-..'],
        'strings': ['none', 'solid', 'dashed', 'dotted', 'dashdot', 'dashdotdot'],
    }

    # markers
    markers = {
        'pyqtgraph': ['none', 'o', 's', 't', 'd', '+', 't1', 't2', 't3', 'p', 'h', 'star', '|', '_', 'x', 'arrow_up', 'arrow_right', 'arrow_down', 'arrow_left', 'crosshair'],
        'labels': ['None', 'Circle', 'Square', 'Triangle', 'Diamond', 'Plus', 'Triangle Up', 'Triangle Right', 'Triangle Left', 'Pentagon', 'Hexagon', 'Star', 'Vertical Line', 'Horizontal Line', 'Cross', 'Arrow Up', 'Arrow Right', 'Arrow Down', 'Arrow Left', 'Crosshair'],
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
            # fallback to linewidth
            if 'linewidth' in self:
                return self['linewidth']
        elif key == 'markeredgecolor':
            # fallback to color
            if 'color' in self:
                return self['color']
        elif key == 'markerfacecolor':
            # fallback to markeredgecolor
            if 'markeredgecolor' in self:
                return self['markeredgecolor']
            # fallback to color
            if 'color' in self:
                return self['color']
        if key in self._defaults:
            return self._defaults[key]
    
    def __setitem__(self, key: str, value):
        if value is None:
            del self[key]
            return
        key = self.getKey(key)
        if key.endswith('color'):
            from xarray_graph.utils.color import toQColor
            value = toQColor(value)
        elif key in ['linestyle', 'markeredgestyle']:
            value = self._toLineStyle(value)
        elif key in ['linewidth', 'markersize', 'markeredgewidth']:
            value = max(0, value)
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

    @staticmethod
    def _strToPen(linestyle: str) -> Qt.PenStyle:
        try:
            index = PlotCurveStyle.lineStyles['strings'].index(linestyle)
            return PlotCurveStyle.lineStyles['pens'][index]
        except ValueError:
            try:
                index = PlotCurveStyle.lineStyles['symbols'].index(linestyle)
                return PlotCurveStyle.lineStyles['pens'][index]
            except ValueError:
                try:
                    index = PlotCurveStyle.lineStyles['labels'].index(linestyle)
                    return PlotCurveStyle.lineStyles['pens'][index]
                except ValueError:
                    raise ValueError(f'Invalid linestyle: {linestyle}')

    @staticmethod
    def _penToStr(pen: Qt.PenStyle, opt: str = 'strings') -> str:
        if opt not in ['strings', 'symbols', 'labels']:
            raise ValueError(f'Invalid option: "{opt}". Must be one of: "strings", "symbols", "labels"')
        try:
            index = PlotCurveStyle.lineStyles['pens'].index(pen)
            return PlotCurveStyle.lineStyles[opt][index]
        except ValueError:
            raise ValueError(f'Invalid pen style: {pen}')

    @staticmethod
    def _toLineStyle(value: str | Qt.PenStyle) -> str:
        try:
            if isinstance(value, str):
                if value == '.-':
                    value = '-.'
                elif value == '..-' or value == '.-.':
                    value = '-..'
                pen = PlotCurveStyle._strToPen(value)
                return PlotCurveStyle._penToStr(pen)
            elif isinstance(value, Qt.PenStyle):
                return PlotCurveStyle._penToStr(value)
        except ValueError:
            raise ValueError(f'Invalid linestyle: {value}')

    def color(self) -> QColor:
        from xarray_graph.utils.color import toQColor
        color = self['color']
        return toQColor(color)

    def markerEdgeColor(self) -> QColor:
        from xarray_graph.utils.color import toQColor
        color = self['markeredgecolor']
        return toQColor(color)

    def markerFaceColor(self) -> QColor:
        from xarray_graph.utils.color import toQColor
        color = self['markerfacecolor']
        return toQColor(color)

    def linePen(self) -> QPen:
        color = self['color']
        linestyle = self['linestyle']
        penstyle = self._strToPen(linestyle)
        linewidth = self['linewidth']
        from pyqtgraph import mkPen
        return mkPen(color=color, style=penstyle, width=linewidth)

    def markerPen(self) -> QPen:
        color = self['markeredgecolor']
        linestyle = self['markeredgestyle']
        penstyle = self._strToPen(linestyle)
        linewidth = self['markeredgewidth']
        from pyqtgraph import mkPen
        return mkPen(color=color, style=penstyle, width=linewidth)

    def markerBrush(self) -> QBrush:
        color = self['markerfacecolor']
        from pyqtgraph import mkBrush
        return mkBrush(color=color)


class PlotCurveStylePanel(QWidget):

    def __init__(self, *args, **kwargs):
        QWidget.__init__(self, *args, **kwargs)

        from xarray_graph.widgets.ColorButton import ColorButton
        from qtpy.QtWidgets import QLabel, QComboBox, QDoubleSpinBox, QCheckBox, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox

        self._color_label = QLabel('Color')
        self._color_button = ColorButton()
        self._color_button.colorChanged.connect(self._on_color_changed)

        self._linestyle_label = QLabel('Style')
        self._linestyle_combobox = QComboBox()
        self._linestyle_combobox.addItems(PlotCurveStyle.lineStyles['labels'])
        self._linestyle_combobox.setCurrentIndex(1)  # default to solid line

        self._linewidth_label = QLabel('Width')
        self._linewidth_spinbox = QDoubleSpinBox()
        self._linewidth_spinbox.setMinimum(0)
        self._linewidth_spinbox.setValue(1)

        self._marker_label = QLabel('Marker')
        self._marker_combobox = QComboBox()
        self._marker_combobox.addItems(list(PlotCurveStyle.markers['labels']))
        self._marker_combobox.setCurrentIndex(0)  # default to no marker

        self._markersize_label = QLabel('Size')
        self._markersize_spinbox = QDoubleSpinBox()
        self._markersize_spinbox.setMinimum(0)
        self._markersize_spinbox.setValue(10)

        self._markeredgestyle_label = QLabel('Edge Style')
        self._markeredgestyle_combobox = QComboBox()
        self._markeredgestyle_combobox.addItems(PlotCurveStyle.lineStyles['labels'])
        self._markeredgestyle_combobox.setCurrentIndex(1)  # default to solid line

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
        return self._color_button.color()

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

    def style(self) -> PlotCurveStyle:
        style = PlotCurveStyle()
        for key, widget in self._widgets.items():
            try:
                if key in ['color', 'markeredgecolor', 'markerfacecolor']:
                    if key == 'markerfacecolor' and self._markerfacecolor_nofill_checkbox.isChecked():
                        value = 'none'
                    else:
                        value = widget.color()
                elif key in ['linestyle', 'markeredgestyle']:
                    index = widget.currentIndex()
                    value = PlotCurveStyle.lineStyles['strings'][index]
                elif key in ['linewidth', 'markersize', 'markeredgewidth']:
                    value = widget.value()
                elif key == 'marker':
                    index = widget.currentIndex()
                    value = PlotCurveStyle.markers['pyqtgraph'][index]
                else:
                    # should not happen
                    continue
                style[key] = value
            except Exception:
                continue
        return style
    
    def setStyle(self, style: PlotCurveStyle):
        for key, widget in self._widgets.items():
            try:
                value = style[key]
                if key == 'color':
                    if key in style:
                        self._default_color_checkbox.setChecked(False)
                        self._color_button.setColor(value)
                    else:
                        self._default_color_checkbox.setChecked(True)
                elif key in ['linestyle', 'markeredgestyle']:
                    try:
                        pen = PlotCurveStyle._strToPen(value)
                        index = PlotCurveStyle.lineStyles['pens'].index(pen)
                        widget.setCurrentIndex(index)
                    except ValueError:
                        continue
                elif key in ['linewidth', 'markersize', 'markeredgewidth']:
                    value = max(0, value)
                    widget.setValue(value)
                elif key == 'marker':
                    try:
                        index = PlotCurveStyle.markers['pyqtgraph'].index(value)
                        widget.setCurrentIndex(index)
                    except ValueError:
                        continue
                elif key == 'markeredgecolor':
                    if key in style:
                        self._default_markeredgecolor_checkbox.setChecked(False)
                        self._markeredgecolor_button.setColor(value)
                    else:
                        self._default_markeredgecolor_checkbox.setChecked(True)
                elif key == 'markerfacecolor':
                    if key in style:
                        self._default_markerfacecolor_checkbox.setChecked(False)
                        self._markerfacecolor_nofill_checkbox.setChecked(value == 'none')
                        self._markerfacecolor_button.setColor(value)
                    else:
                        self._default_markerfacecolor_checkbox.setChecked(True)
            except Exception:
                continue


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


def test_live():
    from qtpy.QtWidgets import QApplication
    app = QApplication()
    style = PlotCurveStyle()
    style['color'] = 'red'
    style['marker'] = 'o'
    style['markerfacecolor'] = 'none'
    ui = PlotCurveStylePanel()
    ui.setStyle(style)
    ui.show()
    app.exec()


if __name__ == '__main__':
    test_live()
