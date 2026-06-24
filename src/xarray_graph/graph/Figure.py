""" PlotWidget with matlab color scheme and CustomPlotItem.
"""

from __future__ import annotations
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import pyqtgraph as pg
from xarray_graph.graph import Plot
import platform


class Figure(pg.PlotWidget):
    """ PlotWidget with matlab color scheme and CustomPlotItem. """

    def __init__(self, *args, **kwargs):
        if 'plotItem' not in kwargs:
            kwargs['plotItem'] = Plot()
        pg.PlotWidget.__init__(self, *args, **kwargs)

        # MATLAB color scheme
        self.setBackground(QColor(240, 240, 240))

        if platform.system() == 'Darwin':
            # Fix error message due to touch events on MacOS trackpad.
            # !!! Warning: This may break touch events on a touch screen or mobile device.
            # See https://bugreports.qt.io/browse/QTBUG-103935
            for view in self.scene().views():
                view.viewport().setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, False)
