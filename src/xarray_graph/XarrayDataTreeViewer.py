""" PyQt widget for visualizing and manipulating Xarray DataTrees.

TODO:
- file I/O
    - multi-file loading/saving (maybe all files loaded as children of root and named after filename?)
- check info view for multiple selected items on Windows computer
- attrs view for selected items
- optional debug symbols and highlighting in tree view
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
from xarray_graph import xarray_utils, XarrayDataTreeItem, XarrayDataTreeModel, XarrayDataTreeView, IPythonConsole, CollapsibleSectionsSplitter


class XarrayDataTreeViewer(QMainWindow):
    """ PyQt widget for visualizing and manipulating Xarray DataTrees.
    """

    # global list of all XarrayDataTreeViewer top level windows
    _windows: list[XarrayDataTreeViewer] = []

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

        n = len(XarrayDataTreeViewer._windows)
        self.setWindowTitle(f'Untitled {n}')

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

        self._outer_splitter = CollapsibleSectionsSplitter()
        self._outer_splitter.addSection('DataTree', self._inner_splitter)
        self._outer_splitter.addSection('Console', self._console)
        self._outer_splitter.setFirstSectionHeaderVisible(False)
        self._outer_splitter.sectionIsExpandedChanged.connect(self.onOuterSplitterSectionIsExpandedChanged)

        self.setCentralWidget(self._outer_splitter)

        msg = self._console._one_time_message_on_show
        QTimer.singleShot(300, lambda msg=msg: self._console.print_message(msg))

        # initial state
        self.setConsoleVisible(False)

        # for testing only
        dt = xr.open_datatree('examples/ERPdata.nc', engine='h5netcdf')
        dt['eggs'] = dt['EEG'] * 10
        self.setDatatree(dt)

        # register with global windows list
        XarrayDataTreeViewer._windows.append(self)
    
    def datatree(self) -> xr.DataTree:
        return self._datatree_view.datatree()
    
    def setDatatree(self, datatree: xr.DataTree) -> None:
        self._datatree_view.setDatatree(datatree)
        self._console.add_variable('dt', datatree)
    
    def sizeHint(self) -> QSize:
        return QSize(1000, 800)

    def refresh(self) -> None:
        self._datatree_view.refresh()
    
    def about(self) -> None:
        """ Popup about message dialog.
        """
        import textwrap

        text = f"""
        {self.__class__.__name__}
        
        PyQt widget for visualizing and manipulating Xarray DataTrees.

        Author: Marcel Goldschen-Ohm

        Repository: https://github.com/marcel-goldschen-ohm/xarray-graph
        PyPI: https://pypi.org/project/xarray-graph
        """
        text = textwrap.dedent(text).strip()
        
        QMessageBox.about(self, f'About {self.__class__.__name__}', text)

    def settings(self) -> None:
        print('settings') # TODO
    
    def new(self) -> XarrayDataTreeViewer:
        """ Create new XarrayDataTreeViewer top level window.
        """
        window = XarrayDataTreeViewer()
        window.show()
        return window
    
    def open(self, filepath: str | os.PathLike | list[str | os.PathLike] = None, filetype: str = None) -> None:
        """ Load datatree from file.
        """

        if filepath is None:
            if filetype == 'Zarr Directory':
                filepath = QFileDialog.getExistingDirectory(self, 'Open Zarr Directory')
            else:
                filepath, _ = QFileDialog.getOpenFileNames(self, 'Open File(s)')
            if not filepath:
                return
            if isinstance(filepath, list) and len(filepath) == 1:
                filepath = filepath[0]
        
        # handle sequence of multiple filepaths
        if isinstance(filepath, list):
            for path in filepath:
                self.open(path, filetype)
            return
        
        # ensure Path filepath object
        if isinstance(filepath, str):
            filepath = Path(filepath)
        
        if not filepath.exists():
            QMessageBox.warning(self, 'File Not Found', f'File not found: {filepath}')
            return
        
        # get filetype
        if filepath.is_dir():
            filetype = 'Zarr Directory'
        elif filetype is None:
            # infer filetype from file extension
            extension_filetype_map = {
                ext: filetype
                for filetype, extensions in self._filetype_extensions_map.items()
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
                QMessageBox.warning(self, 'Invalid File Type', f'"{filepath}" format is not supported.')
                return
        
        if datatree is None:
            QMessageBox.warning(self, 'Invalid File', f'Unable to open file: {filepath}')
            return

        # use filename for root node
        datatree.name = filepath.stem
    
    def save(self) -> None:
        """ Save data tree to current file. """

        filepath = getattr(self, '_filepath', None)
        self.saveAs(filepath)
    
    def saveAs(self, filepath: str | os.PathLike = None, filetype: str = None) -> None:
        """ Save data tree to file. """

        if filepath is None:
            filepath, _ = QFileDialog.getSaveFileName(self, 'Save File')
            if not filepath:
                return
        
        # ensure Path filepath object
        if isinstance(filepath, str):
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

        # prepare datatree for storage
        datatree: xr.DataTree = self.datatree()

        # write datatree to filesystem
        if filetype == 'Zarr Directory':
            with zarr.storage.LocalStore(filepath, mode='w') as store:
                datatree.to_zarr(store)
        elif filetype == 'Zarr Zip':
            if filepath.suffix != '.zip':
                filepath = filepath.with_suffix('.zip')
            with zarr.storage.ZipStore(filepath, mode='w') as store:
                datatree.to_zarr(store)
        elif filetype == 'NetCDF':
            QMessageBox.warning(self, 'Under Construction', f'{filetype} support is in the works.')
            return
        elif filetype == 'HDF5':
            QMessageBox.warning(self, 'Under Construction', f'{filetype} support is in the works.')
            return
        else:
            QMessageBox.warning(self, 'Invalid File Type', f'Saving to {filetype} format is not supported.')
            return
        
        self._filepath = filepath
    
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
    
    def isConsoleVisible(self) -> bool:
        index: int = self._outer_splitter.indexOfSection('Console')
        return self._outer_splitter.isSectionExpanded(index)
    
    def setConsoleVisible(self, visible: bool) -> None:
        index: int = self._outer_splitter.indexOfSection('Console')
        return self._outer_splitter.setSectionExpanded(index, visible)
    
    def onOuterSplitterSectionIsExpandedChanged(self, index: int, expanded: bool) -> None:
        if index == self._outer_splitter.indexOfSection('Console'):
            self._toggle_console_action.setChecked(expanded)
    
    def onSelectionChanged(self) -> None:
        self._update_info_view()
    
    def _update_info_view(self) -> None:
        selected_items: list[XarrayDataTreeItem] = self._datatree_view.selectedItems()
        if not selected_items:
            try:
                selected_items = [self._datatree_view.model().root()]
            except:
                self._info_view.clear()
                return
        
        self._info_view.clear()
        sep = False
        item: XarrayDataTreeItem
        for item in self._datatree_view.model().root().subtree_depth_first():
            if item in selected_items:
                data: xr.DataTree | xr.DataArray = item.data
                if isinstance(data, xr.DataTree):
                    data = data.dataset
                if sep:
                    # TODO: check if this works on Windows (see https://stackoverflow.com/questions/76710833/how-do-i-add-a-full-width-horizontal-line-in-qtextedit)
                    self._info_view.insertHtml('<br><hr><br>')
                else:
                    sep = True
                self._info_view.insertPlainText(f'{item.path}:\n{data}')

                # tc = self.result_text_box.textCursor()
                # # move the cursor to the end of the document
                # tc.movePosition(tc.End)
                # # insert an arbitrary QTextBlock that will inherit the previous format
                # tc.insertBlock()
                # # get the block format
                # fmt = tc.blockFormat()
                # # remove the horizontal ruler property from the block
                # fmt.clearProperty(fmt.BlockTrailingHorizontalRulerWidth)
                # # set (not merge!) the block format
                # tc.setBlockFormat(fmt)
                # # eventually, apply the cursor so that editing actually starts at the end
                # self.result_text_box.setTextCursor(tc)
    
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
        self._attrs_view = QTreeView() # TODO

        # console
        self._console = IPythonConsole()
        self._console.execute('import numpy as np', hidden=True)
        self._console.execute('import xarray as xr', hidden=True)
        self._console.add_variable('ui', self) # mostly for debugging
        self._console.executed.connect(self._datatree_view.refresh)
        self._console._one_time_message_on_show = """
        ----------------------------------------------------
        Variables:
          dt -> The Xarray DataTree
          ui -> This app widget
        Modules loaded at startup:
          numpy as np
          xarray as xr
        ----------------------------------------------------
        """
    
    def _init_actions(self) -> None:
        """ Actions.
        """

        self._refresh_action = QAction(
            parent=self,
            icon=qta.icon('mdi.refresh', options=[{'opacity': 1.0}]),
            iconVisibleInMenu=False,
            text='Refresh',
            toolTip='Refresh UI',
            shortcut = QKeySequence('Ctrl+R'),
            triggered=lambda checked: self.refresh())

        self._about_action = QAction(
            parent=self,
            iconVisibleInMenu=False,
            text=f'About {self.__class__.__name__}',
            toolTip=f'About {self.__class__.__name__}',
            triggered=lambda checked: self.about())

        self._settings_action = QAction(
            parent=self,
            icon=qta.icon('msc.gear', options=[{'opacity': 1.0}]),
            iconVisibleInMenu=False,
            text='Settings',
            toolTip='Settings',
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

        self._toggle_console_action = QAction(
            parent=self,
            icon=qta.icon('mdi.console', options=[{'opacity': 1.0}]),
            iconVisibleInMenu=False,
            text='Console',
            toolTip='Console',
            checkable=True,
            checked=True,
            shortcut=QKeySequence('`'),
            triggered=lambda checked: self.setConsoleVisible(checked))

        self._new_action = QAction(
            parent=self,
            iconVisibleInMenu=False,
            text='New',
            toolTip='New Window',
            checkable=False,
            shortcut=QKeySequence.StandardKey.New,
            triggered=lambda: self.new())

        self._open_action = QAction(
            parent=self,
            icon=qta.icon('fa5.folder-open', options=[{'opacity': 1.0}]),
            iconVisibleInMenu=False,
            text='Open',
            toolTip='Open',
            checkable=False,
            shortcut=QKeySequence.StandardKey.Open,
            triggered=lambda: self.open())

        self._save_action = QAction(
            parent=self,
            icon=qta.icon('fa5.save', options=[{'opacity': 1.0}]),
            iconVisibleInMenu=False,
            text='Save',
            toolTip='Save',
            checkable=False,
            shortcut=QKeySequence.StandardKey.Save,
            triggered=lambda: self.save())

        self._save_as_action = QAction(
            parent=self,
            icon=qta.icon('fa5.save', options=[{'opacity': 1.0}]),
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
        self._view_menu.addAction(self._toggle_console_action)
        self._view_menu.addSeparator()
        self._view_menu.addAction(self._about_action)
        self._view_menu.addAction(self._settings_action)
        self._view_menu.addAction(self._refresh_action)

        self._window_menu = menubar.addMenu('Window')
        self._window_menu.addAction('Combine All')
        self._window_menu.addSeparator()
        self._window_menu.addAction('Separate First Level Children')
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

    window = XarrayDataTreeViewer()
    window.show()
    dt = xr.open_datatree('examples/ERPdata.nc', engine='h5netcdf')
    dt['eggs'] = dt['EEG'] * 10
    window.setDatatree(dt)

    app.exec()


if __name__ == '__main__':
    test_live()