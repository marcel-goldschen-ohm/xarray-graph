""" PlotItem with matlab color scheme and CustomViewBox.
"""
from __future__ import annotations

from qtpy.QtGui import QColor
from pyqtgraph.graphicsItems.PlotItem import PlotItem
from xarray_graph.graph.View import View


class Plot(PlotItem):
    """ PlotItem with matlab color scheme and custom ViewBox.
    
    !!! If you provide a viewBox during instantiation,
        it will be replaced with a new ViewBox instance.
        To get the valid viewBox reference after plot creation,
        use `self.getViewBox()`.
    """

    def __init__(self, *args, **kwargs):
        if 'viewBox' not in kwargs:
            kwargs['viewBox'] = View()
        if 'pen' not in kwargs:
            # MATLAB color scheme
            from pyqtgraph import mkPen
            kwargs['pen'] = mkPen(QColor.fromRgbF(0.15, 0.15, 0.15), width=1)
        PlotItem.__init__(self, *args, **kwargs)

        # MATLAB color scheme
        for axis in ['left', 'bottom', 'right', 'top']:
            from pyqtgraph import AxisItem
            axis_item: AxisItem = self.getAxis(axis)
            if axis_item is not None:
                axis_item.setTextPen(QColor.fromRgbF(0.15, 0.15, 0.15))
