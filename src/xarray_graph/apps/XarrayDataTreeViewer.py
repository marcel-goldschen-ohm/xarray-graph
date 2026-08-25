""" PyQt widget for visualizing and manipulating Xarray DataTrees.

TODO:
- saveAs Zarr Directory allow selecting non-existent directory
"""
from __future__ import annotations

# import time
# t0 = time.time()
from xarray import DataTree
from qtpy.QtWidgets import QMainWindow
from importlib.metadata import version
# print(f'XarrayDataTreeViewer.py imports took {time.time() - t0:.3f} seconds')

from typing import TYPE_CHECKING, cast, Self
if TYPE_CHECKING:
    from os import PathLike
    from qtpy.QtCore import QSize
    from xarray_graph.utils.WindowManager import WindowManager
    from xarray_graph.widgets.IPythonConsole import IPythonConsole
    from xarray_graph.tree.XarrayDataTreeItem import XarrayDataTreeItem
    from xarray_graph.tree.XarrayDataTreeModel import XarrayDataTreeModel


# version info (stored in metadata in case needed later)
XARRAY_GRAPH_VERSION = version('xarray-graph')
VERSION_KEY = '_XG_VERSION'


class XarrayDataTreeViewer(QMainWindow):
    """ PyQt widget for visualizing and manipulating Xarray DataTrees.
    """

    # global window manager (will be initialized when the first window is created)
    _window_mgr: WindowManager | None = None

    # global console (will be initialized when needed)
    _console: IPythonConsole | None = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # add to window manager
        self.windowManager().addWindow(self)
        
        # datatree
        from xarray_graph.tree.XarrayDataTreeItem import XarrayDataTreeItem
        from xarray_graph.tree.XarrayDataTreeModel import XarrayDataTreeModel
        from xarray_graph.tree.XarrayDataTreeView import XarrayDataTreeView
        self._datatree_view = XarrayDataTreeView()
        root = XarrayDataTreeItem(DataTree())
        model = XarrayDataTreeModel(root)
        self._datatree_view.setModel(model)
        self._datatree_view.selectionWasChanged.connect(self.onDataTreeSelectionChanged)
        self._datatree_view.wasRefreshed.connect(self.refresh)

        # setup
        self._initActions()
        self._initMenubar()
        self._initUI()

    @classmethod
    def windowManager(cls) -> WindowManager:
        if cls._window_mgr is None:
            from xarray_graph.utils.WindowManager import WindowManager
            cls._window_mgr = WindowManager()

        return cls._window_mgr

    @classmethod
    def newWindow(cls) -> Self:
        """ Create new top level window.
        """
        window = cls()
        window.show()
        return window
    
    @classmethod
    def open(cls, filepath: str | PathLike | list[str | PathLike] = None, filetype: str = None, is_dir: bool = False) -> Self | None:
        """ Load datatree from file.
        """
        from qtpy.QtWidgets import QApplication
        app = cast(QApplication, QApplication.instance())
        focus_widget = app.focusWidget()

        if filepath is None:
            from qtpy.QtWidgets import QFileDialog
            if is_dir:
                filepath = QFileDialog.getExistingDirectory(focus_widget, 'Open Zarr Directory')
                if not filepath:
                    return
            else:
                filepaths, filter = QFileDialog.getOpenFileNames(focus_widget, 'Open File(s)')
                if not filepaths:
                    return
                if len(filepaths) == 1:
                    filepath = filepaths[0]
                else:
                    filepath = [fp for fp in filepaths]
        
        try:
            from pathlib import Path
            from xarray_graph.io.io import open_datatree
            if isinstance(filepath, (list, tuple)):
                # combine multiple files as first-level groups in single datatree
                import xarray as xr
                datatree = DataTree()
                for path in filepath:
                    path = Path(path)
                    datatree[path.stem] = open_datatree(path, filetype=filetype)
                title = 'Combined'
            else:
                filepath = Path(filepath)
                datatree = open_datatree(filepath, filetype=filetype)
                title = filepath.stem
        except Exception as err:
            from qtpy.QtWidgets import QMessageBox
            QMessageBox.critical(focus_widget, 'Failed to open file', str(err))
            return
        
        # new window
        window = cls.newWindow()
        window.setDatatree(datatree)
        window.setWindowTitle(title)
        window.show()
        if not isinstance(filepath, (list, tuple)):
            window._filepath = Path(filepath)
        return window
    
    def save(self) -> None:
        """ Save data tree to current file.
        """
        filepath = getattr(self, '_filepath', None)
        self.saveAs(filepath)
    
    def saveAs(self, filepath: str | PathLike = None, filetype: str = None) -> None:
        """ Save data tree to file.
        """
        if filepath is None:
            from qtpy.QtWidgets import QFileDialog
            filepath, _ = QFileDialog.getSaveFileName(self, 'Save File')
            if not filepath:
                return
        
        from pathlib import Path
        filepath = Path(filepath)
        datatree: DataTree = self.datatree()
        datatree.attrs[VERSION_KEY] = XARRAY_GRAPH_VERSION
        try:
            from xarray_graph.io.io import save_datatree
            save_datatree(datatree, filepath, filetype=filetype)
            self._filepath = filepath
            self.setWindowTitle(filepath.stem)
        except Exception as err:
            from qtpy.QtWidgets import QMessageBox
            QMessageBox.critical(self, 'Failed to save file', str(err))
    
    @classmethod
    def combineWindows(cls, windows: list[Self] = None) -> Self | None:
        """ Combine windows into one window as multiple top-level groups in a single datatree.
        """
        window_mgr = cls.windowManager()
        if windows is None:
            windows = [window for window in window_mgr.windows() if isinstance(window, cls)]
        if not windows or len(windows) == 1:
            return
        
        # combined datatree
        combined_datatree = DataTree()
        for window in windows:
            title = window.windowTitle()
            datatree = window.datatree() #or DataTree()
            combined_datatree[title] = datatree
        
        noncombined_windows: list[QMainWindow] = [window for window in window_mgr.windows() if window not in windows]
        noncombined_window_titles: list[str] = [window.windowTitle() for window in noncombined_windows]

        # new combined window
        combined_window = cls.newWindow()
        from xarray_graph.utils.utils import unique_name
        combined_window_title: str = unique_name('Combined', noncombined_window_titles)
        combined_window.setWindowTitle(combined_window_title)
        combined_window.setDatatree(combined_datatree)

        # close old windows
        for window in tuple(windows):
            if window is not combined_window:
                window.close()

        # this seems to be needed?
        window_mgr.updateAllWindowMenus()
        
        return combined_window
    
    @classmethod
    def splitFirstLevelNodesIntoSeparateWindows(cls, window: Self = None) -> None:
        """ Separate first level groups into multiple windows.
        """
        window_mgr = cls.windowManager()
        if window is None:
            active_window = window_mgr.activeWindow()
            if isinstance(active_window, cls):
                window = active_window
        if window is None:
            return

        dt: DataTree = window.datatree()
        nodes: tuple[DataTree, ...] = tuple(dt.children.values())
        if not nodes:
            return
        
        for node in nodes:
            new_window = cls.newWindow()
            new_window.setWindowTitle(node.name or 'Untitled')
            node.orphan()
            new_window.setDatatree(node)
        
        # close old window
        window.close()

        # this seems to be needed?
        window_mgr.updateAllWindowMenus()
       
    @classmethod
    def refreshAllWindows(cls) -> None:
        for window in cls.windowManager().windows():
            if isinstance(window, cls):
                window.refresh()
    
    @classmethod
    def console(cls) -> IPythonConsole:
        if cls._console is None:
            from xarray_graph.widgets.IPythonConsole import IPythonConsole
            console = IPythonConsole()
            cls._console = console
            cls._initConsole()

        return cls._console

    @classmethod
    def _initConsole(cls) -> None:
        console = cls.console()
        console.execute('import numpy as np', hidden=True)
        console.execute('import xarray as xr', hidden=True)
        console.addVariables({'wm': cls.windowManager()})
        msg = """
        ----------------------------------------------------
        Variables:
        wm -> WindowManager
        
        e.g., window = wm['window title'] or wm[index]
                datatree = window.datatree()
        
        wm.dir() or wm.ls() -> List all windows as "index: title".
        
        Modules loaded at startup: numpy as np, xarray as xr
        ----------------------------------------------------
        """
        console.printMessage(msg)
    
    @classmethod
    def showConsole(cls) -> None:
        if cls._console is None:
            # show a splash screen while the console is loading
            from qtpy.QtCore import Qt, QSize
            from qtpy.QtGui import QPixmap
            from qtpy.QtWidgets import QApplication, QSplashScreen
            from qtawesome import icon as qta_icon
            splash_pix: QPixmap = qta_icon('msc.console').pixmap(QSize(256, 256))
            splash = QSplashScreen(splash_pix, Qt.WindowType.WindowStaysOnTopHint)
            splash.show()
            splash.raise_()
            splash.repaint() # !? needed to ensure splash screen is painted before the main window is shown despite the call to app.processEvents() below
            splash.showMessage(f"\tLoading IPython console...\t", Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter, Qt.GlobalColor.white)
            app = cast(QApplication, QApplication.instance())
            app.processEvents() # force Qt to paint the splash screen immediately

            # this will load the console and block until it is ready, so the splash screen will be visible while the console is loading
            console = cls.console()

            console._show_and_raise()
            splash.finish(console)  # type: ignore
            return

        console = cls.console()
        console._show_and_raise()

    @classmethod
    def about(cls) -> None:
        """ Popup about message dialog.
        """
        from qtpy.QtWidgets import QApplication, QMessageBox
        import textwrap

        app = cast(QApplication, QApplication.instance())
        focus_widget = app.focusWidget()

        text = f"""
        {cls.__name__}

        PyQt UIs for visualizing and manipulating Xarray DataTrees.

        Author: Marcel Goldschen-Ohm

        Repository: https://github.com/marcel-goldschen-ohm/xarray-graph
        PyPI: https://pypi.org/project/xarray-graph

        Version: {XARRAY_GRAPH_VERSION}

        !! Currently in beta development. Please report any issues or feature requests on GitHub.
        """
        text = textwrap.dedent(text).strip()
        
        QMessageBox.about(focus_widget, f'About {cls.__name__}', text)

    def settings(self) -> None:
        raise NotImplementedError('Settings dialog not implemented.')

    def sizeHint(self) -> QSize:
        from qtpy.QtCore import QSize
        return super().sizeHint().expandedTo(QSize(1000, 800))

    def datatree(self) -> DataTree:
        return self._datatree_view.treeData()
    
    def setDatatree(self, datatree: DataTree) -> None:
        self._datatree_view.setTreeData(datatree)
        self.refresh()

    def onDataTreeSelectionChanged(self) -> None:
        self._updateInfoView()
        self._updateAttrsView()
    
    def refresh(self) -> None:
        from qtpy.QtCore import QSignalBlocker
        with QSignalBlocker(self._datatree_view):
            self._datatree_view.refresh()
        self.onDataTreeSelectionChanged()
    
    def _initActions(self) -> None:
        from qtpy.QtCore import Qt
        from qtpy.QtGui import QKeySequence
        from qtpy.QtGui import QAction  # type: ignore (pylance doesn't recognize some qtpy abstractions)
        from qtpy.QtWidgets import QActionGroup  # type: ignore (pylance doesn't recognize some qtpy abstractions)
        from qtawesome import icon

        self._refresh_action = QAction(
            icon=icon('msc.refresh'),
            iconVisibleInMenu=True,
            text='Refresh',
            toolTip='Refresh UI',
            shortcut = QKeySequence(QKeySequence.StandardKey.Refresh)
        )
        self._refresh_action.triggered.connect(self.refresh)

        self._about_action = QAction(
            iconVisibleInMenu=False,
            text=f'About {self.__class__.__name__}',
            toolTip=f'About {self.__class__.__name__}'
        )
        self._about_action.triggered.connect(self.about)

        self._settings_action = QAction(
            icon=icon('msc.gear'),
            iconVisibleInMenu=False,
            text='Settings',
            toolTip='Settings',
            shortcut=QKeySequence(QKeySequence.StandardKey.Preferences)
        )
        self._settings_action.triggered.connect(self.settings)
        
        self._console_action = QAction(
            icon=icon('mdi.console'),
            iconVisibleInMenu=True,
            text='Console',
            toolTip='Show Console',
            checkable=False,
            shortcut=QKeySequence('`'),
            shortcutContext=Qt.ShortcutContext.ApplicationShortcut
        )
        self._console_action.triggered.connect(self.showConsole)

        self._new_action = QAction(
            iconVisibleInMenu=False,
            text='New',
            toolTip='New Window',
            checkable=False,
            shortcut=QKeySequence(QKeySequence.StandardKey.New)
        )
        self._new_action.triggered.connect(self.newWindow)

        self._open_action = QAction(
            icon=icon('fa5.folder-open'),
            iconVisibleInMenu=False,
            text='Open',
            toolTip='Open',
            checkable=False,
            shortcut=QKeySequence(QKeySequence.StandardKey.Open)
        )
        self._open_action.triggered.connect(lambda: self.open())

        self._open_zarr_dir_action = QAction(
            icon=icon('fa5.folder-open'),
            iconVisibleInMenu=False,
            text='Open Zarr Directory',
            toolTip='Open Zarr Directory',
            checkable=False,
            shortcut=QKeySequence(QKeySequence.StandardKey.Open)
        )
        self._open_zarr_dir_action.triggered.connect(lambda: self.open(is_dir=True))

        self._save_action = QAction(
            icon=icon('fa5.save'),
            iconVisibleInMenu=False,
            text='Save',
            toolTip='Save',
            checkable=False,
            shortcut=QKeySequence(QKeySequence.StandardKey.Save)
        )
        self._save_action.triggered.connect(self.save)

        self._save_as_action = QAction(
            icon=icon('fa5.save'),
            iconVisibleInMenu=False,
            text='Save As',
            toolTip='Save As',
            checkable=False,
            shortcut=QKeySequence(QKeySequence.StandardKey.SaveAs)
        )
        self._save_as_action.triggered.connect(lambda: self.saveAs())
        
        self._theme_action_group = QActionGroup(self)
        self._theme_action_group.setExclusionPolicy(QActionGroup.ExclusionPolicy.Exclusive)
        from xarray_graph.tree.XarrayDataTreeModel import XarrayDataTreeModel
        themes = XarrayDataTreeModel.themes
        current_theme = self._datatree_view.model().theme()
        for theme in themes:
            theme_action = QAction(
                iconVisibleInMenu=False,
                text=theme,
                checkable=True,
                checked=(theme == current_theme)
            )
            theme_action.triggered.connect(lambda checked, theme=theme: self._datatree_view.model().setTheme(theme))
            self._theme_action_group.addAction(theme_action)
    
    def _initMenubar(self) -> None:
        """ Main menubar.
        """
        from qtpy.QtGui import QKeySequence
        from qtpy.QtWidgets import QApplication

        app = cast(QApplication, QApplication.instance())
        menubar = self.menuBar()

        self._file_menu = menubar.addMenu('File')
        self._file_menu.addAction(self._new_action)
        self._file_menu.addSeparator()
        self._file_menu.addAction(self._open_action)
        self._file_menu.addAction(self._open_zarr_dir_action)
        self._import_menu = self._file_menu.addMenu('Import')
        self._file_menu.addSeparator()
        self._file_menu.addAction(self._save_action)
        self._file_menu.addAction(self._save_as_action)
        self._export_menu = self._file_menu.addMenu('Export')
        self._file_menu.addSeparator()
        self._file_menu.addAction('Close Window', QKeySequence.StandardKey.Close, self.close)
        self._file_menu.addSeparator()
        self._file_menu.addAction('Quit', QKeySequence.StandardKey.Quit, app.quit)

        for filetype in ['Zarr Directory', 'NetCDF/HDF5']:
            self._import_menu.addAction(filetype, lambda filetype=filetype: self.open(filetype=filetype))
            self._export_menu.addAction(filetype, lambda filetype=filetype: self.saveAs(filetype=filetype))
        self._import_menu.addSeparator()
        for filetype in ['WinWCP', 'HEKA', 'LabChart MATLAB (GOlab TEVC)']:
            self._import_menu.addAction(filetype, lambda filetype=filetype: self.open(filetype=filetype))
        
        self._view_menu = menubar.addMenu('View')
        self._view_menu.addAction(self._console_action)
        self._view_menu.addSeparator()
        self._theme_menu = self._view_menu.addMenu('Theme')
        self._view_menu.addSeparator()
        self._view_menu.addAction(self._about_action)
        self._view_menu.addAction(self._settings_action)
        self._view_menu.addAction(self._refresh_action)

        for theme_action in self._theme_action_group.actions():
            self._theme_menu.addAction(theme_action)

        window_mgr = self.windowManager()
        self._window_menu = menubar.addMenu('Window')
        self._window_menu.addAction('Combine All', self.combineWindows)
        self._window_menu.addAction('Separate First Level Groups', self.splitFirstLevelNodesIntoSeparateWindows)
        self._window_menu.addSeparator()
        self._window_menu.addAction('Bring All to Front', window_mgr.bringAllVisibleWindowsToFront)
        window_mgr.updateWindowMenu(self._window_menu)
    
    def _initUI(self) -> None:
        """ Initialize UI elements and layout.
        """
        # selection info
        from xarray_graph.tree.XarrayDataTreeView import infoTextEdit
        self._info_view = infoTextEdit([])

        # selected item attrs
        from xarray_graph.tree.KeyValueTreeView import KeyValueTreeView
        self._attrs_view = KeyValueTreeView()

        # selection info and attrs splitter
        from xarray_graph.widgets.CollapsibleSectionsSplitter import CollapsibleSectionsSplitter
        self._selection_splitter = CollapsibleSectionsSplitter()
        self._selection_splitter.addSection('Info', self._info_view)
        self._selection_splitter.addSection('Attrs', self._attrs_view)
        self._selection_splitter.setFirstSectionHeaderVisible(False)

        # # needed to ensure collapsing all sections doesn't shrink neighboring widgets in the parent horizontal splitter
        # from qtpy.QtWidgets import QWidget, QVBoxLayout
        # self._selection_splitter_wrapper = QWidget()
        # vbox = QVBoxLayout(self._selection_splitter_wrapper)
        # vbox.setContentsMargins(0, 0, 0, 0)
        # vbox.setSpacing(0)
        # vbox.addWidget(self._selection_splitter, stretch=10000)
        # vbox.addStretch(1)

        # main layout
        from qtpy.QtCore import Qt
        from qtpy.QtWidgets import QSplitter
        hsplitter = QSplitter(Qt.Orientation.Horizontal)
        hsplitter.addWidget(self._datatree_view)
        hsplitter.addWidget(self._selection_splitter)
        self.setCentralWidget(hsplitter)
    
    def _updateInfoView(self) -> None:
        items: list[XarrayDataTreeItem] = self._datatree_view.selectedItems()
        if not items:
            model: XarrayDataTreeModel = self._datatree_view.model()
            items = [model.rootItem()]
        data = [item.data() for item in items]
        from xarray_graph.tree.XarrayDataTreeView import infoTextEdit
        infoTextEdit(data, text_edit_to_update=self._info_view)
    
    def _updateAttrsView(self) -> None:
        items: list[XarrayDataTreeItem] = self._datatree_view.selectedItems()
        if not items:
            model: XarrayDataTreeModel = self._datatree_view.model()
            items = [model.rootItem()]
        if len(items) == 1:
            item: XarrayDataTreeItem = items[0]
            attrs: dict = item.data().attrs
            self._attrs_view.setTreeData(attrs)
            self._attrs_view.show()
        else:
            self._attrs_view.hide()
    

def test_live():
    from qtpy.QtWidgets import QApplication
    app = QApplication()
    # app.setQuitOnLastWindowClosed(False)

    # window = XarrayDataTreeViewer.open('examples/ERPdata.nc')
    # dt = window.datatree()
    # dt['eggs'] = dt['EEG'] * 10
    # window.refresh()

    import xarray as xr
    from xarray import DataTree
    dt = DataTree()
    dt['air_temperature'] = xr.tutorial.load_dataset('air_temperature')
    dt['air_temperature/twice air'] = dt['air_temperature/air'] * 2
    dt['air_temperature/inherits'] = xr.tutorial.load_dataset('air_temperature')
    dt['air_temperature/inherits/again'] = xr.tutorial.load_dataset('air_temperature')
    dt['child'] = DataTree()
    dt['child/grandchild/greatgrandchild'] = DataTree()
    dt['child/grandchild/tiny'] = xr.tutorial.load_dataset('tiny')
    dt['rasm'] = xr.tutorial.load_dataset('rasm')
    dt['rasm/rasm'] = xr.tutorial.load_dataset('rasm')
    dt['air_temperature_gradient'] = xr.tutorial.load_dataset('air_temperature_gradient')
    
    window = XarrayDataTreeViewer()
    window.setDatatree(dt)
    window._datatree_view.viewAll()
    window.show()

    app.exec()


if __name__ == '__main__':
    test_live()