""" PlotWidget with matlab color scheme and CustomPlotItem.
"""
from __future__ import annotations

from pyqtgraph import PlotWidget


class Figure(PlotWidget):
    """ PlotWidget with matlab color scheme and custom plot item. """

    def __init__(self, *args, **kwargs):
        if 'plotItem' not in kwargs:
            from xarray_graph.graph.Plot import Plot
            kwargs['plotItem'] = Plot()
        PlotWidget.__init__(self, *args, **kwargs)

        # MATLAB color scheme
        from qtpy.QtGui import QColor
        self.setBackground(QColor(240, 240, 240))

        import platform
        if platform.system() == 'Darwin':
            # Fix error message due to touch events on MacOS trackpad.
            # !!! Warning: This may break touch events on a touch screen or mobile device.
            # See https://bugreports.qt.io/browse/QTBUG-103935
            for view in self.scene().views():
                from qtpy.QtCore import Qt
                view.viewport().setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, False)
