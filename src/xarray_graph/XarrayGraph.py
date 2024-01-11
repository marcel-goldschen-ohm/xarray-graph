""" PySide/PyQt widget for analyzing (x,y) data series in a Xarray dataset or a tree of datasets.
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
# import datatree as xt
# import zarr
import sys, re
from pyqt_ext import *
from pyqtgraph_ext import *
from xarray_treeview import *


# pg.setConfigOption('background', (235, 235, 235))
# pg.setConfigOption('foreground', (0, 0, 0))


DEBUG = 0
DEFAULT_AXIS_LABEL_FONT_SIZE = 12
DEFAULT_AXIS_TICK_FONT_SIZE = 11
DEFAULT_TEXT_ITEM_FONT_SIZE = 10
DEFAULT_LINE_WIDTH = 1


class XarrayGraph(QWidget):
    """ PySide/PyQt widget for analyzing (x,y) data series in a Xarray dataset. """

    def __init__(self, *args, **kwargs):
        QWidget.__init__(self, *args, **kwargs)

        # the waveform data
        self._data: XarrayTreeNode | None = None

        # the x-axis dimension to be plotted against
        self._xdim: str = 'time'

        # selections
        self._tree_coords: dict[str, xr.DataArray] = {}

        # setup the graphical user interface
        self.setup_ui()
    
    @property
    def data(self) -> XarrayTreeNode | None:
        return self._data
    
    @data.setter
    def data(self, data: XarrayTreeNode | xr.Dataset | None, **kwargs):
        # set xarray tree
        if isinstance(data, xr.Dataset):
            root_node: XarrayTreeNode = XarrayTreeNode(name='/', dataset=None)
            XarrayTreeNode(name='dataset', dataset=data, parent=root_node)
            self._data = root_node
        elif isinstance(data, XarrayTreeNode):
            if data.dataset is not None and data.parent is None:
                # add an empty root node
                root_node: XarrayTreeNode = XarrayTreeNode(name='/', dataset=None)
                data.parent = root_node
                data = root_node
            self._data = data
        elif isinstance(data, np.ndarray):
            return # TODO: y
        elif isinstance(data, tuple):
            return # TODO: (x, y)
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

        autoscale = kwargs.get('autoscale', True)
        if autoscale:
            self.autoscale_plots()
    
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
        self.setup_top_toolbar()
        self.setup_view_panel()
        self.setup_plot_grid()
        self.setup_display_settings()

        # main layout
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(3, 3, 3, 3)
        vbox.setSpacing(0)
        vbox.addWidget(self._toolbar_top)
        hsplitter = QSplitter(Qt.Orientation.Horizontal)
        hsplitter.addWidget(self._view_panel)
        hsplitter.addWidget(self._plot_grid)
        hsplitter.setStretchFactor(0, 0)
        hsplitter.setStretchFactor(1, 1)
        vbox.addWidget(hsplitter)
    
    def setup_top_toolbar(self) -> None:
        # toolbar
        self._toolbar_top = QToolBar()
        self._toolbar_top.setStyleSheet("QToolBar{spacing:2px;}")

        # view button
        self._view_button = QToolButton()
        self._view_button.setIcon(qta.icon('ph.eye-thin', options=[{'opacity': 0.7}]))
        self._view_button.setToolTip('View Selections/Options')
        self._view_button.clicked.connect(lambda: self._view_panel.setVisible(not self._view_panel.isVisible()))
        self._toolbar_top.addWidget(self._view_button)

        # widgets and toolbar actions for iterating dimension indices
        self._dim_iter_things: dict[str, dict[str, QLabel | MultiValueSpinBox | QAction]] = {}

        # region button
        self._region_button = QToolButton()
        self._region_button.setIcon(qta.icon('mdi.arrow-expand-horizontal', options=[{'opacity': 0.5}]))
        self._region_button.setToolTip('X axis regions')
        self._region_button.setCheckable(True)
        self._region_button.setChecked(False)
        self._region_button.setPopupMode(QToolButton.InstantPopup)
        self._region_button_menu = QMenu()
        self._draw_regions_action = self._region_button_menu.addAction(qta.icon('mdi.pencil'), 'Draw regions', self.draw_regions)
        self._draw_regions_action.setCheckable(True)
        self._draw_regions_action.setChecked(False)
        self._region_button_menu.addSeparator()
        self._region_button_menu.addAction('Hide visible regions', lambda: self.update_regions(is_visible=False))
        self._region_button_menu.addAction('Show hidden regions', lambda: self.update_regions(is_visible=True))
        self._region_button_menu.addSeparator()
        self._region_button_menu.addAction('Freeze visible regions', lambda: self.update_regions(which_regions='visible', is_moveable=False))
        self._region_button_menu.addAction('Unfreeze visible regions', lambda: self.update_regions(which_regions='visible', is_moveable=True))
        self._region_button_menu.addSeparator()
        self._region_button_menu.addAction('Name visible regions').setDisabled(True) # TODO: implement
        self._region_button_menu.addAction('Manage named regions').setDisabled(True) # TODO: implement
        self._region_button_menu.addSeparator()
        self._region_button_menu.addAction('Clear regions', lambda: self.update_regions(clear=True))
        self._region_button.setMenu(self._region_button_menu)
        self._region_action = self._toolbar_top.addWidget(self._region_button)
        self._action_after_dim_iter_things = self._region_action

        # home button
        self._home_button = QToolButton()
        self._home_button.setIcon(qta.icon('mdi.home-outline', options=[{'opacity': 0.5}]))
        self._home_button.setToolTip('Autoscale all plots')
        self._home_button.clicked.connect(self.autoscale_plots)
        self._home_action = self._toolbar_top.addWidget(self._home_button)
    
    def setup_view_panel(self) -> None:
        # data tree
        self._data_treeview = XarrayTreeView()
        self._data_treeview.setSelectionMode(QAbstractItemView.MultiSelection)
        root_node: XarrayTreeNode = self.data if self.data is not None else XarrayTreeNode('/', None)
        root_item = XarrayTreeItem(node=root_node, key=None)
        model: XarrayTreeModel = XarrayTreeModel(root_item)
        model._allowed_selections = ['var']
        self._data_treeview.setModel(model)
        self._data_treeview.selection_changed.connect(self.on_var_selection_changed)

        # x-axis selection
        self._xdim_combobox = QComboBox()
        self._xdim_combobox.currentTextChanged.connect(self.set_xdim)

        # display settings button
        self._display_settings_button = QToolButton()#QPushButton('Display Options')
        self._display_settings_button.setIcon(qta.icon('msc.settings-gear', options=[{'opacity': 0.7}]))
        self._display_settings_button.setToolTip('Display Options')
        self._display_settings_button.clicked.connect(self.display_settings_dialog)
        
        # view panel
        self._view_panel = QWidget()
        vbox = QVBoxLayout(self._view_panel)
        vbox.setContentsMargins(3, 3, 3, 3)
        vbox.setSpacing(5)
        vbox.addWidget(self._data_treeview)
        hbox = QHBoxLayout()
        hbox.addWidget(QLabel('X axis:'))
        hbox.addWidget(self._xdim_combobox)
        hbox.addStretch()
        hbox.addWidget(self._display_settings_button)
        vbox.addLayout(hbox)
    
    def setup_plot_grid(self) -> None:
        self._plot_grid = PlotGrid()
        self._grid_rowlim = ()
        self._grid_collim = ()
    
    def setup_display_settings(self) -> None:
        # row/col tile selection
        self._row_tile_combobox = QComboBox()
        self._row_tile_combobox.addItems(['None'])
        self._row_tile_combobox.setCurrentText('None')
        self._row_tile_combobox.currentTextChanged.connect(self.update_plot_grid)

        self._col_tile_combobox = QComboBox()
        self._col_tile_combobox.addItems(['None'])
        self._col_tile_combobox.setCurrentText('None')
        self._col_tile_combobox.currentTextChanged.connect(self.update_plot_grid)

        # link axes
        self._link_xaxis_checkbox = QCheckBox()
        self._link_xaxis_checkbox.setChecked(True)
        self._link_xaxis_checkbox.stateChanged.connect(lambda: self.link_axes())

        self._link_yaxis_checkbox = QCheckBox()
        self._link_yaxis_checkbox.setChecked(True)
        self._link_yaxis_checkbox.stateChanged.connect(lambda: self.link_axes())

        # font size
        self._axislabel_fontsize_spinbox = QSpinBox()
        self._axislabel_fontsize_spinbox.setValue(DEFAULT_AXIS_LABEL_FONT_SIZE)
        self._axislabel_fontsize_spinbox.setSuffix('pt')
        self._axislabel_fontsize_spinbox.valueChanged.connect(self.update_axes_labels)

        self._axistick_fontsize_spinbox = QSpinBox()
        self._axistick_fontsize_spinbox.setValue(DEFAULT_AXIS_TICK_FONT_SIZE)
        self._axistick_fontsize_spinbox.setSuffix('pt')
        self._axistick_fontsize_spinbox.valueChanged.connect(self.update_axes_tick_font)

        self._textitem_fontsize_spinbox = QSpinBox()
        self._textitem_fontsize_spinbox.setValue(DEFAULT_TEXT_ITEM_FONT_SIZE)
        self._textitem_fontsize_spinbox.setSuffix('pt')
        self._textitem_fontsize_spinbox.valueChanged.connect(self.update_item_font)

        # line width
        self._linewidth_spinbox = QSpinBox()
        self._linewidth_spinbox.setValue(DEFAULT_LINE_WIDTH)
        self._linewidth_spinbox.setMinimum(1)
        self._linewidth_spinbox.valueChanged.connect(lambda: self.update_plot_items(item_types=[XYDataItem]))
    
    def display_settings_dialog(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle('Display Settings')
        form = QFormLayout(dlg)
        form.setContentsMargins(5, 5, 5, 5)
        form.setSpacing(5)

        form.addRow('Tile rows', self._row_tile_combobox)
        form.addRow('Tile columns', self._col_tile_combobox)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        form.addRow(line)
        form.addRow('Link X axis', self._link_xaxis_checkbox)
        form.addRow('Link Y axis', self._link_yaxis_checkbox)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        form.addRow(line)
        form.addRow('Axis label font size', self._axislabel_fontsize_spinbox)
        form.addRow('Axis tick font size', self._axistick_fontsize_spinbox)
        form.addRow('Text item font size', self._textitem_fontsize_spinbox)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        form.addRow(line)
        form.addRow('Default line width', self._linewidth_spinbox)

        pos = self.mapToGlobal(self.rect().topLeft())
        dlg.move(pos)
        dlg.exec()
    
    def update_dim_iter_things(self) -> None:
        # remove dim iter actions from toolbar
        for dim in self._dim_iter_things:
            for value in self._dim_iter_things[dim].values():
                if isinstance(value, QAction):
                    self._toolbar_top.removeAction(value)
        
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
                    self._toolbar_top.insertAction(self._action_after_dim_iter_things, label_action)
                else:
                    label_action: QAction = self._toolbar_top.insertWidget(self._action_after_dim_iter_things, label)
                    self._dim_iter_things[dim]['labelAction'] = label_action
                if 'spinboxAction' in self._dim_iter_things[dim]:
                    spinbox_action: QAction = self._dim_iter_things[dim]['spinboxAction']
                    self._toolbar_top.insertAction(self._action_after_dim_iter_things, spinbox_action)
                else:
                    spinbox_action: QAction = self._toolbar_top.insertWidget(self._action_after_dim_iter_things, spinbox)
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
        self._plot_info = np.ndarray((rowmax + 1, colmax + 1), dtype=dict)
        for row in range(rowmin, rowmax + 1):
            var_name = self._selected_var_names[(row - rowmin) % n_vars]
            for col in range(colmin, colmax + 1):
                plot_coords = selected_coords.copy()
                if row_tile_dim != 'None':
                    tile_index = (row - rowmin) % n_row_tiles
                    tile_coord = row_tile_coords.values[tile_index]
                    plot_coords[row_tile_dim] = xr.DataArray(data=[tile_coord], dims=[row_tile_dim], attrs=row_tile_coords.attrs)
                if col_tile_dim != 'None':
                    tile_index = (col - colmin) % n_col_tiles
                    tile_coord = col_tile_coords.values[tile_index]
                    plot_coords[col_tile_dim] = xr.DataArray(data=[tile_coord], dims=[col_tile_dim], attrs=col_tile_coords.attrs)
                self._plot_info[row,col] = {
                    'vars': [var_name],
                    'coords': plot_coords,
                    'coord_permutations': XarrayTreeNode.permutations(plot_coords)
                }
        if DEBUG:
            print(self._plot_info)
        
        # axis labels
        self.update_axes_labels()
        
        # update plot items
        self.update_plot_items()

        # ensure all plots have appropriate draw state
        self.draw_regions()

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
        axis_label_style = {'font-size': f'{self._axislabel_fontsize_spinbox.value()}pt'}
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
                    row_label.setLabel(text=label_text, **axis_label_style)
                    row_label.setPen(pg.mkPen(width=0)) # hide axis lines
                    row_label.setStyle(showValues=False, tickLength=0) # hide tick labels
                    self._plot_grid.addItem(row_label, row, 0)
                else:
                    row_label.setLabel(text=label_text, **axis_label_style)
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
                    col_label.setLabel(text=label_text, **axis_label_style)
                    col_label.setPen(pg.mkPen(width=0)) # hide axis lines
                    col_label.setStyle(showValues=False, tickLength=0) # hide tick labels
                    self._plot_grid.addItem(col_label, rowmax + 1, col)
                else:
                    col_label.setLabel(text=label_text, **axis_label_style)
    
    def update_axes_tick_font(self) -> None:
        try:
            rowmin, rowmax = self._grid_rowlim
            colmin, colmax = self._grid_collim
        except:
            return
        axis_tick_font = QFont()
        axis_tick_font.setPointSize(self._axistick_fontsize_spinbox.value())
        for row in range(rowmin, rowmax + 1):
            for col in range(colmin, colmax + 1):
                plot = self._plot_grid.getItem(row, col)
                if plot is not None and issubclass(type(plot), pg.PlotItem):
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
    
    def update_plot_items(self, grid_rows: list[int] = None, grid_cols: list[int] = None, item_types: list = None) -> None:
        try:
            rowmin, rowmax = self._grid_rowlim
            colmin, colmax = self._grid_collim
        except:
            return
        if grid_rows is None:
            grid_rows = range(rowmin, rowmax + 1)
        if grid_cols is None:
            grid_cols = range(colmin, colmax + 1)
        
        default_line_width = self._linewidth_spinbox.value()
        for row in grid_rows:
            for col in grid_cols:
                plot = self._plot_grid.getItem(row, col)
                if plot is None or not issubclass(type(plot), pg.PlotItem):
                    continue
                view: View = plot.getViewBox()
                info: dict = self._plot_info[row,col]
                    
                if item_types is None or XYData in item_types:
                    # existing plot traces
                    trace_items = [item for item in plot.listDataItems() if isinstance(item, XYData)]
                    
                    # update plot traces
                    trace_count = 0
                    color_index = 0
                    for tree_item in self._selected_tree_items:
                        if not tree_item.is_var():
                            continue
                        if 'vars' not in info or tree_item.key not in info['vars']:
                            continue
                        if tree_item.node is None:
                            continue
                        xarr, yarr = self.get_xy_data(tree_item.node, tree_item.key)
                        if xarr is None or yarr is None:
                            continue
                        xdata: np.ndarray = xarr.values
                        for coords in info['coord_permutations']:
                            # trace data
                            try:
                                # generally yarr_coords should be exactly coords, but just in case...
                                yarr_coords = {dim: dim_coords for dim, dim_coords in coords.items() if dim in yarr.dims}
                                ydata: np.ndarray = np.squeeze(yarr.sel(yarr_coords).values)
                                if len(ydata.shape) == 0:
                                    ydata = ydata.reshape((1,))
                            except:
                                continue
                            
                            # show trace in plot
                            if len(trace_items) > trace_count:
                                # update existing trace in plot
                                trace_item = trace_items[trace_count]
                                trace_item.setData(x=xdata, y=ydata)
                            else:
                                # add new trace to plot
                                trace_item = XYData(x=xdata, y=ydata)
                                plot.addItem(trace_item)
                                trace_items.append(trace_item)
                            
                            # trace style
                            style = yarr.attrs.get('style', {})
                            if 'LineWidth' not in style:
                                style['LineWidth'] = default_line_width
                            style = XYDataStyleDict(style)
                            color_index = trace_item.setStyleDict(style, colorIndex=color_index)
                            
                            # trace name (limit to 50 characters)
                            trace_name: str = tree_item.node.path + tree_item.key
                            trace_name_parts: list[str] = trace_name.split('/')
                            trace_name = trace_name_parts[-1]
                            for i in reversed(range(len(trace_name_parts) - 1)):
                                if i > 0 and len(trace_name) + len(trace_name_parts[i]) >= 50:
                                    trace_name = '.../' + trace_name
                                    break
                                trace_name = trace_name_parts[i] + '/' + trace_name
                            trace_item.setName(trace_name)
                            
                            # next trace
                            trace_count += 1
                    
                    # remove extra plot traces
                    while len(trace_items) > trace_count:
                        trace_item = trace_items.pop()
                        plot.removeItem(trace_item)
                        trace_item.deleteLater()
    
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
                    for item in view.allChildren():
                        if isinstance(item, XAxisRegion):
                            item.setFontSize(self._textitem_fontsize_spinbox.value())

    def autoscale_plots(self, grid_rows: list[int] = None, grid_cols: list[int] = None) -> None:
        try:
            rowmin, rowmax = self._grid_rowlim
            colmin, colmax = self._grid_collim
        except:
            return
        if grid_rows is None:
            grid_rows = range(rowmin, rowmax + 1)
        if grid_cols is None:
            grid_cols = range(colmin, colmax + 1)
        
        for row in grid_rows:
            for col in grid_cols:
                plot = self._plot_grid.getItem(row, col)
                if plot is not None and issubclass(type(plot), pg.PlotItem):
                    plot.autoRange()
                    plot.enableAutoRange()

    def resizeEvent(self, event: QResizeEvent) -> None:
        QWidget.resizeEvent(self, event)
        self.update_grid_layout()
 
    def draw_regions(self, draw: bool | None = None) -> None:
        if draw is None:
            draw = self._draw_regions_action.isChecked()
        self._region_button.setChecked(draw)
        self._draw_regions_action.blockSignals(True)
        self._draw_regions_action.setChecked(draw)
        self._draw_regions_action.blockSignals(False)
        
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
    
    @Slot(QGraphicsObject)
    def on_item_added_to_axes(self, item: QGraphicsObject):
        view: View = self.sender()
        plot: Plot = view.parentItem()
        if isinstance(item, XAxisRegion):
            item.setFontSize(self._textitem_fontsize_spinbox.value())
            # editing the region text via the popup dialog will also reset the region,
            # so this will cover text changes too
            item.sigRegionChangeFinished.connect(self.on_axes_item_changed)

    @Slot()
    def on_axes_item_changed(self):
        item = self.sender()
        if isinstance(item, XAxisRegion):
            pass # TODO: handle region change?
    
#     @Slot()
#     def measure(self, plot: pg.PlotItem):
#         dlg = QDialog(plot.vb.getViewWidget())
#         dlg.setWindowTitle('Measure')

#         measurementTypesList = QListWidget()
#         measurementTypesList.addItems([
#             'Mean', 
#             'Median', 
#             'Min', 
#             'Max', 
#             'AbsMax', 
#             'Standard Deviation', 
#             'Variance'
#         ])
#         measurementTypesList.setCurrentRow(0)

#         resultNameLineEdit = QLineEdit()
#         resultNameLineEdit.setPlaceholderText('defaults to type')

#         measureInEachROICheckBox = QCheckBox('Measure in each visible ROI')
#         measureInEachROICheckBox.setChecked(True)

#         peakWidthSpinBox = QSpinBox()
#         peakWidthSpinBox.setValue(0)

#         btns = QDialogButtonBox()
#         btns.setStandardButtons(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
#         btns.accepted.connect(dlg.accept)
#         btns.rejected.connect(dlg.reject)

#         name_form = QFormLayout()
#         name_form.setContentsMargins(2, 2, 2, 2)
#         name_form.setSpacing(2)
#         name_form.addRow('Result Name', resultNameLineEdit)

#         peak_options_group = QGroupBox('Min, Max, AbsMax')
#         form = QFormLayout(peak_options_group)
#         form.setContentsMargins(2, 2, 2, 2)
#         form.setSpacing(2)
#         form.addRow('Mean \u00B1Samples', peakWidthSpinBox)

#         right_vbox = QVBoxLayout()
#         right_vbox.addLayout(name_form)
#         right_vbox.addWidget(measureInEachROICheckBox)
#         right_vbox.addStretch()
#         right_vbox.addWidget(peak_options_group)
#         right_vbox.addStretch()

#         layout = QVBoxLayout(dlg)
#         main_hbox = QHBoxLayout()
#         main_hbox.addWidget(measurementTypesList)
#         main_hbox.addLayout(right_vbox)
#         layout.addLayout(main_hbox)
#         layout.addWidget(btns)

#         dlg.setWindowModality(Qt.ApplicationModal)
#         if dlg.exec() != QDialog.Accepted:
#             return

#         # measurement options
#         measurementType = measurementTypesList.currentItem().text()
#         resultName = resultNameLineEdit.text().strip()
#         if resultName == '':
#             resultName = measurementType
#         peakWidth = peakWidthSpinBox.value()
        
#         # x,y data traces to measure
#         xydata_items = [item for item in plot.vb.listItemsOfType(XYDataItem) if item.isVisible()]
#         if not xydata_items:
#             return
        
#         # x-axis ROIs
#         xregions = [item.getRegion() for item in plot.vb.listItemsOfType(XAxisRegionItem) if item.isVisible()]

#         # measurements for each data trace
#         measurements = []
#         for xydata_item in xydata_items:
#             # get x,y data
#             try:
#                 xarr, var = self.get_xy_data(xydata_item._tree_item.node, xydata_item._tree_item.key)
#                 xdata: np.ndarray = xarr.values
#                 ydata: np.ndarray = var.sel(xydata_item._coords).values
#                 if len(ydata.shape) == 0:
#                     ydata = ydata.reshape((1,))
#                 dims = var.dims
#             except:
#                 xdata = xydata_item.xData
#                 ydata = xydata_item.yData
#                 dims = [self.xdim]
#             # mask for each measurement point
#             masks = []
#             if xregions and measureInEachROICheckBox.isChecked():
#                 # one mask per xregion
#                 for xregion in xregions:
#                     xmin, xmax = xregion
#                     mask = (xdata >= xmin) & (xdata <= xmax)
#                     masks.append(mask)
#             elif xregions:
#                 # mask for combined xregions
#                 mask = np.full(xdata.shape, False)
#                 for xregion in xregions:
#                     xmin, xmax = xregion
#                     mask[(xdata >= xmin) & (xdata <= xmax)] = True
#                 masks = [mask]
#             else:
#                 # mask for everything
#                 mask = np.full(xdata.shape, True)
#                 masks = [mask]
#             # measure in each mask
#             xmeasure = []
#             ymeasure = []
#             for mask in masks:
#                 if not np.any(mask):
#                     continue
#                 x = xdata[mask]
#                 y = ydata[mask]
#                 if measurementType == 'Mean':
#                     xmeasure.append(np.median(x))
#                     ymeasure.append(np.mean(y))
#                 elif measurementType == 'Median':
#                     xmeasure.append(np.median(x))
#                     ymeasure.append(np.median(y))
#                 elif measurementType == 'Min':
#                     i = np.argmin(y)
#                     xmeasure.append(x[i])
#                     if peakWidth == 0:
#                         ymeasure.append(y[i])
#                     else:
#                         j = np.where(mask)[0][i]
#                         start, stop = j, j + 1
#                         for w in range(peakWidth):
#                             if j - w >= 0 and mask[j - w] and start == j - w + 1:
#                                 start = j - w
#                             if j + w < len(mask) and mask[j + w] and stop == j + w:
#                                 stop = j + w + 1
#                         ymeasure.append(np.mean(ydata[start:stop]))
#                 elif measurementType == 'Max':
#                     i = np.argmax(y)
#                     xmeasure.append(x[i])
#                     if peakWidth == 0:
#                         ymeasure.append(y[i])
#                     else:
#                         j = np.where(mask)[0][i]
#                         start, stop = j, j + 1
#                         for w in range(peakWidth):
#                             if j - w >= 0 and mask[j - w] and start == j - w + 1:
#                                 start = j - w
#                             if j + w < len(mask) and mask[j + w] and stop == j + w:
#                                 stop = j + w + 1
#                         ymeasure.append(np.mean(ydata[start:stop]))
#                 elif measurementType == 'AbsMax':
#                     i = np.argmax(np.abs(y))
#                     xmeasure.append(x[i])
#                     if peakWidth == 0:
#                         ymeasure.append(y[i])
#                     else:
#                         j = np.where(mask)[0][i]
#                         start, stop = j, j + 1
#                         for w in range(peakWidth):
#                             if j - w >= 0 and mask[j - w] and start == j - w + 1:
#                                 start = j - w
#                             if j + w < len(mask) and mask[j + w] and stop == j + w:
#                                 stop = j + w + 1
#                         ymeasure.append(np.mean(ydata[start:stop]))
#                 elif measurementType == 'Standard Deviation':
#                     xmeasure.append(np.median(x))
#                     ymeasure.append(np.std(y))
#                 elif measurementType == 'Variance':
#                     xmeasure.append(np.median(x))
#                     ymeasure.append(np.var(y))
#             if not ymeasure:
#                 measurements.append(None)
#                 continue
#             xmeasure = np.array(xmeasure)
#             ymeasure = np.array(ymeasure)
#             order = np.argsort(xmeasure)
#             xmeasure = xmeasure[order]
#             ymeasure = ymeasure[order]
#             shape =[1] * len(dims)
#             shape[dims.index(self.xdim)] = len(ymeasure)
#             coords = {}
#             for dim, coord in xydata_item._coords.items():
#                 attrs = self._selected_tree_coords[dim].attrs.copy()
#                 if dim == self.xdim:
#                     coords[dim] = (dim, xmeasure, attrs)
#                 else:
#                     coords[dim] = (dim, np.array([coord], dtype=type(coord)), attrs)
#             if self.xdim not in coords:
#                 attrs = self._selected_tree_coords[self.xdim].attrs.copy()
#                 coords[self.xdim] = (self.xdim, xmeasure, attrs)
#             measurement = xr.Dataset(
#                 data_vars={
#                     xydata_item._tree_item.key: (dims, ymeasure.reshape(shape), var.attrs.copy())
#                 },
#                 coords=coords
#             )
#             measurement.data_vars[xydata_item._tree_item.key].attrs['style'] = {
#                 'LineWidth': 2,
#                 'Marker': 'o'
#             }
#             measurements.append(measurement)
#         numMeasurements = np.sum([1 for measurement in measurements if measurement is not None])
#         if numMeasurements == 0:
#             return
        
#         # preview measurements
#         for measurement in measurements:
#             if measurement is None:
#                 continue
#             var_name = list(measurement.data_vars)[0]
#             var = measurement.data_vars[var_name]
#             xdata = measurement.coords[self.xdim].values
#             ydata = np.squeeze(var.values)
#             if len(ydata.shape) == 0:
#                 ydata = ydata.reshape((1,))
#             measurement_item = XYDataItem(x=xdata, y=ydata)
#             measurement_item.setStyle(XYDataStyleDict({
#                 'Color': (255, 0, 0),
#                 'LineWidth': 2,
#                 'Marker': 'o',
#             }))
#             plot.addItem(measurement_item)
#         answer = QMessageBox.question(plot.vb.getViewWidget(), 'Keep Measurements?', 'Keep measurements?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
#         if answer != QMessageBox.StandardButton.Yes:
#             row, col, info = self.plot_loc_info(plot)
#             self.update_plot_items(grid_rows=[row], grid_cols=[col], item_types=[XYDataItem])
#             return
        
#         # add measurements to data tree
#         parent_tree_nodes = [item._tree_item.node for item in xydata_items]
#         measure_tree_nodes = []
#         mergeApproved = None
#         for parent_node, measurement in zip(parent_tree_nodes, measurements):
#             # append measurement as child tree node
#             if resultName in parent_node.children:
#                 if mergeApproved is None:
#                     answer = QMessageBox.question(plot.vb.getViewWidget(), 'Merge Result?', 'Merge measurements with existing datasets of same name?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
#                     mergeApproved = (answer == QMessageBox.Yes)
#                 if not mergeApproved:
#                     continue
#                 # merge measurement with existing child dataset (use measurement for any overlap)
#                 existing_child_node: XarrayTreeNode = parent_node.children[resultName]
#                 existing_child_node.dataset: xr.Dataset = measurement.combine_first(existing_child_node.dataset)
#                 measure_tree_nodes.append(existing_child_node)
#             else:
#                 # append measurement as new child node
#                 node = XarrayTreeNode(name=resultName, dataset=measurement, parent=parent_node)
#                 measure_tree_nodes.append(node)
        
#         # update data tree
#         self.data = self.data

#         # make sure newly added measurement nodes are selected and expanded
#         model: XarrayTreeModel = self._dataTreeView.model()
#         item: XarrayTreeItem = model.root
#         while item is not None:
#             for node in measure_tree_nodes:
#                 if item.node is node and item.is_var():
#                     index: QModelIndex = model.createIndex(item.row(), 0, item)
#                     self._dataTreeView.selectionModel().select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
#                     self._dataTreeView.setExpanded(model.parent(index), True)
#             item = item.next_item_depth_first()
    
#     @Slot()
#     def curve_fit(self, plot: pg.PlotItem):
#         options = {}
#         dlg = CurveFitDialog(options, plot.vb.getViewWidget())
#         dlg.setWindowTitle('Curve Fit')
#         dlg.setWindowModality(Qt.ApplicationModal)
#         if dlg.exec() != QDialog.Accepted:
#             return
        
#         # fit options
#         options: dict = dlg.options()
#         resultName = options['resultName'].strip()
#         if resultName == '':
#             resultName = options['fitType']

#         # x,y data traces to measure
#         xydata_items = [item for item in plot.vb.listItemsOfType(XYDataItem) if item.isVisible()]
#         if not xydata_items:
#             return
        
#         # x-axis ROIs
#         xregions = [item.getRegion() for item in plot.vb.listItemsOfType(XAxisRegionItem) if item.isVisible()]

#         # init fit equation
#         if 'equation' in options:
#             equation = options['equation']
#             fitModel = lmfit.models.ExpressionModel(equation, independent_vars=['x'])
#             for param in fitModel.param_names:
#                 initialValue = options['params'][param]['value']
#                 vary = options['params'][param]['vary']
#                 lowerBound, upperBound = options['params'][param]['bounds']
#                 if initialValue is None:
#                     if not vary:
#                         QErrorMessage(plot.vb.getViewWidget()).showMessage(f'Parameter {param} is fixed but has no initial value.')
#                         return
#                     initialValue = 1
#                 if initialValue < lowerBound:
#                     initialValue = lowerBound
#                 if initialValue > upperBound:
#                     initialValue = upperBound
#                 hint = {}
#                 hint['value'] = initialValue
#                 if lowerBound != -np.inf:
#                     hint['min'] = lowerBound
#                 if upperBound != np.inf:
#                     hint['max'] = upperBound
#                 fitModel.set_param_hint(param, **hint)
#             params = fitModel.make_params()

#         # fits for each data trace
#         fits = []
#         for xydata_item in xydata_items:
#             # get x,y data
#             try:
#                 xarr, var = self.get_xy_data(xydata_item._tree_item.node, xydata_item._tree_item.key)
#                 xdata: np.ndarray = xarr.values
#                 ydata: np.ndarray = var.sel(xydata_item._coords).values
#                 if len(ydata.shape) == 0:
#                     ydata = ydata.reshape((1,))
#                 dims = var.dims
#             except:
#                 xdata = xydata_item.xData
#                 ydata = xydata_item.yData
#                 dims = [self.xdim]
#             # optimization mask
#             if xregions and options['optimizeWithinROIsOnly']:
#                 # mask for combined xregions
#                 mask = np.full(xdata.shape, False)
#                 for xregion in xregions:
#                     xmin, xmax = xregion
#                     mask[(xdata >= xmin) & (xdata <= xmax)] = True
#                 xopt = xdata[mask]
#                 yopt = ydata[mask]
#             else:
#                 # use everything
#                 xopt = xdata
#                 yopt = ydata
#             # output mask
#             if xregions and options['fitWithinROIsOnly']:
#                 # mask for combined xregions
#                 mask = np.full(xdata.shape, False)
#                 for xregion in xregions:
#                     xmin, xmax = xregion
#                     mask[(xdata >= xmin) & (xdata <= xmax)] = True
#                 xfit = xdata[mask]
#             else:
#                 # use everything
#                 xfit = xdata
#             # fit
#             fit_attrs = {
#                 'type': options['fitType']
#             }
#             if options['fitType'] == 'Mean':
#                 yfit = np.full(len(xfit), np.mean(yopt))
#             elif options['fitType'] == 'Median':
#                 yfit = np.full(len(xfit), np.median(yopt))
#             elif options['fitType'] == 'Polynomial':
#                 degree = options['degree']
#                 coef = np.polyfit(xopt, yopt, degree)
#                 yfit = np.polyval(coef, xfit)
#                 fit_attrs['degree'] = degree
#                 fit_attrs['coefficients'] = coef
#             elif options['fitType'] == 'Spline':
#                 n_segments = options['segments']
#                 segmentLength = max(1, int(len(yopt) / n_segments))
#                 knots = xopt[segmentLength:-segmentLength:segmentLength]
#                 if len(knots) < 2:
#                     knots = xopt[[1, -2]]
#                 knots, coef, degree = sp.interpolate.splrep(xopt, yopt, t=knots)
#                 yfit = sp.interpolate.splev(xfit, (knots, coef, degree), der=0)
#                 fit_attrs['segments'] = n_segments
#                 fit_attrs['knots'] = knots
#                 fit_attrs['coefficients'] = coef
#                 fit_attrs['degree'] = degree
#             elif 'equation' in options:
#                 equation = options['equation']
#                 result = fitModel.fit(yopt, params, x=xopt)
#                 print('----------')
#                 print(f'Fit: var={var.name}, coords={xydata_item._coords}')
#                 print(result.fit_report())
#                 print('----------')
#                 yfit = fitModel.eval(result.params, x=xfit)
#                 fit_attrs['equation'] = equation
#                 fit_attrs['params'] = {
#                     param: {
#                         'value': float(result.params[param].value),
#                         'stderr': float(result.params[param].stderr),
#                         'init_value': float(result.params[param].init_value),
#                         'vary': bool(result.params[param].vary),
#                         'min': float(result.params[param].min),
#                         'max': float(result.params[param].max)
#                     }
#                     for param in result.params
#                 }
#             else:
#                 fits.append(None)
#                 continue
#             shape =[1] * len(dims)
#             shape[dims.index(self.xdim)] = len(yfit)
#             coords = {}
#             for dim, coord in xydata_item._coords.items():
#                 attrs = self._selected_tree_coords[dim].attrs.copy()
#                 if dim == self.xdim:
#                     coords[dim] = (dim, xfit, attrs)
#                 else:
#                     coords[dim] = (dim, np.array([coord], dtype=type(coord)), attrs)
#             if self.xdim not in coords:
#                 attrs = self._selected_tree_coords[self.xdim].attrs.copy()
#                 coords[self.xdim] = (self.xdim, xfit, attrs)
#             attrs = var.attrs.copy()
#             if 'fit' not in attrs:
#                 attrs['fit'] = {}
#             coord_key = ', '.join([f'{dim}: {coord}' for dim, coord in xydata_item._coords.items()])
#             attrs['fit'][coord_key] = fit_attrs
#             fit = xr.Dataset(
#                 data_vars={
#                     xydata_item._tree_item.key: (dims, yfit.reshape(shape), attrs)
#                 },
#                 coords=coords
#             )
#             fits.append(fit)
#         numFits = np.sum([1 for fit in fits if fit is not None])
#         if numFits == 0:
#             return
        
#         # preview fits
#         for fit in fits:
#             if fit is None:
#                 continue
#             var_name = list(fit.data_vars)[0]
#             var = fit.data_vars[var_name]
#             xdata = fit.coords[self.xdim].values
#             ydata = np.squeeze(var.values)
#             if len(ydata.shape) == 0:
#                 ydata = ydata.reshape((1,))
#             fit_item = XYDataItem(x=xdata, y=ydata)
#             fit_item.set_style({
#                 'Color': (255, 0, 0),
#                 'LineWidth': 2,
#             })
#             plot.addItem(fit_item)
#         answer = QMessageBox.question(plot.vb.getViewWidget(), 'Keep Fits?', 'Keep fits?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
#         if answer != QMessageBox.StandardButton.Yes:
#             row, col, info = self.plot_loc_info(plot)
#             self.update_plot_items(grid_rows=[row], grid_cols=[col], item_types=[XYDataItem])
#             return
        
#         # add fits to data tree
#         parent_tree_nodes = [item._tree_item.node for item in xydata_items]
#         fit_tree_nodes = []
#         mergeApproved = None
#         for parent_node, fit in zip(parent_tree_nodes, fits):
#             # append fit as child tree node
#             if resultName in parent_node.children:
#                 if mergeApproved is None:
#                     answer = QMessageBox.question(plot.vb.getViewWidget(), 'Merge Result?', 'Merge fits with existing datasets of same name?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
#                     mergeApproved = (answer == QMessageBox.Yes)
#                 if not mergeApproved:
#                     continue
#                 # merge fit with existing child dataset (use fit for any overlap)
#                 existing_child_node: XarrayTreeNode = parent_node.children[resultName]
#                 try:
#                     var_name = list(fit.data_vars)[0]
#                     existing_var = existing_child_node.dataset.data_vars[var_name]
#                     fit_attrs = existing_var.attrs['fit']
#                     for key, value in fit.data_vars[var_name].attrs['fit'].items():
#                         fit_attrs[key] = value
#                 except:
#                     fit_attrs = fit.data_vars[var_name].attrs['fit']
#                 existing_child_node.dataset: xr.Dataset = fit.combine_first(existing_child_node.dataset)
#                 existing_child_node.dataset.data_vars[var_name].attrs['fit'] = fit_attrs
#                 fit_tree_nodes.append(existing_child_node)
#             else:
#                 # append fit as new child node
#                 node = XarrayTreeNode(name=resultName, dataset=fit, parent=parent_node)
#                 fit_tree_nodes.append(node)
        
#         # update data tree
#         self.data = self.data

#         # make sure newly added fit nodes are selected and expanded
#         model: XarrayTreeModel = self._dataTreeView.model()
#         item: XarrayTreeItem = model.root
#         while item is not None:
#             for node in fit_tree_nodes:
#                 if item.node is node and item.is_var():
#                     index: QModelIndex = model.createIndex(item.row(), 0, item)
#                     self._dataTreeView.selectionModel().select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
#                     self._dataTreeView.setExpanded(model.parent(index), True)
#             item = item.next_item_depth_first()

   
# class CurveFitDialog(QDialog):
#     def __init__(self, options: dict, *args, **kwargs):
#         QDialog.__init__(self, *args, **kwargs)
#         if options is None:
#             options = {}

#         self.fitTypes = {
#             'Mean': '', 
#             'Median': '', 
#             'Line': 'a * x + b', 
#             'Polynomial': '', 
#             'Spline': '', 
#             'Exponential Decay': 'a * exp(-b * x) + c', 
#             'Exponential Rise': 'a * (1 - exp(-b * x)) + c', 
#             'Hill Equation': 'a / (1 + (K / x)**n)', 
#             'Custom': ''
#             }
#         self.fitTypeSelectionBox = QListWidget()
#         self.fitTypeSelectionBox.addItems(self.fitTypes.keys())
#         self.fitTypeSelectionBox.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
#         self.fitTypeSelectionBox.currentItemChanged.connect(self.onEquationSelected)

#         self.resultNameLineEdit = QLineEdit()
#         self.resultNameLineEdit.setPlaceholderText('defaults to type')

#         self.optimizeWithinROIsOnlyCheckBox = QCheckBox('Optimize within visible ROIs only')
#         self.optimizeWithinROIsOnlyCheckBox.setChecked(True)

#         self.fitWithinROIsOnlyCheckBox = QCheckBox('Fit within visible ROIs only')
#         self.fitWithinROIsOnlyCheckBox.setChecked(False)

#         self.equationEdit = QLineEdit()
#         self.equationEdit.setPlaceholderText('a * x**2 + b')
#         self.equationEdit.textEdited.connect(self.onEquationChanged)
#         self._customEquation = ''

#         self.paramNames = []
#         self.paramInitialValueEdits = {}
#         self.paramFixedCheckBoxes = {}
#         self.paramLowerBoundEdits = {}
#         self.paramUpperBoundEdits = {}

#         self.paramsGrid = QGridLayout()
#         self.paramsGrid.addWidget(QLabel('Parameter'), 0, 0)
#         self.paramsGrid.addWidget(QLabel('Initial Value'), 0, 1)
#         self.paramsGrid.addWidget(QLabel('Fixed'), 0, 2)
#         self.paramsGrid.addWidget(QLabel('Lower Bound'), 0, 3)
#         self.paramsGrid.addWidget(QLabel('Upper Bound'), 0, 4)

#         name_form = QFormLayout()
#         name_form.setContentsMargins(2, 2, 2, 2)
#         name_form.setSpacing(2)
#         name_form.addRow('Result Name', self.resultNameLineEdit)

#         self.equationGroupBox = QGroupBox('Equation: y = f(x)')
#         vbox = QVBoxLayout(self.equationGroupBox)
#         vbox.setContentsMargins(5, 5, 5, 5)
#         vbox.setSpacing(5)
#         vbox.addWidget(self.equationEdit)
#         vbox.addLayout(self.paramsGrid)

#         self.polynomialDegreeSpinBox = QSpinBox()
#         self.polynomialDegreeSpinBox.setValue(2)

#         self.polynomialGroupBox = QGroupBox('Polynomial')
#         form = QFormLayout(self.polynomialGroupBox)
#         form.setContentsMargins(5, 5, 5, 5)
#         form.setSpacing(5)
#         form.addRow('Degree', self.polynomialDegreeSpinBox)

#         self.splineNumSegmentsSpinBox = QSpinBox()
#         self.splineNumSegmentsSpinBox.setValue(10)

#         self.splineGroupBox = QGroupBox('Spline')
#         form = QFormLayout(self.splineGroupBox)
#         form.setContentsMargins(5, 5, 5, 5)
#         form.setSpacing(5)
#         form.addRow('# Segments', self.splineNumSegmentsSpinBox)

#         btns = QDialogButtonBox()
#         btns.setStandardButtons(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
#         btns.accepted.connect(self.accept)
#         btns.rejected.connect(self.reject)

#         vbox = QVBoxLayout()
#         vbox.setContentsMargins(0, 0, 0, 0)
#         vbox.setSpacing(5)
#         vbox.addLayout(name_form)
#         vbox.addWidget(self.optimizeWithinROIsOnlyCheckBox)
#         vbox.addWidget(self.fitWithinROIsOnlyCheckBox)
#         vbox.addStretch()
#         vbox.addWidget(self.equationGroupBox)
#         vbox.addWidget(self.polynomialGroupBox)
#         vbox.addWidget(self.splineGroupBox)
#         vbox.addStretch()

#         hbox = QHBoxLayout()
#         hbox.setContentsMargins(0, 0, 0, 0)
#         hbox.setSpacing(5)
#         hbox.addWidget(self.fitTypeSelectionBox)
#         hbox.addLayout(vbox)

#         mainLayout = QVBoxLayout(self)
#         mainLayout.addLayout(hbox)
#         mainLayout.addWidget(btns)

#         if 'fitType' in options:
#             index = list(self.fitTypes.keys()).index(options['fitType'])
#             if index is not None and index != -1:
#                 self.fitTypeSelectionBox.setCurrentRow(index)
#                 self.onEquationSelected()
#             if options['fitType'] == 'Custom' and 'equation' in options:
#                 self.equationEdit.setText(options['equation'])
#                 self._customEquation = options['equation']
    
#     def sizeHint(self):
#         self.fitTypeSelectionBox.setMinimumWidth(self.fitTypeSelectionBox.sizeHintForColumn(0))
#         return QSize(600, 400)
    
#     def onEquationSelected(self):
#         fitType = self.fitTypeSelectionBox.currentItem().text()
#         if fitType == 'Mean':
#             self.equationGroupBox.setVisible(False)
#             self.polynomialGroupBox.setVisible(False)
#             self.splineGroupBox.setVisible(False)
#         elif fitType == 'Median':
#             self.equationGroupBox.setVisible(False)
#             self.polynomialGroupBox.setVisible(False)
#             self.splineGroupBox.setVisible(False)
#         elif fitType == 'Polynomial':
#             self.equationGroupBox.setVisible(False)
#             self.polynomialGroupBox.setVisible(True)
#             self.splineGroupBox.setVisible(False)
#         elif fitType == 'Spline':
#             self.equationGroupBox.setVisible(False)
#             self.polynomialGroupBox.setVisible(False)
#             self.splineGroupBox.setVisible(True)
#         else:
#             self.equationGroupBox.setVisible(True)
#             self.polynomialGroupBox.setVisible(False)
#             self.splineGroupBox.setVisible(False)
#             if fitType == 'Custom':
#                 self.equationEdit.setText(self._customEquation)
#             else:
#                 equation = self.fitTypes[fitType]
#                 self.equationEdit.setText(equation)
#             self.onEquationChanged()

#     def onEquationChanged(self):
#         equation = self.equationEdit.text().strip()
#         # if '=' in equation:
#         #     i = equation.rfind('=')
#         #     if i >= 0:
#         #         equation = equation[i+1:].strip()
#         try:
#             fitModel = lmfit.models.ExpressionModel(equation, independent_vars=['x'])
#             self.paramNames = fitModel.param_names

#             fiTypeEquations = list(self.fitTypes.values())
#             if equation in fiTypeEquations:
#                 self.fitTypeSelectionBox.setCurrentRow(fiTypeEquations.index(equation))
#             else:
#                 self._customEquation = equation
#                 self.fitTypeSelectionBox.setCurrentRow(list(self.fitTypes).index('Custom'))
#         except:
#             self.paramNames = []
#         for name in self.paramNames:
#             if name not in self.paramInitialValueEdits:
#                 self.paramInitialValueEdits[name] = QLineEdit()
#             if name not in self.paramFixedCheckBoxes:
#                 self.paramFixedCheckBoxes[name] = QCheckBox()
#             if name not in self.paramLowerBoundEdits:
#                 self.paramLowerBoundEdits[name] = QLineEdit()
#             if name not in self.paramUpperBoundEdits:
#                 self.paramUpperBoundEdits[name] = QLineEdit()
#         self.updateParamsGrid()
    
#     def clearParamsGrid(self):
#         for row in range(1, self.paramsGrid.rowCount()):
#             for col in range(self.paramsGrid.columnCount()):
#                 item = self.paramsGrid.itemAtPosition(row, col)
#                 if item:
#                     widget = item.widget()
#                     self.paramsGrid.removeItem(item)
#                     widget.setParent(None)
#                     widget.setVisible(False)
    
#     def updateParamsGrid(self):
#         self.clearParamsGrid()
#         for i, name in enumerate(self.paramNames):
#             self.paramsGrid.addWidget(QLabel(name), i + 1, 0)
#             self.paramsGrid.addWidget(self.paramInitialValueEdits[name], i + 1, 1)
#             self.paramsGrid.addWidget(self.paramFixedCheckBoxes[name], i + 1, 2)
#             self.paramsGrid.addWidget(self.paramLowerBoundEdits[name], i + 1, 3)
#             self.paramsGrid.addWidget(self.paramUpperBoundEdits[name], i + 1, 4)
#             self.paramInitialValueEdits[name].setVisible(True)
#             self.paramFixedCheckBoxes[name].setVisible(True)
#             self.paramLowerBoundEdits[name].setVisible(True)
#             self.paramUpperBoundEdits[name].setVisible(True)
    
#     def options(self):
#         options = {}
#         fitType = self.fitTypeSelectionBox.currentItem().text()
#         options['fitType'] = fitType
#         if fitType == 'Polynomial':
#             options['degree'] = self.polynomialDegreeSpinBox.value()
#         elif fitType == 'Spline':
#             options['segments'] = self.splineNumSegmentsSpinBox.value()
#         elif fitType in [name for name, equation in self.fitTypes.items() if equation != '' or name == 'Custom']:
#             options['equation'] = self.equationEdit.text().strip()
#             options['params'] = {}
#             for name in self.paramNames:
#                 try:
#                     value = float(self.paramInitialValueEdits[name].text())
#                 except:
#                     value = None
#                 vary = not self.paramFixedCheckBoxes[name].isChecked()
#                 try:
#                     lowerBound = float(self.paramLowerBoundEdits[name].text())
#                 except:
#                     lowerBound = -np.inf
#                 try:
#                     upperBound = float(self.paramUpperBoundEdits[name].text())
#                 except:
#                     upperBound = np.inf
#                 options['params'][name] = {
#                     'value': value,
#                     'vary': vary,
#                     'bounds': (lowerBound, upperBound)
#                 }
#         options['optimizeWithinROIsOnly'] = self.optimizeWithinROIsOnlyCheckBox.isChecked()
#         options['fitWithinROIsOnly'] = self.fitWithinROIsOnlyCheckBox.isChecked()
#         options['resultName'] = self.resultNameLineEdit.text().strip()
#         return options


def test_live():
    app = QApplication(sys.argv)

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

    status = app.exec()
    sys.exit(status)


if __name__ == '__main__':
    test_live()
