""" ViewBox with matlab color scheme and context menu for drawing ROIs and events.
"""
from __future__ import annotations

from typing import cast
from qtpy.QtCore import Signal  # type: ignore
from qtpy.QtCore import Qt, QPointF
from qtpy.QtGui import QColor
from qtpy.QtWidgets import QGraphicsObject, QGraphicsSceneMouseEvent
from pyqtgraph.graphicsItems.ViewBox import ViewBox
# from pyqtgraph import RectROI, EllipseROI, CircleROI, LineSegmentROI, PlotDataItem, Point
from xarray_graph.graph.AxisRegion import XAxisRegion, YAxisRegion
from xarray_graph.graph.InfLine import VLine, HLine


class View(ViewBox):
    """ ViewBox with context menu for drawing ROIs and events.
    """

    sigStartedDrawingItems = Signal()
    sigItemAdded = Signal(QGraphicsObject)  # emits the newly added QGraphicsObject item
    sigFinishedDrawingItems = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._lastMousePressPosInAxesCoords: dict[Qt.MouseButton, QPointF] = {}  # dict keys are mouse buttons
        self._drawingItemsOfType = None
        self._itemBeingDrawn = None

        # MATLAB color scheme
        self.setBackgroundColor(QColor(255, 255, 255))
    
    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        # store mouse press position in axes coords
        posInAxesCoords = cast(QPointF, self.mapSceneToView(self.mapToScene(event.pos())))
        self._lastMousePressPosInAxesCoords[event.button()] = posInAxesCoords

        if event.button() == Qt.MouseButton.LeftButton:
            # start drawing a new item?
            newItem = None
            if self._drawingItemsOfType is not None:
                if self._drawingItemsOfType == XAxisRegion:
                    limits = [posInAxesCoords.x(), posInAxesCoords.x()]
                    newItem = XAxisRegion(values=limits)
                elif self._drawingItemsOfType == YAxisRegion:
                    limits = [posInAxesCoords.y(), posInAxesCoords.y()]
                    newItem = YAxisRegion(values=limits)
                elif self._drawingItemsOfType == VLine:
                    newItem = VLine(pos=posInAxesCoords.x())
                elif self._drawingItemsOfType == HLine:
                    newItem = HLine(pos=posInAxesCoords.y())
                # elif self._drawingItemsOfType in [RectROI, EllipseROI, CircleROI, LineSegmentROI]:
                #     newItem = self._drawingItemsOfType(pos=posInAxesCoords, size=[0, 0], invertible=True)
                # elif issubclass(self._drawingItemsOfType, PlotDataItem):
                #     if isinstance(self._itemBeingDrawn, PlotDataItem):
                #         # add point to existing Graph
                #         import numpy as np
                #         x, y = self._itemBeingDrawn.getOriginalDataset()
                #         if isinstance(x, np.ndarray) and isinstance(y, np.ndarray):
                #             x = np.append(x, posInAxesCoords.x())
                #             y = np.append(y, posInAxesCoords.y())
                #             self._itemBeingDrawn.setData(x, y)
                #         event.accept()
                #         return
                #     else:
                #         newItem = cast(PlotDataItem, self._drawingItemsOfType())
                #         newItem.setData([posInAxesCoords.x()], [posInAxesCoords.y()])
                if newItem is not None:
                    self._itemBeingDrawn = newItem
                    self.addItem(self._itemBeingDrawn)
                    event.accept()
                    return
        
        # default if event was not handled above
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            # finished drawing region/event?
            if  self._itemBeingDrawn is not None:
                self.sigItemAdded.emit(self._itemBeingDrawn)
                self._itemBeingDrawn = None
                event.accept()
                return
        
        # default if event was not handled above
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        if event.buttons() & Qt.MouseButton.LeftButton:
            # drawing region?
            if self._itemBeingDrawn is not None:
                startPosInAxesCoords = self._lastMousePressPosInAxesCoords[Qt.MouseButton.LeftButton]
                posInAxesCoords = self.mapSceneToView(self.mapToScene(event.pos()))
                if isinstance(self._itemBeingDrawn, XAxisRegion):
                    limits = sorted([startPosInAxesCoords.x(), posInAxesCoords.x()])
                    self._itemBeingDrawn.setRegion(limits)
                elif isinstance(self._itemBeingDrawn, YAxisRegion):
                    limits = sorted([startPosInAxesCoords.y(), posInAxesCoords.y()])
                    self._itemBeingDrawn.setRegion(limits)
                elif isinstance(self._itemBeingDrawn, VLine):
                    self._itemBeingDrawn.setPos(posInAxesCoords.x())
                elif isinstance(self._itemBeingDrawn, HLine):
                    self._itemBeingDrawn.setPos(posInAxesCoords.y())
                # elif isinstance(self._itemBeingDrawn, (RectROI, EllipseROI, CircleROI)):
                #     self._itemBeingDrawn.setSize(posInAxesCoords - self._itemBeingDrawn.pos())
                # elif isinstance(self._itemBeingDrawn, LineSegmentROI):
                #     state = self._itemBeingDrawn.getState()
                #     state['points'] = [Point(startPosInAxesCoords), Point(posInAxesCoords)]
                #     self._itemBeingDrawn.setState(state)
                event.accept()
                return
        
        # default if event was not handled above
        super().mouseMoveEvent(event)
    
    def startDrawingItemsOfType(self, itemType):
        self._itemBeingDrawn = None
        self._drawingItemsOfType = itemType
        self.sigStartedDrawingItems.emit()
    
    def stopDrawingItems(self):
        self._drawingItemsOfType = None
        self._itemBeingDrawn = None
        self.sigFinishedDrawingItems.emit()


def test_live():
    from qtpy.QtWidgets import QApplication
    app = QApplication()

    from xarray_graph.graph.Figure import Figure
    fig = Figure()

    from xarray_graph.graph.Plot import Plot
    plot = fig.getPlotItem()
    assert isinstance(plot, Plot)

    view = plot.getViewBox()
    assert isinstance(view, View)

    import numpy as np
    from pyqtgraph import PlotDataItem
    item = PlotDataItem(y=np.random.randn(1000))
    plot.addItem(item)
    plot.setWindowTitle('pyqtgraph-tools')
    fig.show()

    view.startDrawingItemsOfType(XAxisRegion)
    # view.startDrawingItemsOfType(YAxisRegion)
    # view.startDrawingItemsOfType(VLine)
    # view.startDrawingItemsOfType(HLine)
    # view.startDrawingItemsOfType(RectROI)
    # view.startDrawingItemsOfType(EllipseROI)
    # view.startDrawingItemsOfType(CircleROI)
    # view.startDrawingItemsOfType(LineSegmentROI)
    from qtpy.QtCore import QTimer
    QTimer.singleShot(3000, lambda: view.stopDrawingItems())

    def set_text():
        region_items = [item for item in view.allChildren() if isinstance(item, XAxisRegion)]
        for region in region_items:
            region.setText("Test")

    QTimer.singleShot(3100, set_text)

    app.exec()


if __name__ == '__main__':
    from xarray_graph.graph.View import test_live
    test_live()
