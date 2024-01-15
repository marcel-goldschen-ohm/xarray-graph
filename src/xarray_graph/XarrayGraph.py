""" PySide/PyQt widget for analyzing (x,y) data series in a Xarray dataset or a tree of datasets.

TODO:
- delete selected regions
- update regions when plot item changed
- update plot items when node renamed
- i/o menu (actual i/o in xarray_tree)
- style manipulation
"""

from __future__ import annotations
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
import pyqtgraph as pg
import numpy as np
import scipy as sp
import lmfit
import xarray as xr
from xarray_tree import *
import sys, re
from pyqt_ext import *
from pyqtgraph_ext import *
from xarray_treeview import *


# Currently, color is handled by the widgets themselves.
# pg.setConfigOption('background', (240, 240, 240))
# pg.setConfigOption('foreground', (0, 0, 0))


DEBUG = 0
DEFAULT_ICON_SIZE = 24
DEFAULT_AXIS_LABEL_FONT_SIZE = 12
DEFAULT_AXIS_TICK_FONT_SIZE = 11
DEFAULT_TEXT_ITEM_FONT_SIZE = 10
DEFAULT_LINE_WIDTH = 1


class XarrayGraph(QMainWindow):
    """ PySide/PyQt widget for analyzing (x,y) data series in a Xarray dataset. """

    def __init__(self, *args, **kwargs):
        QMainWindow.__init__(self, *args, **kwargs)

        # xarray data tree
        self._data: XarrayTreeNode | None = None

        # x-axis dimension to be plotted against
        self._xdim: str = 'time'

        # selections
        self._tree_coords: dict[str, xr.DataArray] = {}

        # setup the graphical user interface
        self.setup_ui()
    
    @property
    def data(self) -> XarrayTreeNode | None:
        return self._data
    
    @data.setter
    def data(self, data: XarrayTreeNode | xr.Dataset | None):
        # set xarray tree
        if isinstance(data, XarrayTreeNode):
            self._data = data
        elif isinstance(data, xr.Dataset):
            # add data as child dataset of empty root node
            root_node: XarrayTreeNode = XarrayTreeNode(name='/', dataset=None)
            XarrayTreeNode(name='dataset', dataset=data, parent=root_node)
            self._data = root_node
        elif isinstance(data, xr.DataArray):
            # add data as child dataset of empty root node
            ds = xr.Dataset(data_vars={data.name: data})
            root_node: XarrayTreeNode = XarrayTreeNode(name='/', dataset=None)
            XarrayTreeNode(name='dataset', dataset=ds, parent=root_node)
            self._data = root_node
        elif isinstance(data, np.ndarray):
            # add data as child dataset of empty root node
            ds = xr.Dataset(data_vars={'y': xr.DataArray(data=data)})
            print(ds)
            root_node: XarrayTreeNode = XarrayTreeNode(name='/', dataset=None)
            XarrayTreeNode(name='dataset', dataset=ds, parent=root_node)
            self._data = root_node
            self.data.dump()
        elif (isinstance(data, tuple) or isinstance(data, list)) and len(data) == 2:
            x, y = data
            if not isinstance(y, xr.DataArray):
                if not isinstance(y, np.ndarray):
                    y = np.array(y)
                y = xr.DataArray(data=y)
            if not isinstance(x, xr.DataArray):
                if not isinstance(x, np.ndarray):
                    x = np.array(x)
                for dim in reversed(y.dims):
                    if y.sizes[dim] == x.size:
                        xdim = dim
                        break
                x = xr.DataArray(dims=[xdim], data=x)
            # add data as child dataset of empty root node
            ds = xr.Dataset(data_vars={'y': y}, coords={x.dims[0]: x})
            root_node: XarrayTreeNode = XarrayTreeNode(name='/', dataset=None)
            XarrayTreeNode(name='dataset', dataset=ds, parent=root_node)
            self._data = root_node
        elif data is None:
            self._data = None
        else:
            QMessageBox.warning(parent=self, title='Error', text=f'Unsupported data type: {type(data)}')
            return
        if DEBUG:
            print('self._data:')
            self.data.dump()
        
        # update data tree view
        self._data_treeview.set_data(self.data)

        # store the merged coords for the entire tree
        self._tree_coords: dict[str, xr.DataArray] = {}
        if self.data is not None:
            node: XarrayTreeNode = self.data
            while node is not None:
                ds: xr.Dataset = node.dataset
                if ds is not None:
                    node_coords: dict[str, xr.DataArray] = node.inherited_coords()
                    for name, coords in node_coords.items():
                        if name in self._tree_coords:
                            # TODO: merge floats within some tolerance, keep attrs?
                            values = np.unique(np.concatenate((self._tree_coords[name].values, coords.values)))
                            self._tree_coords[name] = xr.DataArray(dims=name, data=values)
                        else:
                            self._tree_coords[name] = coords
                node = node.next_depth_first()
        if DEBUG:
            print('self._tree_coords:', self._tree_coords)

        # reset xdim in case dims have changed
        # also updates dim spinboxes and plot grid
        self.xdim = self.xdim
    
    def set_data(self, *args, **kwargs):
        x = y = None
        if len(args) == 1:
            y = args
        elif len(args) == 2:
            x, y = args
        if x is None:
            x = kwargs.get('x', None)
        if y is None:
            y = kwargs.get('y', None)
        if y is None:
            return
        if not isinstance(y, xr.Dataset) and not isinstance(y, xr.DataArray):
            if not isinstance(y, np.ndarray):
                y = np.array(y)
            dims = kwargs.get('dims', [f'dim_{i}' for i in range(y.ndim)])
            attrs = kwargs.get('attrs', {})
            y = xr.DataArray(dims=dims, data=y, attrs=attrs)
        if x is not None and not isinstance(x, xr.DataArray):
            if not isinstance(x, np.ndarray):
                x = np.array(x)
            xdim = kwargs.get('xdim', None)
            if xdim is None:
                for dim in reversed(y.dims):
                    if y.sizes[dim] == x.size:
                        xdim = dim
                        break
            xattrs = kwargs.get('xattrs', {})
            x = xr.DataArray(dims=[xdim], data=x, attrs=xattrs)
        if x is None:
            self.data = y
        else:
            self.data = x, y
            self.xdim = xdim
        self.autoscale_plots()
        self._data_treeview.expandToDepth(1)
        self._data_treeview.resizeAllColumnsToContents()
    
    @property
    def xdim(self) -> str:
        return self._xdim

    @xdim.setter
    def xdim(self, xdim: str):
        dims: list[str] = self.dims
        if DEBUG:
            print('dims:', dims)
        if dims and (xdim not in dims):
            # default to last dim if xdim is invalid
            xdim = dims[-1]
        
        self._xdim = xdim
        if DEBUG:
            print('_xdim:', self._xdim)
        
        # update xdim combo box
        self._xdim_combobox.blockSignals(True)
        if dims:
            for i, dim in enumerate(dims):
                if i < self._xdim_combobox.count():
                    self._xdim_combobox.setItemText(i, dim)
                else:
                    self._xdim_combobox.addItem(dim)
            self._xdim_combobox.setCurrentIndex(dims.index(self.xdim))
            while self._xdim_combobox.count() > len(dims):
                self._xdim_combobox.removeItem(self._xdim_combobox.count() - 1)
        else:
            if self._xdim_combobox.count():
                self._xdim_combobox.setItemText(0, self.xdim)
            else:
                self._xdim_combobox.addItem(self.xdim)
            self._xdim_combobox.setCurrentIndex(0)
            while self._xdim_combobox.count() > 1:
                self._xdim_combobox.removeItem(self._xdim_combobox.count() - 1)
        self._xdim_combobox.blockSignals(False)
        
        # update row/col tile combo boxes
        tile_dims = ['None'] + dims
        if xdim in tile_dims:
            tile_dims.remove(self.xdim)
        if DEBUG:
            print('tile_dims:', tile_dims)
        
        row_tile_dim = self._row_tile_combobox.currentText()
        if row_tile_dim not in tile_dims:
            row_tile_dim = 'None'
        self._row_tile_combobox.blockSignals(True)
        for i, dim in enumerate(tile_dims):
            if i < self._row_tile_combobox.count():
                self._row_tile_combobox.setItemText(i, dim)
            else:
                self._row_tile_combobox.addItem(dim)
        self._row_tile_combobox.setCurrentIndex(tile_dims.index(row_tile_dim))
        while self._row_tile_combobox.count() > len(tile_dims):
            self._row_tile_combobox.removeItem(self._row_tile_combobox.count() - 1)
        self._row_tile_combobox.blockSignals(False)
        
        col_tile_dim = self._col_tile_combobox.currentText()
        if col_tile_dim not in tile_dims or col_tile_dim == row_tile_dim:
            col_tile_dim = 'None'
        self._col_tile_combobox.blockSignals(True)
        for i, dim in enumerate(tile_dims):
            if i < self._col_tile_combobox.count():
                self._col_tile_combobox.setItemText(i, dim)
            else:
                self._col_tile_combobox.addItem(dim)
        self._col_tile_combobox.setCurrentIndex(tile_dims.index(col_tile_dim))
        while self._col_tile_combobox.count() > len(tile_dims):
            self._col_tile_combobox.removeItem(self._col_tile_combobox.count() - 1)
        self._col_tile_combobox.blockSignals(False)
        
        # update dim iter spinboxes
        self.update_dim_iter_things()

        # update plots
        self.on_var_selection_changed()

        # update selected regions
        self.select_regions()
    
    def set_xdim(self, xdim: str):
        self.xdim = xdim
    
    @property
    def dims(self) -> list[str]:
        try:
            return list(self._tree_coords)
        except:
            return []
    
    def is_tiling_enabled(self) -> bool:
        row_tile_dim = self._row_tile_combobox.currentText()
        col_tile_dim = self._col_tile_combobox.currentText()
        tiling_enabled: bool = row_tile_dim in self._iter_dims or col_tile_dim in self._iter_dims
        return tiling_enabled
    
    def setup_ui(self) -> None:
        toolbar_icon_size = QSize(DEFAULT_ICON_SIZE, DEFAULT_ICON_SIZE)
        icon_button = QToolButton()
        icon_button.setIcon(qta.icon('fa5s.cubes', options=[{'opacity': 0.5}]))

        self._control_panel_toolbar = QToolBar()
        self._control_panel_toolbar.setOrientation(Qt.Orientation.Vertical)
        self._control_panel_toolbar.setStyleSheet("QToolBar{spacing:2px;}")
        self._control_panel_toolbar.setIconSize(toolbar_icon_size)
        self._control_panel_toolbar.setMovable(False)

        self._plot_grid_toolbar = QToolBar()
        self._plot_grid_toolbar.setStyleSheet("QToolBar{spacing:2px;}")
        self._plot_grid_toolbar.setIconSize(toolbar_icon_size)
        self._plot_grid_toolbar.setMovable(False)
        self._plot_grid_toolbar.addWidget(icon_button)

        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._plot_grid_toolbar)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self._control_panel_toolbar)

        self._control_panel = QStackedWidget()

        self._plot_grid = PlotGrid()
        self._grid_rowlim = ()
        self._grid_collim = ()

        hsplitter = QSplitter(Qt.Orientation.Horizontal)
        hsplitter.addWidget(self._control_panel)
        hsplitter.addWidget(self._plot_grid)
        hsplitter.setStretchFactor(0, 0)
        hsplitter.setStretchFactor(1, 1)
        hsplitter.setHandleWidth(1)
        hsplitter.setSizes([250])

        self.setCentralWidget(hsplitter)

        self.setup_control_panel_toolbar()
        self.setup_plot_grid_toolbar()

        self._control_panel.hide()
    
    def setup_plot_grid_toolbar(self) -> None:
        # widgets and toolbar actions for iterating dimension indices
        self._dim_iter_things: dict[str, dict[str, QLabel | MultiValueSpinBox | QAction]] = {}

        self._region_button = QToolButton()
        self._region_button.setIcon(qta.icon('mdi.arrow-expand-horizontal', options=[{'opacity': 0.5}]))
        self._region_button.setToolTip('Draw X axis region')
        self._region_button.setCheckable(True)
        self._region_button.setChecked(False)
        self._region_button.clicked.connect(self.draw_region)
        self._action_after_dim_iter_things = self._plot_grid_toolbar.addWidget(self._region_button)

        self._home_button = QToolButton()
        self._home_button.setIcon(qta.icon('mdi.home-outline', options=[{'opacity': 0.5}]))
        self._home_button.setToolTip('Autoscale all plots')
        self._home_button.clicked.connect(lambda: self.autoscale_plots())
        self._plot_grid_toolbar.addWidget(self._home_button)
    
    def setup_control_panel_toolbar(self) -> None:
        # control panel toolbar
        # button order reflects setup order
        self.setup_data_control_panel()
        self.setup_grid_control_panel()
        self.setup_region_control_panel()
        self.setup_measure_control_panel()
        self.setup_curve_fit_control_panel()
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._control_panel_toolbar.addWidget(spacer)
        self.setup_settings_control_panel()
    
    def setup_data_control_panel(self) -> None:
        button = QToolButton()
        button.setIcon(qta.icon('ph.eye-thin', options=[{'opacity': 0.7}]))
        button.setCheckable(True)
        button.setChecked(False)
        button.setToolTip('Data browser')
        button.released.connect(lambda i=self._control_panel.count(): self.toggle_control_panel(i))
        self._control_panel_toolbar.addWidget(button)

        self._data_treeview = XarrayTreeView()
        self._data_treeview.setSelectionMode(QAbstractItemView.MultiSelection)
        root_node: XarrayTreeNode = self.data if self.data is not None else XarrayTreeNode('/', None)
        root_item = XarrayTreeItem(node=root_node, key=None)
        model: XarrayTreeModel = XarrayTreeModel(root_item)
        model._allowed_selections = ['var']
        self._data_treeview.setModel(model)
        self._data_treeview.selection_changed.connect(self.on_var_selection_changed)

        self._xdim_combobox = QComboBox()
        self._xdim_combobox.currentTextChanged.connect(self.set_xdim)

        panel = QWidget()
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        vbox.addWidget(self._data_treeview)

        form = QFormLayout()
        form.setContentsMargins(5, 3, 0, 3)
        form.setSpacing(0)
        form.setHorizontalSpacing(5)
        form.addRow('X axis', self._xdim_combobox)
        vbox.addLayout(form)

        self._control_panel.addWidget(panel)
    
    def setup_grid_control_panel(self) -> None:
        button = QToolButton()
        button.setIcon(qta.icon('mdi.grid', options=[{'opacity': 0.5}]))
        button.setCheckable(True)
        button.setChecked(False)
        button.setToolTip('Plot grid')
        button.released.connect(lambda i=self._control_panel.count(): self.toggle_control_panel(i))
        self._control_panel_toolbar.addWidget(button)

        self._link_xaxis_checkbox = QCheckBox('Link X axes')
        self._link_xaxis_checkbox.setChecked(True)
        self._link_xaxis_checkbox.stateChanged.connect(lambda: self.link_axes())

        self._link_yaxis_checkbox = QCheckBox('Link Y axes')
        self._link_yaxis_checkbox.setChecked(True)
        self._link_yaxis_checkbox.stateChanged.connect(lambda: self.link_axes())

        self._row_tile_combobox = QComboBox()
        self._row_tile_combobox.addItems(['None'])
        self._row_tile_combobox.setCurrentText('None')
        self._row_tile_combobox.currentTextChanged.connect(self.update_plot_grid)

        self._col_tile_combobox = QComboBox()
        self._col_tile_combobox.addItems(['None'])
        self._col_tile_combobox.setCurrentText('None')
        self._col_tile_combobox.currentTextChanged.connect(self.update_plot_grid)

        link_group = QGroupBox('Link axis')
        vbox = QVBoxLayout(link_group)
        vbox.setContentsMargins(3, 3, 3, 3)
        vbox.setSpacing(3)
        vbox.addWidget(self._link_xaxis_checkbox)
        vbox.addWidget(self._link_yaxis_checkbox)

        tile_group = QGroupBox('Tile plots')
        form = QFormLayout(tile_group)
        form.setContentsMargins(3, 3, 3, 3)
        form.setSpacing(3)
        form.setHorizontalSpacing(5)
        form.addRow('Rows', self._row_tile_combobox)
        form.addRow('Columns', self._col_tile_combobox)

        panel = QWidget()
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(5, 5, 5, 5)
        vbox.setSpacing(20)
        vbox.addWidget(link_group)
        vbox.addWidget(tile_group)
        vbox.addStretch()

        scroll_area = QScrollArea()
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setWidget(panel)
        scroll_area.setWidgetResizable(True)

        self._control_panel.addWidget(scroll_area)
    
    def setup_region_control_panel(self) -> None:
        button = QToolButton()
        button.setIcon(qta.icon('mdi.arrow-expand-horizontal', options=[{'opacity': 0.5}]))
        button.setCheckable(True)
        button.setChecked(False)
        button.setToolTip('X axis regions')
        button.released.connect(lambda i=self._control_panel.count(): self.toggle_control_panel(i))
        self._control_panel_toolbar.addWidget(button)

        self._hide_regions_button = QPushButton('Hide')
        self._hide_regions_button.setToolTip('Hide selected regions')
        self._hide_regions_button.clicked.connect(lambda: self.update_regions(is_visible=False))

        self._show_regions_button = QPushButton('Show')
        self._show_regions_button.setToolTip('Show selected regions')
        self._show_regions_button.clicked.connect(lambda: self.update_regions(is_visible=True))

        self._lock_regions_button = QPushButton('Lock')
        self._lock_regions_button.setToolTip('Lock selected regions')
        self._lock_regions_button.clicked.connect(lambda: self.update_regions(is_moveable=False))

        self._unlock_regions_button = QPushButton('Unlock')
        self._unlock_regions_button.setToolTip('Unlock selected regions')
        self._unlock_regions_button.clicked.connect(lambda: self.update_regions(is_moveable=True))

        self._clear_regions_button = QPushButton('Clear')
        self._clear_regions_button.setToolTip('Clear region selection')
        self._clear_regions_button.clicked.connect(lambda: self.update_regions(clear=True))

        self._delete_regions_button = QPushButton('Delete') # TODO: implement
        self._delete_regions_button.setToolTip('Delete selected regions')

        self._name_regions_button = QPushButton('Name selected') # TODO: implement
        self._name_regions_button.setToolTip('Name selected regions')
        self._name_regions_button.pressed.connect(self.name_regions)

        self._region_name_list = QListWidget() # TODO: implement
        self._region_name_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self._region_name_list.itemSelectionChanged.connect(self.select_regions)

        selected_group = QGroupBox('Selected regions')
        grid = QGridLayout(selected_group)
        grid.setContentsMargins(3, 3, 3, 3)
        grid.setSpacing(5)
        grid.addWidget(self._hide_regions_button, 0, 0)
        grid.addWidget(self._show_regions_button, 1, 0)
        grid.addWidget(self._lock_regions_button, 0, 1)
        grid.addWidget(self._unlock_regions_button, 1, 1)
        grid.addWidget(self._clear_regions_button, 2, 0)
        grid.addWidget(self._delete_regions_button, 2, 1)

        named_group = QGroupBox('Named regions')
        vbox = QVBoxLayout(named_group)
        vbox.setContentsMargins(3, 3, 3, 3)
        vbox.setSpacing(5)
        vbox.addWidget(self._name_regions_button)
        vbox.addWidget(self._region_name_list)

        panel = QWidget()
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(5, 5, 5, 5)
        vbox.setSpacing(20)
        vbox.addWidget(selected_group)
        vbox.addWidget(named_group)
        vbox.addStretch()

        scroll_area = QScrollArea()
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setWidget(panel)
        scroll_area.setWidgetResizable(True)

        self._control_panel.addWidget(scroll_area)
    
    def setup_measure_control_panel(self) -> None:
        button = QToolButton()
        button.setIcon(qta.icon('mdi6.chart-scatter-plot', options=[{'opacity': 0.5}]))
        button.setCheckable(True)
        button.setChecked(False)
        button.setToolTip('Measure')
        button.released.connect(lambda i=self._control_panel.count(): self.toggle_control_panel(i))
        self._control_panel_toolbar.addWidget(button)

        self._measure_type_combobox = QComboBox()
        self._measure_type_combobox.addItems(['Mean', 'Median'])
        self._measure_type_combobox.insertSeparator(self._measure_type_combobox.count())
        self._measure_type_combobox.addItems(['Min', 'Max', 'AbsMax'])
        self._measure_type_combobox.insertSeparator(self._measure_type_combobox.count())
        self._measure_type_combobox.addItems(['Peaks'])
        self._measure_type_combobox.insertSeparator(self._measure_type_combobox.count())
        self._measure_type_combobox.addItems(['Standard Deviation', 'Variance'])
        self._measure_type_combobox.currentIndexChanged.connect(self.on_measure_type_changed)

        self._peak_half_width_spinbox = QSpinBox()
        self._peak_half_width_spinbox.setValue(0)

        self._peak_width_wrapper = QWidget()
        form = QFormLayout(self._peak_width_wrapper)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(0)
        form.setHorizontalSpacing(5)
        form.addRow('Average +/- samples', self._peak_half_width_spinbox)

        self._peak_type_combobox = QComboBox()
        self._peak_type_combobox.addItems(['Min', 'Max'])
        self._peak_type_combobox.setCurrentText('Max')

        self._peak_threshold_spinbox = QDoubleSpinBox()

        self._peak_options_wrapper = QWidget()
        form = QFormLayout(self._peak_options_wrapper)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(0)
        form.setHorizontalSpacing(5)
        form.addRow('Peak type', self._peak_type_combobox)
        form.addRow('Peak threshold', self._peak_threshold_spinbox)

        self._measure_in_visible_regions_only_checkbox = QCheckBox('In visible regions only')
        self._measure_in_visible_regions_only_checkbox.setChecked(True)

        self._measure_per_visible_region_checkbox = QCheckBox('In each visible region')
        self._measure_per_visible_region_checkbox.setChecked(True)

        self._measure_name_edit = QLineEdit()

        self._measure_name_wrapper = QWidget()
        form = QFormLayout(self._measure_name_wrapper)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(0)
        form.setHorizontalSpacing(5)
        form.addRow('Result name', self._measure_name_edit)

        self._measure_button = QPushButton('Measure')
        self._measure_button.pressed.connect(self.measure)

        measure_group = QGroupBox('Measure')
        vbox = QVBoxLayout(measure_group)
        vbox.setContentsMargins(3, 3, 3, 3)
        vbox.setSpacing(5)
        vbox.addWidget(self._measure_type_combobox)
        vbox.addWidget(self._peak_options_wrapper)
        vbox.addWidget(self._peak_width_wrapper)
        vbox.addWidget(self._measure_in_visible_regions_only_checkbox)
        vbox.addWidget(self._measure_per_visible_region_checkbox)
        vbox.addWidget(self._measure_name_wrapper)
        vbox.addWidget(self._measure_button)
        self.on_measure_type_changed()

        panel = QWidget()
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(5, 5, 5, 5)
        vbox.setSpacing(20)
        vbox.addWidget(measure_group)
        vbox.addStretch()

        scroll_area = QScrollArea()
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setWidget(panel)
        scroll_area.setWidgetResizable(True)

        self._control_panel.addWidget(scroll_area)
    
    def on_measure_type_changed(self) -> None:
        measure_type = self._measure_type_combobox.currentText()
        self._peak_options_wrapper.setVisible(measure_type == 'Peaks')
        self._peak_width_wrapper.setVisible(measure_type in ['Min', 'Max', 'AbsMax', 'Peaks'])
        self._measure_name_edit.setPlaceholderText(measure_type)
    
    def setup_curve_fit_control_panel(self) -> None:
        button = QToolButton()
        button.setIcon(qta.icon('mdi.chart-bell-curve-cumulative', options=[{'opacity': 0.5}]))
        button.setCheckable(True)
        button.setChecked(False)
        button.setToolTip('Measure')
        button.released.connect(lambda i=self._control_panel.count(): self.toggle_control_panel(i))
        self._control_panel_toolbar.addWidget(button)

        self._curve_fit_type_combobox = QComboBox()
        self._curve_fit_type_combobox.addItems(['Mean', 'Median', 'Min', 'Max'])
        self._curve_fit_type_combobox.insertSeparator(self._curve_fit_type_combobox.count())
        self._curve_fit_type_combobox.addItems(['Line', 'Polynomial', 'Spline'])
        self._curve_fit_type_combobox.insertSeparator(self._curve_fit_type_combobox.count())
        self._curve_fit_type_combobox.addItems(['Equation'])
        self._curve_fit_type_combobox.setCurrentText('Equation')
        self._curve_fit_type_combobox.currentIndexChanged.connect(self.on_curve_fit_type_changed)

        self._polynomial_degree_spinbox = QSpinBox()
        self._polynomial_degree_spinbox.setValue(2)

        self._polynomial_options_wrapper = QWidget()
        form = QFormLayout(self._polynomial_options_wrapper)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(0)
        form.setHorizontalSpacing(5)
        form.addRow('Polynomial degree', self._polynomial_degree_spinbox)

        self._spline_segments_spinbox = QSpinBox()
        self._spline_segments_spinbox.setValue(10)
        self._spline_segments_spinbox.setMinimum(1)

        self._spline_options_wrapper = QWidget()
        form = QFormLayout(self._spline_options_wrapper)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(0)
        form.setHorizontalSpacing(5)
        form.addRow('Spline segments', self._spline_segments_spinbox)

        self._equation_edit = QLineEdit()
        self._equation_edit.setPlaceholderText('a * x + b')
        self._equation_edit.editingFinished.connect(self.on_curve_fit_equation_changed)

        self._equation_params = {}

        self._equation_params_table = QTableWidget(0, 5)
        self._equation_params_table.setHorizontalHeaderLabels(['Param', 'Value', 'Vary', 'Min', 'Max'])
        self._equation_params_table.verticalHeader().setVisible(False)
        # self._equation_params_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._equation_params_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

        self._equation_eval_button = QPushButton('Evaluate')
        self._equation_eval_button.pressed.connect(lambda: self.curve_fit(eval_equation_only=True))

        self._equation_clear_eval_button = QPushButton('Clear')
        self._equation_clear_eval_button.pressed.connect(self.clear_curve_fits)

        self._equation_group = QGroupBox('Equation')
        grid = QGridLayout(self._equation_group)
        grid.setContentsMargins(3, 3, 3, 3)
        grid.setSpacing(3)
        grid.addWidget(self._equation_edit, 0, 0, 1, 2)
        grid.addWidget(self._equation_params_table, 1, 0, 1, 2)
        grid.addWidget(self._equation_eval_button, 2, 0)
        grid.addWidget(self._equation_clear_eval_button, 2, 1)

        self._curve_fit_optimize_in_visible_regions_checkbox = QCheckBox('Optimize in visible regions')
        self._curve_fit_optimize_in_visible_regions_checkbox.setChecked(True)

        self._curve_fit_evaluate_in_visible_regions_checkbox = QCheckBox('Evaluate in visible regions')
        self._curve_fit_evaluate_in_visible_regions_checkbox.setChecked(False)

        self._curve_fit_name_edit = QLineEdit()

        self._curve_fit_name_wrapper = QWidget()
        form = QFormLayout(self._curve_fit_name_wrapper)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(0)
        form.setHorizontalSpacing(5)
        form.addRow('Result name', self._curve_fit_name_edit)

        self._curve_fit_button = QPushButton('Fit')
        self._curve_fit_button.pressed.connect(self.curve_fit)

        fit_group = QGroupBox('Curve fit')
        vbox = QVBoxLayout(fit_group)
        vbox.setContentsMargins(3, 3, 3, 3)
        vbox.setSpacing(5)
        vbox.addWidget(self._curve_fit_type_combobox)
        vbox.addWidget(self._polynomial_options_wrapper)
        vbox.addWidget(self._spline_options_wrapper)
        vbox.addWidget(self._equation_group)
        vbox.addWidget(self._curve_fit_optimize_in_visible_regions_checkbox)
        vbox.addWidget(self._curve_fit_evaluate_in_visible_regions_checkbox)
        vbox.addWidget(self._curve_fit_name_wrapper)
        vbox.addWidget(self._curve_fit_button)
        self.on_curve_fit_type_changed()

        panel = QWidget()
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(5, 5, 5, 5)
        vbox.setSpacing(20)
        vbox.addWidget(fit_group)
        vbox.addStretch()

        scroll_area = QScrollArea()
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setWidget(panel)
        scroll_area.setWidgetResizable(True)

        self._control_panel.addWidget(scroll_area)
    
    def on_curve_fit_type_changed(self) -> None:
        fit_type = self._curve_fit_type_combobox.currentText()
        self._polynomial_options_wrapper.setVisible(fit_type == 'Polynomial')
        self._spline_options_wrapper.setVisible(fit_type == 'Spline')
        self._equation_group.setVisible(fit_type not in ['Mean', 'Median', 'Line', 'Polynomial', 'Spline'])
        if self._equation_group.isVisible():
            self._equation_params_table.resizeColumnsToContents()
        self._curve_fit_name_edit.setPlaceholderText(fit_type)
    
    def on_curve_fit_equation_changed(self) -> None:
        equation = self._equation_edit.text().strip()
        if equation == '':
            self._curve_fit_model = None
            param_names = []
        else:
            self._curve_fit_model = lmfit.models.ExpressionModel(equation, independent_vars=['x'])
            param_names = self._curve_fit_model.param_names
            for name in param_names:
                if name not in self._equation_params:
                    self._equation_params[name] = {
                        'value': 0,
                        'vary': True,
                        'min': -np.inf,
                        'max': np.inf
                    }
            self._equation_params = {name: params for name, params in self._equation_params.items() if name in param_names}
        self._equation_params_table.clearContents()
        self._equation_params_table.setRowCount(len(param_names))
        for row, name in enumerate(param_names):
            value = self._equation_params[name]['value']
            vary = self._equation_params[name]['vary']
            value_min = self._equation_params[name]['min']
            value_max = self._equation_params[name]['max']

            name_item = QTableWidgetItem(name)
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            value_item = QTableWidgetItem(f'{value:.6g}')
            vary_item = QTableWidgetItem()
            vary_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            vary_item.setCheckState(Qt.CheckState.Checked if vary else Qt.CheckState.Unchecked)
            min_item = QTableWidgetItem(str(value_min))
            max_item = QTableWidgetItem(str(value_max))

            for col, item in enumerate([name_item, value_item, vary_item, min_item, max_item]):
                self._equation_params_table.setItem(row, col, item)

        self._equation_params_table.resizeColumnsToContents()
    
    def _update_curve_fit_model(self) -> None:
        for row in range(self._equation_params_table.rowCount()):
            name = self._equation_params_table.item(row, 0).text()
            try:
                value = float(self._equation_params_table.item(row, 1).text())
            except:
                value = 0
            vary = self._equation_params_table.item(row, 2).checkState() == Qt.CheckState.Checked
            try:
                value_min = float(self._equation_params_table.item(row, 3).text())
            except:
                value_min = -np.inf
            try:
                value_max = float(self._equation_params_table.item(row, 4).text())
            except:
                value_max = np.inf
            self._equation_params[name] = {
                'value': value,
                'vary': vary,
                'min': value_min,
                'max': value_max
            }
            self._curve_fit_model.set_param_hint(name, **self._equation_params[name])
    
    def setup_settings_control_panel(self) -> None:
        button = QToolButton()
        button.setIcon(qta.icon('msc.settings-gear', options=[{'opacity': 0.5}]))
        button.setCheckable(True)
        button.setChecked(False)
        button.setToolTip('Measure')
        button.released.connect(lambda i=self._control_panel.count(): self.toggle_control_panel(i))
        self._control_panel_toolbar.addWidget(button)

        self._linewidth_spinbox = QSpinBox()
        self._linewidth_spinbox.setValue(DEFAULT_LINE_WIDTH)
        self._linewidth_spinbox.setMinimum(1)
        self._linewidth_spinbox.valueChanged.connect(lambda: self.update_plot_items(item_types=[XYData]))

        self._axislabel_fontsize_spinbox = QSpinBox()
        self._axislabel_fontsize_spinbox.setValue(DEFAULT_AXIS_LABEL_FONT_SIZE)
        self._axislabel_fontsize_spinbox.setMinimum(1)
        self._axislabel_fontsize_spinbox.setSuffix('pt')
        self._axislabel_fontsize_spinbox.valueChanged.connect(self.update_axes_labels)

        self._axistick_fontsize_spinbox = QSpinBox()
        self._axistick_fontsize_spinbox.setValue(DEFAULT_AXIS_TICK_FONT_SIZE)
        self._axistick_fontsize_spinbox.setMinimum(1)
        self._axistick_fontsize_spinbox.setSuffix('pt')
        self._axistick_fontsize_spinbox.valueChanged.connect(self.update_axes_tick_font)

        self._textitem_fontsize_spinbox = QSpinBox()
        self._textitem_fontsize_spinbox.setValue(DEFAULT_TEXT_ITEM_FONT_SIZE)
        self._textitem_fontsize_spinbox.setMinimum(1)
        self._textitem_fontsize_spinbox.setSuffix('pt')
        self._textitem_fontsize_spinbox.valueChanged.connect(self.update_item_font)

        self._iconsize_spinbox = QSpinBox()
        self._iconsize_spinbox.setValue(DEFAULT_ICON_SIZE)
        self._iconsize_spinbox.setMinimum(16)
        self._iconsize_spinbox.setMaximum(64)
        self._iconsize_spinbox.setSingleStep(8)
        self._iconsize_spinbox.valueChanged.connect(self.update_icon_size)

        style_group = QGroupBox('Default plot style')
        form = QFormLayout(style_group)
        form.setContentsMargins(3, 3, 3, 3)
        form.setSpacing(3)
        form.setHorizontalSpacing(5)
        form.addRow('Line width', self._linewidth_spinbox)

        font_group = QGroupBox('Font')
        form = QFormLayout(font_group)
        form.setContentsMargins(3, 3, 3, 3)
        form.setSpacing(3)
        form.setHorizontalSpacing(5)
        form.addRow('Axis label size', self._axislabel_fontsize_spinbox)
        form.addRow('Axis tick size', self._axistick_fontsize_spinbox)
        form.addRow('Text item size', self._textitem_fontsize_spinbox)

        ui_group = QGroupBox('UI options')
        form = QFormLayout(ui_group)
        form.setContentsMargins(3, 3, 3, 3)
        form.setSpacing(3)
        form.setHorizontalSpacing(5)
        form.addRow('Icon size', self._iconsize_spinbox)

        panel = QWidget()
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(5, 5, 5, 5)
        vbox.setSpacing(20)
        vbox.addWidget(style_group)
        vbox.addWidget(font_group)
        vbox.addWidget(ui_group)
        vbox.addStretch()

        scroll_area = QScrollArea()
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setWidget(panel)
        scroll_area.setWidgetResizable(True)

        self._control_panel.addWidget(scroll_area)
    
    def update_icon_size(self) -> None:
        size = self._iconsize_spinbox.value()
        icon_size = QSize(size, size)
        for toolbar in [self._control_panel_toolbar, self._plot_grid_toolbar]:
            toolbar.setIconSize(icon_size)
            actions = toolbar.actions()
            widgets = [toolbar.widgetForAction(action) for action in actions]
            buttons = [widget for widget in widgets if isinstance(widget, QToolButton)]
            for button in buttons:
                button.setIconSize(icon_size)
    
    def toggle_control_panel(self, index: int) -> None:
        actions = self._control_panel_toolbar.actions()
        widgets = [self._control_panel_toolbar.widgetForAction(action) for action in actions]
        buttons = [widget for widget in widgets if isinstance(widget, QToolButton)]
        show = buttons[index].isChecked()
        if show:
            self._control_panel.setCurrentIndex(index)
        self._control_panel.setVisible(show)
        for i, button in enumerate(buttons):
            if i != index:
                button.setChecked(False)
    
    def update_dim_iter_things(self) -> None:
        # remove dim iter actions from toolbar
        for dim in self._dim_iter_things:
            for value in self._dim_iter_things[dim].values():
                if isinstance(value, QAction):
                    self._plot_grid_toolbar.removeAction(value)
        
        # delete unneeded dim iter things
        for dim in list(self._dim_iter_things):
            if dim not in self._tree_coords or len(self._tree_coords[dim]) == 1:
                for value in self._dim_iter_things[dim].values():
                    value.deleteLater()
                del self._dim_iter_things[dim]
        
        # update or create dim iter things and insert actions into toolbar
        for dim in self._tree_coords:
            if len(self._tree_coords[dim]) > 1 and dim != self.xdim:
                if dim not in self._dim_iter_things:
                    self._dim_iter_things[dim] = {}
                if 'label' in self._dim_iter_things[dim]:
                    label: QLabel = self._dim_iter_things[dim]['label']
                else:
                    label: QLabel = QLabel(f'  {dim}:')
                    self._dim_iter_things[dim]['label'] = label
                if 'spinbox' in self._dim_iter_things[dim]:
                    spinbox: MultiValueSpinBox = self._dim_iter_things[dim]['spinbox']
                    spinbox.blockSignals(True)
                    spinbox.setIndexedValues(self._tree_coords[dim])
                    spinbox.blockSignals(False)
                else:
                    spinbox: MultiValueSpinBox = MultiValueSpinBox()
                    spinbox.setToolTip(f'{dim} index/slice (+Shift: page up/down)')
                    spinbox.setIndexedValues(self._tree_coords[dim])
                    spinbox.indicesChanged.connect(self.on_index_selection_changed)
                    self._dim_iter_things[dim]['spinbox'] = spinbox
                if 'labelAction' in self._dim_iter_things[dim]:
                    label_action: QAction = self._dim_iter_things[dim]['labelAction']
                    self._plot_grid_toolbar.insertAction(self._action_after_dim_iter_things, label_action)
                else:
                    label_action: QAction = self._plot_grid_toolbar.insertWidget(self._action_after_dim_iter_things, label)
                    self._dim_iter_things[dim]['labelAction'] = label_action
                if 'spinboxAction' in self._dim_iter_things[dim]:
                    spinbox_action: QAction = self._dim_iter_things[dim]['spinboxAction']
                    self._plot_grid_toolbar.insertAction(self._action_after_dim_iter_things, spinbox_action)
                else:
                    spinbox_action: QAction = self._plot_grid_toolbar.insertWidget(self._action_after_dim_iter_things, spinbox)
                    self._dim_iter_things[dim]['spinboxAction'] = spinbox_action
        
        if DEBUG:
            print('_dim_iter_things:', self._dim_iter_things)
    
    def new_plot(self) -> Plot:
        plot: Plot = Plot()
        view: View = plot.getViewBox()
        view.setMinimumSize(5, 5)
        # viewBox.menu.addAction('Measure', lambda self=self, plot=plot: self.measure(plot))
        # viewBox.menu.addAction('Curve Fit', lambda self=self, plot=plot: self.curve_fit(plot))
        # viewBox.menu.addSeparator()
        view.sigItemAdded.connect(self.on_item_added_to_axes)
        return plot
    
    def on_var_selection_changed(self) -> None:
        # selected tree items
        self._selected_tree_items: list[XarrayTreeItem] = self._data_treeview.selected_items()
        if DEBUG:
            print('_selected_tree_items:', [item.path for item in self._selected_tree_items])
        
        # store the merged coords for the entire selection
        # also store the first defined attrs for each coord
        self._selected_tree_coords: dict[str, xr.DataArray] = {}
        for item in self._selected_tree_items:
            if item.node is None or item.node.dataset is None:
                continue
            item_coords: dict[str, xr.DataArray] = item.node.inherited_coords()
            for name, coords in item_coords.items():
                if name in self._selected_tree_coords:
                    # TODO: merge floats within some tolerance (maybe use xr.join()?), keep attrs?
                    attrs = self._selected_tree_coords[name].attrs
                    if not attrs:
                        attrs = coords.attrs
                    values = np.unique(np.concatenate((self._selected_tree_coords[name].values, coords.values)))
                    self._selected_tree_coords[name] = xr.DataArray(dims=name, data=values, attrs=attrs)
                else:
                    self._selected_tree_coords[name] = coords
        if DEBUG:
            print('_selected_tree_coords:', self._selected_tree_coords)
        
        # store the dims for the entire selection
        self._selected_sizes: dict[str, int] = {name: len(coords) for name, coords in self._selected_tree_coords.items()}
        self._selected_dims = list(self._selected_sizes)
        if DEBUG:
            print('_selected_sizes:', self._selected_sizes)
            print('_selected_dims:', self._selected_dims)

        # iterable dimensions with size > 1 (excluding xdim)
        self._iter_dims = [dim for dim in self._selected_dims if dim != self.xdim and self._selected_sizes[dim] > 1]
        if DEBUG:
            print('_iter_dims:', self._iter_dims)
        
        # update toolbar dim iter spin boxes (show/hide as needed)
        for dim in self._dim_iter_things:
            isVisible = dim in self._selected_dims and dim != self.xdim # and self._selected_sizes[dim] > 1
            self._dim_iter_things[dim]['labelAction'].setVisible(isVisible)
            self._dim_iter_things[dim]['spinboxAction'].setVisible(isVisible)
            if isVisible:
                spinbox: MultiValueSpinBox = self._dim_iter_things[dim]['spinbox']
                spinbox.blockSignals(True)
                values = spinbox.selectedValues()
                spinbox.setIndexedValues(self._selected_tree_coords[dim].values)
                spinbox.setSelectedValues(values)
                spinbox.blockSignals(False)
        if DEBUG:
            print('_dim_iter_things:', self._dim_iter_things)

        # selected var names
        self._selected_var_names = []
        for item in self._selected_tree_items:
            if item.is_var():
                if item.key not in self._selected_var_names:
                    self._selected_var_names.append(item.key)
        if DEBUG:
            print('_selected_var_names:', self._selected_var_names)

        # units for selected coords and vars
        self._selected_units = {}
        for dim in self._selected_tree_coords:
            if 'units' in self._selected_tree_coords[dim].attrs:
                self._selected_units[dim] = self._selected_tree_coords[dim].attrs['units']
        for item in self._selected_tree_items:
            if item.node is None:
                continue
            ds: xr.Dataset = item.node.dataset
            if ds is None:
                continue
            for name in self._selected_var_names:
                if name not in self._selected_units:
                    if name in ds.data_vars:
                        var = ds.data_vars[name]
                        if isinstance(var, xr.DataArray):
                            if 'units' in var.attrs:
                                self._selected_units[name] = var.attrs['units']
        if DEBUG:
            print('_selected_units:', self._selected_units)

        # flag plot grid for update
        self._plot_grid_needs_update = True

        # update index selection
        self.on_index_selection_changed()

    def on_index_selection_changed(self) -> None:
        # selected coords for all non-x-axis dims (from toolbar spin boxes)
        self._selected_coords: dict[str, xr.DataArray] = {}
        for dim in self._selected_tree_coords:
            if dim == self.xdim:
                continue
            if self._selected_sizes[dim] > 1:
                spinbox: MultiValueSpinBox = self._dim_iter_things[dim]['spinbox']
                values = spinbox.selectedValues()
                indices = np.searchsorted(self._selected_tree_coords[dim].values, values)
                self._selected_coords[dim] = self._selected_tree_coords[dim].isel({dim: indices})
            else:
                # single index along this dim
                self._selected_coords[dim] = self._selected_tree_coords[dim]
        if DEBUG:
            print('_selected_coords:', self._selected_coords)
        
        # update plot grid
        self.update_plot_grid()
    
    def update_plot_grid(self) -> None:
        selected_coords = self._selected_coords.copy()
        
        # grid tile dimensions
        n_row_tiles = 1
        n_col_tiles = 1
        row_tile_dim = self._row_tile_combobox.currentText()
        col_tile_dim = self._col_tile_combobox.currentText()
        if col_tile_dim == row_tile_dim:
            col_tile_dim = 'None'
        if row_tile_dim not in selected_coords:
            row_tile_dim = 'None'
        if col_tile_dim not in selected_coords:
            col_tile_dim = 'None'
        if row_tile_dim != 'None':
            row_tile_coords = selected_coords[row_tile_dim]
            n_row_tiles = len(row_tile_coords)
            del selected_coords[row_tile_dim]
        if col_tile_dim != 'None':
            col_tile_coords = selected_coords[col_tile_dim]
            n_col_tiles = len(col_tile_coords)
            del selected_coords[col_tile_dim]
        if DEBUG:
            print('row_tile_dim:', row_tile_dim, 'col_tile_dim:', col_tile_dim)
            if row_tile_dim != 'None':
                print('row_tile_coords:', row_tile_coords)
            if col_tile_dim != 'None':
                print('col_tile_coords:', col_tile_coords)
        
        # grid size
        n_vars = len(self._selected_var_names)
        grid_rows = n_vars * n_row_tiles
        grid_cols = n_col_tiles
        if DEBUG:
            print('n_vars:', n_vars, 'grid_rows:', grid_rows, 'grid_cols:', grid_cols)
        
        # resize plot grid
        if grid_rows * grid_cols == 0:
            self._plot_grid.clear()
            self._grid_rowlim = ()
            self._grid_collim = ()
            return
        if self._grid_rowlim != (0, grid_rows - 1) or self._grid_collim != (1, grid_cols):
            self._grid_rowlim = (0, grid_rows - 1)
            self._grid_collim = (1, grid_cols)
            rowmin, rowmax = self._grid_rowlim
            colmin, colmax = self._grid_collim
            axis_tick_font = QFont()
            axis_tick_font.setPointSize(self._axistick_fontsize_spinbox.value())
            for row in range(max(rowmax + 1, self._plot_grid.rowCount())):
                for col in range(max(colmax + 1, self._plot_grid.columnCount())):
                    item = self._plot_grid.getItem(row, col)
                    if rowmin <= row <= rowmax and colmin <= col <= colmax:
                        if item is not None and not issubclass(type(item), pg.PlotItem):
                            self._plot_grid.removeItem(item)
                            item.deleteLater()
                            item = None
                        if item is None:
                            item = self.new_plot()
                            self._plot_grid.addItem(item, row, col)
                        xaxis = item.getAxis('bottom')
                        yaxis = item.getAxis('left')
                        if row == rowmax:
                            xaxis.label.show() # show axes label
                        else:
                            xaxis.label.hide() # hide axes label
                        if col == colmin:
                            yaxis.label.show() # show axes label
                        else:
                            yaxis.label.hide() # hide axes label
                    else:
                        if item is not None:
                            self._plot_grid.removeItem(item)
                            item.deleteLater()
            
            self.link_axes()
            self.update_axes_tick_font()

        # assign vars and coords to each plot
        rowmin, rowmax = self._grid_rowlim
        colmin, colmax = self._grid_collim
        for row in range(rowmin, rowmax + 1):
            var_name = self._selected_var_names[(row - rowmin) % n_vars]
            for col in range(colmin, colmax + 1):
                plot: Plot = self._plot_grid.getItem(row, col)
                coords = selected_coords.copy()
                if row_tile_dim != 'None':
                    tile_index = int((row - rowmin) / n_vars) % n_row_tiles
                    tile_coord = row_tile_coords.values[tile_index]
                    coords[row_tile_dim] = xr.DataArray(data=[tile_coord], dims=[row_tile_dim], attrs=row_tile_coords.attrs)
                if col_tile_dim != 'None':
                    tile_index = (col - colmin) % n_col_tiles
                    tile_coord = col_tile_coords.values[tile_index]
                    coords[col_tile_dim] = xr.DataArray(data=[tile_coord], dims=[col_tile_dim], attrs=col_tile_coords.attrs)
                if coords:
                    coord_permutations = XarrayTreeNode.permutations(coords)
                else:
                    coord_permutations = [{}]
                plot.info = {
                    'vars': [var_name],
                    'coords': coords,
                    'coord_permutations': coord_permutations,
                }
                if DEBUG:
                    print(plot.info)
        
        # axis labels
        self.update_axes_labels()
        
        # update plot items
        self.update_plot_items()

        # ensure all plots have appropriate draw state
        self.draw_region()

        # update plot grid (hopefully after everything has been redrawn)
        QTimer.singleShot(100, self.update_grid_layout)
    
    def link_axes(self, xlink: bool | None = None, ylink: bool | None = None) -> None:
        if xlink is not None:
            self._link_xaxis_checkbox.blockSignals(True)
            self._link_xaxis_checkbox.setChecked(xlink)
            self._link_xaxis_checkbox.blockSignals(False)
        else:
            xlink = self._link_xaxis_checkbox.isChecked()
        
        if ylink is not None:
            self._link_yaxis_checkbox.blockSignals(True)
            self._link_yaxis_checkbox.setChecked(ylink)
            self._link_yaxis_checkbox.blockSignals(False)
        else:
            ylink = self._link_yaxis_checkbox.isChecked()
        
        try:
            rowmin, rowmax = self._grid_rowlim
            colmin, colmax = self._grid_collim
        except:
            return
        for row in range(rowmin, rowmax + 1):
            for col in range(colmin, colmax + 1):
                plot = self._plot_grid.getItem(row, col)
                if plot is not None and issubclass(type(plot), pg.PlotItem):
                    xaxis = plot.getAxis('bottom')
                    yaxis = plot.getAxis('left')
                    if xlink and row < rowmax:
                        plot.setXLink(self._plot_grid.getItem(rowmax, col))
                        xaxis.setStyle(showValues=False) # hide tick labels
                    else:
                        plot.setXLink(None)
                        xaxis.setStyle(showValues=True) # show tick labels
                    if ylink and col > colmin:
                        plot.setYLink(self._plot_grid.getItem(row, colmin))
                        yaxis.setStyle(showValues=False) # hide tick labels
                    else:
                        plot.setYLink(None)
                        yaxis.setStyle(showValues=True) # show tick labels

    def update_axes_labels(self) -> None:
        try:
            rowmin, rowmax = self._grid_rowlim
            colmin, colmax = self._grid_collim
        except:
            return
        row_tile_dim = self._row_tile_combobox.currentText()
        col_tile_dim = self._col_tile_combobox.currentText()
        if row_tile_dim not in self._selected_coords:
            row_tile_dim = 'None'
        if col_tile_dim not in self._selected_coords:
            col_tile_dim = 'None'
        if col_tile_dim == row_tile_dim:
            col_tile_dim = 'None'
        axis_label_style = {'color': 'rgb(0, 0, 0)', 'font-size': f'{self._axislabel_fontsize_spinbox.value()}pt'}
        tile_label_style = {'color': 'rgb(128, 128, 128)', 'font-size': f'{self._axislabel_fontsize_spinbox.value()}pt'}
        xunits = self._selected_units.get(self.xdim, None)
        for row in range(rowmin, rowmax + 1):
            # ylabel
            plot = self._plot_grid.getItem(row, colmin)
            if plot is not None and issubclass(type(plot), pg.PlotItem):
                var_name = self._selected_var_names[row % len(self._selected_var_names)]
                yunits = self._selected_units.get(var_name, None)
                yaxis: pg.AxisItem = plot.getAxis('left')
                yaxis.setLabel(text=var_name, units=yunits, **axis_label_style)
            # tile row label
            row_label = self._plot_grid.getItem(row, 0)
            if (row_label is not None) and ((row_tile_dim == 'None') or not isinstance(row_label, pg.AxisItem)):
                self._plot_grid.removeItem(row_label)
                row_label = None
            if row_tile_dim != 'None':
                tile_coord = self._plot_info[row,1]['coords'][row_tile_dim].values[0]
                label_text = f'{row_tile_dim}: {tile_coord}'
                if row_label is None:
                    row_label = pg.AxisItem('left')
                    row_label.setPen(pg.mkPen(width=0)) # hide axis lines
                    row_label.setStyle(showValues=False, tickLength=0) # hide tick labels
                    self._plot_grid.addItem(row_label, row, 0)
                    row_label.setLabel(text=label_text, **tile_label_style)
                else:
                    row_label.setLabel(text=label_text, **tile_label_style)
        for col in range(colmin, colmax + 1):
            # xlabel
            plot = self._plot_grid.getItem(rowmax, col)
            if plot is not None and issubclass(type(plot), pg.PlotItem):
                xaxis: pg.AxisItem = plot.getAxis('bottom')
                xaxis.setLabel(text=self.xdim, units=xunits, **axis_label_style)
            # tile col label
            col_label = self._plot_grid.getItem(rowmax + 1, col)
            if (col_label is not None) and ((col_tile_dim == 'None') or not isinstance(col_label, pg.AxisItem)):
                self._plot_grid.removeItem(col_label)
                col_label = None
            if col_tile_dim != 'None':
                tile_coord = self._plot_info[rowmax,col]['coords'][col_tile_dim].values[0]
                label_text = f'{col_tile_dim}: {tile_coord}'
                if col_label is None:
                    col_label = pg.AxisItem('bottom')
                    col_label.setPen(pg.mkPen(width=0)) # hide axis lines
                    col_label.setStyle(showValues=False, tickLength=0) # hide tick labels
                    self._plot_grid.addItem(col_label, rowmax + 1, col)
                    col_label.setLabel(text=label_text, **tile_label_style)
                else:
                    col_label.setLabel(text=label_text, **tile_label_style)
    
    def update_axes_tick_font(self) -> None:
        axis_tick_font = QFont()
        axis_tick_font.setPointSize(self._axistick_fontsize_spinbox.value())
        for plot in self.plots():
            plot.getAxis('left').setTickFont(axis_tick_font)
            plot.getAxis('bottom').setTickFont(axis_tick_font)
    
    def update_grid_layout(self) -> None:
        try:
            rowmin, rowmax = self._grid_rowlim
            colmin, colmax = self._grid_collim
        except:
            return
        # split viewbox area equally amongst plots
        width = height = 0
        for row in range(rowmin, rowmax + 1):
            plot = self._plot_grid.getItem(row, colmin)
            height += plot.getViewBox().height()
        for col in range(colmin, colmax + 1):
            plot = self._plot_grid.getItem(rowmin, col)
            width += plot.getViewBox().width()
        viewbox_width = int(width / float(colmax - colmin + 1))
        viewbox_height = int(height / float(rowmax - rowmin + 1))
        for row in range(rowmin, rowmax + 1):
            for col in range(colmin, colmax + 1):
                plot = self._plot_grid.getItem(row, col)
                xaxis = plot.getAxis('bottom')
                yaxis = plot.getAxis('left')
                plot.setPreferredWidth(viewbox_width + yaxis.width() if yaxis.isVisible() else viewbox_width)
                plot.setPreferredHeight(viewbox_height + xaxis.height() if xaxis.isVisible() else viewbox_height)
    
    def update_plot_items(self, plots: list[Plot] = None, item_types: list = None) -> None:
        if plots is None:
            plots = self.plots()
        default_line_width = self._linewidth_spinbox.value()
        for plot in plots:
            if plot is None or not issubclass(type(plot), pg.PlotItem):
                continue
            view: View = plot.getViewBox()
                
            if item_types is None or XYData in item_types:
                # existing data items in plot
                data_items = [item for item in plot.listDataItems() if isinstance(item, XYData)]
                
                # update data items in plot
                count = 0
                color_index = 0
                for tree_item in self._selected_tree_items:
                    if not tree_item.is_var():
                        continue
                    if 'vars' not in plot.info or tree_item.key not in plot.info['vars']:
                        continue
                    if tree_item.node is None:
                        continue
                    xarr, yarr = self.get_xy_data(tree_item.node, tree_item.key)
                    if xarr is None or yarr is None:
                        continue
                    xdata: np.ndarray = xarr.values
                    for coords in plot.info['coord_permutations']:
                        # x,y data
                        try:
                            # generally yarr_coords should be exactly coords, but just in case...
                            yarr_coords = {dim: dim_coords for dim, dim_coords in coords.items() if dim in yarr.dims}
                            ydata: np.ndarray = np.squeeze(yarr.sel(yarr_coords).values)
                            if len(ydata.shape) == 0:
                                ydata = ydata.reshape((1,))
                        except:
                            continue
                        
                        # show data in plot
                        if len(data_items) > count:
                            # update existing data in plot
                            data_item = data_items[count]
                            data_item.setData(x=xdata, y=ydata)
                        else:
                            # add new data to plot
                            data_item = XYData(x=xdata, y=ydata)
                            plot.addItem(data_item)
                            data_items.append(data_item)
                        
                        # store tree info
                        data_item.info = {
                            'tree_item': tree_item,
                            'coords': coords,
                        }
                        
                        # data style
                        style = yarr.attrs.get('style', {})
                        if 'LineWidth' not in style:
                            style['LineWidth'] = default_line_width
                        style = XYDataStyleDict(style)
                        color_index = data_item.setStyleDict(style, colorIndex=color_index)
                        
                        # data name (limit to 50 characters)
                        name: str = tree_item.node.path + tree_item.key
                        name_parts: list[str] = name.split('/')
                        name = name_parts[-1]
                        for i in reversed(range(len(name_parts) - 1)):
                            if i > 0 and len(name) + len(name_parts[i]) >= 50:
                                name = '.../' + name
                                break
                            name = name_parts[i] + '/' + name
                        data_item.setName(name)
                        
                        # next data item
                        count += 1
                
                # remove extra data items from plot
                while len(data_items) > count:
                    data_item = data_items.pop()
                    plot.removeItem(data_item)
                    data_item.deleteLater()
    
    def plots(self, grid_rows: list[int] = None, grid_cols: list[int] = None) -> list[Plot]:
        try:
            rowmin, rowmax = self._grid_rowlim
            colmin, colmax = self._grid_collim
        except:
            return []
        if grid_rows is None:
            grid_rows = range(rowmin, rowmax + 1)
        if grid_cols is None:
            grid_cols = range(colmin, colmax + 1)
        plots = []
        for row in grid_rows:
            for col in grid_cols:
                plot = self._plot_grid.getItem(row, col)
                if plot is not None and issubclass(type(plot), pg.PlotItem):
                    plots.append(plot)
        return plots
    
    def get_xy_data(self, node: XarrayTreeNode, var_name: str) -> tuple[xr.DataArray | None, xr.DataArray | None]:
        ds: xr.Dataset = node.dataset
        if ds is None:
            return None, None
        try: 
            ydata: xr.DataArray = ds.data_vars[var_name]
            xdata = node.inherited_coord(self.xdim)
            return xdata, ydata
        except:
            return None, None
    
    def update_item_font(self):
        for plot in self.plots():
            view: View = plot.getViewBox()
            for item in view.allChildren():
                if isinstance(item, XAxisRegion):
                    item.setFontSize(self._textitem_fontsize_spinbox.value())

    def autoscale_plots(self, plots: list[Plot] = None) -> None:
        if plots is None:
            plots = self.plots()
        for plot in plots:
            plot.autoRange()
            plot.enableAutoRange()

    def resizeEvent(self, event: QResizeEvent) -> None:
        QWidget.resizeEvent(self, event)
        self.update_grid_layout()
 
    def draw_region(self, draw: bool | None = None) -> None:
        if draw is None:
            draw = self._region_button.isChecked()
        self._region_button.setChecked(draw)
        
        try:
            rowmin, rowmax = self._grid_rowlim
            colmin, colmax = self._grid_collim
        except:
            return
        for row in range(rowmin, rowmax + 1):
            for col in range(colmin, colmax + 1):
                plot = self._plot_grid.getItem(row, col)
                if plot is not None and issubclass(type(plot), pg.PlotItem):
                    view: View = plot.getViewBox()
                    if draw:
                        view.startDrawingItemsOfType(XAxisRegion)
                    else:
                        view.stopDrawingItems()
    
    def update_regions(self, which_regions: str = 'all', is_visible: bool | None = None, is_moveable: bool | None = None, clear: bool = False) -> None:
        for plot in self.plots():
            view: View = plot.getViewBox()
            regions: list[XAxisRegion] = [item for item in view.allChildren() if isinstance(item, XAxisRegion)]
            if which_regions == 'all':
                pass
            elif which_regions == 'visible':
                regions = [region for region in regions if region.isVisible()]
            elif which_regions == 'hidden':
                regions = [region for region in regions if not region.isVisible()]
            if clear:
                for region in regions:
                    view.removeItem(region)
                    region.deleteLater()
                continue
            if is_visible is not None:
                for region in regions:
                    region.setVisible(is_visible)
            if is_moveable is not None:
                for region in regions:
                    region.setMovable(is_moveable)
        if clear:
            self._region_name_list.selectionModel().clear()
    
    def ensure_regions_in_tree(self) -> None:
        if 'regions' not in self.data.children:
            regions_node = XarrayTreeNode(name='regions', dataset=xr.Dataset(attrs={'regions': {}}), parent=self.data)
            # update tree view
            self._data_treeview.set_data(self.data)
            return
        
        regions_node = self.data.children['regions']
        if 'regions' not in regions_node.dataset.attrs:
            regions_node.dataset.attrs['regions'] = {}
    
    def name_regions(self, name: str = '') -> None:
        if name == '':
            name, ok = QInputDialog.getText(self, 'Name Regions', 'Name selected regions:')
            name = name.strip()
            if not ok or name == '':
                return
        
        self.ensure_regions_in_tree()
        regions_attrs = self.data.children['regions'].dataset.attrs['regions']
        xdim = self.xdim
        if xdim not in regions_attrs:
            regions_attrs[xdim] = {}
        if name in regions_attrs[xdim]:
            answer = QMessageBox.question(self, 'Overwrite Existing Name?', f'Name "{name}" already exists. Overwrite?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer == QMessageBox.No:
                return
        # will fill with selected regions
        regions_attrs[xdim][name] = []
        
        for plot in self.plots():
            view: View = plot.getViewBox()
            region_items: list[XAxisRegion] = [item for item in view.allChildren() if isinstance(item, XAxisRegion)]
            for item in region_items:
                item.setGroup(name)
                regions_attrs[xdim][name].append({
                    'region': list(item.getRegion()),
                    'text': item.text(),
                })
        
        names = [self._region_name_list.item(i).text() for i in range(self._region_name_list.count())]
        if name not in names:
            self._region_name_list.addItem(name)
            names.append(name)
        self._region_name_list.setCurrentRow(names.index(name))
    
    def select_regions(self, names: list[str] = None) -> None:
        if self._region_name_list.count() == 0:
            return
        
        if names is None:
            names = []
            for i in range(self._region_name_list.count()):
                if self._region_name_list.item(i).isSelected():
                    names.append(self._region_name_list.item(i).text())
        
        # clear current regions
        self.update_regions(clear=True)
        
        # select regions
        regions_attrs = self.data.children['regions'].dataset.attrs['regions']
        xdim = self.xdim
        
        regions: list[dict] = []
        for name in names:
            try:
                regions += regions_attrs[xdim][name]
                self._region_name_list.selectionModel().select(self._region_name_list.findItems(name, Qt.MatchExactly)[0].index(), QItemSelectionModel.Select)
            except:
                continue
        
        for plot in self.plots():
            view: View = plot.getViewBox()
            for region in regions:
                region_item = XAxisRegion(region['region'])
                region_item.setText(region['text'])
                view.addItem(region_item)
    
    @Slot(QGraphicsObject)
    def on_item_added_to_axes(self, item: QGraphicsObject):
        view: View = self.sender()
        plot: Plot = view.parentItem()
        if isinstance(item, XAxisRegion):
            item.setFontSize(self._textitem_fontsize_spinbox.value())
            # editing the region text via the popup dialog will also reset the region,
            # so this will cover text changes too
            item.sigRegionChangeFinished.connect(self.on_axes_item_changed)
            # stop drawing regions (draw one at a time)
            self.draw_region(False)

    @Slot()
    def on_axes_item_changed(self):
        item = self.sender()
        if isinstance(item, XAxisRegion):
            pass # TODO: handle region change
    
    def measure(self, plots: list[Plot] = None) -> None:
        if plots is None:
            plots = self.plots()
        
        # name for measure
        result_name = self._measure_name_edit.text().strip()
        if not result_name:
            result_name = self._measure_name_edit.placeholderText()
                
        # measure options
        measure_type = self._measure_type_combobox.currentText()
        if measure_type in ['Mean', 'Median', 'Standard Deviation', 'Variance']:
            def existing_median(x):
                # ensures picking an existing data point for the central value
                i = np.argpartition(x, len(x) // 2)[len(x) // 2]
                return x[i]
        elif measure_type in ['Min', 'Max', 'AbsMax']:
            peak_width = self._peak_width_spinbox.value()
            if peak_width > 0:
                def get_peak_index_range(mask, center_index):
                    start, stop = center_index, center_index + 1
                    for w in range(peak_width):
                        if center_index - w >= 0 and mask[center_index - w] and start == center_index - w + 1:
                            start = center_index - w
                        if center_index + w < len(mask) and mask[center_index + w] and stop == center_index + w:
                            stop = center_index + w + 1
                    return start, stop
        
        # measure in each plot
        for plot in plots:
            data_items = [item for item in plot.listDataItems() if isinstance(item, XYData)]
            if not data_items:
                continue

            # regions
            view: View = plot.getViewBox()
            regions: list[tuple[float, float]] = [item.getRegion() for item in view.allChildren() if isinstance(item, XAxisRegion) and item.isVisible()]

            # measure for each data item
            plot._tmp_measures: list[xr.Dataset] = []
            plot._tmp_measure_tree_items: list[XarrayTreeItem] = []

            for data_item in data_items:
                tree_item: XarrayTreeItem = data_item.info['tree_item']
                data_coords: dict = data_item.info['coords']

                # x,y data
                xarr, yarr = self.get_xy_data(tree_item.node, tree_item.key)
                if xarr is None or yarr is None:
                    continue
                xdata: np.ndarray = xarr.values
                # generally yarr_coords should be exactly data_coords, but just in case...
                yarr_coords = {dim: dim_coords for dim, dim_coords in data_coords.items() if dim in yarr.dims}
                ydata: np.ndarray = np.squeeze(yarr.sel(yarr_coords).values)
                if len(ydata.shape) == 0:
                    ydata = ydata.reshape((1,))
                
                # dimensions
                dims = yarr.dims
                
                # mask for each measurement point
                masks = []
                if regions and self._measure_per_visible_region_checkbox.isChecked():
                    # one mask per region
                    for region in regions:
                        xmin, xmax = region
                        mask = (xdata >= xmin) & (xdata <= xmax)
                        masks.append(mask)
                elif regions and self._measure_in_visible_regions_only_checkbox.isChecked():
                    # mask for combined regions
                    mask = np.full(xdata.shape, False)
                    for region in regions:
                        xmin, xmax = region
                        mask[(xdata >= xmin) & (xdata <= xmax)] = True
                    masks = [mask]
                else:
                    # mask for everything
                    mask = np.full(xdata.shape, True)
                    masks = [mask]
                
                # measure in each mask
                xmeasure = []
                ymeasure = []
                for mask in masks:
                    if not np.any(mask):
                        continue
                    x = xdata[mask]
                    y = ydata[mask]
                    if measure_type == 'Mean':
                        xmeasure.append(existing_median(x))
                        ymeasure.append(np.mean(y))
                    elif measure_type == 'Median':
                        xmeasure.append(existing_median(x))
                        ymeasure.append(np.median(y))
                    elif measure_type == 'Min':
                        i = np.argmin(y)
                        xmeasure.append(x[i])
                        if peak_width == 0:
                            ymeasure.append(y[i])
                        else:
                            center_index = np.where(mask)[0][i]
                            start, stop = get_peak_index_range(mask, center_index)
                            ymeasure.append(np.mean(ydata[start:stop]))
                    elif measure_type == 'Max':
                        i = np.argmax(y)
                        xmeasure.append(x[i])
                        if peak_width == 0:
                            ymeasure.append(y[i])
                        else:
                            center_index = np.where(mask)[0][i]
                            start, stop = get_peak_index_range(mask, center_index)
                            ymeasure.append(np.mean(ydata[start:stop]))
                    elif measure_type == 'AbsMax':
                        i = np.argmax(np.abs(y))
                        xmeasure.append(x[i])
                        if peak_width == 0:
                            ymeasure.append(y[i])
                        else:
                            center_index = np.where(mask)[0][i]
                            start, stop = get_peak_index_range(mask, center_index)
                            ymeasure.append(np.mean(ydata[start:stop]))
                    elif measure_type == 'Peaks':
                        pass # TODO
                    elif measure_type == 'Standard Deviation':
                        xmeasure.append(existing_median(x))
                        ymeasure.append(np.std(y))
                    elif measure_type == 'Variance':
                        xmeasure.append(existing_median(x))
                        ymeasure.append(np.var(y))
                
                if not ymeasure:
                    continue
                
                # order measures by x
                xmeasure = np.array(xmeasure)
                ymeasure = np.array(ymeasure)
                order = np.argsort(xmeasure)
                xmeasure = xmeasure[order]
                ymeasure = ymeasure[order]

                # measures as xarray dataset
                shape =[1] * len(dims)
                shape[dims.index(self.xdim)] = len(ymeasure)
                measure_coords = {}
                for dim, coord in data_coords.items():
                    attrs = self._selected_tree_coords[dim].attrs.copy()
                    if dim == self.xdim:
                        measure_coords[dim] = xr.DataArray(dims=[dim], data=xmeasure, attrs=attrs)
                    else:
                        coord_values = np.array(coord.values).reshape((1,))
                        measure_coords[dim] = xr.DataArray(dims=[dim], data=coord_values, attrs=attrs)
                if self.xdim not in measure_coords:
                    attrs = self._selected_tree_coords[self.xdim].attrs.copy()
                    measure_coords[self.xdim] = xr.DataArray(dims=[self.xdim], data=xmeasure, attrs=attrs)
                attrs = yarr.attrs.copy()
                if 'style' not in attrs:
                    attrs['style'] = {}
                attrs['style']['LineStyle'] = 'none'
                attrs['style']['Marker'] = 'o'
                attrs['style']['MarkerEdgeWidth'] = 2
                measure = xr.Dataset(
                    data_vars={
                        tree_item.key: xr.DataArray(dims=dims, data=ymeasure.reshape(shape), attrs=attrs)
                    },
                    coords=measure_coords
                )
                plot._tmp_measures.append(measure)
                plot._tmp_measure_tree_items.append(tree_item)
        
        # preview measurements
        for plot in plots:
            plot._tmp_measure_items = []
            for measure in plot._tmp_measures:
                var_name = list(measure.data_vars)[0]
                var = measure.data_vars[var_name]
                xdata = measure.coords[self.xdim].values
                ydata = np.squeeze(var.values)
                if len(ydata.shape) == 0:
                    ydata = ydata.reshape((1,))
                pen = pg.mkPen(color=(255, 0, 0), width=2)
                measure_item = XYData(x=xdata, y=ydata, pen=pen, symbol='o', symbolSize=10, symbolPen=pen, symbolBrush=(255, 0, 0, 0))
                plot.addItem(measure_item)
                plot._tmp_measure_items.append(measure_item)
        
        # query user to keep measures
        answer = QMessageBox.question(self, 'Keep Measures?', 'Keep measurements?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            for plot in plots:
                for item in plot._tmp_measure_items:
                    plot.removeItem(item)
                    item.deleteLater()
                plot._tmp_measure_items = []
                plot._tmp_measures = []
                plot._tmp_measure_tree_items = []
            return
        
        # add measures to data tree
        measure_tree_nodes = []
        merge_approved = None
        for plot in plots:
            for tree_item, measure in zip(plot._tmp_measure_tree_items, plot._tmp_measures):
                parent_node: XarrayTreeNode = tree_item.node
                # append measure as child tree node
                if result_name in parent_node.children:
                    if merge_approved is None:
                        answer = QMessageBox.question(self, 'Merge Result?', 'Merge measures with existing datasets of same name?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                        merge_approved = (answer == QMessageBox.Yes)
                    if not merge_approved:
                        continue
                    # merge measurement with existing child dataset (use measurement for any overlap)
                    existing_child_node: XarrayTreeNode = parent_node.children[result_name]
                    existing_child_node.dataset: xr.Dataset = measure.combine_first(existing_child_node.dataset)
                    measure_tree_nodes.append(existing_child_node)
                else:
                    # append measurement as new child node
                    node = XarrayTreeNode(name=result_name, dataset=measure, parent=parent_node)
                    measure_tree_nodes.append(node)
        
        # update data tree
        self.data = self.data

        # make sure newly added measure nodes are selected and expanded
        model: XarrayTreeModel = self._data_treeview.model()
        item: XarrayTreeItem = model.root
        while item is not None:
            for node in measure_tree_nodes:
                if item.node is node and item.is_var():
                    index: QModelIndex = model.createIndex(item.row(), 0, item)
                    self._data_treeview.selectionModel().select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
                    self._data_treeview.setExpanded(model.parent(index), True)
            item = item.next_depth_first()

    def curve_fit(self, plots: list[Plot] = None, eval_equation_only: bool = False) -> None:
        if plots is None:
            plots = self.plots()
        
        # name for fit
        result_name = self._curve_fit_name_edit.text().strip()
        if not result_name:
            result_name = self._curve_fit_name_edit.placeholderText()
                
        # fit options
        fit_type = self._curve_fit_type_combobox.currentText()
        if fit_type == 'Polynomial':
            degree = self._polynomial_degree_spinbox.value()
        elif fit_type == 'Spline':
            segments = self._spline_segments_spinbox.value()
        elif fit_type == 'Equation':
            self._update_curve_fit_model()
            params = self._curve_fit_model.make_params()
        
        # fit in each plot
        for plot in plots:
            data_items = [item for item in plot.listDataItems() if isinstance(item, XYData)]
            if not data_items:
                continue

            # regions
            view: View = plot.getViewBox()
            regions: list[tuple[float, float]] = [item.getRegion() for item in view.allChildren() if isinstance(item, XAxisRegion) and item.isVisible()]

            # fit for each data item
            plot._tmp_fits: list[xr.Dataset] = []
            plot._tmp_fit_tree_items: list[XarrayTreeItem] = []

            for data_item in data_items:
                tree_item: XarrayTreeItem = data_item.info['tree_item']
                data_coords: dict = data_item.info['coords']

                # x,y data
                xarr, yarr = self.get_xy_data(tree_item.node, tree_item.key)
                if xarr is None or yarr is None:
                    continue
                xdata: np.ndarray = xarr.values
                # generally yarr_coords should be exactly data_coords, but just in case...
                yarr_coords = {dim: dim_coords for dim, dim_coords in data_coords.items() if dim in yarr.dims}
                ydata: np.ndarray = np.squeeze(yarr.sel(yarr_coords).values)
                if len(ydata.shape) == 0:
                    ydata = ydata.reshape((1,))
                
                # dimensions
                dims = yarr.dims
                
                # region mask for fit optimization and/or evaluation
                if regions and (self._curve_fit_optimize_in_visible_regions_checkbox.isChecked() or self._curve_fit_evaluate_in_visible_regions_checkbox.isChecked()):
                    # mask for combined regions
                    regions_mask = np.full(xdata.shape, False)
                    for region in regions:
                        xmin, xmax = region
                        regions_mask[(xdata >= xmin) & (xdata <= xmax)] = True

                if regions and self._curve_fit_optimize_in_visible_regions_checkbox.isChecked():
                    xinput = xdata[regions_mask]
                    yinput = ydata[regions_mask]
                else:
                    xinput = xdata
                    yinput = ydata

                if regions and self._curve_fit_evaluate_in_visible_regions_checkbox.isChecked():
                    xoutput = xdata[regions_mask]
                else:
                    xoutput = xdata
                
                # fit
                if fit_type == 'Mean':
                    youtput = np.full(len(xoutput), np.mean(yinput))
                elif fit_type == 'Median':
                    youtput = np.full(len(xoutput), np.median(yinput))
                elif fit_type == 'Polynomial':
                    coef = np.polyfit(xinput, yinput, degree)
                    youtput = np.polyval(coef, xoutput)
                elif fit_type == 'Spline':
                    segment_length = max(1, int(len(xinput) / segments))
                    knots = xinput[segment_length:-segment_length:segment_length]
                    if len(knots) < 2:
                        knots = xinput[[1, -2]]
                    knots, coef, degree = sp.interpolate.splrep(xinput, yinput, t=knots)
                    youtput = sp.interpolate.splev(xoutput, (knots, coef, degree), der=0)
                elif fit_type == 'Equation':
                    result = self._curve_fit_model.fit(yinput, params=params, x=xinput)
                    if DEBUG:
                        print(result.fit_report())
                    youtput = self._curve_fit_model.eval(params=result.params, x=xoutput)

                # fit as xarray dataset
                shape =[1] * len(dims)
                shape[dims.index(self.xdim)] = len(xoutput)
                fit_coords = {}
                for dim, coord in data_coords.items():
                    attrs = self._selected_tree_coords[dim].attrs.copy()
                    if dim == self.xdim:
                        fit_coords[dim] = xr.DataArray(dims=[dim], data=xoutput, attrs=attrs)
                    else:
                        coord_values = np.array(coord.values).reshape((1,))
                        fit_coords[dim] = xr.DataArray(dims=[dim], data=coord_values, attrs=attrs)
                if self.xdim not in fit_coords:
                    attrs = self._selected_tree_coords[self.xdim].attrs.copy()
                    fit_coords[self.xdim] = xr.DataArray(dims=[self.xdim], data=xoutput, attrs=attrs)
                attrs = yarr.attrs.copy()
                fit = xr.Dataset(
                    data_vars={
                        tree_item.key: xr.DataArray(dims=dims, data=youtput.reshape(shape), attrs=attrs)
                    },
                    coords=fit_coords
                )
                plot._tmp_fits.append(fit)
                plot._tmp_fit_tree_items.append(tree_item)
        
        # preview fits
        for plot in plots:
            plot._tmp_fit_items = []
            for fit in plot._tmp_fits:
                var_name = list(fit.data_vars)[0]
                var = fit.data_vars[var_name]
                xdata = fit.coords[self.xdim].values
                ydata = np.squeeze(var.values)
                if len(ydata.shape) == 0:
                    ydata = ydata.reshape((1,))
                pen = pg.mkPen(color=(255, 0, 0), width=2)
                fit_item = XYData(x=xdata, y=ydata, pen=pen)
                plot.addItem(fit_item)
                plot._tmp_fit_items.append(fit_item)
        
        # update equation params table with final fit params
        if fit_type == 'Equation':
            for row in range(self._equation_params_table.rowCount()):
                name = self._equation_params_table.item(row, 0).text()
                if result.params[name].vary:
                    value_item = self._equation_params_table.item(row, 1)
                    value_item.setText(f'{result.params[name].value:.6g}')
            self._equation_params_table.resizeColumnToContents(1)
            if eval_equation_only:
                return
        
        # query user to keep fits
        answer = QMessageBox.question(self, 'Keep Fits?', 'Keep fits?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            for plot in plots:
                for item in plot._tmp_fit_items:
                    plot.removeItem(item)
                    item.deleteLater()
                plot._tmp_fit_items = []
                plot._tmp_fits = []
                plot._tmp_fit_tree_items = []
            return
        
        # add fits to data tree
        fit_tree_nodes = []
        merge_approved = None
        for plot in plots:
            for tree_item, fit in zip(plot._tmp_fit_tree_items, plot._tmp_fits):
                parent_node: XarrayTreeNode = tree_item.node
                # append measure as child tree node
                if result_name in parent_node.children:
                    if merge_approved is None:
                        answer = QMessageBox.question(self, 'Merge Result?', 'Merge fits with existing datasets of same name?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                        merge_approved = (answer == QMessageBox.Yes)
                    if not merge_approved:
                        continue
                    # merge measurement with existing child dataset (use measurement for any overlap)
                    existing_child_node: XarrayTreeNode = parent_node.children[result_name]
                    existing_child_node.dataset: xr.Dataset = fit.combine_first(existing_child_node.dataset)
                    fit_tree_nodes.append(existing_child_node)
                else:
                    # append measurement as new child node
                    node = XarrayTreeNode(name=result_name, dataset=fit, parent=parent_node)
                    fit_tree_nodes.append(node)
        
        # update data tree
        self.data = self.data

        # make sure newly added fit nodes are selected and expanded
        model: XarrayTreeModel = self._data_treeview.model()
        item: XarrayTreeItem = model.root
        while item is not None:
            for node in fit_tree_nodes:
                if item.node is node and item.is_var():
                    index: QModelIndex = model.createIndex(item.row(), 0, item)
                    self._data_treeview.selectionModel().select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
                    self._data_treeview.setExpanded(model.parent(index), True)
            item = item.next_depth_first()
    
    def clear_curve_fits(self, plots: list[Plot] = None) -> None:
        if plots is None:
            plots = self.plots()
        for plot in plots:
            for item in plot._tmp_fit_items:
                plot.removeItem(item)
                item.deleteLater()
            plot._tmp_fit_items = []
            plot._tmp_fits = []
            plot._tmp_fit_tree_items = []


def test_live():
    app = QApplication()

    ui = XarrayGraph()
    ui.setWindowTitle(ui.__class__.__name__)
    ui.show()

    n = 100
    raw_ds = xr.Dataset(
        data_vars={
            'current': (['series', 'sweep', 'time'], np.random.rand(3, 10, n) * 1e-9, {'units': 'A'}),
            'voltage': (['series', 'sweep', 'time'], np.random.rand(3, 10, n) * 10000, {'units': 'V'}),
        },
        coords={
            'time': ('time', np.arange(n) * 0.01, {'units': 's'}),
        },
    )

    baselined_ds = xr.Dataset(
        data_vars={
            'current': (['series', 'sweep', 'time'], np.random.rand(3, 10, n) * 1e-9, {'units': 'A'}),
        },
    )

    scaled_ds = xr.Dataset(
        data_vars={
            'current': (['series', 'sweep', 'time'], np.random.rand(1, 2, n) * 1e-9, {'units': 'A'}),
        },
        coords={
            'series': ('series', [1]),
            'sweep': ('sweep', [5,8]),
        },
    )
    
    root_node = XarrayTreeNode(name='/', dataset=None)
    raw_node = XarrayTreeNode(name='raw data', dataset=raw_ds, parent=root_node)
    baselined_node = XarrayTreeNode(name='baselined', dataset=baselined_ds, parent=raw_node)
    scaled_node = XarrayTreeNode(name='scaled', dataset=scaled_ds, parent=baselined_node)

    ui.data = root_node

    # ui.data = np.linspace(0, 5, 100), np.random.random((3, 10, 100))
    # ui.set_data([1, 3, 5, 7, 9], [10, 13, 56, 47, 29])
    # ui.data = np.random.random((1000,))

    app.exec()


if __name__ == '__main__':
    test_live()
