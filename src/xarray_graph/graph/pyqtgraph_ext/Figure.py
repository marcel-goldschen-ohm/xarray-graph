""" PlotWidget with matlab color scheme and CustomPlotItem.
"""

from __future__ import annotations
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import pyqtgraph as pg
from xarray_graph.graph.pyqtgraph_ext import Plot
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


def test_live():
    import numpy as np
    import xarray_graph.graph.pyqtgraph_ext as pgx
    app = QApplication()
    plot = pgx.Figure()
    view: pgx.View = plot.getViewBox()
    for i in range(3):
        line = pgx.Graph(y=np.random.randn(10), pen=pg.mkPen(color=view.nextColor(), width=3))
        plot.addItem(line)
    plot.setWindowTitle('pyqtgraph-tools')
    plot.show()
    # view.startDrawingItemsOfType(pgx.XAxisRegion)
    # QTimer.singleShot(2000, lambda: view.stopDrawingItems())
    app.exec()


if __name__ == '__main__':
    test_live()
