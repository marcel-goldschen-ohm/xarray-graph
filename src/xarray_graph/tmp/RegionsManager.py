

import numpy as np
import scipy as sp
import lmfit
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
from pyqt_ext import *
from pyqtgraph_ext import *


class AxisRegionsManager():

    def __init__(self):
        self.regions: list[dict] = []
        self.plots: list[Plot] = []
    
    def update_plots_from_regions(self):
        for plot in self.plots:
            view: View = plot.getViewBox()
            items: list[XAxisRegion] = [item for item in view.allChildren() if isinstance(item, XAxisRegion)]
            
            for item in view.allChildren():
                if isinstance(item, XAxisRegion):
                    view.removeItem(item)
            for region in self.regions:
                self.add_region(region)
    
    def add_region(self, region: dict) -> None:
        if region not in self.regions:
            self.regions.append(region)
        for plot in self.plots:
            view: View = plot.getViewBox()
            item = XAxisRegion(region.get('region', [0, 0]))
            item.setText(region.get('text', ''))
            item.setLabel(region.get('label', ''))
            item.setIsMovable(region.get('moveable', True))
            region['color'] = toColorStr(item.brush.color())
            region['line_color'] = toColorStr(item.pen.color())
            item._data = region
            view.addItem(item)
            item.setFontSize(self._textitem_fontsize_spinbox.value())
            # editing the region text via the popup dialog will also reset the region,
            # so this will cover changes to text and label region properties too
            item.sigRegionChangeFinished.connect(self._on_region_item_changed)
    
    def update_item(self, item: XAxisRegion):
        pass

    def update_region_from_item(self, item: XAxisRegion):
        pass