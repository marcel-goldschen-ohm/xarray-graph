""" PyQt widget for visualizing and manipulating Xarray DataTrees.
"""

from __future__ import annotations
import os
from pathlib import Path
import xarray as xr
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
import xarray_graph.io as io
from xarray_graph.utils import xarray_utils, WindowManager, IPythonConsole
from xarray_graph.tree import XarrayDataTreeModel, XarrayDataTreeView


class XarrayDataTreeWindow(QMainWindow):
    """ PyQt window for visualizing and manipulating Xarray DataTrees.
    """

    window_mgr = WindowManager()

    # global console (will be initialized by first instance)
    console: IPythonConsole = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # add to window manager
        XarrayDataTreeWindow.window_mgr.addWindow(self)

        # global console
        if XarrayDataTreeWindow.console is None:
            console = IPythonConsole()
            console.execute('import numpy as np', hidden=True)
            console.execute('import xarray as xr', hidden=True)
            console.addVariables({'wm': XarrayDataTreeWindow.window_mgr})
            msg = """
            ----------------------------------------------------
            Variables:
            wm -> WindowManager
            e.g., window = wm['window title'] or wm[index]
                  datatree = window.datatree()
            Modules loaded at startup: numpy as np, xarray as xr
            ----------------------------------------------------
            """
            console.printMessage(msg)
            XarrayDataTreeWindow.console = console
        
        # datatree model/view
        self._datatree_view = XarrayDataTreeView()
        model = XarrayDataTreeModel()
        self._datatree_view.setModel(model)
        self._datatree_view.selectionWasChanged.connect(self.onSelectionChanged)

        # UI
        self._init_components()
        self._init_actions()
        self._init_menubar()
        self._init_layout()

    def sizeHint(self) -> QSize:
        return super().sizeHint().expandedTo(QSize(1000, 800))

    def datatree(self) -> xr.DataTree:
        return self._datatree_view.treeData()
    
    def setDatatree(self, datatree: xr.DataTree) -> None:
        self._datatree_view.setTreeData(datatree)
        self.refresh()

    def refresh(self) -> None:
        self._datatree_view.refresh()
        self.onSelectionChanged()
    
    # @staticmethod
    # def refreshAllWindows():
    #     window: XarrayDataTreeViewer
    #     for window in XarrayDataTreeViewer.window_mgr.windows():
    #         if issubclass(type(window), XarrayDataTreeViewer):
    #             window.refresh()

    def onSelectionChanged(self) -> None:
        pass
    
    @staticmethod
    def about() -> None:
        """ Popup about message dialog.
        """
        import textwrap
        focus_widget: QWidget = QApplication.instance().focusWidget()

        text = f"""
        XarrayGraph

        PyQt UIs for visualizing and manipulating Xarray DataTrees.

        Author: Marcel Goldschen-Ohm

        Repository: https://github.com/marcel-goldschen-ohm/xarray-graph
        PyPI: https://pypi.org/project/xarray-graph
        """
        text = textwrap.dedent(text).strip()
        
        QMessageBox.about(focus_widget, 'About XarrayGraph', text)

    # def settings(self) -> None:
    #     print('settings') # TODO
    
    @staticmethod
    def new() -> XarrayDataTreeWindow:
        """ Create new XarrayDataTreeWindow top level window.
        """
        window = XarrayDataTreeWindow()
        window.show()
        return window
    
    @staticmethod
    def open(filepath: str | os.PathLike | list[str | os.PathLike] = None, filetype: str = None, is_dir: bool = False) -> XarrayDataTreeWindow:
        """ Load datatree from file.
        """
        focus_widget: QWidget = QApplication.instance().focusWidget()

        if filepath is None:
            if is_dir:
                filepath = QFileDialog.getExistingDirectory(focus_widget, 'Open Zarr Directory')
            else:
                filepath, filter = QFileDialog.getOpenFileNames(focus_widget, 'Open File(s)')
            if not filepath:
                return
            if len(filepath) == 1:
                filepath = filepath[0]
        
        if isinstance(filepath, (list, tuple)):
            # combine multiple files as first-level groups in single datatree
            datatree = xr.DataTree()
            for path in filepath:
                path = Path(path)
                datatree[path.stem] = io.open_datatree(path, filetype=filetype)
            title = 'Combined'
        else:
            filepath = Path(filepath)
            datatree = io.open_datatree(filepath, filetype=filetype)
            title = filepath.stem
        
        # new window
        window = XarrayDataTreeWindow.new()
        window.setDatatree(datatree)
        window.setWindowTitle(title)
        window.show()
        if isinstance(filepath, Path):
            window._filepath = filepath
        return window
    
    def save(self) -> None:
        """ Save data tree to current file.
        """
        filepath = getattr(self, '_filepath', None)
        self.saveAs(filepath)
    
    def saveAs(self, filepath: str | os.PathLike = None, filetype: str = None) -> None:
        """ Save data tree to file.
        """
        if filepath is None:
            filepath, _ = QFileDialog.getSaveFileName(self, 'Save File')
            if not filepath:
                return
        
        filepath = Path(filepath)
        datatree: xr.DataTree = self.datatree()
        io.save_datatree(datatree, filepath, filetype=filetype)
        self._filepath = filepath
        self.setWindowTitle(filepath.stem)
    
    @staticmethod
    def combineWindows(windows: list[XarrayDataTreeWindow] = None) -> XarrayDataTreeWindow:
        """ Combine windows into one window as multiple top-level groups in a single datatree.
        """
        if windows is None:
            windows = XarrayDataTreeWindow.window_mgr.windows()
        if not windows or len(windows) == 1:
            return
        
        # combined datatree
        combined_datatree = xr.DataTree()
        window: XarrayDataTreeWindow
        for window in windows:
            title = window.windowTitle()
            datatree = window.datatree() #or xr.DataTree()
            combined_datatree[title] = datatree
        
        noncombined_windows: list[XarrayDataTreeWindow] = [window for window in XarrayDataTreeWindow.window_mgr.windows() if window not in windows]
        noncombined_window_titles: list[str] = [window.windowTitle() for window in noncombined_windows]

        # new combined window
        combined_window = XarrayDataTreeWindow.new()
        combined_window_title: str = xarray_utils.unique_name('Combined', noncombined_window_titles)
        combined_window.setWindowTitle(combined_window_title)
        combined_window.setDatatree(combined_datatree)

        # close old windows
        for window in tuple(windows):
            if window is not combined_window:
                window.close()
        
        return combined_window
    
    def separateFirstLevelGroups(self) -> None:
        """ Separate first level groups into multiple windows.
        """
        dt: xr.DataTree = self.datatree()
        groups: tuple[xr.DataTree] = tuple(dt.children.values())
        if not groups:
            return
        
        for group in groups:
            window = XarrayDataTreeWindow.new()
            window.setWindowTitle(group.name)
            group.orphan()
            window.setDatatree(group)
        
        # close this window
        self.close()
   
    def _init_components(self) -> None:
        pass
    
    def _init_actions(self) -> None:

        self._refresh_action = QAction(
            icon=qta.icon('msc.refresh'),
            iconVisibleInMenu=True,
            text='Refresh',
            toolTip='Refresh UI',
            shortcut = QKeySequence.StandardKey.Refresh,
            triggered=lambda checked: self.refresh())

        self._about_action = QAction(
            iconVisibleInMenu=False,
            text=f'About {self.__class__.__name__}',
            toolTip=f'About {self.__class__.__name__}',
            triggered=lambda checked: XarrayDataTreeWindow.about())

        # self._settings_action = QAction(
        #     icon=qta.icon('msc.gear'),
        #     iconVisibleInMenu=False,
        #     text='Settings',
        #     toolTip='Settings',
        #     shortcut=QKeySequence.StandardKey.Preferences,
        #     triggered=lambda checked: self.settings())

        self._new_action = QAction(
            iconVisibleInMenu=False,
            text='New',
            toolTip='New Window',
            checkable=False,
            shortcut=QKeySequence.StandardKey.New,
            triggered=lambda: XarrayDataTreeWindow.new())

        self._open_action = QAction(
            icon=qta.icon('fa5.folder-open'),
            iconVisibleInMenu=False,
            text='Open',
            toolTip='Open',
            checkable=False,
            shortcut=QKeySequence.StandardKey.Open,
            triggered=lambda: XarrayDataTreeWindow.open())

        self._open_zarr_dir_action = QAction(
            icon=qta.icon('fa5.folder-open'),
            iconVisibleInMenu=False,
            text='Open Zarr Directory',
            toolTip='Open Zarr Directory',
            checkable=False,
            triggered=lambda: XarrayDataTreeWindow.open(is_dir=True))

        self._save_action = QAction(
            icon=qta.icon('fa5.save'),
            iconVisibleInMenu=False,
            text='Save',
            toolTip='Save',
            checkable=False,
            shortcut=QKeySequence.StandardKey.Save,
            triggered=lambda: self.save())

        self._save_as_action = QAction(
            icon=qta.icon('fa5.save'),
            iconVisibleInMenu=False,
            text='Save As',
            toolTip='Save As',
            checkable=False,
            shortcut=QKeySequence.StandardKey.SaveAs,
            triggered=lambda: self.saveAs())
    
    def _init_menubar(self) -> None:
        """ Main menubar.
        """
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
        self._file_menu.addAction('Quit', QKeySequence.StandardKey.Quit, QApplication.instance().quit)

        for filetype in ['Zarr Zip', 'Zarr Directory', 'NetCDF', 'HDF5']:
            self._import_menu.addAction(filetype, lambda filetype=filetype: self.open(filetype=filetype))
            self._export_menu.addAction(filetype, lambda filetype=filetype: self.saveAs(filetype=filetype))
        self._import_menu.addSeparator()
        for filetype in ['WinWCP', 'HEKA', 'LabChart MATLAB TEVC']:
            self._import_menu.addAction(filetype, lambda filetype=filetype: self.open(filetype=filetype))

        self._view_menu = menubar.addMenu('View')
        self._view_menu.addAction(XarrayDataTreeWindow.console._console_action)
        self._view_menu.addSeparator()
        self._view_menu.addAction(self._about_action)
        # self._view_menu.addAction(self._settings_action)
        self._view_menu.addAction(self._refresh_action)

        self._window_menu = menubar.addMenu('Window')
        self._window_menu.addAction('Combine All', XarrayDataTreeWindow.combineWindows)
        self._window_menu.addAction('Separate First Level Groups', self.separateFirstLevelGroups)
        self._window_menu.addSeparator()
        self._window_menu.addAction('Bring All to Front', XarrayDataTreeWindow.window_mgr.bringAllVisibleWindowsToFront)
        XarrayDataTreeWindow.window_mgr.updateWindowMenu(self._window_menu)
    
    def _init_layout(self) -> None:
        self.setCentralWidget(self._datatree_view)
    

def test_live():
    app = QApplication()
    # app.setQuitOnLastWindowClosed(False)

    # window = XarrayDataTreeViewer.open('examples/ERPdata.nc')
    # dt = window.datatree()
    # dt['eggs'] = dt['EEG'] * 10
    # window.refresh()

    dt = xr.DataTree()
    dt['air_temperature'] = xr.tutorial.load_dataset('air_temperature')
    dt['air_temperature/twice air'] = dt['air_temperature/air'] * 2
    dt['air_temperature/inherits'] = xr.tutorial.load_dataset('air_temperature')
    dt['air_temperature/inherits/again'] = xr.tutorial.load_dataset('air_temperature')
    dt['child'] = xr.DataTree()
    dt['child/grandchild/greatgrandchild'] = xr.DataTree()
    dt['child/grandchild/tiny'] = xr.tutorial.load_dataset('tiny')
    dt['rasm'] = xr.tutorial.load_dataset('rasm')
    dt['rasm/rasm'] = xr.tutorial.load_dataset('rasm')
    dt['air_temperature_gradient'] = xr.tutorial.load_dataset('air_temperature_gradient')
    
    window = XarrayDataTreeWindow()
    window.setDatatree(dt)
    window._datatree_view.showAll()
    window.show()

    app.exec()


if __name__ == '__main__':
    test_live()