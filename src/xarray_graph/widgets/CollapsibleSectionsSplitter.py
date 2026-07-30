""" PyQt widget emulating a list of collapsible views like in VSCode sidebar (e.g., explorer, outline).

TODO:
- expand/collapse in response to dragging handle?
"""
from __future__ import annotations

from qtpy.QtCore import Qt, Signal, QRect
from qtpy.QtWidgets import QSplitter, QSplitterHandle

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from qtpy.QtGui import QMouseEvent, QPaintEvent
    from qtpy.QtWidgets import QWidget, QAction


class CollapsibleSectionsSplitter(QSplitter):

    sectionIsExpandedChanged = Signal(int, bool)  # index, expanded

    def __init__(self, *args, **kwargs):
        if 'orientation' not in kwargs:
            kwargs['orientation'] = Qt.Orientation.Vertical
        super().__init__(*args, **kwargs)

        # set handle width to height of QToolButton with text beside icon
        from qtpy.QtWidgets import QToolButton, QStyleOptionToolButton
        button = QToolButton(toolButtonStyle=Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        opt = QStyleOptionToolButton()
        button.initStyleOption(opt)
        self.setHandleWidth(opt.fontMetrics.height())

        # the first widget is a spacer to allow the first section to be collapsed, so that the first section can be expanded/collapsed like all other sections
        from qtpy.QtWidgets import QWidget, QSizePolicy
        self._begin_spacer = QWidget()
        if self.orientation() == Qt.Orientation.Vertical:
            self._begin_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._begin_spacer.setFixedHeight(0)
        elif self.orientation() == Qt.Orientation.Horizontal:
            self._begin_spacer.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
            self._begin_spacer.setFixedWidth(0)
        self.addWidget(self._begin_spacer)

        # the first section (index 0) is reserved for the initial spacer, so the first actual section has index 1
        self._sections: list[dict] = [{
            'title': None,
            'spacer': self._begin_spacer,
            'widget': None,
            'actions': None
        }]

        from qtawesome import icon as qta_icon
        if self.orientation() == Qt.Orientation.Vertical:
            self._collapsed_icon = qta_icon('msc.chevron-right')
            self._expanded_icon = qta_icon('msc.chevron-down')
        elif self.orientation() == Qt.Orientation.Horizontal:
            self._collapsed_icon = qta_icon('msc.chevron-up')
            self._expanded_icon = qta_icon('msc.chevron-right')
        self._focus_icon = qta_icon('ri.fullscreen-line')
        self._unfocus_icon = qta_icon('ri.fullscreen-exit-line')

    def _validateIndex(self, index: int):
        if index < 1:
            raise IndexError('The first section has index 1 (index 0 is reserved for the initial spacer).')
        if index >= self.count():
            raise IndexError(f'Index {index} is out of range (count={self.count()}).')
    
    def addSection(self, title: str, widget: QWidget):
        self.insertSection(self.count(), title, widget)
    
    def insertSection(self, index: int, title: str, widget: QWidget):
        if index < 1:
            raise IndexError('The first section has index 1 (index 0 is reserved for the initial spacer).')
        if index > self.count():
            raise IndexError(f'Index {index} is out of range (count={self.count()}).')
        
        self.insertWidget(index, widget)

        # create a spacer widget to replace the section widget when collapsed
        from qtpy.QtWidgets import QWidget, QSizePolicy
        spacer = QWidget()
        if self.orientation() == Qt.Orientation.Vertical:
            spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            spacer.setFixedHeight(0)
        elif self.orientation() == Qt.Orientation.Horizontal:
            spacer.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
            spacer.setFixedWidth(0)

        self._sections.insert(index, {
            'title': title,
            'spacer': spacer,
            'widget': widget,
            'actions': None
        })

    def removeSection(self, index: int):
        self._validateIndex(index)

        # remove the section widget (or spacer if section is collapsed) from the splitter
        current_widget = self.widget(index)
        current_widget.setParent(None)

        self._sections.pop(index)
    
    def sectionIndex(self, title_or_widget: str | QWidget) -> int:
        if isinstance(title_or_widget, str):
            title: str = title_or_widget
            for i in range(1, self.count()):
                if self._sections[i]['title'] == title:
                    return i
            return None
        from qtpy.QtWidgets import QWidget
        if isinstance(title_or_widget, QWidget):
            # do NOT use self.indexOf(widget) because it returns the index of the widget in the splitter, which may be a spacer if the section is collapsed
            widget: QWidget = title_or_widget
            for i in range(1, self.count()):
                if self._sections[i]['widget'] is widget:
                    return i
            return None
    
    def sectionTitle(self, index: int) -> QWidget:
        self._validateIndex(index)
        return self._sections[index]['title']

    def setSectionTitle(self, index: int, title: str):
        self._validateIndex(index)
        self._sections[index]['title'] = title
        self.update()
    
    def sectionWidget(self, index: int) -> QWidget:
        self._validateIndex(index)
        return self._sections[index]['widget']

    def setSectionWidget(self, index: int, widget: QWidget):
        self._validateIndex(index)
        section: dict = self._sections[index]
        current_widget: QWidget = self.widget(index)
        if current_widget is section['widget']:
            # section is expanded, so replace the widget in the splitter
            current_widget.setParent(None)
            self.insertWidget(index, widget)
        section['widget'] = widget
        self.update()

    def sectionActions(self, index: int) -> list[QAction]:
        self._validateIndex(index)
        return self._sections[index]['actions']

    def setSectionActions(self, index: int, actions: list[QAction]):
        self._validateIndex(index)
        self._sections[index]['actions'] = actions
        self.update()
    
    def isSectionExpanded(self, index: int) -> bool:
        self._validateIndex(index)
        current_widget: QWidget = self.widget(index)
        return current_widget is self._sections[index]['widget']
    
    def setSectionExpanded(self, index: int, expanded: bool):
        self._validateIndex(index)
        section: dict = self._sections[index]
        
        current_widget: QWidget = self.widget(index)
        if expanded:
            if current_widget is section['spacer']:
                # expand by replacing spacer with widget
                current_widget.setParent(None)
                self.insertWidget(index, section['widget'])
                self.sectionIsExpandedChanged.emit(index, True)
        else:
            if current_widget is section['widget']:
                # collapse by replacing widget with spacer
                current_widget.setParent(None)
                self.insertWidget(index, section['spacer'])
                self.sectionIsExpandedChanged.emit(index, False)
    
    def isSectionVisible(self, index: int) -> bool:
        self._validateIndex(index)
        widget: QWidget = self.widget(index)
        return widget.isVisible()
    
    def setSectionVisible(self, index: int, visible: bool):
        self._validateIndex(index)
        widget: QWidget = self.widget(index)
        widget.setVisible(visible)
    
    def focusSection(self, index: int):
        self._validateIndex(index)

        # check if a section is focused
        is_focused: bool = getattr(self, '_focused_index', None) is not None

        # store the expanded state of all sections before focusing, so that we can restore it when unfocusing
        if is_focused:
            # expanded state array should alredy exist, so just update the focused section to expanded
            self._expanded_state[index] = True
        else:
            # first None is for the initial spacer, which is not a section and should not be expanded/collapsed
            self._expanded_state = [None] + [self.isSectionExpanded(i) for i in range(1, self.count())]

        # collapse all sections except the focused one
        for i in range(1, self.count()):
            self.setSectionExpanded(i, i == index)

        # store the focused index
        self._focused_index: int = index

        # force repaint of handles (primarily for first handle which otherwise may not repaint)
        self.update()
    
    def unfocusSection(self):
        # check if a section is focused
        focused_index: int =  getattr(self, '_focused_index', None)
        if focused_index is None:
            return

        # restore the expanded state of all sections before focusing
        for i in range(1, self.count()):
            self.setSectionExpanded(i, self._expanded_state[i])

        # clear the focused index
        self._focused_index = None

        # force repaint of handles (primarily for first handle which otherwise may not repaint)
        self.update()
    
    def firstSectionHeaderVisible(self) -> bool:
        return self._begin_spacer.isVisible()
    
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
            # focus icon
            focus_icon_rect: QRect = self._focus_icon_rect()
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
                    splitter.focusSection(index)
                # clear last press info to avoid toggling expand/collapse as well
                self._last_press_position = None
                self._last_press_time_sec = None
                return

            # custom actions icons
            splitter: CollapsibleSectionsSplitter = self.splitter()
            index: int = splitter.indexOf(self)
            section: dict = splitter._sections[index]
            n_actions: int = len(section['actions']) if section['actions'] is not None else 0
            if n_actions > 0:
                custom_icons_rect: QRect = self._custom_icons_rect(n_actions)
                if custom_icons_rect.contains(event.pos()):
                    if self.orientation() == Qt.Orientation.Vertical:
                        action_index: int = (event.pos().x() - custom_icons_rect.left()) // self.height()
                    elif self.orientation() == Qt.Orientation.Horizontal:
                        action_index: int = (custom_icons_rect.bottom() - event.pos().y()) // self.width()
                    action: QAction = section['actions'][action_index]
                    action.trigger()
                    return
            
            # store press position and time
            import time
            from qtpy.QtCore import QPoint
            self._last_press_position: QPoint = event.pos()
            self._last_press_time_sec: float = time.time()

        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event: QMouseEvent):
        super().mouseMoveEvent(event)

        # check if mouse over a button-like icon in handle and set cursor accordingly

        # expand/collapse icon
        expanded_icon_rect: QRect = self._expand_collapse_icon_rect()
        if expanded_icon_rect.contains(event.pos()):
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        # focus icon
        focus_icon_rect: QRect = self._focus_icon_rect()
        if focus_icon_rect.contains(event.pos()):
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        
        # custom actions icons
        splitter: CollapsibleSectionsSplitter = self.splitter()
        index: int = splitter.indexOf(self)
        section: dict = splitter._sections[index]
        n_actions: int = len(section['actions']) if section['actions'] is not None else 0
        if n_actions > 0:
            custom_icons_rect: QRect = self._custom_icons_rect(n_actions)
            if custom_icons_rect.contains(event.pos()):
                self.setCursor(Qt.CursorShape.ArrowCursor)
                return

        # anywhere else in the handle
        self.setCursor(Qt.CursorShape.SplitVCursor if self.orientation() == Qt.Orientation.Vertical else Qt.CursorShape.SplitHCursor)
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        super().mouseReleaseEvent(event)

        if event.button() == Qt.MouseButton.LeftButton:
            # if release is close to press in both space and time, treat as click
            has_last_press_time: bool = hasattr(self, '_last_press_time_sec') and self._last_press_time_sec is not None
            if not has_last_press_time:
                return
            import time, math
            from qtpy.QtCore import QPoint
            delta_time_sec: float = time.time() - self._last_press_time_sec
            if delta_time_sec <= self._click_time_sec:
                delta_position: QPoint = event.pos() - self._last_press_position
                distance: float = math.sqrt(delta_position.x()**2 + delta_position.y()**2)
                if distance <= self._click_radius:
                    # treat as click => toggle section
                    splitter: CollapsibleSectionsSplitter = self.splitter()
                    index: int = splitter.indexOf(self)
                    expanded: bool = not splitter.isSectionExpanded(index)
                    splitter.setSectionExpanded(index, expanded)
                    # if we collapsed the focused section, unfocus it
                    if splitter.isSectionExpanded(index) == False:
                        focused_index: int =  getattr(splitter, '_focused_index', None)
                        if index == focused_index:
                            splitter._expanded_state[index] = False
                            splitter.unfocusSection()
                    splitter.sectionIsExpandedChanged.emit(index, expanded)
    
    def paintEvent(self, event: QPaintEvent):
        splitter: CollapsibleSectionsSplitter = self.splitter()
        index: int = splitter.indexOf(self)
        section: dict = splitter._sections[index]
        rect: QRect = self.rect()

        # QToolButton style options
        from qtpy.QtWidgets import QToolButton, QStyleOptionToolButton
        button = QToolButton()
        opt = QStyleOptionToolButton()
        button.initStyleOption(opt)
        opt.rect = rect

        # QToolButton background
        from qtpy.QtWidgets import QStylePainter, QStyle
        painter = QStylePainter(self)
        painter.drawComplexControl(QStyle.CC_ToolButton, opt)

        from qtpy.QtGui import QIcon, QPixmap

        # expand/collapse icon
        bbox: QRect = self._expand_collapse_icon_rect()
        is_expanded: bool = splitter.widget(index) is section['widget']
        icon: QIcon = splitter._expanded_icon if is_expanded else splitter._collapsed_icon
        pixmap: QPixmap = icon.pixmap(bbox.size(), QIcon.Mode.Normal, QIcon.State.On)
        painter.drawPixmap(bbox.left(), bbox.top(), pixmap)

        # focus section icon
        bbox: QRect = self._focus_icon_rect()
        is_focused: bool = index == getattr(splitter, '_focused_index', None)
        icon: QIcon = splitter._unfocus_icon if is_focused else splitter._focus_icon
        pixmap: QPixmap = icon.pixmap(bbox.size(), QIcon.Mode.Normal, QIcon.State.On)
        painter.drawPixmap(bbox.left(), bbox.top(), pixmap)

        # custom actions icons
        n_actions: int = len(section['actions']) if section['actions'] is not None else 0
        if n_actions > 0:
            action: QAction
            for i, action in enumerate(section['actions'] or []):
                bbox: QRect = self._custom_icon_rect(i, n_actions)
                icon: QIcon = action.icon()
                pixmap: QPixmap = icon.pixmap(bbox.size(), QIcon.Mode.Normal, QIcon.State.On)
                painter.drawPixmap(bbox.left(), bbox.top(), pixmap)

        # title
        font = painter.font()
        if self.orientation() == Qt.Orientation.Vertical:
            font.setPixelSize(rect.height() - 4)
            painter.setFont(font)
            painter.drawText(rect.adjusted(rect.height() + 5, 0, -rect.height() - 5, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, section['title'])
        elif self.orientation() == Qt.Orientation.Horizontal:
            font.setPixelSize(rect.width() - 4)
            painter.setFont(font)
            painter.save()
            painter.translate(rect.right(), rect.bottom() - rect.width() - 5)
            # painter.setBrush(Qt.GlobalColor.red)
            # painter.drawRect(QRect(-5, -5, 10, 10))
            painter.rotate(-90)
            # painter.setBrush(Qt.GlobalColor.red)
            # painter.drawRect(QRect(0, -rect.width(), rect.height(), rect.width()))
            painter.drawText(QRect(0, -rect.width(), rect.height(), rect.width()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, section['title'])
            # painter.drawText(0, 0, section['title'])
            painter.restore()
    
    def _expand_collapse_icon_rect(self) -> QRect:
        rect: QRect = self.rect()
        if self.orientation() == Qt.Orientation.Vertical:
            return QRect(rect.left(), rect.top(), rect.height(), rect.height())
        elif self.orientation() == Qt.Orientation.Horizontal:
            return QRect(rect.left(), rect.bottom() - rect.width(), rect.width(), rect.width())
    
    def _focus_icon_rect(self) -> QRect:
        rect: QRect = self.rect()
        if self.orientation() == Qt.Orientation.Vertical:
            return QRect(rect.right() - rect.height(), rect.top(), rect.height(), rect.height())
        elif self.orientation() == Qt.Orientation.Horizontal:
            return QRect(rect.left(), rect.top(), rect.width(), rect.width())
    
    def _custom_icons_rect(self, n_icons: int) -> QRect:
        rect: QRect = self.rect()
        if self.orientation() == Qt.Orientation.Vertical:
            return QRect(rect.right() - rect.height() * (n_icons + 1), rect.top(), rect.height() * n_icons, rect.height())
        elif self.orientation() == Qt.Orientation.Horizontal:
            return QRect(rect.left(), rect.top() + rect.width(), rect.width(), rect.width() * n_icons)
    
    def _custom_icon_rect(self, index: int, n_icons: int) -> QRect:
        rect: QRect = self.rect()
        if self.orientation() == Qt.Orientation.Vertical:
            return QRect(rect.right() - rect.height() * (n_icons - index + 1), rect.top(), rect.height(), rect.height())
        elif self.orientation() == Qt.Orientation.Horizontal:
            return QRect(rect.left(), rect.top() + rect.width() * (n_icons - index), rect.width(), rect.width())


def test_live():
    from qtpy.QtWidgets import QApplication, QTableView, QTreeView, QListView, QPushButton, QAction
    app = QApplication()

    ui = CollapsibleSectionsSplitter()#(orientation=Qt.Orientation.Horizontal)
    table = QTableView()
    ui.addSection('tree', QTreeView())
    ui.addSection('table', table)
    ui.addSection('list', QListView())
    ui.addSection('button', QPushButton('click me'))
    ui.addSection('try', QTreeView())
    ui.addSection('button', QPushButton('click me too'))
    # ui.removeSection(1)
    print('index of "table":', ui.indexOf(table))
    ui.setFirstSectionHeaderVisible(False)
    print('index of "table":', ui.indexOf(table))

    from qtawesome import icon as qta_icon
    actions = [QAction(qta_icon('fa5s.plus'), 'Add', triggered=lambda: print('Add')), QAction(qta_icon('fa5s.minus'), 'Remove', triggered=lambda: print('Remove'))]
    index = ui.sectionIndex('list')
    ui.setSectionActions(index, actions)
    
    ui.show()
    app.exec()


if __name__ == '__main__':
    test_live()