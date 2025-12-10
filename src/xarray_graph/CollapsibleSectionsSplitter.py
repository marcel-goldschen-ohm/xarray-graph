""" PyQt widget emulating a list of collapsible views like in VSCode sidebar (e.g., explorer, outline).

TODO:
- optionally remove first handle (remove first spacer)
- query and set expanded/collapsed state of sections
"""

from __future__ import annotations
import time, math
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta


class CollapsibleSectionsSplitter(QSplitter):

    def __init__(self):
        super().__init__(orientation=Qt.Orientation.Vertical, handleWidth=14)

        self._begin_spacer = QWidget()
        self._begin_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._begin_spacer.setFixedHeight(0)
        self.addWidget(self._begin_spacer)

        self._widgets: list[QWidget] = [self._begin_spacer]
        self._titles: list[str] = ['']
        self._spacers: list[QWidget] = [None]

        self._collapsed_icon = qta.icon('msc.chevron-right')
        self._expanded_icon = qta.icon('msc.chevron-down')
    
    def addSection(self, title: str, widget: QWidget):
        index: int = self.count()# - 1
        self.insertWidget(index, widget)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        spacer.setFixedHeight(0)

        self._widgets.insert(index, widget)
        self._titles.insert(index, title)
        self._spacers.insert(index, spacer)
    
    def createHandle(self) -> QSplitterHandle:
        return CollapsibleSectionsHandle(self.orientation(), self)


class CollapsibleSectionsHandle(QSplitterHandle):

    _click_radius: float = 2.5
    _click_time_sec: float = 0.25

    def __init__(self, orientation: Qt.Orientation, parent: QSplitter):
        super().__init__(orientation, parent)
    
    def mousePressEvent(self, event: QMouseEvent):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            # store press position and time
            self._last_press_position: QPoint = event.pos()
            self._last_press_time_sec: float = time.time()
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            # if release is close to press in both space and time, treat as click
            delta_time_sec: float = time.time() - self._last_press_time_sec
            if delta_time_sec <= self._click_time_sec:
                delta_position: QPoint = event.pos() - self._last_press_position
                distance: float = math.sqrt(delta_position.x()**2 + delta_position.y()**2)
                if distance <= self._click_radius:
                    # treat as click => toggle section
                    splitter: CollapsibleSectionsSplitter = self.splitter()
                    index: int = splitter.indexOf(self)
                    # print(index, 'of', tray.count())
                    if splitter._spacers[index] is None:
                        # this is a bookending spacer
                        return
                    current_widget: QWidget = splitter.widget(index)
                    current_widget.setParent(None)
                    if current_widget is splitter._widgets[index]:
                        # toggle off by replacing widget with spacer
                        splitter.insertWidget(index, splitter._spacers[index])
                    else:
                        # toggle on by replacing spacer with widget
                        splitter.insertWidget(index, splitter._widgets[index])
    
    def paintEvent(self, event: QPaintEvent):
        splitter: CollapsibleSectionsSplitter = self.splitter()
        index: int = splitter.indexOf(self)
        title: str = splitter._titles[index]
        rect: QRect = self.rect()

        # QToolButton style options
        button = QToolButton()
        opt = QStyleOptionToolButton()
        button.initStyleOption(opt)
        opt.rect = rect

        # QToolButton background
        painter = QStylePainter(self)
        painter.drawComplexControl(QStyle.CC_ToolButton, opt)

        # icon
        is_expanded: bool = splitter.widget(index) is splitter._widgets[index]
        if is_expanded:
            icon: QIcon = splitter._expanded_icon
        else:
            icon: QIcon = splitter._collapsed_icon
        height: int = splitter.handleWidth()
        icon_size = QSize(height, height)
        pixmap: QPixmap = icon.pixmap(icon_size, QIcon.Normal, QIcon.On)
        painter.drawPixmap(rect.x(), rect.y(), pixmap)

        # title
        font = painter.font()
        font.setPixelSize(rect.height() - 4)
        painter.setFont(font)
        painter.drawText(rect.adjusted(height + 5, 0, -1, -1), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)


def test_live():
    app = QApplication()

    ui = CollapsibleSectionsSplitter()
    ui.addSection('tree', QTreeView())
    ui.addSection('table', QTableView())
    ui.addSection('list', QListView())
    ui.addSection('try', QTreeView())
    ui.show()

    app.exec()


if __name__ == '__main__':
    test_live()