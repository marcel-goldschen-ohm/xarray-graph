""" PyQt widget emulating a list of collapsible views like in VSCode sidebar (e.g., explorer, outline).
"""

from __future__ import annotations
import time, math
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta


class CollapsibleSectionsSplitter(QSplitter):

    def __init__(self):
        super().__init__(orientation=Qt.Orientation.Vertical)

        # set handle width to height of QToolButton with text beside icon
        button = QToolButton(toolButtonStyle=Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        opt = QStyleOptionToolButton()
        button.initStyleOption(opt)
        self.setHandleWidth(opt.fontMetrics.height())

        self._begin_spacer = QWidget()
        self._begin_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._begin_spacer.setFixedHeight(0)
        self.addWidget(self._begin_spacer)

        self._widgets: list[QWidget] = [None]
        self._titles: list[str] = [None]
        self._spacers: list[QWidget] = [self._begin_spacer]

        self._collapsed_icon = qta.icon('msc.chevron-right')
        self._expanded_icon = qta.icon('msc.chevron-down')
        self._focus_icon = qta.icon('ri.fullscreen-line')
        self._unfocus_icon = qta.icon('ri.fullscreen-exit-line')
    
    def addSection(self, title: str, widget: QWidget):
        self.insertSection(self.count() - 1, title, widget)
    
    def insertSection(self, index: int, title: str, widget: QWidget):
        index += 1  # account for initial spacer
        self.insertWidget(index, widget)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        spacer.setFixedHeight(0)

        self._widgets.insert(index, widget)
        self._titles.insert(index, title)
        self._spacers.insert(index, spacer)
    
    def removeSection(self, index: int):
        index += 1  # account for initial spacer

        current_widget = self.widget(index)
        current_widget.setParent(None)

        self._widgets.pop(index)
        self._titles.pop(index)
        self._spacers.pop(index)
    
    def isExpanded(self, index: int) -> bool:
        index += 1  # account for initial spacer
        current_widget: QWidget = self.widget(index)
        return current_widget is self._widgets[index]
    
    def setExpanded(self, index: int, expanded: bool):
        index += 1  # account for initial spacer
        current_widget: QWidget = self.widget(index)
        if expanded:
            if current_widget is self._spacers[index]:
                # toggle on by replacing spacer with widget
                current_widget.setParent(None)
                self.insertWidget(index, self._widgets[index])
        else:
            if current_widget is self._widgets[index]:
                # toggle off by replacing widget with spacer
                current_widget.setParent(None)
                self.insertWidget(index, self._spacers[index])
    
    def toggleExpanded(self, index: int):
        index += 1  # account for initial spacer
        current_widget: QWidget = self.widget(index)
        if current_widget is self._widgets[index]:
            # toggle off by replacing widget with spacer
            current_widget.setParent(None)
            self.insertWidget(index, self._spacers[index])
        else:
            # toggle on by replacing spacer with widget
            current_widget.setParent(None)
            self.insertWidget(index, self._widgets[index])
    
    def focusSection(self, index: int):
        index += 1  # account for initial spacer
        is_focused: bool = getattr(self, '_focused_index', None) is not None
        if is_focused:
            self._expanded_state[index] = True
        else:
            self._expanded_state = [None] # for initial spacer
        for i in range(self.count() - 1):
            if not is_focused:
                self._expanded_state.append(self.isExpanded(i))
            self.setExpanded(i, i + 1 == index)
        self._focused_index: int = index
        self.update() # force repaint of handles (primarily for first handle which otherwise may not repaint)
    
    def unfocusSection(self):
        focused_index: int =  getattr(self, '_focused_index', None)
        if focused_index is None:
            return
        for i in range(self.count() - 1):
            self.setExpanded(i, self._expanded_state[i + 1])
        self._focused_index = None
        self.update() # force repaint of handles (primarily for first handle which otherwise may not repaint)
    
    def setFirstSectionHeaderVisible(self, visible: bool):
        self._begin_spacer.setVisible(visible)
    
    def createHandle(self) -> QSplitterHandle:
        return CollapsibleSectionsHandle(self.orientation(), self)


class CollapsibleSectionsHandle(QSplitterHandle):

    _click_radius: float = 2.5
    _click_time_sec: float = 0.25

    def __init__(self, orientation: Qt.Orientation, parent: QSplitter):
        super().__init__(orientation, parent)
        self.setMouseTracking(True)
    
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            focus_icon_rect: QRect = QRect(self.width() - self.height(), 0, self.height(), self.height())
            if focus_icon_rect.contains(event.pos()):
                # toggle fullscreen of section
                splitter: CollapsibleSectionsSplitter = self.splitter()
                index: int = splitter.indexOf(self)
                is_focused: bool = getattr(splitter, '_focused_index', None) == index
                if is_focused:
                    # unfocus: expand all sections
                    splitter.unfocusSection()
                else:
                    # focus this section
                    splitter.focusSection(index - 1)  # account for initial spacer
                # clear last press info to avoid toggling expand/collapse as well
                self._last_press_position = None
                self._last_press_time_sec = None
                return
            # store press position and time
            self._last_press_position: QPoint = event.pos()
            self._last_press_time_sec: float = time.time()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event: QMouseEvent):
        super().mouseMoveEvent(event)
        # check if mouse over a button-like icon in handle and set cursor accordingly
        expanded_icon_rect: QRect = QRect(0, 0, self.height(), self.height())
        focus_icon_rect: QRect = QRect(self.width() - self.height(), 0, self.height(), self.height())
        if expanded_icon_rect.contains(event.pos()):
            self.setCursor(Qt.CursorShape.ArrowCursor)
        elif focus_icon_rect.contains(event.pos()):
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.setCursor(Qt.CursorShape.SplitVCursor if self.orientation() == Qt.Orientation.Vertical else Qt.CursorShape.SplitHCursor)
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            # if release is close to press in both space and time, treat as click
            has_last_press_time: bool = hasattr(self, '_last_press_time_sec') and self._last_press_time_sec is not None
            if not has_last_press_time:
                return
            delta_time_sec: float = time.time() - self._last_press_time_sec
            if delta_time_sec <= self._click_time_sec:
                delta_position: QPoint = event.pos() - self._last_press_position
                distance: float = math.sqrt(delta_position.x()**2 + delta_position.y()**2)
                if distance <= self._click_radius:
                    # treat as click => toggle section
                    splitter: CollapsibleSectionsSplitter = self.splitter()
                    index: int = splitter.indexOf(self)
                    splitter.toggleExpanded(index - 1)  # account for initial spacer
    
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

        # expand/collapse icon
        is_expanded: bool = splitter.widget(index) is splitter._widgets[index]
        if is_expanded:
            icon: QIcon = splitter._expanded_icon
        else:
            icon: QIcon = splitter._collapsed_icon
        icon_size = QSize(rect.height(), rect.height())
        pixmap: QPixmap = icon.pixmap(icon_size, QIcon.Normal, QIcon.On)
        painter.drawPixmap(rect.x(), rect.y(), pixmap)

        # focus section icon
        is_focused: bool = index == getattr(splitter, '_focused_index', None)
        if is_focused:
            icon: QIcon = splitter._unfocus_icon
        else:
            icon: QIcon = splitter._focus_icon
        icon_size = QSize(rect.height(), rect.height())
        pixmap: QPixmap = icon.pixmap(icon_size, QIcon.Normal, QIcon.On)
        painter.drawPixmap(rect.right() - rect.height(), rect.y(), pixmap)

        # title
        font = painter.font()
        font.setPixelSize(rect.height() - 4)
        painter.setFont(font)
        painter.drawText(rect.adjusted(rect.height() + 5, 0, -1, -1), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)


def test_live():
    app = QApplication()

    ui = CollapsibleSectionsSplitter()
    ui.addSection('tree', QTreeView())
    ui.addSection('table', QTableView())
    ui.addSection('list', QListView())
    ui.addSection('button', QPushButton('click me'))
    ui.addSection('try', QTreeView())
    ui.addSection('button', QPushButton('click me too'))
    # ui.setFirstSectionHeaderVisible(False)
    # ui.removeSection(0)
    ui.show()

    app.exec()


if __name__ == '__main__':
    test_live()