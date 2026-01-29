""" PyQt widget for visualizing and manipulating Xarray DataTrees.

TODO:
- multi-file loading/saving (maybe all files loaded as children of root and named after filename?)
- check info view for multiple selected items on Windows computer
"""

from __future__ import annotations
import os
# from copy import copy, deepcopy
from pathlib import Path
# import numpy as np
import xarray as xr
import zarr

from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
from qtconsole.rich_jupyter_widget import RichJupyterWidget
from qtconsole.inprocess import QtInProcessKernelManager
from xarray_graph.utils import xarray_utils
from xarray_graph.tree import XarrayDataTreeItem, XarrayDataTreeModel, XarrayDataTreeView, KeyValueTreeView
from xarray_graph.widgets import CollapsibleSectionsSplitter


class XarrayDataTreeViewer(QMainWindow):
    """ PyQt widget for visualizing and manipulating Xarray DataTrees.
    """

    # global list of all XarrayDataTreeViewer top level windows
    _windows: list[XarrayDataTreeViewer] = []
    _windows_dict: dict[str, XarrayDataTreeViewer] = {} # for access by window title

    # global console (will be initialized with kernel in first instance, see _init_componenets)
    console = None

    _filetype_extensions_map: dict[str, list[str]] = {
        'Zarr Directory': [''],
        'Zarr Zip': ['.zip'],
        'NetCDF': ['.nc'],
        'HDF5': ['.h5', '.hdf5'],
    }

    _default_settings = {
        'icon size': 32,
        'icon opacity': 0.5,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        title = xarray_utils.unique_name('Untitled', [w.windowTitle() for w in XarrayDataTreeViewer._windows])
        self.setWindowTitle(title)

        self._init_global_console()
        self._init_componenets()
        self._init_actions()
        self._init_menubar()
        # self._init_top_toolbar()

        # layout
        self._selection_splitter = CollapsibleSectionsSplitter()
        self._selection_splitter.addSection('Info', self._info_view)
        self._selection_splitter.addSection('Attrs', self._attrs_view)

        self._selection_splitter_wrapper = QWidget()
        vbox = QVBoxLayout(self._selection_splitter_wrapper)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)
        vbox.addWidget(self._selection_splitter, stretch=10000)
        vbox.addStretch(1)
    
        self._inner_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._inner_splitter.addWidget(self._datatree_view)
        self._inner_splitter.addWidget(self._selection_splitter_wrapper)

        # self._outer_splitter = CollapsibleSectionsSplitter()
        # self._outer_splitter.addSection('DataTree', self._inner_splitter)
        # self._outer_splitter.addSection('Console', self._console)
        # self._outer_splitter.setFirstSectionHeaderVisible(False)
        # self._outer_splitter.sectionIsExpandedChanged.connect(self.onOuterSplitterSectionIsExpandedChanged)

        self.setCentralWidget(self._inner_splitter)

        # for testing only
        dt = xr.open_datatree('examples/ERPdata.nc', engine='h5netcdf')
        dt['eggs'] = dt['EEG'] * 10
        self.setDatatree(dt)

        # register with global windows list
        XarrayDataTreeViewer._windows.append(self)
        XarrayDataTreeViewer._windows_dict[self.windowTitle()] = self
        self.windowTitleChanged.connect(XarrayDataTreeViewer._updateWindowsDict)
    
    @staticmethod
    def isConsoleVisible() -> bool:
        return XarrayDataTreeViewer.console.isVisible()
    
    @staticmethod
    def setConsoleVisible(visible: bool) -> None:
        old_visible = XarrayDataTreeViewer.isConsoleVisible()
        XarrayDataTreeViewer.console.setVisible(visible)
        if visible and not old_visible:
            XarrayDataTreeViewer.console.kernel_manager.kernel.shell.push({'windows': XarrayDataTreeViewer._windows_dict})
            import textwrap
            msg = """
            ----------------------------------------------------
            Modules loaded at startup:
              numpy as np
              xarray as xr
            
            Variables:
              windows -> Dict of all XarrayDataTreeViewer windows keyed on window titles.

            e.g., To access the datatree for the window titled 'MyData':
              windows['MyData'].datatree()
            ----------------------------------------------------
            """
            msg = textwrap.dedent(msg).strip()
            XarrayDataTreeViewer.console._append_plain_text(msg + '\n', before_prompt=True)
        if visible and old_visible:
            XarrayDataTreeViewer.console.raise_()
    
    def datatree(self) -> xr.DataTree:
        return self._datatree_view.datatree()
    
    def setDatatree(self, datatree: xr.DataTree) -> None:
        self._datatree_view.setDatatree(datatree)
        self.onSelectionChanged()
    
    def sizeHint(self) -> QSize:
        return QSize(1000, 800)

    @staticmethod
    def refreshAllWindows():
        for window in XarrayDataTreeViewer._windows:
            window.refresh()
    
    def refresh(self) -> None:
        self._datatree_view.refresh()
    
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

    def settings(self) -> None:
        print('settings') # TODO
    
    @staticmethod
    def new() -> XarrayDataTreeViewer:
        """ Create new XarrayDataTreeViewer top level window.
        """
        window = XarrayDataTreeViewer()
        window.show()
        return window
    
    @staticmethod
    def open(filepath: str | os.PathLike | list[str | os.PathLike] = None, filetype: str = None) -> XarrayDataTreeViewer | list[XarrayDataTreeViewer] | None:
        """ Load datatree from file.
        """

        focus_widget: QWidget = QApplication.instance().focusWidget()

        if filepath is None:
            if filetype == 'Zarr Directory':
                filepath = QFileDialog.getExistingDirectory(focus_widget, 'Open Zarr Directory')
            else:
                filepath, _ = QFileDialog.getOpenFileNames(focus_widget, 'Open File(s)')
            if not filepath:
                return
            if isinstance(filepath, list) and len(filepath) == 1:
                filepath = filepath[0]
        
        # handle sequence of multiple filepaths
        if isinstance(filepath, list):
            title = 'Combine Files?'
            text = 'Combine files as first-level groups in single datatree?'
            combine: QMessageBox.StandardButton = QMessageBox.question(focus_widget, title, text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, defaultButton=QMessageBox.StandardButton.No)

            windows: list[XarrayDataTreeViewer] = []
            for path in filepath:
                window = XarrayDataTreeViewer.open(path, filetype)
                windows.append(window)
            
            if combine == QMessageBox.StandardButton.Yes:
                return XarrayDataTreeViewer._combineWindows(windows)
            return windows
        
        # ensure Path filepath object
        filepath = Path(filepath)
        
        if not filepath.exists():
            QMessageBox.warning(focus_widget, 'File Not Found', f'File not found: {filepath}')
            return
        
        # get filetype
        if filepath.is_dir():
            filetype = 'Zarr Directory'
        elif filetype is None:
            # infer filetype from file extension
            extension_filetype_map = {
                ext: filetype
                for filetype, extensions in XarrayDataTreeViewer._filetype_extensions_map.items()
                for ext in extensions
            }
            filetype = extension_filetype_map.get(filepath.suffix, None)
        
        # read datatree from filesystem
        datatree: xr.DataTree = None
        if filetype == 'Zarr Directory':
            with zarr.storage.LocalStore(filepath, mode='r') as store:
                datatree = xr.open_datatree(store, engine='zarr')
        elif filetype == 'Zarr Zip':
            with zarr.storage.ZipStore(filepath, mode='r') as store:
                datatree = xr.open_datatree(store, engine='zarr')
        elif filetype == 'NetCDF':
            datatree: xr.DataTree = xr.open_datatree(filepath)#, engine='netcdf4')
        elif filetype == 'HDF5':
            datatree: xr.DataTree = xr.open_datatree(filepath)#, engine='h5netcdf')
        else:
            try:
                # see if xarray can open the file
                datatree = xr.open_datatree(filepath)
            except:
                QMessageBox.warning(focus_widget, 'Invalid File Type', f'"{filepath}" format is not supported.')
                return
        
        if datatree is None:
            QMessageBox.warning(focus_widget, 'Invalid File', f'Unable to read file: {filepath}')
            return
        
        # restore datatree from serialization
        datatree = xarray_utils.recover_datatree_post_serialization(datatree)

        # new window
        window: XarrayDataTreeViewer = XarrayDataTreeViewer.new()
        
        # set datatree
        window.setDatatree(datatree)

        # keep track of current filepath
        window._filepath = filepath

        # set window title to filename without extension
        window.setWindowTitle(filepath.stem)

        window.show()
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
        
        # ensure Path filepath object
        filepath = Path(filepath)
        
        # get filetype
        if filepath.is_dir():
            filetype = 'Zarr Directory'
        elif filetype is None:
            if filepath.suffix == '':
                # default
                filetype = 'Zarr Zip'
            else:
                # get filetype from file extension
                extension_filetype_map = {
                    ext: filetype
                    for filetype, extensions in self._filetype_extensions_map.items()
                    for ext in extensions
                }
                filetype = extension_filetype_map.get(filepath.suffix, None)
        
        # ensure proper file extension for new files
        if not filepath.exists() and (filetype != 'Zarr Directory'):
            ext = self._filetype_extensions_map.get(filetype, [None])[0]
            if ext is not None:
                filepath = filepath.with_suffix(ext)

        # prepare datatree for serilazation
        datatree: xr.DataTree = self.datatree()
        datatree = xarray_utils.prepare_datatree_for_serialization(datatree)

        # write datatree to filesystem
        if filetype == 'Zarr Directory':
            with zarr.storage.LocalStore(filepath, mode='w') as store:
                datatree.to_zarr(store)
        elif filetype == 'Zarr Zip':
            with zarr.storage.ZipStore(filepath, mode='w') as store:
                datatree.to_zarr(store)
        elif filetype == 'NetCDF':
            datatree.to_netcdf(filepath, mode='w')
        elif filetype == 'HDF5':
            datatree.to_netcdf(filepath, mode='w')
        else:
            QMessageBox.warning(self, 'Invalid File Type', f'Saving to {filetype} format is not supported.')
            return
        
        # keep track of current filepath
        self._filepath = filepath

        # set window title to filename without extension
        self.setWindowTitle(filepath.stem)
    
    @staticmethod
    def windows() -> list[XarrayDataTreeViewer]:
        """ Get list of all XarrayDataTreeViewer top level windows in z-order from front to back.
        """
        windows = []
        for widget in QApplication.instance().topLevelWidgets():
            if isinstance(widget, XarrayDataTreeViewer):
                windows.append(widget)
        return windows
    
    @staticmethod
    def _combineWindows(windows: list[XarrayDataTreeViewer] = None) -> XarrayDataTreeViewer:
        """ Combine windows into one window with multiple top-level groups.
        """
        if windows is None:
            windows = XarrayDataTreeViewer._windows
        if not windows:
            return
        
        # combined datatree
        combined_datatree = xr.DataTree()
        window: XarrayDataTreeViewer
        for window in windows:
            title = window.windowTitle()
            combined_datatree[title] = window.datatree()
        
        noncombined_windows: list[XarrayDataTreeViewer] = [window for window in XarrayDataTreeViewer._windows if window not in windows]
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
    
    def _separateFirstLevelGroups(self) -> None:
        """ Separate first level groups into multiple windows.
        """
        dt: xr.DataTree = self.datatree()
        groups: tuple[xr.DataTree] = tuple(dt.children.values())
        if not groups:
            return
        
        group: xr.DataTree
        for group in groups:
            window: XarrayDataTreeViewer = XarrayDataTreeViewer.new()
            window.setWindowTitle(group.name)
            group.orphan()
            window.setDatatree(group)
        
        # close this window
        self.close()
   
    @staticmethod
    def _update_window_menus() -> None:
        """ Update Window menu with list of open windows.
        """
        if not XarrayDataTreeViewer._windows:
            return
        
        top_window: XarrayDataTreeViewer = QApplication.instance().activeWindow()
        # print(f'Top window: {top_window.windowTitle()}')
        
        window: XarrayDataTreeViewer
        for window in XarrayDataTreeViewer._windows:
            # clear old window list
            for action in window._windows_list_action_group.actions():
                window._windows_list_action_group.removeAction(action)
                window._window_menu.removeAction(action)
            
            # make current window list
            for i, list_window in enumerate(XarrayDataTreeViewer._windows):
                action = QAction(
                    parent=window,
                    text=list_window.windowTitle() or f'Untitled {i}',
                    checkable=True,
                    checked=list_window is top_window,
                    triggered=lambda checked, window=list_window: window.raise_())
                window._windows_list_action_group.addAction(action)
                window._window_menu.addAction(action)
    
    @staticmethod
    def _updateWindowsDict() -> None:
        XarrayDataTreeViewer._windows_dict = {win.windowTitle(): win for win in XarrayDataTreeViewer._windows}
        XarrayDataTreeViewer.console.kernel_manager.kernel.shell.push({'windows': XarrayDataTreeViewer._windows_dict})
    
    def onSelectionChanged(self) -> None:
        self._update_info_view()
        self._update_attrs_view()
    
    def _update_info_view(self) -> None:
        selected_items: list[XarrayDataTreeItem] = self._datatree_view.selectedItems()
        if not selected_items:
            try:
                selected_items = [self._datatree_view.model().rootItem()]
            except:
                self._info_view.clear()
                return
            
        XarrayDataTreeView.updateInfoTextEdit(selected_items, self._info_view)
    
    def _update_attrs_view(self) -> None:
        selected_items: list[XarrayDataTreeItem] = self._datatree_view.selectedItems()
        if not selected_items:
            model: XarrayDataTreeModel = self._datatree_view.model()
            item: XarrayDataTreeItem = model.rootItem()
            if item:
                selected_items = [item]
        if len(selected_items) == 1:
            item: XarrayDataTreeItem = selected_items[0]
            attrs: dict = item.data.attrs
            self._attrs_view.setKeyValueMap(attrs)
            self._attrs_view.show()
        else:
            self._attrs_view.hide()
    
    def _init_global_console(self) -> None:
        """ Initialize UI components.
        """

        # global console with kernel (shared across all windows)
        if XarrayDataTreeViewer.console is None:
            kernel_manager = QtInProcessKernelManager()
            kernel_manager.start_kernel()
            kernel_client = kernel_manager.client()
            kernel_client.start_channels()
            console = RichJupyterWidget()
            console.setWindowTitle(self.__class__.__name__)
            console.kernel_manager = kernel_manager
            console.kernel_client = kernel_client
            console.execute('import numpy as np', hidden=True)
            console.execute('import xarray as xr', hidden=True)
            console.executed.connect(XarrayDataTreeViewer.refreshAllWindows)
            XarrayDataTreeViewer.console = console
    
    def _init_componenets(self) -> None:
        """ Initialize UI components.
        """

        # tree view
        self._datatree_view = XarrayDataTreeView()
        self._datatree_view.setDatatree(xr.DataTree())
        self._datatree_view.selectionWasChanged.connect(self.onSelectionChanged)

        # info for selected items
        self._info_view = QTextEdit()
        self._info_view.setReadOnly(True)

        # attrs for selected items
        self._attrs_view = KeyValueTreeView()
    
    def _init_actions(self) -> None:
        """ Actions.
        """

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

        self._settings_action = QAction(
            icon=qta.icon('msc.gear'),
            iconVisibleInMenu=False,
            text='Settings',
            toolTip='Settings',
            shortcut=QKeySequence.StandardKey.Preferences,
            triggered=lambda checked: self.settings())

        # self._toggle_toolbar_action = QAction(
        #     parent=self,
        #     # icon=qta.icon('mdi.console', options=[{'opacity': 1.0}]),
        #     iconVisibleInMenu=False,
        #     text='Tool Bar',
        #     toolTip='Tool Bar',
        #     checkable=True,
        #     checked=True,
        #     # shortcut=QKeySequence('`'),
        #     triggered=lambda checked: self._toolbar.setVisible(checked))

        self._console_action = QAction(
            icon=qta.icon('mdi.console'),
            iconVisibleInMenu=True,
            text='Console',
            toolTip='Console',
            checkable=False,
            shortcut=QKeySequence('`'),
            triggered=lambda checked: self.setConsoleVisible(True))

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
        self._import_menu = self._file_menu.addMenu('Import')
        self._file_menu.addSeparator()
        self._file_menu.addAction(self._save_action)
        self._file_menu.addAction(self._save_as_action)
        self._export_menu = self._file_menu.addMenu('Export')
        self._file_menu.addSeparator()
        self._file_menu.addAction('Close Window', QKeySequence.StandardKey.Close, self.close)
        self._file_menu.addSeparator()
        self._file_menu.addAction('Quit', QKeySequence.StandardKey.Quit, QApplication.instance().quit)

        self._import_menu.addAction('Zarr Zip', lambda: self.open(filetype='Zarr Zip'))
        self._import_menu.addAction('Zarr Directory', lambda: self.open(filetype='Zarr Directory'))
        self._import_menu.addAction('NetCDF', lambda: self.open(filetype='NetCDF'))
        self._import_menu.addAction('HDF5', lambda: self.open(filetype='HDF5'))

        self._export_menu.addAction('Zarr Zip', lambda: self.saveAs(filetype='Zarr Zip'))
        self._export_menu.addAction('Zarr Directory', lambda: self.saveAs(filetype='Zarr Directory'))
        self._export_menu.addAction('NetCDF', lambda: self.saveAs(filetype='NetCDF'))
        self._export_menu.addAction('HDF5', lambda: self.saveAs(filetype='HDF5'))

        self._view_menu = menubar.addMenu('View')
        # self._view_menu.addAction(self._toggle_toolbar_action)
        self._view_menu.addAction(self._console_action)
        self._view_menu.addSeparator()
        self._view_menu.addAction(self._about_action)
        self._view_menu.addAction(self._settings_action)
        self._view_menu.addAction(self._refresh_action)

        self._window_menu = menubar.addMenu('Window')
        self._window_menu.addAction('Combine All', XarrayDataTreeViewer._combineWindows)
        self._window_menu.addAction('Separate First Level Groups', self._separateFirstLevelGroups)
        self._window_menu.addSeparator()
        self._window_menu.addAction('Bring All to Front')
        self._before_windows_list_action: QAction = self._window_menu.addSeparator()
        self._windows_list_action_group = QActionGroup(self)
        self._windows_list_action_group.setExclusive(True)

    # def _init_top_toolbar(self) -> None:
    #     """ Toolbar.
    #     """

    #     self._toolbar = QToolBar()
    #     self._toolbar.setOrientation(Qt.Orientation.Horizontal)
    #     self._toolbar.setStyleSheet("QToolBar{spacing:2px;}")
    #     self._toolbar.setIconSize(QSize(24, 24))
    #     self._toolbar.setMovable(False)
    #     self._toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)

    #     self._toolbar.addAction(self._open_action)
    #     self._toolbar.addAction(self._save_as_action)

    #     self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._toolbar)

    def changeEvent(self, event: QEvent):
        """ Overrides the changeEvent to catch window activation changes.
        """
        super().changeEvent(event)
        if event.type() == QEvent.ActivationChange:
            if self.isActiveWindow():
                # print(f"\n{self.windowTitle()} gained focus/activation")
                XarrayDataTreeViewer._update_window_menus()
            # else:
            #     print(f"\n{self.windowTitle()} lost focus/activation")
    
    def closeEvent(self, event: QCloseEvent) -> None:
        # Unregister the window from the global list when closed
        XarrayDataTreeViewer._windows.remove(self)
        XarrayDataTreeViewer._update_window_menus()
        super().closeEvent(event)
    
    # def eventFilter(self, obj, event):
    #     if event.type() == QEvent.WindowActivate:
    #         print('WindowActivate')
    #         return True
    #     if event.type() == QEvent.WindowFocusIn:
    #         print('WindowFocusIn')
    #         return True
    #     return super().eventFilter(obj, event)


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
    dt['child2'] = xr.DataTree()
    # dt['child3/grandchild1/greatgrandchild1'] = xr.DataTree()
    # dt['child3/grandchild1/tiny'] = xr.tutorial.load_dataset('tiny')
    dt['rasm'] = xr.tutorial.load_dataset('rasm')
    dt['air_temperature_gradient'] = xr.tutorial.load_dataset('air_temperature_gradient')
    
    window = XarrayDataTreeViewer()
    window.setDatatree(dt)

    model: XarrayDataTreeModel = window._datatree_view.model()
    model.setCoordsVisible(True)
    model.setInheritedCoordsVisible(True)
    model.setDetailsColumnVisible(True)
    model.setSharedDataHighlighted(True)
    model.setDebugInfoVisible(True)
    window._datatree_view._updateViewOptionsFromModel()
    window._datatree_view.showAll()
    
    window.show()
    # window.raise_() # !? this cuases havoc with MacOS native menubar (have to click out of app and back in again to get menubar working again)

    app.exec()


if __name__ == '__main__':
    test_live()