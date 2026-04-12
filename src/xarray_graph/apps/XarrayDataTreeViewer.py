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
from xarray_graph.tree import XarrayDataTreeItem, XarrayDataTreeModel, XarrayDataTreeView, KeyValueTreeView
from xarray_graph.widgets import CollapsibleSectionsSplitter
from xarray_graph.tree.XarrayDataTreeView import infoTextEdit


class XarrayDataTreeViewer(QMainWindow):
    """ PyQt widget for visualizing and manipulating Xarray DataTrees.
    """

    window_mgr = WindowManager()

    # global console (will be initialized by first instance)
    console: IPythonConsole = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # add to window manager
        XarrayDataTreeViewer.window_mgr.addWindow(self)

        # global console
        if XarrayDataTreeViewer.console is None:
            XarrayDataTreeViewer.console = IPythonConsole()
        
        # datatree
        self._datatree_view = XarrayDataTreeView()
        model = XarrayDataTreeModel()
        self._datatree_view.setModel(model)
        self._datatree_view.selectionWasChanged.connect(self.onSelectionChanged)

        # selection
        self._info_view = QTextEdit()
        self._attrs_view = KeyValueTreeView()

        self._selection_splitter = CollapsibleSectionsSplitter()
        self._selection_splitter.addSection('Info', self._info_view)
        self._selection_splitter.addSection('Attrs', self._attrs_view)

        # needed to ensure collapsing all sections doesn't shrink neighboring widgets in the parent horizontal splitter
        self._selection_splitter_wrapper = QWidget()
        vbox = QVBoxLayout(self._selection_splitter_wrapper)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)
        vbox.addWidget(self._selection_splitter, stretch=10000)
        vbox.addStretch(1)

        # layout
        hsplitter = QSplitter(Qt.Orientation.Horizontal)
        hsplitter.addWidget(self._datatree_view)
        hsplitter.addWidget(self._selection_splitter_wrapper)
        self.setCentralWidget(hsplitter)

        # actions
        self._init_actions()

        # menubar
        self._init_menubar()

    def sizeHint(self) -> QSize:
        return super().sizeHint().expandedTo(QSize(1000, 800))

    def datatree(self) -> xr.DataTree:
        return self._datatree_view.treeData()
    
    def setDatatree(self, datatree: xr.DataTree) -> None:
        self._datatree_view.setTreeData(datatree)
        self.onSelectionChanged()

    def refresh(self) -> None:
        self._datatree_view.refresh()
        self.onSelectionChanged()
    
    # @staticmethod
    # def refreshAllWindows():
    #     window: XarrayDataTreeViewer
    #     for window in XarrayDataTreeViewer.window_mgr.windows():
    #         if issubclass(type(window), XarrayDataTreeViewer):
    #             window.refresh()
    
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
    def new() -> XarrayDataTreeViewer:
        """ Create new XarrayDataTreeViewer top level window.
        """
        window = XarrayDataTreeViewer()
        window.show()
        return window
    
    @staticmethod
    def open(filepath: str | os.PathLike | list[str | os.PathLike] = None, is_dir: bool = False) -> XarrayDataTreeViewer | list[XarrayDataTreeViewer] | None:
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
                datatree[path.stem] = io.open_datatree(path)
            title = 'Combined'
        else:
            filepath = Path(filepath)
            datatree = io.open_datatree(filepath)
            title = filepath.stem
        
        # new window
        window: XarrayDataTreeViewer = XarrayDataTreeViewer.new()
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
        io.save_datatree(datatree, filepath)
        self._filepath = filepath
        self.setWindowTitle(filepath.stem)
    
    @staticmethod
    def combineWindows(windows: list[XarrayDataTreeViewer] = None) -> XarrayDataTreeViewer:
        """ Combine windows into one window as multiple top-level groups in a single datatree.
        """
        if windows is None:
            windows = XarrayDataTreeViewer.window_mgr.windows()
        if not windows or len(windows) == 1:
            return
        
        # combined datatree
        combined_datatree = xr.DataTree()
        window: XarrayDataTreeViewer
        for window in windows:
            title = window.windowTitle()
            datatree = window.datatree() #or xr.DataTree()
            combined_datatree[title] = datatree
        
        noncombined_windows: list[XarrayDataTreeViewer] = [window for window in XarrayDataTreeViewer.window_mgr.windows() if window not in windows]
        noncombined_window_titles: list[str] = [window.windowTitle() for window in noncombined_windows]

        # new combined window
        combined_window: XarrayDataTreeViewer = XarrayDataTreeViewer.new()
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
            window: XarrayDataTreeViewer = XarrayDataTreeViewer.new()
            window.setWindowTitle(group.name)
            group.orphan()
            window.setDatatree(group)
        
        # close this window
        self.close()
   
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
            triggered=lambda checked: XarrayDataTreeViewer.about())

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
            triggered=lambda: XarrayDataTreeViewer.new())

        self._open_action = QAction(
            icon=qta.icon('fa5.folder-open'),
            iconVisibleInMenu=False,
            text='Open',
            toolTip='Open',
            checkable=False,
            shortcut=QKeySequence.StandardKey.Open,
            triggered=lambda: XarrayDataTreeViewer.open())

        self._open_zarr_dir_action = QAction(
            icon=qta.icon('fa5.folder-open'),
            iconVisibleInMenu=False,
            text='Open Zarr Directory',
            toolTip='Open Zarr Directory',
            checkable=False,
            triggered=lambda: XarrayDataTreeViewer.open(is_dir=True))

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
        self._file_menu.addSeparator()
        self._file_menu.addAction(self._save_action)
        self._file_menu.addAction(self._save_as_action)
        self._file_menu.addSeparator()
        self._file_menu.addAction('Close Window', QKeySequence.StandardKey.Close, self.close)
        self._file_menu.addSeparator()
        self._file_menu.addAction('Quit', QKeySequence.StandardKey.Quit, QApplication.instance().quit)

        self._view_menu = menubar.addMenu('View')
        self._view_menu.addAction(XarrayDataTreeViewer.console._console_action)
        self._view_menu.addSeparator()
        self._view_menu.addAction(self._about_action)
        # self._view_menu.addAction(self._settings_action)
        self._view_menu.addAction(self._refresh_action)

        self._window_menu = menubar.addMenu('Window')
        self._window_menu.addAction('Combine All', XarrayDataTreeViewer.combineWindows)
        self._window_menu.addAction('Separate First Level Groups', self.separateFirstLevelGroups)
        self._window_menu.addSeparator()
        self._window_menu.addAction('Bring All to Front', XarrayDataTreeViewer.window_mgr.bringAllVisibleWindowsToFront)
        XarrayDataTreeViewer.window_mgr.updateWindowMenu(self._window_menu)
    
    def onSelectionChanged(self) -> None:
        self._update_info_view()
        self._update_attrs_view()
    
    def _update_info_view(self) -> None:
        items: list[XarrayDataTreeItem] = self._datatree_view.selectedItems()
        if not items:
            model: XarrayDataTreeModel = self._datatree_view.model()
            items = [model.rootItem()]
        data = [item.data() for item in items]    
        infoTextEdit(data, text_edit_to_update=self._info_view)
    
    def _update_attrs_view(self) -> None:
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
    dt['air_temperature_gradient'] = xr.tutorial.load_dataset('air_temperature_gradient')
    
    window = XarrayDataTreeViewer()
    window.setDatatree(dt)
    window._datatree_view.showAll()
    window.show()

    app.exec()


if __name__ == '__main__':
    test_live()