""" PyQt widget for viewing/analyzing (x,y) slices of a Xarray DataTree.

TODO:
"""

from __future__ import annotations
import faulthandler
faulthandler.enable()
import os
from copy import copy, deepcopy
from pathlib import Path
import numpy as np
import xarray as xr
import zarr
import cftime

from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
from qtconsole.rich_jupyter_widget import RichJupyterWidget
from qtconsole.inprocess import QtInProcessKernelManager
import pyqtgraph as pg
from xarray_graph.utils import xarray_utils
from xarray_graph.utils import *
from xarray_graph.tree import XarrayDataTreeItem, XarrayDataTreeModel, XarrayDataTreeView, KeyValueTreeView, AnnotationTreeItem, AnnotationTreeModel, AnnotationTreeView
from xarray_graph.widgets import CollapsibleSectionsSplitter, MultiValueSpinBox
from xarray_graph.graph import FilterControlPanel, CurveFitControlPanel, MeasureControlPanel
import xarray_graph.graph.pyqtgraph_ext as pgx


ROI_KEY = '_ROI_'
MASK_KEY = '_mask_'
CURVE_FIT_KEY = '_curve_fit_'
NOTES_KEY = '_notes_'
MASK_COLOR = '(200, 200, 200)'


class XarrayGraph(QMainWindow):
    """ PyQt widget for viewing/analyzing (x,y) slices of a Xarray DataTree.
    """

    # global list of all XarrayGraph top level windows
    _windows: list[XarrayGraph] = []
    _windows_dict: dict[str, XarrayGraph] = {} # for access by window title

    # global console (will be initialized with kernel in first instance, see _init_componenets)
    console = None

    _filetype_extensions_map: dict[str, list[str]] = {
        'Zarr Directory': [''],
        'Zarr Zip': ['.zip'],
        'NetCDF': ['.nc'],
        'HDF5': ['.h5', '.hdf5'],
    }

    _default_settings = {
        'icon size': 24,
        'line width': 1,
        'axis label font size': 12,
        'axis tick font size': 11,
        'ROI font size': 10,
        'max default tile size': 10,
    }
    _settings = deepcopy(_default_settings)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # settings
        if 'text color' not in self._default_settings:
            palette = QApplication.instance().palette()
            text_color: QColor = palette.color(QPalette.Active, QPalette.Text)
            XarrayGraph._default_settings['text color'] = text_color
            XarrayGraph._settings['text color'] = text_color

        self._xdim: str | None = None
        self._dim_iter_widgets: dict[str, dict] = {}

        # plot grid [variable, row, column]
        self._plots = np.empty((0,0,0), dtype=object)

        title = xarray_utils.unique_name('Untitled', [w.windowTitle() for w in XarrayGraph._windows])
        self.setWindowTitle(title)

        self._init_global_console()
        self._init_componenets()
        self._init_actions()
        self._init_menubar()
        self._init_top_toolbar()
        self._init_left_toolbar()

        # layout
        width = self.sizeHint().width()
        height = self.sizeHint().height()

        # self._datatree_ROIs_splitter = CollapsibleSectionsSplitter()
        # self._datatree_ROIs_splitter.addSection('DataTree', self._datatree_view)
        # self._datatree_ROIs_splitter.addSection('ROIs', self._ROIs_view)
        # self._datatree_ROIs_splitter.setFirstSectionHeaderVisible(False)

        self._datatree_ROIs_splitter = QSplitter(Qt.Orientation.Vertical)
        self._datatree_ROIs_splitter.addWidget(self._datatree_view)
        self._datatree_ROIs_splitter.addWidget(self._ROIs_view)

        self._control_panel = QStackedWidget()
        self._control_panel.addWidget(self._datatree_ROIs_splitter)
        self._control_panel.addWidget(self._filter_controls)
        self._control_panel.addWidget(self._curve_fit_controls)
        self._control_panel.addWidget(self._measure_controls)
        self._control_panel.addWidget(self._notes_edit)
        self._control_panel.setCurrentWidget(self._datatree_ROIs_splitter)

        self._data_var_views_splitter = QSplitter(Qt.Orientation.Vertical)
    
        self._main_hsplitter = QSplitter(Qt.Orientation.Horizontal)
        self._main_hsplitter.addWidget(self._control_panel)
        self._main_hsplitter.addWidget(self._data_var_views_splitter)

        self.setCentralWidget(self._main_hsplitter)

        self._datatree_ROIs_splitter.setSizes([height - 300, 300])
        self._main_hsplitter.setSizes([300, width - 300])
        
        # register with global windows list
        XarrayGraph._windows.append(self)
        XarrayGraph._windows_dict[self.windowTitle()] = self
        self.windowTitleChanged.connect(XarrayGraph._updateWindowsDict)
    
    def _init_global_console(self) -> None:
        """ Initialize UI components.
        """

        # global console with kernel (shared across all windows)
        if XarrayGraph.console is None:
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
            console.executed.connect(XarrayGraph.refreshAllWindows)
            XarrayGraph.console = console
    
    def _init_componenets(self) -> None:
        """ Initialize UI components.
        """

        # datatree view
        model = XarrayDataTreeModel()
        model.setCoordsVisible(False)
        model.setInheritedCoordsVisible(False)
        model.setDetailsColumnVisible(False)
        model.setSharedDataHighlighted(False)
        model.setDebugInfoVisible(False)
        model.setDatatree(xr.DataTree())
        self._datatree_view = XarrayDataTreeView()
        self._datatree_view.setModel(model)
        self._datatree_view.selectionWasChanged.connect(self._on_datatree_selection_changed)

        # ROIs view
        model = AnnotationTreeModel()
        model.setColumnLabels(['ROIs', 'Type'])
        model.setTypesColumnVisible(False)
        model.setAnnotations([])
        self._ROIs_view = AnnotationTreeView()
        self._ROIs_view.setModel(model)
        self._ROIs_view.selectionWasChanged.connect(self._on_ROI_selection_changed)

        # plot grid
        self._plot_grid = QWidget()

        # control panels
        self._filter_controls = FilterControlPanel()
        self._curve_fit_controls = CurveFitControlPanel()
        self._measure_controls = MeasureControlPanel()
        self._notes_edit = QTextEdit()

        # settings
        self._linewidth_spinbox = QSpinBox()
        self._linewidth_spinbox.setValue(self._settings['line width'])
        self._linewidth_spinbox.setMinimum(1)
        self._linewidth_spinbox.valueChanged.connect(self._update_plot_data)

        self._axis_label_fontsize_spinbox = QSpinBox()
        self._axis_label_fontsize_spinbox.setValue(self._settings['axis label font size'])
        self._axis_label_fontsize_spinbox.setMinimum(1)
        self._axis_label_fontsize_spinbox.setSuffix('pt')
        self._axis_label_fontsize_spinbox.valueChanged.connect(self._update_plot_axis_labels)

        self._axis_tick_fontsize_spinbox = QSpinBox()
        self._axis_tick_fontsize_spinbox.setValue(self._settings['axis tick font size'])
        self._axis_tick_fontsize_spinbox.setMinimum(1)
        self._axis_tick_fontsize_spinbox.setSuffix('pt')
        self._axis_tick_fontsize_spinbox.valueChanged.connect(self._update_plot_axis_tick_font)

        self._ROI_fontsize_spinbox = QSpinBox()
        self._ROI_fontsize_spinbox.setValue(self._settings['ROI font size'])
        self._ROI_fontsize_spinbox.setMinimum(1)
        self._ROI_fontsize_spinbox.setSuffix('pt')
        # self._ROI_fontsize_spinbox.valueChanged.connect(self._update_ROI_font)

        self._toolbar_iconsize_spinbox = QSpinBox()
        self._toolbar_iconsize_spinbox.setValue(self._settings['icon size'])
        self._toolbar_iconsize_spinbox.setMinimum(16)
        self._toolbar_iconsize_spinbox.setMaximum(64)
        self._toolbar_iconsize_spinbox.setSingleStep(8)
        self._toolbar_iconsize_spinbox.valueChanged.connect(self._update_icon_size)
        
        self._settings_panel = QWidget()
        self._settings_panel.setWindowTitle('Settings')
        form = QFormLayout(self._settings_panel)
        form.setContentsMargins(5, 5, 5, 5)
        form.setSpacing(5)
        form.setHorizontalSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.addRow('Line width', self._linewidth_spinbox)
        form.addRow('Axis label size', self._axis_label_fontsize_spinbox)
        form.addRow('Axis tick label size', self._axis_tick_fontsize_spinbox)
        form.addRow('ROI text size', self._ROI_fontsize_spinbox)
        form.addRow('Icon size', self._toolbar_iconsize_spinbox)
    
    def _init_actions(self) -> None:
        """ Actions.
        """
        color_on: QColor = self._settings['text color']
        color_off = QColor(color_on)
        color_off.setAlphaF(0.5)

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
            icon=qta.icon('msc.gear', color=color_off, color_on=color_on),
            iconVisibleInMenu=False,
            text='Settings',
            toolTip='Settings',
            shortcut=QKeySequence.StandardKey.Preferences,
            triggered=lambda checked: self.settings()
        )

        self._console_action = QAction(
            icon=qta.icon('mdi.console', color=color_off, color_on=color_on),
            iconVisibleInMenu=True,
            text='Console',
            toolTip='Console',
            checkable=False,
            shortcut=QKeySequence('`'),
            triggered=lambda checked: self.setConsoleVisible(True)
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
            icon=qta.icon('fa5.folder-open', color=color_off, color_on=color_on),
            iconVisibleInMenu=False,
            text='Open',
            toolTip='Open',
            checkable=False,
            shortcut=QKeySequence.StandardKey.Open,
            triggered=lambda: XarrayGraph.open()
        )

        self._save_action = QAction(
            icon=qta.icon('fa5.save', color=color_off, color_on=color_on),
            iconVisibleInMenu=False,
            text='Save',
            toolTip='Save',
            checkable=False,
            shortcut=QKeySequence.StandardKey.Save,
            triggered=lambda: self.save()
        )

        self._save_as_action = QAction(
            icon=qta.icon('fa5.save', color=color_off, color_on=color_on),
            iconVisibleInMenu=False,
            text='Save As',
            toolTip='Save As',
            checkable=False,
            shortcut=QKeySequence.StandardKey.SaveAs,
            triggered=lambda: self.saveAs()
        )

        self._home_action = QAction(
            icon=qta.icon('mdi.home', color=color_off, color_on=color_on),
            iconVisibleInMenu=False,
            text='Home',
            toolTip='Autoscale (A)',
            shortcut=QKeySequence('A'),
            triggered=lambda: self.autoscale()
        )

        self._draw_ROI_action = QAction(
            icon=qta.icon('mdi.arrow-expand-horizontal', color=color_off, color_on=color_on),
            iconVisibleInMenu=False,
            text='ROI', 
            toolTip='Create range ROI with mouse click+drag (R).',
            checkable=True, 
            checked=False,
            shortcut=QKeySequence('R'),
            triggered=lambda: self._on_draw_ROI_button_clicked()
        )
        
        self._data_action = QAction(
            icon=qta.icon('mdi.file-tree', color=color_off, color_on=color_on),
            iconVisibleInMenu=False,
            text='Data',
            toolTip='DataTree',
            checkable=True, 
            checked=True,
            triggered=lambda checked: self._update_control_panel()
        )

        # self._ROIs_action = QAction(
        #     icon=qta.icon('mdi.arrow-expand-horizontal', color=icon_color_off, color_on=icon_color_on),
        #     iconVisibleInMenu=False,
        #     text='ROIs', 
        #     toolTip='ROIs',
        #     checkable=True, 
        #     checked=True,
        #     triggered=lambda checked: self._update_control_panel()
        # )

        self._filter_action = QAction(
            icon=qta.icon('mdi.sine-wave', color=color_off, color_on=color_on),
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
            icon=qta.icon('mdi.chart-bell-curve-cumulative', color=color_off, color_on=color_on),
            iconVisibleInMenu=False,
            text='Curve Fit', 
            toolTip='Curve Fit', 
            checkable=True, 
            checked=False,
            triggered=lambda checked: self._update_control_panel()
        )

        self._measure_action = QAction(
            parent=self, 
            icon=qta.icon('mdi.chart-scatter-plot', color=color_off, color_on=color_on),
            iconVisibleInMenu=False,
            text='Measure', 
            toolTip='Measure', 
            checkable=True, 
            checked=False,
            triggered=lambda checked: self._update_control_panel()
        )

        self._notes_action = QAction(
            parent=self, 
            icon=qta.icon('mdi6.text-box-edit-outline', color=color_off, color_on=color_on),
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
        self._window_menu.addAction('Separate First Level Groups', self.separateFirstLevelGroupsIntoNewWindows)
        self._window_menu.addSeparator()
        self._window_menu.addAction('Bring All to Front')
        self._before_windows_list_action: QAction = self._window_menu.addSeparator()
        self._windows_list_action_group = QActionGroup(self)
        self._windows_list_action_group.setExclusive(True)

    def _init_top_toolbar(self) -> None:
        """ Top toolbar.
        """

        icon_size = self._settings.get('icon size', 24)

        self._top_toolbar = QToolBar()
        self._top_toolbar.setOrientation(Qt.Orientation.Horizontal)
        self._top_toolbar.setStyleSheet("QToolBar{spacing:2px;}")
        self._top_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self._top_toolbar.setIconSize(QSize(icon_size, icon_size))
        self._top_toolbar.setMovable(False)
        self._top_toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        # self._top_toolbar.setStyleSheet("QToolButton:checked { background-color: rgb(105, 136, 176); }")

        self._before_dim_iters_spacer = QLabel()
        self._before_dim_iters_spacer.setAlignment(Qt.AlignmentFlag.AlignCenter)
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

        icon_size = self._settings.get('icon size', 24)

        self._left_toolbar = QToolBar()
        self._left_toolbar.setOrientation(Qt.Orientation.Vertical)
        self._left_toolbar.setStyleSheet("QToolBar{spacing:2px;}")
        self._left_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self._left_toolbar.setIconSize(QSize(icon_size, icon_size))
        self._left_toolbar.setMovable(False)
        self._left_toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        # self._left_toolbar.setStyleSheet("QToolButton:checked { background-color: rgb(105, 136, 176); }")

        vspacer = QWidget()
        vspacer.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)

        self._left_toolbar.addAction(self._data_action)
        self._left_toolbar.addAction(self._filter_action)
        self._left_toolbar.addAction(self._curve_fit_action)
        self._left_toolbar.addAction(self._measure_action)
        self._left_toolbar.addAction(self._notes_action)
        self._left_toolbar.addWidget(vspacer)
        self._left_toolbar.addAction(self._console_action)
        self._left_toolbar.addAction(self._settings_action)

        self._control_panel_action_group = QActionGroup(self)
        self._control_panel_action_group.addAction(self._data_action)
        self._control_panel_action_group.addAction(self._filter_action)
        self._control_panel_action_group.addAction(self._curve_fit_action)
        self._control_panel_action_group.addAction(self._measure_action)
        self._control_panel_action_group.addAction(self._notes_action)
        self._control_panel_action_group.setExclusionPolicy(QActionGroup.ExclusionPolicy.ExclusiveOptional)

        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self._left_toolbar)

    @staticmethod
    def isConsoleVisible() -> bool:
        return XarrayGraph.console.isVisible()
    
    @staticmethod
    def setConsoleVisible(visible: bool) -> None:
        old_visible = XarrayGraph.isConsoleVisible()
        XarrayGraph.console.setVisible(visible)
        if visible and not old_visible:
            XarrayGraph.console.kernel_manager.kernel.shell.push({'windows': XarrayGraph._windows_dict})
            import textwrap
            msg = """
            ----------------------------------------------------
            Modules loaded at startup:
              numpy as np
              xarray as xr
            
            Variables:
              windows -> Dict of all XarrayGraph windows keyed on window titles.

            e.g., To access the datatree for the window titled 'MyData':
              windows['MyData'].datatree()
            ----------------------------------------------------
            """
            msg = textwrap.dedent(msg).strip()
            XarrayGraph.console._append_plain_text(msg + '\n', before_prompt=True)
        if visible and old_visible:
            XarrayGraph.console.raise_()
    
    def _update_control_panel(self) -> None:
        selected_action = self._control_panel_action_group.checkedAction()
        if selected_action is None:
            self._control_panel.setVisible(False)
            return
        action_to_widget = {
            self._data_action: self._datatree_ROIs_splitter,
            self._filter_action: self._filter_controls,
            self._curve_fit_action: self._curve_fit_controls,
            self._measure_action: self._measure_controls,
            self._notes_action: self._notes_edit,
        }
        self._control_panel.setCurrentWidget(action_to_widget[selected_action])
        self._control_panel.setVisible(True)
    
    def datatree(self) -> xr.DataTree:
        return self._datatree_view.datatree()
    
    def setDatatree(self, datatree: xr.DataTree) -> None:
        if datatree is None:
            datatree = xr.DataTree()
        self._datatree_view.setDatatree(datatree)
        self.refresh()
    
    def xdim(self) -> str | None:
        return self._xdim
    
    def setXDim(self, xdim: str | None) -> None:
        self._xdim = xdim
        self.refresh()
    
    def tileDimension(self, dim: str, orientation: Qt.Orientation | None) -> None:
        """ Tile plots along coordinate dimension.
        """
        if getattr(self, '_vertical_tile_dimension', None) == dim:
            self._vertical_tile_dimension = None
        if getattr(self, '_horizontal_tile_dimension', None) == dim:
            self._horizontal_tile_dimension = None
        
        if orientation == Qt.Orientation.Vertical:
            self._vertical_tile_dimension = dim
        elif orientation == Qt.Orientation.Horizontal:
            self._horizontal_tile_dimension = dim
        
        if orientation is not None:
            selected_coords = self._selection_visible_coords[dim]
            if selected_coords.size == 1:
                max_default_tile_size = self._settings.get('max default tile size', self._default_settings['max default tile size'])
                dim_coords = self._selection_combined_coords[dim]
                if dim_coords.size <= max_default_tile_size:
                    selected_coords = dim_coords
                else:
                    i = np.where(dim_coords == selected_coords[0])[0][0]
                    stop = min(i + max_default_tile_size, dim_coords.size)
                    start = max(0, stop - max_default_tile_size)
                    selected_coords = dim_coords[start:stop]
                dim_iter_widget: DimIterWidget = self._dim_iter_widgets[dim]['widget']
                dim_iter_widget.setSelectedCoords(selected_coords.values)
        
        self.refresh()
    
    def sizeHint(self) -> QSize:
        return QSize(1000, 800)

    @staticmethod
    def refreshAllWindows():
        for window in XarrayGraph._windows:
            window.refresh()
    
    def refresh(self) -> None:
        self._datatree_view.refresh()
        self._on_datatree_selection_changed()
    
    def replot(self) -> None:
        """ Update all plots.
        """
        self._clear_plot_ROIs()
        self._update_plot_data()
        self._update_plot_ROIs()
    
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
        dlg = QDialog(self)
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.setWindowTitle('Settings')
        layout = QVBoxLayout(dlg)
        layout.addWidget(self._settings_panel)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, Qt.Orientation.Horizontal)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        dlg.exec()
        self._settings_panel.setParent(None)
    
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
    
    def separateFirstLevelGroupsIntoNewWindows(self) -> None:
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
    
    @staticmethod
    def _updateWindowsDict() -> None:
        XarrayGraph._windows_dict = {win.windowTitle(): win for win in XarrayGraph._windows}
        XarrayGraph.console.kernel_manager.kernel.shell.push({'windows': XarrayGraph._windows_dict})
    
    def autoscale(self) -> None:
        """ Autoscale all plots while preserving axis linking.
        """
        if not hasattr(self, '_plots'):
            return
        xlinked_views = []
        xlinked_range = []
        n_vars, n_rows, n_cols = self._plots.shape
        for i in range(n_vars):
            ylinked_views = []
            ylinked_range = []
            for row in range(n_rows):
                for col in range(n_cols):
                    plot = self._plots[i, row, col]
                    view = plot.getViewBox()
                    xlinked_view = view.linkedView(view.XAxis)
                    ylinked_view = view.linkedView(view.YAxis)
                    if (xlinked_view is None) and (ylinked_view is None):
                        view.enableAutoRange()
                    elif xlinked_view is None:
                        view.enableAutoRange(axis=view.XAxis)
                    elif ylinked_view is None:
                        view.enableAutoRange(axis=view.YAxis)
                    view.updateAutoRange()

                    if xlinked_view is not None:
                        xlim, ylim = view.childrenBounds()
                        # print(xlim, ylim)
                        if xlim is not None:
                            xlinked_range.append(xlim)
                        if xlinked_view not in xlinked_views:
                            xlinked_views.append(xlinked_view)
                            xlim, ylim = xlinked_view.childrenBounds()
                            if xlim is not None:
                                xlinked_range.append(xlim)
                    if ylinked_view is not None:
                        xlim, ylim = view.childrenBounds()
                        if ylim is not None:
                            ylinked_range.append(ylim)
                        if ylinked_view not in ylinked_views:
                            ylinked_views.append(ylinked_view)
                            xlim, ylim = ylinked_view.childrenBounds()
                            if ylim is not None:
                                ylinked_range.append(ylim)
            
            if ylinked_views:
                ylinked_range = np.array(ylinked_range)
                ymin = np.min(ylinked_range)
                ymax = np.max(ylinked_range)
                for view in ylinked_views:
                    view.setYRange(ymin, ymax)
        
        if xlinked_views:
            xlinked_range = np.array(xlinked_range)
            xmin = np.min(xlinked_range)
            xmax = np.max(xlinked_range)
            for view in xlinked_views:
                view.setXRange(xmin, xmax)
    
    def _on_datatree_changed(self) -> None:
        self.refresh()
    
    def _on_xdim_changed(self) -> None:
        self.refresh()
        self.autoscale()
    
    def _on_datatree_selection_changed(self) -> None:
        print('\n'*2, 'v'*50)

        # # for filtering selected data_vars
        # var_filter = self._get_data_var_filter()

        # selected data_vars
        dt: xr.DataTree = self.datatree()
        # selected_datatree_items: list[XarrayDataTreeItem] = self._datatree_view.selectedItems()
        # selected_datatree_paths: list[str] = [item.path for item in selected_datatree_items]
        # selection_datatree = xr.DataTree()
        # for node in dt.subtree:
        #     if node.path in selected_datatree_paths:
        #         for name, data_var in node.data_vars.items():
        #             data_var_path = f'{node.path}/{name}'
        #             selection_datatree[data_var_path] = data_var
        #         continue
        #     for name, data_var in node.data_vars.items():
        #         data_var_path = f'{node.path.rstrip('/')}/{name}'
        #         if data_var_path in selected_datatree_paths:
        #             selection_datatree[data_var_path] = data_var
        # return
        selected_datatree_items: list[XarrayDataTreeItem] = self._datatree_view.selectedItems()
        selected_datatree_paths: list[str] = [item.path for item in selected_datatree_items]
        self._selected_data_var_paths: list[str] = []
        for node in xarray_utils.subtree_depth_first_iter(dt):
            if node.path in selected_datatree_paths:
                for data_var_name in node.data_vars:
                    data_var_path = f'{node.path}/{data_var_name}'
                    self._selected_data_var_paths.append(data_var_path)
                continue
            for data_var_name in node.data_vars:
                data_var_path = f'{node.path.rstrip('/')}/{data_var_name}'
                if data_var_path in selected_datatree_paths:
                    self._selected_data_var_paths.append(data_var_path)
        # print(f'_selected_data_var_paths: {self._selected_data_var_paths}')
        self._selected_data_vars = [dt[path] for path in self._selected_data_var_paths]
        
        # ordered dimensions
        self._selection_ordered_dims = xarray_utils.get_ordered_dims(self._selected_data_vars)

        # try and ensure valid xdim
        if self.xdim() not in self._selection_ordered_dims:
            if self._selection_ordered_dims:
                self._xdim = self._selection_ordered_dims[-1]
        print(f'xdim: {self.xdim()}')
        
        # limit selection to variables with the xdim coordinate
        self._selected_data_var_paths = [path for path in self._selected_data_var_paths if self.xdim() in dt[path].dims]
        self._selected_data_vars = [dt[path] for path in self._selected_data_var_paths]
        self._selection_ordered_dims = xarray_utils.get_ordered_dims(self._selected_data_vars)
        print(f'_selected_data_var_paths: {self._selected_data_var_paths}')
        # print(f'_selection_ordered_dims: {self._selection_ordered_dims}')

        # selection combined coords
        selected_coords = []#var.reset_coords(drop=True).coords for var in selected_vars]
        for data_var in self._selected_data_vars:
            coords_ds = xr.Dataset(
                coords=data_var.coords
                # coords={name: to_base_units(coord) for name, coord in data_var.coords.items()}
            )
            selected_coords.append(coords_ds)
        try:
            self._selection_combined_coords: xr.Dataset = xr.merge(selected_coords, compat='no_conflicts', join='outer')
        except Exception as e:
            # print(f'Error merging coords: {e}')
            self._selection_combined_coords = None
            self._selected_data_var_paths = []
            self._selected_data_vars = []
        print(f'_selection_combined_coords: {self._selection_combined_coords}')
        
        # selection variable names and units
        self._selected_data_var_unique_names = []
        self._selection_units = {}
        for data_var in self._selected_data_vars:
            if data_var.name not in self._selected_data_var_unique_names:
                self._selected_data_var_unique_names.append(data_var.name)
            if data_var.name not in self._selection_units:
                if 'units' in data_var.attrs:
                    self._selection_units[data_var.name] = data_var.attrs['units']
            for dim, coord in data_var.coords.items():
                if dim not in self._selection_units:
                    if 'units' in coord.attrs:
                        self._selection_units[dim] = coord.attrs['units']
        # print(f'_selected_data_var_unique_names: {self._selected_data_var_unique_names}')
        # print(f'_selection_units: {self._selection_units}')
        
        # update toolbar dim iter widgets for selected variables
        self._update_dim_iter_widgets()

        # update ROI tree
        self._update_ROIs_view()

        # update dimension slice selection (this will update the plots)
        self._on_dimension_slice_changed()

        print('^'*50, '\n' *2)
    
    def _on_dimension_slice_changed(self) -> None:
        """ Handle selection changes in dimension iterators.
        """

        # get coords for current slice of selected variables
        iter_coords = {}
        for dim in self._dim_iter_widgets:
            if self._dim_iter_widgets[dim]['active']:
                widget: DimIterWidget = self._dim_iter_widgets[dim]['widget']
                iter_coords[dim] = widget.selectedCoords()
        if iter_coords:
            self._selection_visible_coords: xr.Dataset = self._selection_combined_coords.sel(iter_coords)#, method='nearest')
        else:
            self._selection_visible_coords: xr.Dataset = self._selection_combined_coords
        print(f'_selection_visible_coords: {self._selection_visible_coords}')
        
        # update plot grids
        self._update_plot_grids()

    def _update_dim_iter_widgets(self) -> None:
        """ Update dimension iterator widgets in the top toolbar.
        """
        coords: xr.Dataset = self._selection_combined_coords
        ordered_dims = self._selection_ordered_dims
        vdim = getattr(self, '_vertical_tile_dimension', None)
        hdim = getattr(self, '_horizontal_tile_dimension', None)

        # remove dim iter actions from toolbar
        # items are not deleted, so the current iteration state will be restored if the dim is reselected again
        for dim in self._dim_iter_widgets:
            # block spinbox signals so that _on_index_selection_changed is not called
            # if the spinbox had focus and loses it here
            if 'widget' in self._dim_iter_widgets[dim]:
                widget: DimIterWidget = self._dim_iter_widgets[dim]['widget']
                widget._spinbox.blockSignals(True)
            for value in self._dim_iter_widgets[dim].values():
                if isinstance(value, QAction):
                    self._top_toolbar.removeAction(value)
            self._dim_iter_widgets[dim]['active'] = False
        
        if self._selection_combined_coords is None:
            self._before_dim_iters_spacer.setText('Selected data variables are not aligned.')
            self._before_dim_iters_spacer_action.setVisible(True)
            return
        else:
            self._before_dim_iters_spacer.setText('')
        
        # update or create dim iter widgets and insert actions into toolbar
        iter_dims = [dim for dim in ordered_dims if (dim != self.xdim()) and (coords.sizes[dim] > 1)]
        for dim in iter_dims:
            if dim not in self._dim_iter_widgets:
                widget = DimIterWidget()
                widget.setDim(dim)
                widget._spinbox.indicesChanged.connect(lambda: self._on_dimension_slice_changed())
                widget.xdimChanged.connect(self.setXDim)
                widget.tileChanged.connect(self.tileDimension)
                self._dim_iter_widgets[dim] = {'widget': widget}
            
            widget = self._dim_iter_widgets[dim]['widget']
            widget.setCoords(coords[dim].values)
            widget.updateTileButton(vdim, hdim)

            if 'separatorAction' in self._dim_iter_widgets[dim]:
                action = self._dim_iter_widgets[dim]['separatorAction']
                self._top_toolbar.insertAction(self._after_dim_iters_separator_action, action)
            else:
                action = self._top_toolbar.insertSeparator(self._after_dim_iters_separator_action)
                self._dim_iter_widgets[dim]['separatorAction'] = action

            if 'widgetAction' in self._dim_iter_widgets[dim]:
                action = self._dim_iter_widgets[dim]['widgetAction']
                self._top_toolbar.insertAction(self._after_dim_iters_separator_action, action)
            else:
                action = self._top_toolbar.insertWidget(self._after_dim_iters_separator_action, widget)
                self._dim_iter_widgets[dim]['widgetAction'] = action
            
            self._dim_iter_widgets[dim]['active'] = True
            widget._spinbox.blockSignals(False)
        
        self._before_dim_iters_spacer_action.setVisible(len(iter_dims) == 0)
    
    def _update_plot_grids(self) -> None:
        """ Update plot grids for selected variables and current plot tiling. """

        # one plot grid per selected variable
        n_data_var_names = len(self._selected_data_var_unique_names)
        while self._data_var_views_splitter.count() < n_data_var_names:
            grid = pgx.PlotGrid()
            grid.setHasRegularLayout(True)
            self._data_var_views_splitter.addWidget(grid)
        while self._data_var_views_splitter.count() > n_data_var_names:
            index = self._data_var_views_splitter.count() - 1
            widget = self._data_var_views_splitter.widget(index)
            widget.setParent(None)
            widget.deleteLater()
        
        # grid tiling
        vdim, hdim, vcoords, hcoords = self._tile_dims()
        n_grid_rows, n_grid_cols = 1, 1
        if vdim is not None:
            n_grid_rows = vcoords.size
        if hdim is not None:
            n_grid_cols = hcoords.size

        # tile grids and store plots in array (if needed)
        if not hasattr(self, '_plots') or self._plots.shape != (n_data_var_names, n_grid_rows, n_grid_cols):
            self._plots = np.empty((n_data_var_names, n_grid_rows, n_grid_cols), dtype=object)
            self._plot_grids: list[pgx.PlotGrid] = [self._data_var_views_splitter.widget(i) for i in range(n_data_var_names)]
            for i, grid in enumerate(self._plot_grids):
                data_var_name = self._selected_data_var_unique_names[i]
                if grid.rowCount() != n_grid_rows or grid.columnCount() != n_grid_cols:
                    grid.setGrid(n_grid_rows, n_grid_cols)
                for row in range(grid.rowCount()):
                    for col in range(grid.columnCount()):
                        plot: pgx.Plot = grid.getItem(row, col)
                        self._plots[i, row, col] = plot
                if i == n_data_var_names - 1:
                    grid.setAxisLabelAndTickVisibility(xlabel_rows=[-1], xtick_rows=[-1], ylabel_columns=[0], ytick_columns=[0])
                else:
                    grid.setAxisLabelAndTickVisibility(xlabel_rows=[], xtick_rows=[-1], ylabel_columns=[0], ytick_columns=[0])
                grid.applyRegularLayout()
        
        self._update_plot_metadata()
        self._update_plot_axis_labels()
        self._update_plot_axis_tick_font()
        self._update_plot_axis_links()
        self.replot()

    def _update_plot_metadata(self) -> None:
        """ Update metadata stored in each plot. """

        vdim, hdim, vcoords, hcoords = self._tile_dims()
        n_vars, n_grid_rows, n_grid_cols = self._plots.shape
        for i in range(n_vars):
            var_name = self._selected_data_var_unique_names[i]
            # yunits = self._selection_units.get(var_name, None)
            vis_coords = self._selection_visible_coords.copy(deep=False)  # TODO: may include extra coords? get rid of these?
            
            for row in range(n_grid_rows):
                if vdim is not None:
                    row_coords = vis_coords.sel({vdim: vcoords[row]})
                else:
                    row_coords = vis_coords
                
                for col in range(n_grid_cols):
                    if hdim is not None:
                        plot_coords = row_coords.sel({hdim: hcoords[col]})
                    else:
                        plot_coords = row_coords
                    plot_coords_dict = {dim: arr.values for dim, arr in plot_coords.coords.items() if dim != self.xdim()}
                    
                    plot = self._plots[i, row, col]
                    plot._metadata = {
                        'data_vars': [var_name],
                        'grid_row': row,
                        'grid_col': col,
                        'coords': plot_coords,
                        'non_xdim_coord_permutations': coord_permutations(plot_coords_dict),
                    }
    
    def _update_plot_axis_labels(self) -> None:
        """ Update axis labels for each plot (use settings font). """

        xunits = self._selection_units.get(self.xdim(), None)
        axis_label_style = {'color': 'rgb(0, 0, 0)', 'font-size': f'{self._axis_label_fontsize_spinbox.value()}pt'}

        vdim, hdim, vcoords, hcoords = self._tile_dims()
        n_vars, n_grid_rows, n_grid_cols = self._plots.shape
        for i in range(n_vars):
            var_name = self._selected_data_var_unique_names[i]
            yunits = self._selection_units.get(var_name, None)
            for row in range(n_grid_rows):
                for col in range(n_grid_cols):
                    plot = self._plots[i, row, col]
                    if (i == n_vars - 1) and (row == n_grid_rows - 1):
                        label = self.xdim()
                        if (hdim is not None) and (n_grid_cols > 1):
                            label += f'[{hcoords[col]}]'
                        plot.setLabel('bottom', text=label, units=xunits, **axis_label_style)
                    if col == 0:
                        label = var_name
                        if (vdim is not None) and (n_grid_rows > 1):
                            label += f'[{vcoords[row]}]'
                        plot.setLabel('left', text=label, units=yunits, **axis_label_style)

    def _update_plot_axis_tick_font(self) -> None:
        """ Update axis tick labels for each plot (use settings font). """

        axis_tick_font = QFont()
        axis_tick_font.setPointSize(self._axis_tick_fontsize_spinbox.value())
        
        for plot in self._plots.flatten().tolist():
            plot.getAxis('left').setTickFont(axis_tick_font)
            plot.getAxis('bottom').setTickFont(axis_tick_font)

    def _update_plot_axis_links(self) -> None:
        """ Update axis linking for selected variables and current plot tiling. """

        n_vars, n_grid_rows, n_grid_cols = self._plots.shape
        for i in range(n_vars):
            for row in range(n_grid_rows):
                for col in range(n_grid_cols):
                    plot = self._plots[i, row, col]
                    if (i != 0) or (row != 0) or (col != 0):
                        plot.setXLink(self._plots[0, 0, 0])
                    if (row > 0) or (col > 0):
                        plot.setYLink(self._plots[i, 0, 0])

    def _update_plot_data(self) -> None:
        """ Update graphs in each plot to show current datatree selection.
        """
        print('Updating plot data...')
        dt: xr.DataTree = self.datatree()
        xdim: str = self.xdim()
        if (xdim is None) or (self._selection_combined_coords is None) or (xdim not in self._selection_combined_coords):
            return
        # selection_combined_xdata = self._selection_combined_coords[xdim].values
        # xdtype = selection_combined_xdata.dtype
        
        default_line_width = self._linewidth_spinbox.value()

        # categorical (string) xdim values?
        is_xdim_categorical = False
        all_xticks = None  # will use default ticks
        all_xdata = self._selection_combined_coords[xdim].values
        print('xtype:', type(all_xdata[0]))
        print('xdtype:', all_xdata.dtype)
        if np.issubdtype(all_xdata.dtype, np.datetime64) or isinstance(all_xdata[0], cftime.datetime):
            pass
        elif not np.issubdtype(all_xdata.dtype, np.number):
            is_xdim_categorical = True
            all_xtick_values = np.arange(len(all_xdata))
            all_xtick_labels = all_xdata  # str xdim values
            all_xticks = [list(zip(all_xtick_values, all_xtick_labels))]
        # print(f'xdim: {xdim}, is_xdim_categorical: {is_xdim_categorical}, all_xticks: {all_xticks}')

        axisChanged = False
        
        print('plot grid:', self._plots.shape)
        for plot in self._plots.flatten().tolist():
            view: pgx.View = plot.getViewBox()

            # update bottom axis (datetime or not)
            bottomAxis: pgx.Axis = plot.getAxis('bottom')
            if np.issubdtype(all_xdata.dtype, np.datetime64) or isinstance(all_xdata[0], cftime.datetime):
                if not isinstance(bottomAxis, pg.DateAxisItem):
                    bottomAxis = pg.DateAxisItem(orientation='bottom')
                    plot.setAxisItems({'bottom': bottomAxis})
                    axisChanged = True
            else:
                if isinstance(bottomAxis, pg.DateAxisItem):
                    bottomAxis = pg.AxisItem(orientation='bottom')
                    plot.setAxisItems({'bottom': bottomAxis})
                    axisChanged = True

            # set xticks (in case change between numerical and categorical)
            bottomAxis.setTicks(all_xticks)

            # yunits for all graphs in this plot (set by first graph)
            plot_yunits: str | None = None
            
            # existing graphs in plot
            graphs = [item for item in plot.listDataItems() if isinstance(item, pgx.Graph)]
            data_graphs = [graph for graph in graphs if hasattr(graph, '_metadata') and graph._metadata.get('type', None) == 'data']
            masked_graphs = [graph for graph in graphs if hasattr(graph, '_metadata') and graph._metadata.get('type', None) == 'masked']
            preview_graphs = [graph for graph in graphs if hasattr(graph, '_metadata') and graph._metadata.get('type', None) == 'preview']
            print(f'Existing graphs in plot: {len(graphs)}, data: {len(data_graphs)}, masked: {len(masked_graphs)}, preview: {len(preview_graphs)}')
            
            # update graphs in plot
            data_count = 0
            masked_count = 0
            preview_count = 0
            color_index = 0
            for var_path in self._selected_data_var_paths:
                var_name = var_path.rstrip('/').split('/')[-1]
                if var_name not in plot._metadata['data_vars']:
                    continue
                print(f'Plotting variable at path: {var_path}')
                
                data_var = dt[var_path]#.reset_coords(drop=True)
                # print(f'Plotting variable: {data_var}')
                if xdim not in data_var.coords:
                    continue
                if plot_yunits is None:
                    plot_yunits = data_var.attrs.get('units', None)
                else:
                    data_var_yunits = data_var.attrs.get('units', None)
                    # TODO: handle unit conversion here instead of just assuming same units or no units
                    # if data_var_yunits != plot_yunits:
                    #     data_var = to_units(data_var, plot_yunits)

                node_path = var_path.rstrip('/').rstrip(var_name).rstrip('/')
                node = dt[node_path]
                
                mask = None
                if var_name != MASK_KEY:
                    node_ = node
                    while node_.has_data:
                        if MASK_KEY in node_.data_vars:
                            mask = node_.data_vars[MASK_KEY]
                            break
                        if node_.parent is None:
                            break
                        node_ = node_.parent
                
                non_xdim_coord_permutations = plot._metadata['non_xdim_coord_permutations']
                if len(non_xdim_coord_permutations) == 0:
                    non_xdim_coord_permutations = [{}]
                for coords in non_xdim_coord_permutations:
                    print(f'Plotting with coords: {coords}')
                    if not coords:
                        data_var_slice = data_var
                    else:
                        index_coords = {dim: values for dim, values in coords.items() if dim in data_var.dims}
                        nonindex_coords = {dim: values for dim, values in coords.items() if dim in data_var.coords and dim not in data_var.dims}
                        print(f'index coords: {index_coords}')
                        print(f'nonindex coords: {nonindex_coords}')
                        if index_coords:
                            data_var_slice = data_var.sel(index_coords)
                        else:
                            data_var_slice = data_var
                        for name, coord in nonindex_coords.items():
                            data_var_slice = data_var_slice.where(data_var_slice.coords[name] == coord, drop=True)
                    data_var_slice = data_var_slice.reset_coords(drop=True).squeeze(drop=True)
                    # print(f'data_var_slice: {data_var_slice}')
                    xdim_coord_slice = data_var_slice.coords[xdim]
                    # print(f'xdim_coord_slice: {xdim_coord_slice}')
                    xdata = xdim_coord_slice.values
                    ydata = data_var_slice.values

                    if np.all(np.isnan(ydata)):
                        continue
                    
                    # categorical xdim values?
                    if np.issubdtype(xdata.dtype, np.datetime64) or isinstance(xdata[0], cftime.datetime):
                        xdata = xdata.astype('datetime64[s]').astype(int)
                    elif not np.issubdtype(xdata.dtype, np.number):
                        intersect, xdata_indices, all_xtick_labels_indices = np.intersect1d(xdata, all_xtick_labels, assume_unique=True, return_indices=True)
                        xdata = np.sort(all_xtick_labels_indices)
                        xdim_coord_slice = data_var_slice.coords[xdim].copy(data=xdata)
                    
                    # filter data?
                    if False:#self._filterLivePreviewCheckbox.isChecked():
                        filtered_var_slice = self._filter(xdim_coord_slice, data_var_slice)
                        if filtered_var_slice is not None:
                            ydata = filtered_var_slice.values
                    
                    # mask data?
                    mask_slice = None
                    if (mask is not None) and (var_name != MASK_KEY):
                        mask_slice = mask.sel(coords)
                        if not self.isMaskedVisible():
                            xdata = xdata.copy() # don't overwrite original data
                            ydata = ydata.copy() # don't overwrite original data
                            xdata[mask_slice.values] = np.nan
                            ydata[mask_slice.values] = np.nan
                    
                    print(xdata, ydata)
                    
                    # graph data
                    if len(data_graphs) > data_count:
                        # update existing data in plot
                        data_graph = data_graphs[data_count]
                        data_graph.setData(x=xdata, y=ydata)
                    else:
                        # add new data to plot
                        data_graph = pgx.Graph(x=xdata, y=ydata)
                        plot.addItem(data_graph)
                        data_graphs.append(data_graph)
                    data_count += 1
                    # print('data_count:', data_count)
                    
                    data_graph._metadata = {
                        'type': 'data',
                        'data': data_var_slice,
                        'mask': mask_slice,
                        'path': var_path,
                        'coords': coords,
                    }

                    data_graph.setZValue(1)

                    # graph name is path plus non-xdim coords
                    name = var_path
                    if coords:
                        name += '[' + ','.join([f'{dim}={coords[dim]}' for dim in coords]) + ']'
                    data_graph.setName(name)

                    # graph style
                    style: pgx.GraphStyle = data_graph.graphStyle()
                    style['color'] = view.colorAtIndex(color_index)
                    style['lineWidth'] = default_line_width
                    if (len(ydata) == 1) or (np.sum(~np.isnan(ydata)) == 1):
                        # ensure single point shown with marker
                        if 'marker' not in style:
                            style['marker'] = 'o'
                    data_graph.setGraphStyle(style)

                    # show masked in different color
                    if (mask is not None) and (var_name != MASK_KEY) and self.isMaskedVisible():
                        xdata = xdata.copy() # don't overwrite original data
                        ydata = ydata.copy() # don't overwrite original data
                        xdata[~mask_slice.values] = np.nan
                        ydata[~mask_slice.values] = np.nan

                        if len(masked_graphs) > masked_count:
                            # update existing data in plot
                            masked_graph = masked_graphs[masked_count]
                            masked_graph.setData(x=xdata, y=ydata)
                        else:
                            # add new data to plot
                            masked_graph = pgx.Graph(x=xdata, y=ydata)
                            plot.addItem(masked_graph)
                            masked_graphs.append(masked_graph)
                        masked_count += 1
                        
                        masked_graph._metadata = {
                            'type': 'masked',
                            'data': data_var_slice,
                            'mask': mask_slice,
                            'path': var_path,
                            'coords': coords,
                        }

                        data_graph._metadata['masked graph'] = masked_graph

                        masked_graph.setZValue(1)
                        masked_graph.setName(name + ' masked')
                        style['color'] = MASK_COLOR
                        masked_graph.setGraphStyle(style)
                
                # next dataset (tree path)
                color_index += 1
            
            # remove extra graph items from plot
            cleanup_graphs = [(data_graphs, data_count), (masked_graphs, masked_count)]
            # if not self._curve_fit_live_preview_enabled() and not self._measurement_live_preview_enabled():
            #     cleanup_graphs += [(preview_graphs, preview_count)]
            for graphs, count in cleanup_graphs:
                while len(graphs) > count:
                    graph = graphs.pop()
                    plot.removeItem(graph)
                    graph.deleteLater()
        
        # if self._curve_fit_live_preview_enabled():
        #     self._update_curve_fit_preview()
        # elif self._measurement_live_preview_enabled():
        #     self._update_measurement_preview()

        if axisChanged:
            self._update_plot_axis_labels()
            self._update_plot_axis_tick_font()
            self._update_plot_axis_links()

    def _update_icon_size(self) -> None:
        """ Apply settings icon options to all toolbar icons.
        """
        size = self._toolbar_iconsize_spinbox.value()
        icon_size = QSize(size, size)
        for toolbar in [self._top_toolbar, self._left_toolbar]:
            toolbar.setIconSize(icon_size)

    def _tile_dims(self) -> tuple[str | None, str | None, np.ndarray | None, np.ndarray | None]:
        vdim = getattr(self, '_vertical_tile_dimension', None)
        hdim = getattr(self, '_horizontal_tile_dimension', None)
        coords = self._selection_visible_coords
        if coords is None:
            vdim, hdim = None, None
        else:
            if vdim:
                if (vdim not in coords) or (coords[vdim].size <= 1):
                    vdim = None
            if hdim:
                if (hdim not in coords) or (coords[hdim].size <= 1):
                    hdim = None
        vcoords = None if vdim is None else coords[vdim].values
        hcoords = None if hdim is None else coords[hdim].values
        return vdim, hdim, vcoords, hcoords
    
    def _on_draw_ROI_button_clicked(self) -> None:
        if self._draw_ROI_action.isChecked():
            self._start_drawing_ROIs()
        else:
            self._stop_drawing_ROIs()
    
    def _start_drawing_ROIs(self) -> None:
        """ Start drawing ROI regions in each plot view box.
        """
        for plot in self._plots.flatten().tolist():
            plot.vb.sigItemAdded.connect(self._on_finished_drawing_ROI)
            plot.vb.startDrawingItemsOfType(pgx.XAxisRegion)
    
    def _stop_drawing_ROIs(self) -> None:
        """ Stop drawing ROI regions in each plot view box.
        """
        for plot in self._plots.flatten().tolist():
            plot.vb.stopDrawingItems()
            plot.vb.sigItemAdded.disconnect(self._on_finished_drawing_ROI)
        self._draw_ROI_action.setChecked(False)
    
    def _on_finished_drawing_ROI(self, item: pgx.XAxisRegion) -> None:
        """ Handle adding ROI after user has drawn it.
        """

        view: pgx.View = self.sender()

        ROI = {
            'type': 'hregion',
            'position': {self.xdim(): list(item.getRegion())},
        }

        # link ROI dict to region item
        item._ROI = ROI

        # # setup ROI plot item signals/slots, etc.
        # self._setup_ROI_plot_item(item)

        # add ROI to datatree root
        dt: xr.DataTree = self.datatree()
        if ROI_KEY not in dt.attrs:
            dt.attrs[ROI_KEY] = []
        dt.attrs[ROI_KEY].append(ROI)
            
        # draw one ROI at a time
        self._stop_drawing_ROIs()

        # # if not previously showing ROIs, deselect all other ROIs before showing the new ROI
        # if not self._view_ROIs_action.isChecked():
        #     self._ROItree_view.clearSelection()
        
        # update ROI tree and ensure new ROI is selected
        self._update_ROIs_view()
        selected_ROIs = self._ROIs_view.selectedAnnotations()
        if ROI not in selected_ROIs:
            selected_ROIs.append(ROI)
        self._ROIs_view.setSelectedAnnotations(selected_ROIs)

        # # ensure ROIs visible
        # # update checkbox which will also update the associated action (the reverse does not work)
        # self._view_ROIs_checkbox.setChecked(True)

        # update ROIs in plots
        self._update_plot_ROIs()
        
        # if self._curve_fit_live_preview_enabled() and self._curve_fit_depends_on_ROIs():
        #     self._update_curve_fit_preview()

    def _add_ROI_to_plot(self, ROI: dict, plot: pgx.Plot) -> pgx.XAxisRegion | None:
        """ Add ROI region item to plot.
        """
        item = pgx.XAxisRegion()
        item._ROI = ROI
        self._update_ROI_plot_item_from_data(item, item._ROI)
        self._setup_ROI_plot_item(item)
        try:
            print('trying to add ROI item to plot...')
            plot.vb.addItem(item)
            print('added ROI item to plot.')
            return item
        except:
            print('failed to add ROI item to plot.')
            return None
    
    def _setup_ROI_plot_item(self, item: pgx.XAxisRegion) -> None:
        """ Signals/Slots and properties for ROI plot item.
        """
        print('_setup_ROI_plot_item()...')
        # item.sigRegionChanged.connect(lambda: print('sigRegionChanged'))
        # item.sigRegionDragFinished.connect(lambda: print('sigRegionDragFinished'))
        # item.sigEditingFinished.connect(lambda: print('sigEditingFinished'))
        item.sigRegionChanged.connect(lambda item=item: self._on_ROI_plot_item_changed(item))
        item.sigRegionDragFinished.connect(lambda item=item: self._on_ROI_plot_item_changed(item))
        item.sigEditingFinished.connect(lambda item=item: self._on_ROI_plot_item_changed(item))
        # item.sigDeletionRequested.connect(lambda item=item: self.deleteROIs(item._ROI))

        # item.sigRegionDragFinished.connect(lambda: self._update_ROIs_view())
        # item.sigEditingFinished.connect(lambda: self._update_ROIs_view())
        
        item.setZValue(0)
    
    def _on_ROI_plot_item_changed(self, item: pgx.XAxisRegion) -> None:
        """ Handle changes to ROI region item in the plot.
        """
        ROI = getattr(item, '_ROI', None)
        if ROI is None:
            return
        
        self._update_ROI_data_from_plot_item(item, ROI)

        # update same ROI in other plots
        for plot in self._plots.flatten().tolist():
            like_items = [item_ for item_ in plot.vb.allChildren() if type(item_) == type(item)]
            for like_item in like_items:
                if getattr(like_item, '_ROI', None) is ROI:
                    if like_item is not item:
                        self._update_ROI_plot_item_from_data(like_item, ROI)
                    break
        
        # update ROI tree view (only update the item associated with ROI)
        model: AnnotationTreeModel = self._ROIs_view.model()
        root: AnnotationTreeItem = model.rootItem()
        for item in root.subtree_leaves():
            if item.data is ROI:
                index: QModelIndex = model.indexFromItem(item)
                model.dataChanged.emit(index, index)
                break
        
        # if self._curve_fit_live_preview_enabled() and self._curve_fit_depends_on_ROIs():
        #     self._update_curve_fit_preview()

    def _clear_plot_ROIs(self) -> None:
        plots = self._plots.flatten().tolist()
        for plot in plots:
            ROI_items = [item for item in plot.vb.allChildren() if isinstance(item, pgx.XAxisRegion) and hasattr(item, '_ROI')]
            for item in ROI_items:
                plot.vb.removeItem(item)
                item.deleteLater()
    
    def _update_plot_ROIs(self) -> None:
        """ Update ROI regions in each plot to show current ROItree selection. """
        print('_update_plot_ROIs()...')
        
        self._clear_plot_ROIs()
        print('ROIs cleared')
        
        selected_ROIs = self._ROIs_view.selectedAnnotations()
        if not selected_ROIs:
            return
        
        plots = self._plots.flatten().tolist()
        for plot in plots:
            print(plot)
            for ROI in selected_ROIs:
                print(ROI)
                self._add_ROI_to_plot(ROI, plot)

    def _update_ROI_plot_item_from_data(self, item: pgx.XAxisRegion, data: dict) -> None:
        """ Apply ROI data to plotted ROI region.
        """
        print('_update_ROI_plot_item_from_data()...')
        pos = data['position']
        print('pos', pos)
        if isinstance(pos, dict):
            region = pos.get(self.xdim(), [0, 0])
        elif isinstance(pos, list) or isinstance(pos, tuple):
            if isinstance(pos[0], list) or isinstance(pos[0], tuple):
                region = pos[0]
            else:
                region = pos
        else:
            raise ValueError('Invalid ROI region.')
        print(region)
        item.setRegion(region)
        item.setMovable(data.get('movable', True))
        item.setText(data.get('text', ''))
        # item.setFormat(data.get('format', {}))

    def _update_ROI_data_from_plot_item(self, item: pgx.XAxisRegion, data: dict) -> None:
        """ Update ROI data from plotted ROI region.
        """
        region = list(item.getRegion())
        pos = data['position']
        if isinstance(pos, dict):
            pos[self.xdim()] = region
        elif isinstance(pos, list):
            if isinstance(pos[0], list):
                pos[0] = region
            else:
                data['position'] = region
        data['movable'] = item.movable
        data['text'] = item.text()
        # data['format'] = item.getFormat()
    
    def _update_ROIs_view(self) -> None:
        """ Update the ROI tree view for the current datatree selection.
        """
        dt: xr.DataTree = self.datatree()
        if ROI_KEY not in dt.attrs:
            dt.attrs[ROI_KEY] = []
        ROIs = dt.attrs[ROI_KEY]
        self._ROIs_view.setAnnotations(ROIs)
    
    def _on_ROI_selection_changed(self) -> None:
        """ Handle selection changes in ROI tree view.
        """
        self._update_plot_ROIs()

        # if self._curve_fit_live_preview_enabled() and self._curve_fit_depends_on_ROIs() and self.isROIsVisible() and self.selectedROIs():
        #     self._update_curve_fit_preview()

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


class DimIterWidget(QWidget):

    xdimChanged = Signal(str)
    tileChanged = Signal(str, object)

    def __init__(self, *args, **kwargs):
        QWidget.__init__(self, *args, **kwargs)

        color_on: QColor = XarrayGraph._settings['text color']
        color_off = QColor(color_on)
        color_off.setAlphaF(0.5)

        self._pile_action = QAction(
            parent = self, 
            icon = qta.icon('ph.stack', color=color_off, color_on=color_on), 
            text = 'Pile Traces', 
            iconVisibleInMenu = True, 
            checkable = True, 
            checked = True,
            triggered = self.pile,
        )
        self._tile_vertically_action = QAction(
            parent = self, 
            icon = qta.icon('mdi.reorder-horizontal', color=color_off, color_on=color_on), 
            text = 'Tile Traces Vertically', 
            iconVisibleInMenu = True, 
            checkable = True, 
            checked = False,
            triggered = self.tileVertically,
        )
        self._tile_horizontally_action = QAction(
            parent = self, 
            icon = qta.icon('mdi.reorder-vertical', color=color_off, color_on=color_on), 
            text = 'Tile Traces Horizontally', 
            iconVisibleInMenu = True, 
            checkable = True, 
            checked = False,
            triggered = self.tileHorizontally,
        )

        self._tile_menu = QMenu()
        self._tile_menu.addAction(self._pile_action)
        self._tile_menu.addAction(self._tile_vertically_action)
        self._tile_menu.addAction(self._tile_horizontally_action)

        self._tile_action_group = QActionGroup(self._tile_menu)
        self._tile_action_group.addAction(self._pile_action)
        self._tile_action_group.addAction(self._tile_vertically_action)
        self._tile_action_group.addAction(self._tile_horizontally_action)
        self._tile_action_group.setExclusive(True)

        self._dim_label = QLabel('dim')
        self._dim_label.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred))

        self._size_label = QLabel(': n')
        self._size_label.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred))
        self._size_label_opacity_effect = QGraphicsOpacityEffect(self._size_label)
        self._size_label_opacity_effect.setOpacity(0.5)
        self._size_label.setGraphicsEffect(self._size_label_opacity_effect)

        self._xdim_button = QToolButton(
            icon=qta.icon('ph.arrow-line-down', color=color_off, color_on=color_on),
            toolTip='Set as X-axis dimension',
            pressed=self.setAsXDim,
        )
        self._xdim_button.setMaximumSize(QSize(20, 20))

        self._tile_button = QToolButton(
            icon=self._pile_action.icon(),
            text='Tile traces',
            toolTip='Tile traces',
            popupMode=QToolButton.ToolButtonPopupMode.InstantPopup,
        )
        self._tile_button.setMaximumSize(QSize(20, 20))
        self._tile_button.setMenu(self._tile_menu)
        self._tile_button.setStyleSheet('QToolButton::menu-indicator { image: none; }')

        self._spinbox = MultiValueSpinBox()
        self._spinbox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        grid = QGridLayout(self)
        grid.setContentsMargins(5, 2, 5, 2)
        grid.setSpacing(2)
        grid.addWidget(self._dim_label, 0, 0)
        grid.addWidget(self._size_label, 0, 1)
        grid.addWidget(self._xdim_button, 0, 2)
        grid.addWidget(self._tile_button, 0, 3)
        grid.addWidget(self._spinbox, 1, 0, 1, 4)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    
    def dim(self) -> str:
        return self._dim_label.text()
    
    def setDim(self, dim: str) -> None:
        self._dim_label.setText(dim)
    
    def coords(self) -> np.ndarray:
        return self._spinbox.indexedValues()
    
    def setCoords(self, coords: np.ndarray) -> None:
        self._spinbox.blockSignals(True)
        values = self._spinbox.selectedValues()
        self._spinbox.setIndexedValues(coords)
        if values.size > 0:
            try:
                self._spinbox.setSelectedValues(values)
            except:
                pass # in case value types are not compatible with new coords (e.g., datetime vs float time coords)
        if self._spinbox.selectedValues().size == 0 and coords.size > 0:
            self._spinbox.setIndices([0])
        self._spinbox.blockSignals(False)
        self._size_label.setText(f': {coords.size}')
    
    def selectedCoords(self) -> np.ndarray:
        return self._spinbox.selectedValues()
    
    def setSelectedCoords(self, coords: np.ndarray) -> None:
        self._spinbox.blockSignals(True)
        self._spinbox.setSelectedValues(coords)
        self._spinbox.blockSignals(False)
    
    def updateTileButton(self, vertical_tile_dim: str | None = None, horizontal_tile_dim: str | None = None) -> None:
        dim = self.dim()
        if vertical_tile_dim == dim:
            self._tile_vertically_action.setChecked(True)
            self._tile_button.setIcon(self._tile_vertically_action.icon())
        elif horizontal_tile_dim == dim:
            self._tile_horizontally_action.setChecked(True)
            self._tile_button.setIcon(self._tile_horizontally_action.icon())
        else:
            self._pile_action.setChecked(True)
            self._tile_button.setIcon(self._pile_action.icon())
    
    def setAsXDim(self) -> None:
        self.xdimChanged.emit(self.dim())

    def pile(self) -> None:
        self._pile_action.setChecked(True)
        self._tile_button.setIcon(self._pile_action.icon())
        self.tileChanged.emit(self.dim(), None)
    
    def tileVertically(self) -> None:
        self._tile_vertically_action.setChecked(True)
        self._tile_button.setIcon(self._tile_vertically_action.icon())
        self.tileChanged.emit(self.dim(), Qt.Orientation.Vertical)
    
    def tileHorizontally(self) -> None:
        self._tile_horizontally_action.setChecked(True)
        self._tile_button.setIcon(self._tile_horizontally_action.icon())
        self.tileChanged.emit(self.dim(), Qt.Orientation.Horizontal)


class IgnoreLettersKeyPressFilter(QObject):

    def eventFilter(self, object, event):
        if event.type() == QEvent.Type.KeyPress:
            if event.text().isalpha():
                # Do not handle letters A-Z
                return True
        return False


def coord_permutations(coords: dict) -> list[dict]:
    """ return list of all permutations of coords along each dimension

    Example:
        coords = {'subject': [0, 1], 'trial': [0, 1, 2]}
        coord_permutations(coords) = [
            {'subject': 0, 'trial': 0},
            {'subject': 0, 'trial': 1},
            {'subject': 0, 'trial': 2},
            {'subject': 1, 'trial': 0},
            {'subject': 1, 'trial': 1},
            {'subject': 1, 'trial': 2},
        ]
    """
    if not coords:
        return []
    for dim in coords:
        # ensure coords[dim] is iterable
        try:
            iter(coords[dim])
        except:
            # in case coords[dim] is a scalar
            coords[dim] = [coords[dim]]
    permutations: list[dict] = []
    dims = list(coords)
    index = {dim: 0 for dim in dims}
    while index is not None:
        try:
            # coord for index
            coord = {dim: coords[dim][i] for dim, i in index.items()}
            # store coord
            permutations.append(coord)
        except:
            pass
        # next index
        for dim in reversed(dims):
            if index[dim] + 1 < len(coords[dim]):
                index[dim] += 1
                break
            elif dim == dims[0]:
                index = None
                break
            else:
                index[dim] = 0
    return permutations


def test_live():
    app = QApplication()
    # app.setQuitOnLastWindowClosed(False)

    # window = XarrayDataTreeViewer.open('examples/ERPdata.nc')
    # dt = window.datatree()
    # dt['eggs'] = dt['EEG'] * 10
    # window.refresh()
    
    window = XarrayGraph()

    dt = xr.DataTree()
    dt['eeg'] = xr.open_datatree('examples/ERPdata.nc')
    dt['air_temperature'] = xr.tutorial.load_dataset('air_temperature')
    dt['air_temperature/twice air'] = dt['air_temperature/air'] * 2
    dt['air_temperature/inherits'] = xr.tutorial.load_dataset('air_temperature')
    dt['air_temperature/inherits/again'] = xr.tutorial.load_dataset('air_temperature')
    dt['child'] = xr.DataTree()
    # dt['child3/grandchild1/greatgrandchild1'] = xr.DataTree()
    # dt['child3/grandchild1/tiny'] = xr.tutorial.load_dataset('tiny')
    dt['child/rasm'] = xr.tutorial.load_dataset('rasm')
    dt['child/air_temperature_gradient'] = xr.tutorial.load_dataset('air_temperature_gradient')

    # n = len(dt['air_temperature/time'])
    # dt['air_temperature'] = dt['air_temperature'].to_dataset().assign_coords(time=dt['air_temperature/time'].copy(data=np.arange(n)))
    window.setDatatree(dt)

    # model: XarrayDataTreeModel = window._datatree_view.model()
    # model.setCoordsVisible(True)
    # model.setInheritedCoordsVisible(True)
    # model.setDetailsColumnVisible(True)
    # model.setSharedDataHighlighted(True)
    # model.setDebugInfoVisible(False)
    # window._datatree_view._updateViewOptionsFromModel()
    window._datatree_view.showAll()
    
    window.show()
    # window.raise_() # !? this cuases havoc with MacOS native menubar (have to click out of app and back in again to get menubar working again)

    app.exec()


if __name__ == '__main__':
    test_live()