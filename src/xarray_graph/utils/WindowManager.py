""" PyQt QMainWindow manager.

TODO:
"""

from __future__ import annotations
from qtpy.QtCore import QObject, QEvent, Slot, QSignalBlocker
from qtpy.QtGui import QAction
from qtpy.QtWidgets import QMainWindow, QMenu, QActionGroup, QApplication
import qtawesome as qta


class WindowManager(QObject):
    """ PyQt QMainWindow manager.
    """

    def __init__(self):
        super().__init__()

        # global dict for of all windows keyed on their unique window titles
        self._windows: list[QMainWindow] = []

        # event filter for managed windows
        self._window_event_filter: QObject = WindowEventFilter(self)

        # options
        self._remove_window_on_close = True
        self._enforce_unique_window_titles = True
        self._manage_window_menus = True
    
    def windows(self) -> list[QMainWindow]:
        return self._windows
    
    def setWindows(self, windows: list[QMainWindow]) -> None:
        self._windows = windows
        if self.manageWindowMenus():
            self.updateAllWindowMenus()
    
    def windowTitles(self) -> list[str]:
        return [window.windowTitle() for window in self._windows]
    
    def windowEventFilter(self) -> QObject:
        return self._window_event_filter
    
    def insertWindow(self, index: int, window: QMainWindow) -> None:
        windows = self.windows()
        if window in windows:
            # already in manager
            return
        
        if self.enforceUniqueWindowTitles():
            title = window.windowTitle()
            unique_title = self.uniqueName(title, self.windowTitles())
            if unique_title != title:
                window.setWindowTitle(unique_title)
        
        windows.insert(index, window)
        window.installEventFilter(self.windowEventFilter())
        if self.manageWindowMenus():
            window._window_menu = self.createWindowMenu()
            self.updateAllWindowMenus()
    
    def addWindow(self, window: QMainWindow) -> None:
        windows = self.windows()
        self.insertWindow(len(windows), window)
    
    def removeWindow(self, window: QMainWindow) -> None:
        windows = self.windows()
        windows.remove(window)
    
    def selectWindow(self, window: QMainWindow) -> None:
        window.show()
        window.raise_()
        window.activateWindow()
    
    def removeWindowOnClose(self) -> bool:
        return self._remove_window_on_close
    
    def setRemoveWindowOnClose(self, remove_on_close: bool) -> None:
        self._remove_window_on_close = remove_on_close
    
    def enforceUniqueWindowTitles(self) -> bool:
        return self._enforce_unique_window_titles
    
    def setEnforceUniqueWindowTitles(self, enforce: bool) -> None:
        self._enforce_unique_window_titles = enforce
    
    def manageWindowMenus(self) -> bool:
        return self._manage_window_menus
    
    def setManageWindowMenus(self, manage_menus: bool) -> None:
        self._manage_window_menus = manage_menus
        if manage_menus:
            self.updateAllWindowMenus()
    
    def createWindowMenu(self) -> QMenu:
        menu = QMenu('Window')

        bring_all_to_front_action = QAction(
            parent=menu,
            text='Bring All to Front',
            icon=qta.icon('ph.stack'),
            iconVisibleInMenu=True,
            triggered=lambda checked, mgr=self: mgr.bringAllVisibleWindowsToFront()
        )
        menu.addAction(bring_all_to_front_action)

        # show list of managed windows at end of menu
        menu._before_windows_action = menu.addSeparator()
        menu._windows_action_group = QActionGroup(menu)
        menu._windows_action_group.setExclusive(True)

        self.updateWindowMenu(menu)
        return menu

    def updateWindowMenu(self, menu: QMenu) -> None:
        """ Update window menu with list of managed windows.
        """
        active_window: QMainWindow = QApplication.instance().activeWindow()
        
        # clear old window list from menu
        windows_action_group: QActionGroup = menu._windows_action_group
        for action in windows_action_group.actions():
            windows_action_group.removeAction(action)
            menu.removeAction(action)
        
        # add current window list to menu
        for window in self.windows():
            action = QAction(
                text=window.windowTitle() or 'Untitled',
                icon=qta.icon('ph.app-window'),
                checkable=True,
                checked=window is active_window,
                triggered=lambda checked, mgr=self, window=window: mgr.selectWindow(window))
            windows_action_group.addAction(action)
            menu.addAction(action)
    
    def updateAllWindowMenus(self) -> None:
        for window in self.windows():
            menu: QMenu = getattr(window, '_window_menu', None)
            if menu is None:
                continue
            self.updateWindowMenu(menu)
    
    def bringAllVisibleWindowsToFront(self) -> None:
        # raise all visible windows
        for window in self.windows():
            if window.isVisible():
                window.raise_()
        
        # ensure active window is on top
        active_window: QMainWindow = QApplication.instance().activeWindow()
        if active_window in self.windows():
            active_window.raise_()
    
    @Slot(str)
    def windowTitleChanged(self, title: str) -> None:
        if self.enforceUniqueWindowTitles():
            window: QMainWindow = self.sender()
            other_windows = [win for win in self.windows() if win is not window]
            other_titles = [win.windowTitle() for win in other_windows]
            unique_title = self.uniqueName(title, other_titles)
            if unique_title != title:
                with QSignalBlocker(window):
                    window.setWindowTitle(unique_title)
        if self.manageWindowMenus():
            self.updateAllWindowMenus()

    @Slot()
    def activeWindowChanged(self) -> None:
        if self.manageWindowMenus():
            self.updateAllWindowMenus()
    
    @staticmethod
    def uniqueName(name: str, names: list[str], unique_counter_start: int = 1) -> str:
        """ Return name_1, or name_2, etc. until a unique name is found that does not exist in names.
        """
        if name not in names:
            return name
        base_name = name
        i = unique_counter_start
        name = f'{base_name}_{i}'
        while name in names:
            i += 1
            name = f'{base_name}_{i}'
        return name
    

class WindowEventFilter(QObject):

    def __init__(self, window_manager: WindowManager):
        super().__init__()
        self._window_manager = window_manager

    def eventFilter(self, window: QMainWindow, event: QEvent):
        if event.type() == QEvent.ActivationChange:
            window.changeEvent(event)
            self._window_manager.activeWindowChanged()
            return True
        elif event.type() == QEvent.Close:
            if self._window_manager.removeWindowOnClose():
                self._window_manager.removeWindow(window)
            window.closeEvent(event)
            return True
        return False


def test_live():
    app = QApplication()
    # app.setQuitOnLastWindowClosed(False)
    mgr = WindowManager()
    window = QMainWindow()
    window2 = QMainWindow()
    mgr.addWindow(window)
    mgr.addWindow(window2)
    window.menuBar().addMenu(window._window_menu)
    window2.menuBar().addMenu(window2._window_menu)
    window.show()
    window2.show()
    app.exec()


if __name__ == '__main__':
    test_live()