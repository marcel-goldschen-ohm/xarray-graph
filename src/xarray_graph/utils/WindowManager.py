""" PyQt QMainWindow manager.

Manages a list of QMainWindow instances, including a Window menu that lists all managed windows and allows switching between them.

TODO:
- tile/pile windows
"""
from __future__ import annotations

from typing import cast
from qtpy.QtCore import Slot  # type: ignore
from qtpy.QtCore import QObject, QEvent
from qtpy.QtWidgets import QMainWindow, QMenu


class WindowManager[Window: QMainWindow](QObject):
    """ PyQt QMainWindow manager.
    """

    def __init__(self):
        super().__init__()

        # list of managed windows
        self._windows: list[Window] = []

        # event filter for managed windows
        self._window_event_filter: QObject = WindowEventFilter(self)

        # options
        self._remove_window_on_close = True
        self._enforce_unique_window_titles = True
        self._manage_window_menus = True
    
    def windows(self) -> list[Window]:
        return self._windows
    
    def windowTitles(self) -> list[str]:
        return [window.windowTitle() for window in self._windows]
    
    def __getitem__(self, key: str | int) -> Window | None:
        windows = self.windows()
        if isinstance(key, int):
            return windows[key]
        if isinstance(key, str):
            for window in windows:
                if window.windowTitle() == key:
                    return window
    
    def activeWindow(self) -> Window | None:
        from qtpy.QtWidgets import QApplication
        app = cast(QApplication, QApplication.instance())
        active_window = app.activeWindow()
        if active_window is None:
            return None
        if active_window in self.windows():
            return cast(Window, active_window)
    
    def ls(self) -> str:
        return '\n'.join(f'{i}: {window.windowTitle()}' for i, window in enumerate(self.windows()))
    
    def dir(self) -> str:
        return self.ls()
    
    def windowEventFilter(self) -> QObject:
        return self._window_event_filter
    
    def insertWindow(self, index: int, window: Window) -> None:
        windows = self.windows()
        if window in windows:
            # already in manager
            return
        
        if self.enforceUniqueWindowTitles():
            title = window.windowTitle()
            unique_title = self.uniqueName(title or 'Untitled', self.windowTitles())
            if unique_title != title:
                window.setWindowTitle(unique_title)
        
        windows.insert(index, window)
        window.installEventFilter(self.windowEventFilter())
        if self.manageWindowMenus():
            window_menu = self.createWindowMenu()
            setattr(window, '_window_menu', window_menu)
            from qtpy.QtCore import QTimer
            QTimer.singleShot(0, self.updateAllWindowMenus)
    
    def addWindow(self, window: Window) -> None:
        windows = self.windows()
        self.insertWindow(len(windows), window)
    
    def removeWindow(self, window: Window) -> None:
        windows = self.windows()
        if window not in windows:
            # not in manager
            return
        window.removeEventFilter(self.windowEventFilter())
        windows.remove(window)
        if self.manageWindowMenus():
            from qtpy.QtCore import QTimer
            QTimer.singleShot(0, self.updateAllWindowMenus)
    
    def clear(self) -> None:
        for window in tuple(self.windows()):
            self.removeWindow(window)
    
    def selectWindow(self, window: Window) -> None:
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
            from qtpy.QtCore import QTimer
            QTimer.singleShot(0, self.updateAllWindowMenus)
    
    def createWindowMenu(self) -> QMenu:
        from qtpy.QtGui import QAction  # type: ignore
        from qtpy.QtWidgets import QActionGroup  # type: ignore
        from qtpy.QtWidgets import QMenu
        from qtawesome import icon

        menu = QMenu('Window')

        bring_all_to_front_action = QAction(
            parent=menu,
            text='Bring All to Front',
            icon=icon('ph.stack'),
            iconVisibleInMenu=True
        )
        bring_all_to_front_action.triggered.connect(self.bringAllVisibleWindowsToFront)
        menu.addAction(bring_all_to_front_action)

        # show list of managed windows at end of menu
        separator = menu.addSeparator()
        windows_action_group = QActionGroup(menu)
        windows_action_group.setExclusive(True)
        setattr(menu, '_before_windows_action', separator)
        setattr(menu, '_windows_action_group', windows_action_group)

        self.updateWindowMenu(menu)
        return menu

    def updateWindowMenu(self, menu: QMenu) -> None:
        """ Update window menu with list of managed windows.

        !! It is up to you to add the menu to the menu bar of each managed window, e.g.:
            window.menuBar().addMenu(window._window_menu)
        """
        from qtpy.QtGui import QAction  # type: ignore
        from qtpy.QtWidgets import QActionGroup  # type: ignore
        from qtawesome import icon

        # clear old window list from menu
        try:
            windows_action_group = cast(QActionGroup, getattr(menu, '_windows_action_group'))
            for action in windows_action_group.actions():
                windows_action_group.removeAction(action)
                menu.removeAction(action)
        except AttributeError:
            # menu does not have window list yet
            separator = menu.addSeparator()
            windows_action_group = QActionGroup(menu)
            windows_action_group.setExclusive(True)
            setattr(menu, '_before_windows_action', separator)
            setattr(menu, '_windows_action_group', windows_action_group)
        
        # add current window list to menu
        active_window: Window | None = self.activeWindow()
        for window in self.windows():
            action = QAction(
                text=window.windowTitle() or 'Untitled',
                icon=icon('ph.app-window'),
                checkable=True,
                checked=window is active_window
            )
            action.triggered.connect(lambda checked, mgr=self, window=window: mgr.selectWindow(window))
            windows_action_group.addAction(action)
            menu.addAction(action)

    def windowMenu(self, window: Window) -> QMenu | None:
        """ Returns the window menu for the given window, or None if the window is not managed.
        """
        return getattr(window, '_window_menu', None)
    
    def updateAllWindowMenus(self) -> None:
        for window in self.windows():
            menu: QMenu | None = self.windowMenu(window)
            if menu is None:
                continue
            self.updateWindowMenu(menu)
    
    def bringAllVisibleWindowsToFront(self) -> None:
        # raise all visible windows
        for window in self.windows():
            if window.isVisible():
                window.raise_()
        
        # ensure active window is on top
        active_window: Window | None = self.activeWindow()
        if active_window is not None:
            active_window.raise_()
    
    @Slot(str)
    def windowTitleChanged(self, title: str) -> None:
        if self.enforceUniqueWindowTitles():
            window = self.sender()
            window = cast(Window, window)
            other_windows = [win for win in self.windows() if win is not window]
            other_titles = [win.windowTitle() for win in other_windows]
            unique_title = self.uniqueName(title, other_titles)
            if unique_title != title:
                from qtpy.QtCore import QSignalBlocker
                with QSignalBlocker(window):
                    window.setWindowTitle(unique_title)
        if self.manageWindowMenus():
            from qtpy.QtCore import QTimer
            QTimer.singleShot(0, self.updateAllWindowMenus)

    @Slot()
    def activeWindowChanged(self) -> None:
        if self.manageWindowMenus():
            from qtpy.QtCore import QTimer
            QTimer.singleShot(0, self.updateAllWindowMenus)
    
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
        from qtpy.QtCore import QEvent
        self._window_manager = window_manager

    def eventFilter(self, window: QMainWindow, event: QEvent):
        if event.type() == QEvent.Type.ActivationChange:
            # window.changeEvent(event)
            self._window_manager.activeWindowChanged()
            # return True
        elif event.type() == QEvent.Type.Close:
            if self._window_manager.removeWindowOnClose():
                self._window_manager.removeWindow(window)
            # window.closeEvent(event)
            # return True
        return False


def test_live():
    from qtpy.QtWidgets import QApplication, QMainWindow
    app = QApplication()
    # app.setQuitOnLastWindowClosed(False)
    mgr = WindowManager()
    window = QMainWindow()
    window2 = QMainWindow()
    mgr.addWindow(window)
    mgr.addWindow(window2)
    menu1 = cast(QMenu, mgr.windowMenu(window))
    menu2 = cast(QMenu, mgr.windowMenu(window2))
    window.menuBar().addMenu(menu1)
    window2.menuBar().addMenu(menu2)
    window.show()
    window2.show()
    app.exec()


if __name__ == '__main__':
    test_live()