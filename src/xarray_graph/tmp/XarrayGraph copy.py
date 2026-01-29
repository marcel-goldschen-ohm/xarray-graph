""" PyQt widget for viewing/analyzing (x,y) slices of a Xarray DataTree.

TODO:
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
from xarray_graph.utils import xarray_utils
from xarray_graph.tree import XarrayDataTreeItem, XarrayDataTreeModel, XarrayDataTreeView, KeyValueTreeView
from xarray_graph.widgets import IPythonConsole, CollapsibleSectionsSplitter
from xarray_graph.graph import FilterControlPanel, CurveFitControlPanel, MeasureControlPanel


class XarrayGraph(QMainWindow):
    """ PyQt widget for viewing/analyzing (x,y) slices of a Xarray DataTree.
    """

    # global list of all XarrayGraph top level windows
    _windows: list[XarrayGraph] = []

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

        title = xarray_utils.unique_name('Untitled', [w.windowTitle() for w in XarrayGraph._windows])
        self.setWindowTitle(title)

        self._init_componenets()
        self._init_actions()
        self._init_menubar()
        self._init_top_toolbar()
        self._init_left_toolbar()

        # layout
        width = self.sizeHint().width()
        height = self.sizeHint().height()

        self._control_panel_splitter = CollapsibleSectionsSplitter()
        self._control_panel_splitter.addSection(self._datatree_action.text(), self._datatree_view)
        self._control_panel_splitter.addSection(self._ROIs_action.text(), self._ROIs_view)
        self._control_panel_splitter.addSection(self._filter_action.text(), self._filter_controls)
        self._control_panel_splitter.addSection(self._curve_fit_action.text(), self._curve_fit_controls)
        self._control_panel_splitter.addSection(self._measure_action.text(), self._measure_controls)
        self._control_panel_splitter.addSection(self._notes_action.text(), self._notes_edit)
        self._control_panel_splitter.setFirstSectionHeaderVisible(False)
        self._update_control_panel()

        self._graph_console_splitter = CollapsibleSectionsSplitter()
        self._graph_console_splitter.addSection('Graphs', self._plot_grid)
        self._graph_console_splitter.addSection('Console', self._console)
        self._graph_console_splitter.setFirstSectionHeaderVisible(False)
        self._graph_console_splitter.setSectionExpanded('Console', self._console_action.isChecked())
        self._graph_console_splitter.sectionIsExpandedChanged.connect(self._on_graph_console_splitter_section_expanded_changed)
    
        self._main_hsplitter = QSplitter(Qt.Orientation.Horizontal)
        self._main_hsplitter.addWidget(self._control_panel_splitter)
        self._main_hsplitter.addWidget(self._graph_console_splitter)
        self._main_hsplitter.setSizes([300, width - 300])

        self.setCentralWidget(self._main_hsplitter)

        msg = self._console._one_time_message_on_show
        QTimer.singleShot(300, lambda msg=msg: self._console.printMessage(msg))

        # for testing only
        dt = xr.open_datatree('examples/ERPdata.nc', engine='netcdf4')
        dt['eggs'] = dt['EEG'] * 10
        self.setDatatree(dt)

        # register with global windows list
        XarrayGraph._windows.append(self)
    
    def _init_componenets(self) -> None:
        """ Initialize UI components.
        """

        # datatree view
        self._datatree_view = XarrayDataTreeView()
        self._datatree_view.setDatatree(xr.DataTree())
        self._datatree_view.selectionWasChanged.connect(self._onSelectionChanged)

        # ROIs view
        self._ROIs_view = QTreeView()

        # plot grid
        self._plot_grid = QWidget()

        # console
        self._console = IPythonConsole()
        self._console.execute('import numpy as np', hidden=True)
        self._console.execute('import xarray as xr', hidden=True)
        self._console.addVariable('ui', self) # mostly for debugging
        self._console.executed.connect(self.refresh)
        self._console._one_time_message_on_show = f"""
        ----------------------------------------------------
        Variables:
          dt -> The Xarray DataTree
          ui -> This instance of {self.__class__.__name__}
        Modules loaded at startup:
          numpy as np
          xarray as xr
        ----------------------------------------------------
        """

        # control panels
        self._filter_controls = FilterControlPanel()
        self._curve_fit_controls = CurveFitControlPanel()
        self._measure_controls = MeasureControlPanel()
        self._notes_edit = QTextEdit()
    
    def _init_actions(self) -> None:
        """ Actions.
        """

        self._refresh_action = QAction(
            icon=qta.icon('msc.refresh'),
            iconVisibleInMenu=True,
            text='Refresh',
            toolTip='Refresh UI',
            shortcut = QKeySequence.StandardKey.Refresh,
            triggered=lambda checked: self.refresh()
        )

        self._about_action = QAction(
            iconVisibleInMenu=False,
            text='About',
            toolTip=f'About {self.__class__.__name__}',
            triggered=lambda checked: XarrayGraph.about()
        )

        self._settings_action = QAction(
            icon=qta.icon('msc.gear'),
            iconVisibleInMenu=False,
            text='Settings',
            toolTip='Settings',
            shortcut=QKeySequence.StandardKey.Preferences,
            triggered=lambda checked: self.settings()
        )

        self._console_action = QAction(
            icon=qta.icon('mdi.console'),
            iconVisibleInMenu=True,
            text='Console',
            toolTip='Console',
            checkable=True,
            checked=True,
            shortcut=QKeySequence('`'),
            triggered=lambda checked: self._graph_console_splitter.setSectionExpanded('Console', checked)
        )

        self._new_action = QAction(
            iconVisibleInMenu=False,
            text='New',
            toolTip='New Window',
            checkable=False,
            shortcut=QKeySequence.StandardKey.New,
            triggered=lambda: XarrayGraph.new()
        )

        self._open_action = QAction(
            icon=qta.icon('fa5.folder-open'),
            iconVisibleInMenu=False,
            text='Open',
            toolTip='Open',
            checkable=False,
            shortcut=QKeySequence.StandardKey.Open,
            triggered=lambda: XarrayGraph.open()
        )

        self._save_action = QAction(
            icon=qta.icon('fa5.save'),
            iconVisibleInMenu=False,
            text='Save',
            toolTip='Save',
            checkable=False,
            shortcut=QKeySequence.StandardKey.Save,
            triggered=lambda: self.save()
        )

        self._save_as_action = QAction(
            icon=qta.icon('fa5.save'),
            iconVisibleInMenu=False,
            text='Save As',
            toolTip='Save As',
            checkable=False,
            shortcut=QKeySequence.StandardKey.SaveAs,
            triggered=lambda: self.saveAs()
        )

        self._home_action = QAction(
            icon=qta.icon('mdi.home'),
            iconVisibleInMenu=False,
            text='Home',
            toolTip='Autoscale',
            triggered=lambda: self.autoscale()
        )

        self._draw_ROI_action = QAction(
            icon=qta.icon('mdi.arrow-expand-horizontal'),
            iconVisibleInMenu=False,
            text='ROI', 
            toolTip='Create range ROI with mouse click+drag.',
            checkable=True, 
            checked=False,
            shortcut=QKeySequence('R'),
            # triggered=lambda: self._toggle_drawing_ROIs()
        )
        
        self._datatree_action = QAction(
            icon=qta.icon('mdi.file-tree'),
            iconVisibleInMenu=False,
            text='Data',
            toolTip='DataTree',
            checkable=True, 
            checked=True,
            triggered=lambda checked: self._update_control_panel()
        )

        self._ROIs_action = QAction(
            icon=qta.icon('mdi.arrow-expand-horizontal'),
            iconVisibleInMenu=False,
            text='ROIs', 
            toolTip='ROIs',
            checkable=True, 
            checked=True,
            triggered=lambda checked: self._update_control_panel()
        )

        self._filter_action = QAction(
            icon=qta.icon('mdi.sine-wave'),
            # icon=get_icon('ph.waves'), 
            # icon=get_icon('mdi.waveform'), 
            iconVisibleInMenu=False,
            text='Filter', 
            toolTip='Filter', 
            checkable=True, 
            checked=False,
            triggered=lambda checked: self._update_control_panel()
        )

        self._curve_fit_action = QAction(
            icon=qta.icon('mdi.chart-bell-curve-cumulative'),
            iconVisibleInMenu=False,
            text='Curve Fit', 
            toolTip='Curve Fit', 
            checkable=True, 
            checked=False,
            triggered=lambda checked: self._update_control_panel()
        )

        self._measure_action = QAction(
            parent=self, 
            icon=qta.icon('mdi.chart-scatter-plot'),
            iconVisibleInMenu=False,
            text='Measure', 
            toolTip='Measure', 
            checkable=True, 
            checked=False,
            triggered=lambda checked: self._update_control_panel()
        )

        self._notes_action = QAction(
            parent=self, 
            icon=qta.icon('mdi6.text-box-edit-outline'),
            iconVisibleInMenu=False,
            text='Notes', 
            toolTip='Notes', 
            checkable=True, 
            checked=False,
            triggered=lambda checked: self._update_control_panel()
        )
    
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
        self._window_menu.addAction('Combine All', XarrayGraph.combineWindows)
        self._window_menu.addAction('Separate First Level Groups', self.separateFirstLevelGroups)
        self._window_menu.addSeparator()
        self._window_menu.addAction('Bring All to Front')
        self._before_windows_list_action: QAction = self._window_menu.addSeparator()
        self._windows_list_action_group = QActionGroup(self)
        self._windows_list_action_group.setExclusive(True)

    def _init_top_toolbar(self) -> None:
        """ Top toolbar.
        """

        self._top_toolbar = QToolBar()
        self._top_toolbar.setOrientation(Qt.Orientation.Horizontal)
        self._top_toolbar.setStyleSheet("QToolBar{spacing:2px;}")
        self._top_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self._top_toolbar.setIconSize(QSize(24, 24))
        self._top_toolbar.setMovable(False)
        self._top_toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self._top_toolbar.setStyleSheet("QToolButton:checked { background-color: rgb(105, 136, 176); }")

        self._before_dim_iters_spacer = QWidget()
        self._before_dim_iters_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self._top_toolbar.addAction(self._open_action)
        self._top_toolbar.addAction(self._save_as_action)
        self._top_toolbar.addSeparator()
        # self._top_toolbar.addAction(self._filter_action)
        # self._top_toolbar.addAction(self._curve_fit_action)
        # self._top_toolbar.addAction(self._measure_action)
        # self._top_toolbar.addAction(self._notes_action)
        # self._top_toolbar.addSeparator()
        
        self._before_dim_iters_spacer_action = self._top_toolbar.addWidget(self._before_dim_iters_spacer)
        self._after_dim_iters_separator_action = self._top_toolbar.addSeparator()
        self._top_toolbar.addAction(self._draw_ROI_action)
        self._top_toolbar.addAction(self._home_action)

        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._top_toolbar)
    
    def _init_left_toolbar(self) -> None:
        """ Left toolbar.
        """

        self._left_toolbar = QToolBar()
        self._left_toolbar.setOrientation(Qt.Orientation.Vertical)
        self._left_toolbar.setStyleSheet("QToolBar{spacing:2px;}")
        self._left_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self._left_toolbar.setIconSize(QSize(24, 24))
        self._left_toolbar.setMovable(False)
        self._left_toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self._left_toolbar.setStyleSheet("QToolButton:checked { background-color: rgb(105, 136, 176); } QToolButton: sizePolicy {}")

        vspacer = QWidget()
        vspacer.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)

        self._left_toolbar.addAction(self._datatree_action)
        self._left_toolbar.addAction(self._ROIs_action)
        self._left_toolbar.addSeparator()
        self._left_toolbar.addAction(self._filter_action)
        self._left_toolbar.addAction(self._curve_fit_action)
        self._left_toolbar.addAction(self._measure_action)
        self._left_toolbar.addAction(self._notes_action)
        self._left_toolbar.addSeparator()
        self._left_toolbar.addWidget(vspacer)
        # self._left_toolbar.addAction(self._settings_action)
        # self._left_toolbar.addAction(self._toggle_console_action)

        self._left_control_panels_action_group = QActionGroup(self)
        self._left_control_panels_action_group.addAction(self._filter_action)
        self._left_control_panels_action_group.addAction(self._curve_fit_action)
        self._left_control_panels_action_group.addAction(self._measure_action)
        self._left_control_panels_action_group.addAction(self._notes_action)
        self._left_control_panels_action_group.setExclusionPolicy(QActionGroup.ExclusionPolicy.ExclusiveOptional)

        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self._left_toolbar)

    def _on_graph_console_splitter_section_expanded_changed(self, index: int, is_expanded: bool) -> None:
        if index == self._graph_console_splitter.sectionIndex('Console'):
            self._console_action.setChecked(is_expanded)
    
    def _update_control_panel(self) -> None:
        actions: list[QAction] = {
            self._datatree_action,
            self._ROIs_action,
            self._filter_action,
            self._curve_fit_action,
            self._measure_action,
            self._notes_action,
        }
        datatree_visible = self._datatree_action.isChecked()
        has_visible = datatree_visible
        has_expanded = datatree_visible
        action: QAction
        for action in actions:
            visible: bool = action.isChecked()
            title: str = action.text()
            self._control_panel_splitter.setSectionVisible(title, visible)
            if visible:
                has_visible = True
                if not has_expanded:
                    has_expanded = self._control_panel_splitter.isSectionExpanded(title)
        self._control_panel_splitter.setVisible(has_visible)
        if has_visible:
            self._control_panel_splitter.setFirstSectionHeaderVisible(not datatree_visible)
            last_visible_spacer: QWidget = None
            spacer: QWidget
            for spacer in self._control_panel_splitter._spacers:
                if spacer.parent() is self._control_panel_splitter:
                    spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                    last_visible_spacer = spacer
            if not has_expanded:
                last_visible_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    
    def datatree(self) -> xr.DataTree:
        return self._datatree_view.datatree()
    
    def setDatatree(self, datatree: xr.DataTree) -> None:
        self._datatree_view.setDatatree(datatree)
        self.refresh()
    
    def sizeHint(self) -> QSize:
        return QSize(1000, 800)

    def refresh(self) -> None:
        datatree = self.datatree()
        self._console.addVariable('dt', datatree)
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
    def new() -> XarrayGraph:
        """ Create new XarrayGraph top level window.
        """
        window = XarrayGraph()
        window.show()
        return window
    
    @staticmethod
    def open(filepath: str | os.PathLike | list[str | os.PathLike] = None, filetype: str = None) -> XarrayGraph | list[XarrayGraph] | None:
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

            windows: list[XarrayGraph] = []
            for path in filepath:
                window = XarrayGraph.open(path, filetype)
                windows.append(window)
            
            if combine == QMessageBox.StandardButton.Yes:
                return XarrayGraph.combineWindows(windows)
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
                for filetype, extensions in XarrayGraph._filetype_extensions_map.items()
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
        window: XarrayGraph = XarrayGraph.new()
        
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
    def windows() -> list[XarrayGraph]:
        """ Get list of all XarrayDataTreeViewer top level windows in z-order from front to back.
        """
        windows = []
        for widget in QApplication.instance().topLevelWidgets():
            if isinstance(widget, XarrayGraph):
                windows.append(widget)
        return windows
    
    @staticmethod
    def combineWindows(windows: list[XarrayGraph] = None) -> XarrayGraph:
        """ Combine windows into one window with multiple top-level groups.
        """
        if windows is None:
            windows = XarrayGraph._windows
        if not windows:
            return
        
        # combined datatree
        combined_datatree = xr.DataTree()
        window: XarrayGraph
        for window in windows:
            title = window.windowTitle()
            combined_datatree[title] = window.datatree()
        
        noncombined_windows: list[XarrayGraph] = [window for window in XarrayGraph._windows if window not in windows]
        noncombined_window_titles: list[str] = [window.windowTitle() for window in noncombined_windows]

        # new combined window
        combined_window: XarrayGraph = XarrayGraph.new()
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
        
        group: xr.DataTree
        for group in groups:
            window: XarrayGraph = XarrayGraph.new()
            window.setWindowTitle(group.name)
            group.orphan()
            window.setDatatree(group)
        
        # close this window
        self.close()
   
    @staticmethod
    def _updateWindowMenus() -> None:
        """ Update Window menu with list of open windows.
        """
        if not XarrayGraph._windows:
            return
        
        top_window: XarrayGraph = QApplication.instance().activeWindow()
        # print(f'Top window: {top_window.windowTitle()}')
        
        window: XarrayGraph
        for window in XarrayGraph._windows:
            # clear old window list
            for action in window._windows_list_action_group.actions():
                window._windows_list_action_group.removeAction(action)
                window._window_menu.removeAction(action)
            
            # make current window list
            for i, list_window in enumerate(XarrayGraph._windows):
                action = QAction(
                    parent=window,
                    text=list_window.windowTitle() or f'Untitled {i}',
                    checkable=True,
                    checked=list_window is top_window,
                    triggered=lambda checked, window=list_window: window.raise_())
                window._windows_list_action_group.addAction(action)
                window._window_menu.addAction(action)
    
    def autoscale(self) -> None:
        pass # TODO
    
    def _onSelectionChanged(self) -> None:
        pass
    
    def changeEvent(self, event: QEvent):
        """ Overrides the changeEvent to catch window activation changes.
        """
        super().changeEvent(event)
        if event.type() == QEvent.ActivationChange:
            if self.isActiveWindow():
                # print(f"\n{self.windowTitle()} gained focus/activation")
                XarrayGraph._updateWindowMenus()
            # else:
            #     print(f"\n{self.windowTitle()} lost focus/activation")
    
    def closeEvent(self, event: QCloseEvent) -> None:
        # Unregister the window from the global list when closed
        XarrayGraph._windows.remove(self)
        XarrayGraph._updateWindowMenus()
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

    # dt = xr.DataTree()
    # dt['air_temperature'] = xr.tutorial.load_dataset('air_temperature')
    # dt['air_temperature/twice air'] = dt['air_temperature/air'] * 2
    # dt['air_temperature/inherits'] = xr.tutorial.load_dataset('air_temperature')
    # dt['air_temperature/inherits/again'] = xr.tutorial.load_dataset('air_temperature')
    # dt['child2'] = xr.DataTree()
    # # dt['child3/grandchild1/greatgrandchild1'] = xr.DataTree()
    # # dt['child3/grandchild1/tiny'] = xr.tutorial.load_dataset('tiny')
    # dt['rasm'] = xr.tutorial.load_dataset('rasm')
    # dt['air_temperature_gradient'] = xr.tutorial.load_dataset('air_temperature_gradient')
    
    window = XarrayGraph()
    # window.setDatatree(dt)

    model: XarrayDataTreeModel = window._datatree_view.model()
    model.setCoordsVisible(True)
    model.setInheritedCoordsVisible(True)
    model.setDetailsColumnVisible(True)
    model.setSharedDataHighlighted(True)
    model.setDebugInfoVisible(False)
    window._datatree_view._updateViewOptionsFromModel()
    window._datatree_view.showAll()
    
    window.show()
    # window.raise_() # !? this cuases havoc with MacOS native menubar (have to click out of app and back in again to get menubar working again)

    app.exec()


if __name__ == '__main__':
    test_live()