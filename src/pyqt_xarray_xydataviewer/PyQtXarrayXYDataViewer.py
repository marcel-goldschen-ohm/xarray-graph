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
# import datatree as xt
# import zarr
import sys, re
from pyqt_ext import *
from pyqtgraph_ext import *
from pyqt_xarray_treeview import *


# pg.setConfigOption('background', (235, 235, 235))
# pg.setConfigOption('foreground', (0, 0, 0))


AXIS_LABEL_FONT_SIZE = 12
AXIS_TICK_FONT_SIZE = 11
REGION_FONT_SIZE = 10
EVENT_FONT_SIZE = 10


class XarrayXYDataViewer2(QWidget):
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
    def data(self, data: XarrayTreeNode | xr.Dataset | None):
        # set xarray tree
        if isinstance(data, xr.Dataset):
            root_node: XarrayTreeNode = XarrayTreeNode(name='/', dataset=None)
            data_child_node = XarrayTreeNode(name='dataset', dataset=data, parent=root_node)
            self._data = root_node
        elif isinstance(data, XarrayTreeNode):
            self._data = data
        elif data is None:
            self._data = data
        else:
            return
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
        print('self._tree_coords:', self._tree_coords)

        # reset xdim in case dims have changed
        # also updates dim spinboxes and plot grid
        self.xdim = self.xdim

        # self.autoscale_plots()
    
    @property
    def xdim(self) -> str:
        return self._xdim

    @xdim.setter
    def xdim(self, xdim: str):
        dims: list[str] = self.dims
        print('dims:', dims)
        if dims and (xdim not in dims):
            # default to last dim if xdim is invalid
            xdim = dims[-1]
        
        self._xdim = xdim
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

        # home button
        self._home_button = QToolButton()
        self._home_button.setIcon(qta.icon('mdi.home-outline', options=[{'opacity': 0.7}]))
        self._home_button.setToolTip('Autoscale all plots')
        # self._home_button.clicked.connect(self.autoscale_plots)
        self._home_action = self._toolbar_top.addWidget(self._home_button)

        # plots grid
        self._plot_grid = PlotGrid()
        self._plot_grid.resize_grid(1, 1)
        # self._plot_grid_widget = pg.GraphicsLayoutWidget()
        # self._plot_grid_widget.setBackground(QColor(240, 240, 240))
        # self._plot_grid_layout: QGraphicsGridLayout = self._plot_grid_widget.ci.layout
        # self._plot_grid_layout.setContentsMargins(0, 0, 0, 0)
        # self._plot_grid_layout.setSpacing(0)

        # # add empty plot
        # plot: PlotItem = self.new_plot()
        # self._plot_grid: list[list[dict]] = [[{'plot': plot}]]
        # self._plot_grid_widget.addItem(plot, 0, 1)

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

        # display options button
        self._display_options_button = QPushButton('Display Options')
        self._display_options_button.clicked.connect(self.display_options_dialog)

        # display options UI
        self.setup_display_options_ui()
        
        # view sidebar
        self._view_panel = QWidget()
        vbox = QVBoxLayout(self._view_panel)
        vbox.setContentsMargins(3, 3, 3, 3)
        vbox.setSpacing(5)
        vbox.addWidget(self._data_treeview)
        form = QFormLayout()
        form.addRow('X axis:', self._xdim_combobox)
        vbox.addLayout(form)
        vbox.addWidget(self._display_options_button)

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
    
    def setup_display_options_ui(self) -> None:
        # row/col tile selection
        self._row_tile_combobox = QComboBox()
        self._row_tile_combobox.addItems(['None'])
        self._row_tile_combobox.setCurrentText('None')
        # self._row_tile_combobox.currentTextChanged.connect(self.on_plot_grid_layout_changed)

        self._col_tile_combobox = QComboBox()
        self._col_tile_combobox.addItems(['None'])
        self._col_tile_combobox.setCurrentText('None')
        # self._col_tile_combobox.currentTextChanged.connect(self.on_plot_grid_layout_changed)

        # link axes
        self._link_xaxis_checkbox = QCheckBox()
        self._link_xaxis_checkbox.setChecked(True)
        # self._link_xaxis_checkbox.stateChanged.connect(self.update_plot_grid)

        self._link_yaxis_checkbox = QCheckBox()
        self._link_yaxis_checkbox.setChecked(True)
        # self._link_yaxis_checkbox.stateChanged.connect(self.update_plot_grid)

        # font size selection
        self._axislabel_fontsize_spinbox = QSpinBox()
        self._axislabel_fontsize_spinbox.setValue(AXIS_LABEL_FONT_SIZE)
        self._axislabel_fontsize_spinbox.setSuffix('pt')
        # self._axislabel_fontsize_spinbox.valueChanged.connect(self.update_plot_grid)

        self._axistick_fontsize_spinbox = QSpinBox()
        self._axistick_fontsize_spinbox.setValue(AXIS_TICK_FONT_SIZE)
        self._axistick_fontsize_spinbox.setSuffix('pt')
        # self._axistick_fontsize_spinbox.valueChanged.connect(self.update_plot_grid)

        self._regionlabel_fontsize_spinbox = QSpinBox()
        self._regionlabel_fontsize_spinbox.setValue(REGION_FONT_SIZE)
        self._regionlabel_fontsize_spinbox.setSuffix('pt')
        # self._regionlabel_fontsize_spinbox.valueChanged.connect(lambda: self.updatePlotItems(itemTypes=[EventItem]))
    
    def display_options_dialog(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle('Display Options')
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
        form.addRow('Region font size', self._regionlabel_fontsize_spinbox)

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
                    self._toolbar_top.insertAction(self._home_action, label_action)
                else:
                    label_action: QAction = self._toolbar_top.insertWidget(self._home_action, label)
                    self._dim_iter_things[dim]['labelAction'] = label_action
                if 'spinboxAction' in self._dim_iter_things[dim]:
                    spinbox_action: QAction = self._dim_iter_things[dim]['spinboxAction']
                    self._toolbar_top.insertAction(self._home_action, spinbox_action)
                else:
                    spinbox_action: QAction = self._toolbar_top.insertWidget(self._home_action, spinbox)
                    self._dim_iter_things[dim]['spinboxAction'] = spinbox_action
        
        print('_dim_iter_things:', self._dim_iter_things)
    
    def new_plot(self) -> PlotItem:
        print('new_plot()')
        # viewBox: ViewBox = ViewBox()
        plot = PlotItem()
        print('new plot:', plot)
        # plot.vb.setMinimumSize(10, 10)
        # viewBox.menu.addAction('Measure', lambda self=self, plot=plot: self.measure(plot))
        # viewBox.menu.addAction('Curve Fit', lambda self=self, plot=plot: self.curve_fit(plot))
        # viewBox.menu.addSeparator()
        # viewBox.sigItemAdded.connect(self.on_item_added_to_axes)
        return plot
    
    def on_var_selection_changed(self) -> None:
        # selected tree items
        self._selected_tree_items: list[XarrayTreeItem] = self._data_treeview.selected_items()
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
                    # attrs = self._selected_tree_coords[name].attrs
                    # if not attrs:
                    #     attrs = coords.attrs
                    values = np.unique(np.concatenate((self._selected_tree_coords[name].values, coords.values)))
                    self._selected_tree_coords[name] = xr.DataArray(dims=name, data=values) #, attrs=attrs)
                else:
                    self._selected_tree_coords[name] = coords
        print('_selected_tree_coords:', self._selected_tree_coords)
        
        # store the dims for the entire selection
        self._selected_sizes: dict[str, int] = {name: len(coords) for name, coords in self._selected_tree_coords.items()}
        self._selected_dims = list(self._selected_sizes)
        print('_selected_sizes:', self._selected_sizes)
        print('_selected_dims:', self._selected_dims)

        # iterable dimensions with size > 1 (excluding xdim)
        self._iter_dims = [dim for dim in self._selected_dims if dim != self.xdim and self._selected_sizes[dim] > 1]
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
        print('_dim_iter_things:', self._dim_iter_things)

        # selected var names
        self._selected_var_names = []
        for item in self._selected_tree_items:
            if item.is_var():
                if item.key not in self._selected_var_names:
                    self._selected_var_names.append(item.key)
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
                self._selected_coords[dim] = self._selected_tree_coords[dim].sel({dim: values})
            else:
                # single index along this dim
                self._selected_coords[dim] = self._selected_tree_coords[dim]
        print('_selected_coords:', self._selected_coords)
        
        # update plot grid if flagged or if tiling is enabled
        try:
            self._plot_grid_needs_update
        except AttributeError:
            self._plot_grid_needs_update = True
        if self._plot_grid_needs_update or self.is_tiling_enabled():
            self.update_plot_grid()
        
        # # update plot items
        # self.update_plot_items()
    
    def update_plot_grid(self) -> None:
        print('update_plot_grid()')
        selected_coords = self._selected_coords.copy()
        
        # grid tile dimensions
        n_row_tiles = 1
        n_col_tiles = 1
        row_tile_dim = self._row_tile_combobox.currentText()
        col_tile_dim = self._col_tile_combobox.currentText()
        if col_tile_dim == row_tile_dim:
            col_tile_dim = 'None'
        if row_tile_dim != 'None' and row_tile_dim in selected_coords:
            row_tile_coords = selected_coords[row_tile_dim]
            n_row_tiles = len(row_tile_coords)
            del selected_coords[row_tile_dim]
        if col_tile_dim != 'None' and col_tile_dim in selected_coords:
            col_tile_coords = selected_coords[col_tile_dim]
            n_col_tiles = len(col_tile_coords)
            del selected_coords[col_tile_dim]
        print('row_tile_dim:', row_tile_dim, 'col_tile_dim:', col_tile_dim)
        
        # grid size
        n_vars = len(self._selected_var_names)
        grid_rows = n_vars * n_row_tiles
        grid_cols = n_col_tiles
        print('n_vars:', n_vars, 'grid_rows:', grid_rows, 'grid_cols:', grid_cols)
        if grid_rows * grid_cols == 0:
            self._plot_grid.resize_grid(1, 1, default_item=PlotItem)
            return
        self._plot_grid.resize_grid(grid_rows, grid_cols, default_item=PlotItem)
        self._plot_grid.show_xlabels_for_bottom_row_only()
        self._plot_grid.show_ylabels_for_left_column_only()
        self._plot_grid.show_xticklabels_for_bottom_row_only()
        self._plot_grid.show_yticklabels_for_left_column_only()
        # update grid layout after it is redrawn (hopefully that is after 100ms)
        QTimer.singleShot(100, self._plot_grid.set_viewbox_relative_sizes)

        # # link axes
        # xlink = self._link_xaxis_checkbox.isChecked()
        # ylink = self._link_yaxis_checkbox.isChecked()

        # # fonts
        # axislabel_ptsize = self._axislabel_fontsize_spinbox.value()
        # axislabel_sizestr = f'{axislabel_ptsize}pt'
        # axistick_ptsize = self._axistick_fontsize_spinbox.value()
        # axistick_font = QFont()
        # axistick_font.setPointSize(axistick_ptsize)

        # if not self._selected_tree_items or not self._selected_var_names:
        #     # nothing to plot -> show one empty plot
        #     self._plot_grid_widget.clear()
        #     plot = self.new_plot()
        #     self._plot_grid_widget.addItem(plot, 0, 1)
        #     self._plot_grid: list[list[dict]] = [[{'plot': plot}]]
        # else:
        #     # plot grid and dimension indices
        #     self._plot_grid = []
        #     xunits = self._selected_units.get(self.xdim, None)
        #     n_selected_vars = len(self._selected_var_names)
        #     for i in range(n_rows_per_var):
        #         print('i:', i)
        #         for var_name in self._selected_var_names:
        #             print('var_name:', var_name)
        #             yunits = self._selected_units.get(var_name, None)
        #             row = len(self._plot_grid)
        #             self._plot_grid.append([])
        #             # row tile label
        #             print('row tile label')
        #             label: pg.LabelItem = self._plot_grid_widget.getItem(row, 0)
        #             if label and (row_tile_dim == 'None' or not isinstance(label, pg.LabelItem)):
        #                 self._plot_grid_widget.removeItem(label)
        #                 del label
        #                 label = None
        #             if row_tile_dim != 'None':
        #                 text = f'{row_tile_dim} {row_tile_coords[i]}'
        #                 if label and isinstance(label, pg.LabelItem):
        #                     label.setText(text)
        #                 else:
        #                     label = pg.LabelItem(text, angle=-90, size=axislabel_sizestr)
        #                     self._plot_grid_widget.addItem(label, row, 0)
        #             print('row tile label done')
        #             # row plots
        #             for j in range(n_cols_per_var):
        #                 print('j:', j)
        #                 col = 1 + len(self._plot_grid[-1])  # first column is for tile labels
        #                 print(row, col)
        #                 plot: PlotItem = self._plot_grid_widget.getItem(row, col)
        #                 print('plot:', plot)
        #                 if plot is not None and not isinstance(plot, PlotItem):
        #                     self._plot_grid_widget.removeItem(plot)
        #                     del plot
        #                     plot = None
        #                 if plot is None:
        #                     print('make new plot')
        #                     plot = PlotItem()#self.new_plot()
        #                     print('new_plot:', plot)
        #                     self._plot_grid_widget.addItem(plot, row, col)
        #                 print('plot:', plot)
        #                 # axis fonts
        #                 plot.getAxis('left').setTickFont(axistick_font)
        #                 plot.getAxis('bottom').setTickFont(axistick_font)
        #                 # indices
        #                 plot_coords = selected_coords.copy()
        #                 if row_tile_dim != 'None':
        #                     plot_coords |= {row_tile_dim: row_tile_coords[i].copy()}
        #                 if col_tile_dim != 'None':
        #                     plot_coords |= {col_tile_dim: col_tile_coords[j].copy()}
        #                 # add info to grid
        #                 info: dict = {
        #                     'plot': plot,
        #                     'vars': [var_name],
        #                     'coords': plot_coords,
        #                     # 'coord_permutations': XarrayTreeNode.permutations(plot_coords)
        #                 }
        #                 self._plot_grid[-1].append(info)
        #                 print('_plot_grid:', self._plot_grid)
        #                 # x-axis
        #                 axis: pg.AxisItem = plot.getAxis('bottom')
        #                 if var_name == self._selected_var_names[-1] and i == n_rows_per_var - 1:
        #                     style = {'font-size': axislabel_sizestr, 'color': '#000'}
        #                     axis.setLabel(text=self.xdim, units=xunits, **style)
        #                     axis.showLabel(True)
        #                     axis.setStyle(showValues=True)
        #                 else:
        #                     axis.showLabel(False)
        #                     showTickLabels = not xlink
        #                     axis.setStyle(showValues=showTickLabels)
        #                 # y-axis
        #                 axis = plot.getAxis('left')
        #                 if col == 1:
        #                     style = {'font-size': axislabel_sizestr, 'color': '#000'}
        #                     axis.setLabel(text=var_name, units=yunits, **style)
        #                     axis.showLabel(True)
        #                     axis.setStyle(showValues=True)
        #                 else:
        #                     axis.showLabel(False)
        #                     showTickLabels = not ylink
        #                     axis.setStyle(showValues=showTickLabels)
        #                 # link x-axis
        #                 plot.setXLink(None)
        #                 if xlink and (row > 0 or col > 1):
        #                     plot.setXLink(self._plot_grid[0][0]['plot'])
        #                 # link y-axis
        #                 plot.setYLink(None)
        #                 if ylink and (row >= n_selected_vars or col > 1):
        #                     plot.setYLink(self._plot_grid[row % n_selected_vars][0]['plot'])
        #     # col tile labels
        #     print('col tile labels')
        #     row = len(self._plot_grid)
        #     item = self._plot_grid_widget.getItem(row, 0)
        #     if item:
        #         self._plot_grid_widget.removeItem(item)
        #         del item
        #     for j in range(n_cols_per_var):
        #         col = 1 + j
        #         label: pg.LabelItem = self._plot_grid_widget.getItem(row, col)
        #         if label and (col_tile_dim == 'None' or not isinstance(label, pg.LabelItem)):
        #             self._plot_grid_widget.removeItem(label)
        #             del label
        #             label = None
        #         if col_tile_dim != 'None':
        #             text = f'{col_tile_dim} {col_tile_coords[j]}'
        #             if label and isinstance(label, pg.LabelItem):
        #                 label.setText(text)
        #             else:
        #                 label = pg.LabelItem(text, angle=0, size=axislabel_sizestr)
        #                 self._plot_grid_widget.addItem(label, row, col)
        #     print('col tile labels done')
        
        # # remove extra plots
        # print('removing extra plots')
        # n_rows = len(self._plot_grid) + 1       # last row is tile labels
        # n_cols = 1 + len(self._plot_grid[0])    # first column is tile labels
        # for i in reversed(range(self._plot_grid_layout.count())): 
        #     item: pg.GraphicsItem = self._plot_grid_layout.itemAt(i)
        #     cells = self._plot_grid_widget.ci.items[item]
        #     for row, col in cells:
        #         if row >= n_rows or col >= n_cols:
        #             self._plot_grid_widget.removeItem(item)
        #             del item
        #             break
        # print('done removing extra plots')
        
        # # align view boxes in plot grid
        # self.update_plot_grid_alignment()


class XarrayXYDataViewer(QWidget):
    """ PySide/PyQt widget for analyzing (x,y) data series in a Xarray dataset. """

    def __init__(self, *args, **kwargs):
        QWidget.__init__(self, *args, **kwargs)

        # the waveform data
        self._data: XarrayTreeNode | None = None

        # the x-axis dimension to be plotted against
        self._xdim: str = 'time'

        # setup the graphical user interface
        self.setup_ui()

    
    @property
    def data(self) -> XarrayTreeNode | None:
        return self._data
    
    @data.setter
    def data(self, data: XarrayTreeNode | xr.Dataset | None):
        # set xarray tree
        if isinstance(data, xr.Dataset):
            root: XarrayTreeNode = XarrayTreeNode(name='/', dataset=None)
            XarrayTreeNode(name='dataset', dataset=data, parent=root)
            self._data = root
        elif isinstance(data, XarrayTreeNode):
            self._data = data
        elif data is None:
            self._data = data
        else:
            return
        
        # update data tree view
        self._dataTreeView.set_data(self.data)

        # store the merged coords for the entire tree
        self._tree_coords: dict[str, np.ndarray] = {}
        if self.data is not None:
            node: XarrayTreeNode = self.data
            while node is not None:
                ds: xr.Dataset = node.dataset
                if ds is not None:
                    node_coords: dict[str, xr.DataArray | np.ndarray] = node.inherited_coords()
                    for name, coords in node_coords.items():
                        if isinstance(coords, xr.DataArray):
                            coords: np.ndarray = coords.values
                        if name in self._tree_coords:
                            self._tree_coords[name] = np.unique(np.concatenate((self._tree_coords[name], coords)))
                        else:
                            self._tree_coords[name] = coords
                node = node.next_node_depth_first()
        
        # remove dim iter actions from toolbar
        for dim in self._dimIterToolbarThings:
            if 'labelAction' in self._dimIterToolbarThings[dim]:
                self._topToolbar.removeAction(self._dimIterToolbarThings[dim]['labelAction'])
            if 'spinboxAction' in self._dimIterToolbarThings[dim]:
                self._topToolbar.removeAction(self._dimIterToolbarThings[dim]['spinboxAction'])
        # delete unneeded dim iter widgets and actions
        for dim in self._dimIterToolbarThings:
            if dim not in self._tree_coords or len(self._tree_coords[dim]) == 1:
                if 'label' in self._dimIterToolbarThings[dim]:
                    self._dimIterToolbarThings[dim]['label'].deleteLater()
                    del self._dimIterToolbarThings[dim]['label']
                if 'spinbox' in self._dimIterToolbarThings[dim]:
                    self._dimIterToolbarThings[dim]['spinbox'].deleteLater()
                    del self._dimIterToolbarThings[dim]['spinbox']
                if 'labelAction' in self._dimIterToolbarThings[dim]:
                    self._dimIterToolbarThings[dim]['labelAction'].deleteLater()
                    del self._dimIterToolbarThings[dim]['labelAction']
                if 'spinboxAction' in self._dimIterToolbarThings[dim]:
                    self._dimIterToolbarThings[dim]['spinboxAction'].deleteLater()
                    del self._dimIterToolbarThings[dim]['spinboxAction']
                del self._dimIterToolbarThings[dim]
        # update or create dim iter widgets and insert actions into toolbar
        for dim in self._tree_coords:
            if len(self._tree_coords[dim]) > 1:
                if dim not in self._dimIterToolbarThings:
                    self._dimIterToolbarThings[dim] = {}
                if 'label' not in self._dimIterToolbarThings[dim]:
                    self._dimIterToolbarThings[dim]['label'] = QLabel(f'  {dim}:')
                if 'spinbox' not in self._dimIterToolbarThings[dim]:
                    spinbox: MultiValueSpinBox = MultiValueSpinBox()
                    spinbox.indices_changed.connect(self.on_index_selection_changed)
                    self._dimIterToolbarThings[dim]['spinbox'] = spinbox
                spinbox: MultiValueSpinBox = self._dimIterToolbarThings[dim]['spinbox']
                spinbox.indices_changed.disconnect(self.on_index_selection_changed)
                spinbox.setIndexedValues(self._tree_coords[dim])
                spinbox.setToolTip(f'{dim} index/slice (+Shift: page up/down)')
                spinbox.indices_changed.connect(self.on_index_selection_changed)
                if 'labelAction' in self._dimIterToolbarThings[dim]:
                    self._topToolbar.insertAction(self._homeAction, self._dimIterToolbarThings[dim]['labelAction'])
                else:
                    self._dimIterToolbarThings[dim]['labelAction'] = self._topToolbar.insertWidget(self._homeAction, self._dimIterToolbarThings[dim]['label'])
                if 'spinboxAction' in self._dimIterToolbarThings[dim]:
                    self._topToolbar.insertAction(self._homeAction, self._dimIterToolbarThings[dim]['spinboxAction'])
                else:
                    self._dimIterToolbarThings[dim]['spinboxAction'] = self._topToolbar.insertWidget(self._homeAction, self._dimIterToolbarThings[dim]['spinbox'])

        # reset xdim in case dims have changed
        # default to last dim if xdim is invalid
        dim_names: list[str] = self.dim_names()
        xdim = self.xdim
        if dim_names and (xdim not in dim_names):
            xdim = dim_names[-1]
        self.xdim = xdim
        # Note: setting xdim updates plots and toolbar

        self.autoscale_plots()
    
    @property
    def xdim(self) -> str:
        return self._xdim

    @xdim.setter
    def xdim(self, xdim: str):
        self._xdim = xdim

        dim_names: list[str] = self.dim_names()
        
        # update xdim combo box
        self._xdimComboBox.currentTextChanged.disconnect()
        self._xdimComboBox.clear()
        if dim_names:
            self._xdimComboBox.addItems(dim_names)
        if xdim in dim_names:
            self._xdimComboBox.setCurrentText(xdim)
        self._xdimComboBox.currentTextChanged.connect(self.on_xdim_changed)
        
        # update row/col tile combo boxes
        tile_dims = ['None'] + dim_names
        if xdim in tile_dims:
            tile_dims.remove(xdim)
        
        rowTileDim = self._rowTilesComboBox.currentText()
        if rowTileDim not in tile_dims:
            rowTileDim = 'None'
        self._rowTilesComboBox.currentTextChanged.disconnect(self.on_plot_grid_layout_changed)
        self._rowTilesComboBox.clear()
        self._rowTilesComboBox.addItems(tile_dims)
        self._rowTilesComboBox.setCurrentText(rowTileDim)
        self._rowTilesComboBox.currentTextChanged.connect(self.on_plot_grid_layout_changed)
        
        colTileDim = self._colTilesComboBox.currentText()
        if colTileDim not in tile_dims or colTileDim == rowTileDim:
            colTileDim = 'None'
        self._colTilesComboBox.currentTextChanged.disconnect(self.on_plot_grid_layout_changed)
        self._colTilesComboBox.clear()
        self._colTilesComboBox.addItems(tile_dims)
        self._colTilesComboBox.setCurrentText(colTileDim)
        self._colTilesComboBox.currentTextChanged.connect(self.on_plot_grid_layout_changed)

        # update plots
        self.update_plots_and_toolbar()
    
    @Slot(str)
    def on_xdim_changed(self, xdim: str):
        self.xdim = xdim
    
    def var_names(self) -> list[str]:
        if self.data is None:
            return []
        var_names: set[str] = set()
        node: XarrayTreeNode = self.data
        while node is not None:
            ds: xr.Dataset = node.dataset
            if ds is not None:
                var_names |= set(ds.data_vars)
            node = node.next_node_depth_first()
        return list(var_names)
    
    def dim_names(self) -> list[str]:
        if self.data is None:
            return []
        dim_names: list[str] = []
        node: XarrayTreeNode = self.data
        while node is not None:
            ds: xr.Dataset = node.dataset
            if ds is not None:
                for dim in ds.dims:
                    if dim not in dim_names:
                        dim_names.append(dim)
            node = node.next_node_depth_first()
        return dim_names
    
    def is_tiling_enabled(self) -> bool:
        row_tile_dim = self._rowTilesComboBox.currentText()
        col_tile_dim = self._colTilesComboBox.currentText()
        tiling_enabled: bool = row_tile_dim in self._iter_dims or col_tile_dim in self._iter_dims
        return tiling_enabled
    

    @Slot()
    def on_plot_grid_layout_changed(self) -> None:
        self.update_plot_grid()
        self.update_plot_items()
    
    @Slot()
    def on_var_selection_changed(self) -> None:
        # selected tree items
        self._selected_items: list[XarrayTreeItem] = self._dataTreeView.selected_items()
        
        # store the merged coords for the entire selection
        # also store the first defined attrs for each coord
        self._selected_tree_coords: dict[str, xr.DataArray] = {}
        for item in self._selected_items:
            if item.node is None:
                continue
            item_coords: dict[str, xr.DataArray] = item.node.inherited_coords()
            for name, coords in item_coords.items():
                if name in self._selected_tree_coords:
                    attrs = self._selected_tree_coords[name].attrs
                    if not attrs:
                        attrs = coords.attrs
                    values = np.unique(np.concatenate((self._selected_tree_coords[name].values, coords.values)))
                    self._selected_tree_coords[name] = xr.DataArray(data=values, attrs=attrs)
                else:
                    self._selected_tree_coords[name] = coords
        
        # store the dims for the entire selection
        self._selected_dims: dict[str, int] = {name: len(coords) for name, coords in self._selected_tree_coords.items()}

        # iterable dimensions with size > 1 (excluding xdim)
        self._iter_dims = [dim for dim in list(self._selected_dims) if dim != self.xdim and self._selected_dims[dim] > 1]
        
        # update toolbar dim iter spin boxes (show/hide as needed)
        for dim in self._dimIterToolbarThings:
            isVisible = dim in self._selected_tree_coords and dim != self.xdim # and len(self._selected_tree_coords[dim].values) > 1
            self._dimIterToolbarThings[dim]['labelAction'].setVisible(isVisible)
            self._dimIterToolbarThings[dim]['spinboxAction'].setVisible(isVisible)
            if isVisible:
                spinbox: MultiValueSpinBox = self._dimIterToolbarThings[dim]['spinbox']
                spinbox.indices_changed.disconnect(self.on_index_selection_changed)
                values = spinbox.selectedValues()
                spinbox.setIndexedValues(self._selected_tree_coords[dim].values)
                spinbox.setSelectedValues(values)
                spinbox.indices_changed.connect(self.on_index_selection_changed)

        # selected var names
        self._selected_var_names = []
        for item in self._selected_items:
            if item.is_var():
                if item.key not in self._selected_var_names:
                    self._selected_var_names.append(item.key)

        # units
        self._units = {}
        for dim in self._selected_tree_coords:
            if 'units' in self._selected_tree_coords[dim].attrs:
                self._units[dim] = self._selected_tree_coords[dim].attrs['units']
        for item in self._selected_items:
            if item.node is None:
                continue
            ds: xr.Dataset = item.node.dataset
            if ds is None:
                continue
            for name in self._selected_var_names:
                if name not in self._units:
                    if name in ds.data_vars:
                        var = ds.data_vars[name]
                        if isinstance(var, xr.DataArray):
                            if 'units' in var.attrs:
                                self._units[name] = var.attrs['units']

        # flag plot grid for update
        self._plot_grid_needs_update = True

        # update index selection
        self.on_index_selection_changed()

    @Slot()
    def on_index_selection_changed(self) -> None:
        # selected coords for all non-x-axis dims
        self._selected_coords: dict[str, np.ndarray] = {}
        for dim in self._selected_tree_coords:
            if dim == self.xdim:
                continue
            elif dim in self._dimIterToolbarThings and len(self._selected_tree_coords[dim].values) > 1:
                spinbox: MultiValueSpinBox = self._dimIterToolbarThings[dim]['spinbox']
                self._selected_coords[dim] = spinbox.selectedValues()
            else:
                # single index along this dim
                self._selected_coords[dim] = self._selected_tree_coords[dim].values
        
        # update plot grid if flagged or if tiling is enabled
        try:
            plot_grid_needs_update = self._plot_grid_needs_update
        except AttributeError:
            plot_grid_needs_update = True
        if plot_grid_needs_update or self.is_tiling_enabled():
            self.update_plot_grid()
        
        # update plot items
        self.update_plot_items()
    
    
    def update_plots_and_toolbar(self) -> None:
        self.on_var_selection_changed()
    
    def update_plot_grid(self) -> None:
        selected_coords = self._selected_coords.copy()
        
        # grid tile dimensions
        n_rows_per_var = 1
        n_cols_per_var = 1
        row_tile_dim = self._rowTilesComboBox.currentText()
        col_tile_dim = self._colTilesComboBox.currentText()
        if col_tile_dim == row_tile_dim:
            col_tile_dim = 'None'
        if row_tile_dim != 'None' and row_tile_dim in selected_coords:
            row_tile_coords = selected_coords[row_tile_dim]
            n_rows_per_var = len(row_tile_coords)
            del selected_coords[row_tile_dim]
        if col_tile_dim != 'None' and col_tile_dim in selected_coords:
            col_tile_coords = selected_coords[col_tile_dim]
            n_cols_per_var = len(col_tile_coords)
            del selected_coords[col_tile_dim]

        # link axes
        xlink = self._linkXAxisCheckBox.isChecked()
        ylink = self._linkYAxisCheckBox.isChecked()

        # fonts
        axisLabelFontPointSize = self._axisLabelFontSizeSpinBox.value()
        axisLabelFontSizeStr = f'{axisLabelFontPointSize}pt'
        axisTickFontPointSize = self._axisTickFontSizeSpinBox.value()
        axisTickFont = QFont()
        axisTickFont.setPointSize(axisTickFontPointSize)

        if not self._selected_items or not self._selected_var_names:
            # nothing to plot -> show one empty plot
            self._plotGraphicsLayoutWidget.clear()
            plot = self.new_plot()
            self._plotGraphicsLayoutWidget.addItem(plot, 0, 1)
            self._plot_grid: list[list[dict]] = [[{'plot': plot}]]
        else:
            # plot grid and dimension indices
            self._plot_grid = []
            xunits = self._units.get(self.xdim, None)
            n_selected_vars = len(self._selected_var_names)
            for i in range(n_rows_per_var):
                for var_name in self._selected_var_names:
                    yunits = self._units.get(var_name, None)
                    row = len(self._plot_grid)
                    self._plot_grid.append([])
                    # row tile label
                    label: pg.LabelItem = self._plotGraphicsLayoutWidget.getItem(row, 0)
                    if label and (row_tile_dim == 'None' or not isinstance(label, pg.LabelItem)):
                        self._plotGraphicsLayoutWidget.removeItem(label)
                        del label
                        label = None
                    if row_tile_dim != 'None':
                        text = f'{row_tile_dim} {row_tile_coords[i]}'
                        if label and isinstance(label, pg.LabelItem):
                            label.setText(text)
                        else:
                            label = pg.LabelItem(text, angle=-90, size=axisLabelFontSizeStr)
                            self._plotGraphicsLayoutWidget.addItem(label, row, 0)
                    # row plots
                    for j in range(n_cols_per_var):
                        col = 1 + len(self._plot_grid[-1])  # first column is for tile labels
                        plot: pg.PlotItem = self._plotGraphicsLayoutWidget.getItem(row, col)
                        if plot and not isinstance(plot, pg.PlotItem):
                            self._plotGraphicsLayoutWidget.removeItem(plot)
                            del plot
                            plot = None
                        if not plot:
                            plot = self.new_plot()
                            self._plotGraphicsLayoutWidget.addItem(plot, row, col)
                        # axis fonts
                        plot.getAxis('left').setTickFont(axisTickFont)
                        plot.getAxis('bottom').setTickFont(axisTickFont)
                        # indices
                        plot_coords = selected_coords.copy()
                        if row_tile_dim != 'None':
                            plot_coords |= {row_tile_dim: row_tile_coords[i].copy()}
                        if col_tile_dim != 'None':
                            plot_coords |= {col_tile_dim: col_tile_coords[j].copy()}
                        # add info to grid
                        info: dict = {
                            'plot': plot,
                            'vars': [var_name],
                            'coords': plot_coords,
                            'coord_permutations': XarrayTreeNode.permutations(plot_coords)
                        }
                        self._plot_grid[-1].append(info)
                        # x-axis
                        axis: pg.AxisItem = plot.getAxis('bottom')
                        if var_name == self._selected_var_names[-1] and i == n_rows_per_var - 1:
                            style = {'font-size': axisLabelFontSizeStr, 'color': '#000'}
                            axis.setLabel(text=self.xdim, units=xunits, **style)
                            axis.showLabel(True)
                            # # this fails to add an additional line to the axis label
                            # html = axis.label.toHtml()
                            # p_start = html.find('<p')
                            # span_start = html.find('<span')
                            # p_tag = html[p_start:span_start]
                            # span_text_start = html.find('>', span_start) + 1
                            # span_tag = html[span_start:span_text_start]
                            # pos = html.find('</p>', span_text_start) + len('</p>')
                            # html = html[:pos] + p_tag + span_tag + '2nd line' + '</span></p>' + html[pos:]
                            # axis.label.setHtml(html)
                            axis.setStyle(showValues=True)
                        else:
                            axis.showLabel(False)
                            showTickLabels = not xlink
                            axis.setStyle(showValues=showTickLabels)
                        # y-axis
                        axis = plot.getAxis('left')
                        if col == 1:
                            style = {'font-size': axisLabelFontSizeStr, 'color': '#000'}
                            axis.setLabel(text=var_name, units=yunits, **style)
                            axis.showLabel(True)
                            axis.setStyle(showValues=True)
                        else:
                            axis.showLabel(False)
                            showTickLabels = not ylink
                            axis.setStyle(showValues=showTickLabels)
                        # link x-axis
                        plot.setXLink(None)
                        if xlink and (row > 0 or col > 1):
                            plot.setXLink(self._plot_grid[0][0]['plot'])
                        # link y-axis
                        plot.setYLink(None)
                        if ylink and (row >= n_selected_vars or col > 1):
                            plot.setYLink(self._plot_grid[row % n_selected_vars][0]['plot'])
            # col tile labels
            row = len(self._plot_grid)
            item = self._plotGraphicsLayoutWidget.getItem(row, 0)
            if item:
                self._plotGraphicsLayoutWidget.removeItem(item)
                del item
            for j in range(n_cols_per_var):
                col = 1 + j
                label: pg.LabelItem = self._plotGraphicsLayoutWidget.getItem(row, col)
                if label and (col_tile_dim == 'None' or not isinstance(label, pg.LabelItem)):
                    self._plotGraphicsLayoutWidget.removeItem(label)
                    del label
                    label = None
                if col_tile_dim != 'None':
                    text = f'{col_tile_dim} {col_tile_coords[j]}'
                    if label and isinstance(label, pg.LabelItem):
                        label.setText(text)
                    else:
                        label = pg.LabelItem(text, angle=0, size=axisLabelFontSizeStr)
                        self._plotGraphicsLayoutWidget.addItem(label, row, col)
        
        # remove extra plots
        n_rows = len(self._plot_grid) + 1       # last row is tile labels
        n_cols = 1 + len(self._plot_grid[0])    # first column is tile labels
        for i in reversed(range(self._plotGraphicsGridLayout.count())): 
            item: pg.GraphicsItem = self._plotGraphicsGridLayout.itemAt(i)
            cells = self._plotGraphicsLayout.items[item]
            for row, col in cells:
                if row >= n_rows or col >= n_cols:
                    self._plotGraphicsLayoutWidget.removeItem(item)
                    del item
                    break
        
        # align view boxes in plot grid
        self.update_plot_grid_alignment()

    def new_plot(self) -> pg.PlotItem:
        viewBox: ViewBox = ViewBox()
        plot = PlotItem(viewBox=viewBox)
        plot.vb.setMinimumSize(5, 5)
        viewBox.menu.addAction('Measure', lambda self=self, plot=plot: self.measure(plot))
        viewBox.menu.addAction('Curve Fit', lambda self=self, plot=plot: self.curve_fit(plot))
        viewBox.menu.addSeparator()
        viewBox.sigItemAdded.connect(self.on_item_added_to_axes)
        return plot
    
    def plot_grid_size(self) -> tuple[int, int]:
        rows = len(self._plot_grid)
        cols = len(self._plot_grid[0]) if rows > 0 else 0
        return rows, cols
    
    def plot_loc_info(self, plot: pg.PlotItem) -> tuple[int | None, int | None, dict | None]:
        rows, cols = self.plot_grid_size()
        for row in range(rows):
            for col in range(cols):
                info: dict = self._plot_grid[row][col]
                if 'plot' in info and info['plot'] is plot:
                    return row, col, info
        return None, None, None
    
    def update_plot_grid_alignment(self) -> None:
        # align view boxes of equal size for all plots
        rows, cols = self.plot_grid_size()
        if rows * cols == 0:
            return
        marginLeft, marginTop, marginRight, marginBottom = self._plotGraphicsGridLayout.getContentsMargins()
        if rows > 1:
            totalHeight = self.height() - self._topToolbar.height() \
                - self._mainLayout.contentsMargins().top() - self._mainLayout.contentsMargins().bottom() \
                - self._mainLayout.spacing() - marginTop - marginBottom
            bottom_plots: list[pg.PlotItem] = [self._plot_grid[-1][col]['plot'] for col in range(cols)]
            xAxisHeights = [plot.getAxis('bottom').height() for plot in bottom_plots]
            xAxisHeight = int(np.ceil(np.max(xAxisHeights)))
            plotHeight = float(totalHeight - xAxisHeight) / rows
            bottomPlotHeight = plotHeight + xAxisHeight
            for row in range(rows):
                for col in range(cols):
                    info: dict = self._plot_grid[row][col]
                    plot: pg.PlotItem = info['plot']
                    plot.setPreferredHeight(bottomPlotHeight if row == rows - 1 else plotHeight)
        if cols > 1:
            totalWidth = self.width() - marginLeft - marginRight
            left_plots: list[pg.PlotItem] = [self._plot_grid[row][0]['plot'] for row in range(rows)]
            yAxisWidths = [plot.getAxis('left').width() for plot in left_plots]
            yAxisWidth = int(np.ceil(np.max(yAxisWidths)))
            plotWidth = float(totalWidth - yAxisWidth) / cols
            leftPlotWidth = plotWidth + yAxisWidth
            for col in range(cols):
                for row in range(rows):
                    info: dict = self._plot_grid[row][col]
                    plot: pg.PlotItem = info['plot']
                    plot.setPreferredWidth(leftPlotWidth if col == 0 else plotWidth)
    
    def update_plot_items(self, grid_rows: list[int] = None, grid_cols: list[int] = None, item_types: list = None) -> None:
        n_grid_rows, n_grid_cols = self.plot_grid_size()
        if grid_rows is None:
            grid_rows = range(n_grid_rows)
        if grid_cols is None:
            grid_cols = range(n_grid_cols)
        
        for row in grid_rows:
            for col in grid_cols:
                plot_info: dict = self._plot_grid[row][col]
                plot: pg.PlotItem = plot_info['plot']
                    
                if item_types is None or XYDataItem in item_types:
                    # existing plot traces
                    trace_items = [item for item in plot.listDataItems() if isinstance(item, XYDataItem)]
                    
                    # update plot traces
                    trace_count = 0
                    color_index = 0
                    for tree_item in self._selected_items:
                        if not tree_item.is_var():
                            continue
                        if 'vars' not in plot_info or tree_item.key not in plot_info['vars']:
                            continue
                        if tree_item.node is None:
                            continue
                        xdata, var = self.get_xy_data(tree_item.node, tree_item.key)
                        if xdata is None or var is None:
                            continue
                        xdata: np.ndarray = xdata.values
                        for coords in plot_info['coord_permutations']:
                            # trace data
                            try:
                                # generally var_coords should be exactly coords
                                var_coords = {dim: dim_coords for dim, dim_coords in coords.items() if dim in var.dims}
                                ydata: np.ndarray = np.squeeze(var.sel(var_coords).values)
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
                                trace_item = XYDataItem(x=xdata, y=ydata)
                                linePen = pg.mkPen(color=(0, 114, 189), width=1, style=Qt.PenStyle.SolidLine)
                                trace_item.setPen(linePen)
                                plot.addItem(trace_item)
                                trace_items.append(trace_item)
                            # store data info with trace
                            trace_item._tree_item: XarrayTreeItem = tree_item
                            trace_item._coords: dict = coords
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
                            # trace style
                            style = var.attrs['style'] if 'style' in var.attrs else {}
                            style = XYDataStyleDict(style)
                            color_index = trace_item.setStyleDict(style, colorIndex=color_index)
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
    
    def autoscale_plots(self) -> None:
        rows, cols = self.plot_grid_size()
        for row in range(rows):
            for col in range(cols):
                plot_info: dict = self._plot_grid[row][col]
                plot: pg.PlotItem = plot_info['plot']
                plot.autoRange()
                plot.enableAutoRange()
    
    
    def setup_ui(self) -> None:
        # toolbar
        self._topToolbar = QToolBar()
        self._topToolbar.setStyleSheet("QToolBar{spacing:2px;}")

        # # main menu button
        # self.setupMainMenu()
        # self._mainMenuButton = QToolButton()
        # self._mainMenuButton.setIcon(qta.icon('mdi6.menu', options=[{'opacity': 0.7}]))
        # self._mainMenuButton.setToolTip('Main Menu')
        # self._mainMenuButton.setPopupMode(QToolButton.InstantPopup)
        # self._mainMenuButton.setMenu(self._mainMenu)
        # self._topToolbar.addWidget(self._mainMenuButton)

        # view button
        self._viewButton = QToolButton()
        self._viewButton.setIcon(qta.icon('ph.eye-thin', options=[{'opacity': 0.7}]))
        self._viewButton.setToolTip('View Selections/Options')
        self._viewButton.clicked.connect(lambda: self._viewSidebarWidget.setVisible(not self._viewSidebarWidget.isVisible()))
        self._topToolbar.addWidget(self._viewButton)

        # widgets and toolbar actions for iterating dimension indices
        self._dimIterToolbarThings: dict[str, dict[str, QLabel | MultiValueSpinBox | QAction]] = {}

        # home button
        self._homeButton = QToolButton()
        self._homeButton.setIcon(qta.icon('mdi.home-outline', options=[{'opacity': 0.7}]))
        self._homeButton.setToolTip('Autoscale all plots')
        self._homeButton.clicked.connect(self.autoscale_plots)
        self._homeAction = self._topToolbar.addWidget(self._homeButton)

        # plots grid
        self._plotGraphicsLayoutWidget = pg.GraphicsLayoutWidget()
        self._plotGraphicsLayoutWidget.setBackground(QColor(240, 240, 240))
        self._plotGraphicsLayout: pg.GraphicsLayout = self._plotGraphicsLayoutWidget.ci
        self._plotGraphicsGridLayout: QGraphicsGridLayout = self._plotGraphicsLayoutWidget.ci.layout
        self._plotGraphicsGridLayout.setContentsMargins(0, 0, 0, 0)
        self._plotGraphicsGridLayout.setSpacing(0)
        # add empty plot
        plot = self.new_plot()
        self._plot_grid: list[list[dict]] = [[{'plot': plot}]]
        self._plotGraphicsLayoutWidget.addItem(plot, 0, 1)

        # x-axis selection
        self._xdimComboBox = QComboBox()
        self._xdimComboBox.currentTextChanged.connect(self.on_xdim_changed)

        # data tree
        self._dataTreeView = XarrayTreeView()
        root_node: XarrayTreeNode = self.data if self.data is not None else XarrayTreeNode('/', None)
        root_item = XarrayTreeItem(node=root_node, key=None)
        model: XarrayTreeModel = XarrayTreeModel(root_item)
        model._allowed_selections = ['var']
        self._dataTreeView.setModel(model)
        self._dataTreeView.selection_changed.connect(self.on_var_selection_changed)
        
        # row/col tile selection
        self._rowTilesComboBox = QComboBox()
        self._rowTilesComboBox.addItems(['None'])
        self._rowTilesComboBox.setCurrentText('None')
        self._rowTilesComboBox.currentTextChanged.connect(self.on_plot_grid_layout_changed)

        self._colTilesComboBox = QComboBox()
        self._colTilesComboBox.addItems(['None'])
        self._colTilesComboBox.setCurrentText('None')
        self._colTilesComboBox.currentTextChanged.connect(self.on_plot_grid_layout_changed)

        # link axes
        self._linkXAxisCheckBox = QCheckBox()#'Link X-Axis')
        self._linkXAxisCheckBox.setChecked(True)
        self._linkXAxisCheckBox.stateChanged.connect(self.update_plot_grid)

        self._linkYAxisCheckBox = QCheckBox()#'Link Y-Axis')
        self._linkYAxisCheckBox.setChecked(True)
        self._linkYAxisCheckBox.stateChanged.connect(self.update_plot_grid)

        # font size selection
        self._axisLabelFontSizeSpinBox = QSpinBox()
        self._axisLabelFontSizeSpinBox.setValue(AXIS_LABEL_FONT_SIZE)
        self._axisLabelFontSizeSpinBox.setSuffix('pt')
        self._axisLabelFontSizeSpinBox.valueChanged.connect(self.update_plot_grid)

        self._axisTickFontSizeSpinBox = QSpinBox()
        self._axisTickFontSizeSpinBox.setValue(AXIS_TICK_FONT_SIZE)
        self._axisTickFontSizeSpinBox.setSuffix('pt')
        self._axisTickFontSizeSpinBox.valueChanged.connect(self.update_plot_grid)

        self._eventFontSizeSpinBox = QSpinBox()
        self._eventFontSizeSpinBox.setValue(EVENT_FONT_SIZE)
        self._eventFontSizeSpinBox.setSuffix('pt')
        # self._eventFontSizeSpinBox.valueChanged.connect(lambda: self.updatePlotItems(itemTypes=[EventItem]))

        # display options button
        self._displayOptionsButton = QPushButton('Display Options')
        self._displayOptionsButton.clicked.connect(self.display_options_dialog)

        # view sidebar
        self._viewSidebarWidget = QWidget()
        vbox = QVBoxLayout(self._viewSidebarWidget)
        vbox.setContentsMargins(3, 3, 3, 3)
        vbox.setSpacing(5)

        vbox.addWidget(self._dataTreeView)

        form = QFormLayout()
        form.addRow('X axis:', self._xdimComboBox)
        vbox.addLayout(form)

        vbox.addWidget(self._displayOptionsButton)

        # main layout
        self._mainLayout = QVBoxLayout(self)
        self._mainLayout.setContentsMargins(3, 3, 3, 3)
        self._mainLayout.setSpacing(0)
        self._mainLayout.addWidget(self._topToolbar)
        hsplitter = QSplitter(Qt.Orientation.Horizontal)
        hsplitter.addWidget(self._viewSidebarWidget)
        hsplitter.addWidget(self._plotGraphicsLayoutWidget)
        hsplitter.setStretchFactor(0, 0)
        hsplitter.setStretchFactor(1, 1)
        self._mainLayout.addWidget(hsplitter)
    
    def display_options_dialog(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle('Display Options')
        form = QFormLayout(dlg)
        form.setContentsMargins(5, 5, 5, 5)
        form.setSpacing(5)

        form.addRow('Tile plots: rows', self._rowTilesComboBox)
        form.addRow('Tile plots: columns', self._colTilesComboBox)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        form.addRow(line)
        form.addRow('Link X axis', self._linkXAxisCheckBox)
        form.addRow('Link Y axis', self._linkYAxisCheckBox)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        form.addRow(line)
        form.addRow('Axis label font size', self._axisLabelFontSizeSpinBox)
        form.addRow('Axis tick font size', self._axisTickFontSizeSpinBox)
        form.addRow('Event font size', self._eventFontSizeSpinBox)

        pos = self.mapToGlobal(self.rect().topLeft())
        dlg.move(pos)
        dlg.exec()
    
    def resizeEvent(self, event: QResizeEvent) -> None:
        QWidget.resizeEvent(self, event)
        self.update_plot_grid_alignment()
    
    
    @Slot(QGraphicsObject)
    def on_item_added_to_axes(self, item: QGraphicsObject):
        viewBox: ViewBox = self.sender()
        plot: PlotItem = viewBox.parentItem()
        if isinstance(item, EventItem):
            # TODO: add event to xarray tree
            print('TODO: event added')
            # editing the event text via the popup dialog will also reset the region,
            # so this will cover text changes too
            item.sigRegionChangeFinished.connect(self.on_axes_item_changed)

    @Slot()
    def on_axes_item_changed(self):
        item = self.sender()
        if isinstance(item, EventItem):
            # TODO: update event in xarray tree
            print('TODO: event changed')
    
    
    @Slot()
    def measure(self, plot: pg.PlotItem):
        dlg = QDialog(plot.vb.getViewWidget())
        dlg.setWindowTitle('Measure')

        measurementTypesList = QListWidget()
        measurementTypesList.addItems([
            'Mean', 
            'Median', 
            'Min', 
            'Max', 
            'AbsMax', 
            'Standard Deviation', 
            'Variance'
        ])
        measurementTypesList.setCurrentRow(0)

        resultNameLineEdit = QLineEdit()
        resultNameLineEdit.setPlaceholderText('defaults to type')

        measureInEachROICheckBox = QCheckBox('Measure in each visible ROI')
        measureInEachROICheckBox.setChecked(True)

        peakWidthSpinBox = QSpinBox()
        peakWidthSpinBox.setValue(0)

        btns = QDialogButtonBox()
        btns.setStandardButtons(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)

        name_form = QFormLayout()
        name_form.setContentsMargins(2, 2, 2, 2)
        name_form.setSpacing(2)
        name_form.addRow('Result Name', resultNameLineEdit)

        peak_options_group = QGroupBox('Min, Max, AbsMax')
        form = QFormLayout(peak_options_group)
        form.setContentsMargins(2, 2, 2, 2)
        form.setSpacing(2)
        form.addRow('Mean \u00B1Samples', peakWidthSpinBox)

        right_vbox = QVBoxLayout()
        right_vbox.addLayout(name_form)
        right_vbox.addWidget(measureInEachROICheckBox)
        right_vbox.addStretch()
        right_vbox.addWidget(peak_options_group)
        right_vbox.addStretch()

        layout = QVBoxLayout(dlg)
        main_hbox = QHBoxLayout()
        main_hbox.addWidget(measurementTypesList)
        main_hbox.addLayout(right_vbox)
        layout.addLayout(main_hbox)
        layout.addWidget(btns)

        dlg.setWindowModality(Qt.ApplicationModal)
        if dlg.exec() != QDialog.Accepted:
            return

        # measurement options
        measurementType = measurementTypesList.currentItem().text()
        resultName = resultNameLineEdit.text().strip()
        if resultName == '':
            resultName = measurementType
        peakWidth = peakWidthSpinBox.value()
        
        # x,y data traces to measure
        xydata_items = [item for item in plot.vb.listItemsOfType(XYDataItem) if item.isVisible()]
        if not xydata_items:
            return
        
        # x-axis ROIs
        xregions = [item.getRegion() for item in plot.vb.listItemsOfType(XAxisRegionItem) if item.isVisible()]

        # measurements for each data trace
        measurements = []
        for xydata_item in xydata_items:
            # get x,y data
            try:
                xarr, var = self.get_xy_data(xydata_item._tree_item.node, xydata_item._tree_item.key)
                xdata: np.ndarray = xarr.values
                ydata: np.ndarray = var.sel(xydata_item._coords).values
                if len(ydata.shape) == 0:
                    ydata = ydata.reshape((1,))
                dims = var.dims
            except:
                xdata = xydata_item.xData
                ydata = xydata_item.yData
                dims = [self.xdim]
            # mask for each measurement point
            masks = []
            if xregions and measureInEachROICheckBox.isChecked():
                # one mask per xregion
                for xregion in xregions:
                    xmin, xmax = xregion
                    mask = (xdata >= xmin) & (xdata <= xmax)
                    masks.append(mask)
            elif xregions:
                # mask for combined xregions
                mask = np.full(xdata.shape, False)
                for xregion in xregions:
                    xmin, xmax = xregion
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
                if measurementType == 'Mean':
                    xmeasure.append(np.median(x))
                    ymeasure.append(np.mean(y))
                elif measurementType == 'Median':
                    xmeasure.append(np.median(x))
                    ymeasure.append(np.median(y))
                elif measurementType == 'Min':
                    i = np.argmin(y)
                    xmeasure.append(x[i])
                    if peakWidth == 0:
                        ymeasure.append(y[i])
                    else:
                        j = np.where(mask)[0][i]
                        start, stop = j, j + 1
                        for w in range(peakWidth):
                            if j - w >= 0 and mask[j - w] and start == j - w + 1:
                                start = j - w
                            if j + w < len(mask) and mask[j + w] and stop == j + w:
                                stop = j + w + 1
                        ymeasure.append(np.mean(ydata[start:stop]))
                elif measurementType == 'Max':
                    i = np.argmax(y)
                    xmeasure.append(x[i])
                    if peakWidth == 0:
                        ymeasure.append(y[i])
                    else:
                        j = np.where(mask)[0][i]
                        start, stop = j, j + 1
                        for w in range(peakWidth):
                            if j - w >= 0 and mask[j - w] and start == j - w + 1:
                                start = j - w
                            if j + w < len(mask) and mask[j + w] and stop == j + w:
                                stop = j + w + 1
                        ymeasure.append(np.mean(ydata[start:stop]))
                elif measurementType == 'AbsMax':
                    i = np.argmax(np.abs(y))
                    xmeasure.append(x[i])
                    if peakWidth == 0:
                        ymeasure.append(y[i])
                    else:
                        j = np.where(mask)[0][i]
                        start, stop = j, j + 1
                        for w in range(peakWidth):
                            if j - w >= 0 and mask[j - w] and start == j - w + 1:
                                start = j - w
                            if j + w < len(mask) and mask[j + w] and stop == j + w:
                                stop = j + w + 1
                        ymeasure.append(np.mean(ydata[start:stop]))
                elif measurementType == 'Standard Deviation':
                    xmeasure.append(np.median(x))
                    ymeasure.append(np.std(y))
                elif measurementType == 'Variance':
                    xmeasure.append(np.median(x))
                    ymeasure.append(np.var(y))
            if not ymeasure:
                measurements.append(None)
                continue
            xmeasure = np.array(xmeasure)
            ymeasure = np.array(ymeasure)
            order = np.argsort(xmeasure)
            xmeasure = xmeasure[order]
            ymeasure = ymeasure[order]
            shape =[1] * len(dims)
            shape[dims.index(self.xdim)] = len(ymeasure)
            coords = {}
            for dim, coord in xydata_item._coords.items():
                attrs = self._selected_tree_coords[dim].attrs.copy()
                if dim == self.xdim:
                    coords[dim] = (dim, xmeasure, attrs)
                else:
                    coords[dim] = (dim, np.array([coord], dtype=type(coord)), attrs)
            if self.xdim not in coords:
                attrs = self._selected_tree_coords[self.xdim].attrs.copy()
                coords[self.xdim] = (self.xdim, xmeasure, attrs)
            measurement = xr.Dataset(
                data_vars={
                    xydata_item._tree_item.key: (dims, ymeasure.reshape(shape), var.attrs.copy())
                },
                coords=coords
            )
            measurement.data_vars[xydata_item._tree_item.key].attrs['style'] = {
                'LineWidth': 2,
                'Marker': 'o'
            }
            measurements.append(measurement)
        numMeasurements = np.sum([1 for measurement in measurements if measurement is not None])
        if numMeasurements == 0:
            return
        
        # preview measurements
        for measurement in measurements:
            if measurement is None:
                continue
            var_name = list(measurement.data_vars)[0]
            var = measurement.data_vars[var_name]
            xdata = measurement.coords[self.xdim].values
            ydata = np.squeeze(var.values)
            if len(ydata.shape) == 0:
                ydata = ydata.reshape((1,))
            measurement_item = XYDataItem(x=xdata, y=ydata)
            measurement_item.setStyle(XYDataStyleDict({
                'Color': (255, 0, 0),
                'LineWidth': 2,
                'Marker': 'o',
            }))
            plot.addItem(measurement_item)
        answer = QMessageBox.question(plot.vb.getViewWidget(), 'Keep Measurements?', 'Keep measurements?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            row, col, info = self.plot_loc_info(plot)
            self.update_plot_items(grid_rows=[row], grid_cols=[col], item_types=[XYDataItem])
            return
        
        # add measurements to data tree
        parent_tree_nodes = [item._tree_item.node for item in xydata_items]
        measure_tree_nodes = []
        mergeApproved = None
        for parent_node, measurement in zip(parent_tree_nodes, measurements):
            # append measurement as child tree node
            if resultName in parent_node.children:
                if mergeApproved is None:
                    answer = QMessageBox.question(plot.vb.getViewWidget(), 'Merge Result?', 'Merge measurements with existing datasets of same name?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                    mergeApproved = (answer == QMessageBox.Yes)
                if not mergeApproved:
                    continue
                # merge measurement with existing child dataset (use measurement for any overlap)
                existing_child_node: XarrayTreeNode = parent_node.children[resultName]
                existing_child_node.dataset: xr.Dataset = measurement.combine_first(existing_child_node.dataset)
                measure_tree_nodes.append(existing_child_node)
            else:
                # append measurement as new child node
                node = XarrayTreeNode(name=resultName, dataset=measurement, parent=parent_node)
                measure_tree_nodes.append(node)
        
        # update data tree
        self.data = self.data

        # make sure newly added measurement nodes are selected and expanded
        model: XarrayTreeModel = self._dataTreeView.model()
        item: XarrayTreeItem = model.root
        while item is not None:
            for node in measure_tree_nodes:
                if item.node is node and item.is_var():
                    index: QModelIndex = model.createIndex(item.row(), 0, item)
                    self._dataTreeView.selectionModel().select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
                    self._dataTreeView.setExpanded(model.parent(index), True)
            item = item.next_item_depth_first()
    
    @Slot()
    def curve_fit(self, plot: pg.PlotItem):
        options = {}
        dlg = CurveFitDialog(options, plot.vb.getViewWidget())
        dlg.setWindowTitle('Curve Fit')
        dlg.setWindowModality(Qt.ApplicationModal)
        if dlg.exec() != QDialog.Accepted:
            return
        
        # fit options
        options: dict = dlg.options()
        resultName = options['resultName'].strip()
        if resultName == '':
            resultName = options['fitType']

        # x,y data traces to measure
        xydata_items = [item for item in plot.vb.listItemsOfType(XYDataItem) if item.isVisible()]
        if not xydata_items:
            return
        
        # x-axis ROIs
        xregions = [item.getRegion() for item in plot.vb.listItemsOfType(XAxisRegionItem) if item.isVisible()]

        # init fit equation
        if 'equation' in options:
            equation = options['equation']
            fitModel = lmfit.models.ExpressionModel(equation, independent_vars=['x'])
            for param in fitModel.param_names:
                initialValue = options['params'][param]['value']
                vary = options['params'][param]['vary']
                lowerBound, upperBound = options['params'][param]['bounds']
                if initialValue is None:
                    if not vary:
                        QErrorMessage(plot.vb.getViewWidget()).showMessage(f'Parameter {param} is fixed but has no initial value.')
                        return
                    initialValue = 1
                if initialValue < lowerBound:
                    initialValue = lowerBound
                if initialValue > upperBound:
                    initialValue = upperBound
                hint = {}
                hint['value'] = initialValue
                if lowerBound != -np.inf:
                    hint['min'] = lowerBound
                if upperBound != np.inf:
                    hint['max'] = upperBound
                fitModel.set_param_hint(param, **hint)
            params = fitModel.make_params()

        # fits for each data trace
        fits = []
        for xydata_item in xydata_items:
            # get x,y data
            try:
                xarr, var = self.get_xy_data(xydata_item._tree_item.node, xydata_item._tree_item.key)
                xdata: np.ndarray = xarr.values
                ydata: np.ndarray = var.sel(xydata_item._coords).values
                if len(ydata.shape) == 0:
                    ydata = ydata.reshape((1,))
                dims = var.dims
            except:
                xdata = xydata_item.xData
                ydata = xydata_item.yData
                dims = [self.xdim]
            # optimization mask
            if xregions and options['optimizeWithinROIsOnly']:
                # mask for combined xregions
                mask = np.full(xdata.shape, False)
                for xregion in xregions:
                    xmin, xmax = xregion
                    mask[(xdata >= xmin) & (xdata <= xmax)] = True
                xopt = xdata[mask]
                yopt = ydata[mask]
            else:
                # use everything
                xopt = xdata
                yopt = ydata
            # output mask
            if xregions and options['fitWithinROIsOnly']:
                # mask for combined xregions
                mask = np.full(xdata.shape, False)
                for xregion in xregions:
                    xmin, xmax = xregion
                    mask[(xdata >= xmin) & (xdata <= xmax)] = True
                xfit = xdata[mask]
            else:
                # use everything
                xfit = xdata
            # fit
            fit_attrs = {
                'type': options['fitType']
            }
            if options['fitType'] == 'Mean':
                yfit = np.full(len(xfit), np.mean(yopt))
            elif options['fitType'] == 'Median':
                yfit = np.full(len(xfit), np.median(yopt))
            elif options['fitType'] == 'Polynomial':
                degree = options['degree']
                coef = np.polyfit(xopt, yopt, degree)
                yfit = np.polyval(coef, xfit)
                fit_attrs['degree'] = degree
                fit_attrs['coefficients'] = coef
            elif options['fitType'] == 'Spline':
                n_segments = options['segments']
                segmentLength = max(1, int(len(yopt) / n_segments))
                knots = xopt[segmentLength:-segmentLength:segmentLength]
                if len(knots) < 2:
                    knots = xopt[[1, -2]]
                knots, coef, degree = sp.interpolate.splrep(xopt, yopt, t=knots)
                yfit = sp.interpolate.splev(xfit, (knots, coef, degree), der=0)
                fit_attrs['segments'] = n_segments
                fit_attrs['knots'] = knots
                fit_attrs['coefficients'] = coef
                fit_attrs['degree'] = degree
            elif 'equation' in options:
                equation = options['equation']
                result = fitModel.fit(yopt, params, x=xopt)
                print('----------')
                print(f'Fit: var={var.name}, coords={xydata_item._coords}')
                print(result.fit_report())
                print('----------')
                yfit = fitModel.eval(result.params, x=xfit)
                fit_attrs['equation'] = equation
                fit_attrs['params'] = {
                    param: {
                        'value': float(result.params[param].value),
                        'stderr': float(result.params[param].stderr),
                        'init_value': float(result.params[param].init_value),
                        'vary': bool(result.params[param].vary),
                        'min': float(result.params[param].min),
                        'max': float(result.params[param].max)
                    }
                    for param in result.params
                }
            else:
                fits.append(None)
                continue
            shape =[1] * len(dims)
            shape[dims.index(self.xdim)] = len(yfit)
            coords = {}
            for dim, coord in xydata_item._coords.items():
                attrs = self._selected_tree_coords[dim].attrs.copy()
                if dim == self.xdim:
                    coords[dim] = (dim, xfit, attrs)
                else:
                    coords[dim] = (dim, np.array([coord], dtype=type(coord)), attrs)
            if self.xdim not in coords:
                attrs = self._selected_tree_coords[self.xdim].attrs.copy()
                coords[self.xdim] = (self.xdim, xfit, attrs)
            attrs = var.attrs.copy()
            if 'fit' not in attrs:
                attrs['fit'] = {}
            coord_key = ', '.join([f'{dim}: {coord}' for dim, coord in xydata_item._coords.items()])
            attrs['fit'][coord_key] = fit_attrs
            fit = xr.Dataset(
                data_vars={
                    xydata_item._tree_item.key: (dims, yfit.reshape(shape), attrs)
                },
                coords=coords
            )
            fits.append(fit)
        numFits = np.sum([1 for fit in fits if fit is not None])
        if numFits == 0:
            return
        
        # preview fits
        for fit in fits:
            if fit is None:
                continue
            var_name = list(fit.data_vars)[0]
            var = fit.data_vars[var_name]
            xdata = fit.coords[self.xdim].values
            ydata = np.squeeze(var.values)
            if len(ydata.shape) == 0:
                ydata = ydata.reshape((1,))
            fit_item = XYDataItem(x=xdata, y=ydata)
            fit_item.set_style({
                'Color': (255, 0, 0),
                'LineWidth': 2,
            })
            plot.addItem(fit_item)
        answer = QMessageBox.question(plot.vb.getViewWidget(), 'Keep Fits?', 'Keep fits?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            row, col, info = self.plot_loc_info(plot)
            self.update_plot_items(grid_rows=[row], grid_cols=[col], item_types=[XYDataItem])
            return
        
        # add fits to data tree
        parent_tree_nodes = [item._tree_item.node for item in xydata_items]
        fit_tree_nodes = []
        mergeApproved = None
        for parent_node, fit in zip(parent_tree_nodes, fits):
            # append fit as child tree node
            if resultName in parent_node.children:
                if mergeApproved is None:
                    answer = QMessageBox.question(plot.vb.getViewWidget(), 'Merge Result?', 'Merge fits with existing datasets of same name?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                    mergeApproved = (answer == QMessageBox.Yes)
                if not mergeApproved:
                    continue
                # merge fit with existing child dataset (use fit for any overlap)
                existing_child_node: XarrayTreeNode = parent_node.children[resultName]
                try:
                    var_name = list(fit.data_vars)[0]
                    existing_var = existing_child_node.dataset.data_vars[var_name]
                    fit_attrs = existing_var.attrs['fit']
                    for key, value in fit.data_vars[var_name].attrs['fit'].items():
                        fit_attrs[key] = value
                except:
                    fit_attrs = fit.data_vars[var_name].attrs['fit']
                existing_child_node.dataset: xr.Dataset = fit.combine_first(existing_child_node.dataset)
                existing_child_node.dataset.data_vars[var_name].attrs['fit'] = fit_attrs
                fit_tree_nodes.append(existing_child_node)
            else:
                # append fit as new child node
                node = XarrayTreeNode(name=resultName, dataset=fit, parent=parent_node)
                fit_tree_nodes.append(node)
        
        # update data tree
        self.data = self.data

        # make sure newly added fit nodes are selected and expanded
        model: XarrayTreeModel = self._dataTreeView.model()
        item: XarrayTreeItem = model.root
        while item is not None:
            for node in fit_tree_nodes:
                if item.node is node and item.is_var():
                    index: QModelIndex = model.createIndex(item.row(), 0, item)
                    self._dataTreeView.selectionModel().select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
                    self._dataTreeView.setExpanded(model.parent(index), True)
            item = item.next_item_depth_first()

   
class CurveFitDialog(QDialog):
    def __init__(self, options: dict, *args, **kwargs):
        QDialog.__init__(self, *args, **kwargs)
        if options is None:
            options = {}

        self.fitTypes = {
            'Mean': '', 
            'Median': '', 
            'Line': 'a * x + b', 
            'Polynomial': '', 
            'Spline': '', 
            'Exponential Decay': 'a * exp(-b * x) + c', 
            'Exponential Rise': 'a * (1 - exp(-b * x)) + c', 
            'Hill Equation': 'a / (1 + (K / x)**n)', 
            'Custom': ''
            }
        self.fitTypeSelectionBox = QListWidget()
        self.fitTypeSelectionBox.addItems(self.fitTypes.keys())
        self.fitTypeSelectionBox.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.fitTypeSelectionBox.currentItemChanged.connect(self.onEquationSelected)

        self.resultNameLineEdit = QLineEdit()
        self.resultNameLineEdit.setPlaceholderText('defaults to type')

        self.optimizeWithinROIsOnlyCheckBox = QCheckBox('Optimize within visible ROIs only')
        self.optimizeWithinROIsOnlyCheckBox.setChecked(True)

        self.fitWithinROIsOnlyCheckBox = QCheckBox('Fit within visible ROIs only')
        self.fitWithinROIsOnlyCheckBox.setChecked(False)

        self.equationEdit = QLineEdit()
        self.equationEdit.setPlaceholderText('a * x**2 + b')
        self.equationEdit.textEdited.connect(self.onEquationChanged)
        self._customEquation = ''

        self.paramNames = []
        self.paramInitialValueEdits = {}
        self.paramFixedCheckBoxes = {}
        self.paramLowerBoundEdits = {}
        self.paramUpperBoundEdits = {}

        self.paramsGrid = QGridLayout()
        self.paramsGrid.addWidget(QLabel('Parameter'), 0, 0)
        self.paramsGrid.addWidget(QLabel('Initial Value'), 0, 1)
        self.paramsGrid.addWidget(QLabel('Fixed'), 0, 2)
        self.paramsGrid.addWidget(QLabel('Lower Bound'), 0, 3)
        self.paramsGrid.addWidget(QLabel('Upper Bound'), 0, 4)

        name_form = QFormLayout()
        name_form.setContentsMargins(2, 2, 2, 2)
        name_form.setSpacing(2)
        name_form.addRow('Result Name', self.resultNameLineEdit)

        self.equationGroupBox = QGroupBox('Equation: y = f(x)')
        vbox = QVBoxLayout(self.equationGroupBox)
        vbox.setContentsMargins(5, 5, 5, 5)
        vbox.setSpacing(5)
        vbox.addWidget(self.equationEdit)
        vbox.addLayout(self.paramsGrid)

        self.polynomialDegreeSpinBox = QSpinBox()
        self.polynomialDegreeSpinBox.setValue(2)

        self.polynomialGroupBox = QGroupBox('Polynomial')
        form = QFormLayout(self.polynomialGroupBox)
        form.setContentsMargins(5, 5, 5, 5)
        form.setSpacing(5)
        form.addRow('Degree', self.polynomialDegreeSpinBox)

        self.splineNumSegmentsSpinBox = QSpinBox()
        self.splineNumSegmentsSpinBox.setValue(10)

        self.splineGroupBox = QGroupBox('Spline')
        form = QFormLayout(self.splineGroupBox)
        form.setContentsMargins(5, 5, 5, 5)
        form.setSpacing(5)
        form.addRow('# Segments', self.splineNumSegmentsSpinBox)

        btns = QDialogButtonBox()
        btns.setStandardButtons(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        vbox = QVBoxLayout()
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(5)
        vbox.addLayout(name_form)
        vbox.addWidget(self.optimizeWithinROIsOnlyCheckBox)
        vbox.addWidget(self.fitWithinROIsOnlyCheckBox)
        vbox.addStretch()
        vbox.addWidget(self.equationGroupBox)
        vbox.addWidget(self.polynomialGroupBox)
        vbox.addWidget(self.splineGroupBox)
        vbox.addStretch()

        hbox = QHBoxLayout()
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(5)
        hbox.addWidget(self.fitTypeSelectionBox)
        hbox.addLayout(vbox)

        mainLayout = QVBoxLayout(self)
        mainLayout.addLayout(hbox)
        mainLayout.addWidget(btns)

        if 'fitType' in options:
            index = list(self.fitTypes.keys()).index(options['fitType'])
            if index is not None and index != -1:
                self.fitTypeSelectionBox.setCurrentRow(index)
                self.onEquationSelected()
            if options['fitType'] == 'Custom' and 'equation' in options:
                self.equationEdit.setText(options['equation'])
                self._customEquation = options['equation']
    
    def sizeHint(self):
        self.fitTypeSelectionBox.setMinimumWidth(self.fitTypeSelectionBox.sizeHintForColumn(0))
        return QSize(600, 400)
    
    def onEquationSelected(self):
        fitType = self.fitTypeSelectionBox.currentItem().text()
        if fitType == 'Mean':
            self.equationGroupBox.setVisible(False)
            self.polynomialGroupBox.setVisible(False)
            self.splineGroupBox.setVisible(False)
        elif fitType == 'Median':
            self.equationGroupBox.setVisible(False)
            self.polynomialGroupBox.setVisible(False)
            self.splineGroupBox.setVisible(False)
        elif fitType == 'Polynomial':
            self.equationGroupBox.setVisible(False)
            self.polynomialGroupBox.setVisible(True)
            self.splineGroupBox.setVisible(False)
        elif fitType == 'Spline':
            self.equationGroupBox.setVisible(False)
            self.polynomialGroupBox.setVisible(False)
            self.splineGroupBox.setVisible(True)
        else:
            self.equationGroupBox.setVisible(True)
            self.polynomialGroupBox.setVisible(False)
            self.splineGroupBox.setVisible(False)
            if fitType == 'Custom':
                self.equationEdit.setText(self._customEquation)
            else:
                equation = self.fitTypes[fitType]
                self.equationEdit.setText(equation)
            self.onEquationChanged()

    def onEquationChanged(self):
        equation = self.equationEdit.text().strip()
        # if '=' in equation:
        #     i = equation.rfind('=')
        #     if i >= 0:
        #         equation = equation[i+1:].strip()
        try:
            fitModel = lmfit.models.ExpressionModel(equation, independent_vars=['x'])
            self.paramNames = fitModel.param_names

            fiTypeEquations = list(self.fitTypes.values())
            if equation in fiTypeEquations:
                self.fitTypeSelectionBox.setCurrentRow(fiTypeEquations.index(equation))
            else:
                self._customEquation = equation
                self.fitTypeSelectionBox.setCurrentRow(list(self.fitTypes).index('Custom'))
        except:
            self.paramNames = []
        for name in self.paramNames:
            if name not in self.paramInitialValueEdits:
                self.paramInitialValueEdits[name] = QLineEdit()
            if name not in self.paramFixedCheckBoxes:
                self.paramFixedCheckBoxes[name] = QCheckBox()
            if name not in self.paramLowerBoundEdits:
                self.paramLowerBoundEdits[name] = QLineEdit()
            if name not in self.paramUpperBoundEdits:
                self.paramUpperBoundEdits[name] = QLineEdit()
        self.updateParamsGrid()
    
    def clearParamsGrid(self):
        for row in range(1, self.paramsGrid.rowCount()):
            for col in range(self.paramsGrid.columnCount()):
                item = self.paramsGrid.itemAtPosition(row, col)
                if item:
                    widget = item.widget()
                    self.paramsGrid.removeItem(item)
                    widget.setParent(None)
                    widget.setVisible(False)
    
    def updateParamsGrid(self):
        self.clearParamsGrid()
        for i, name in enumerate(self.paramNames):
            self.paramsGrid.addWidget(QLabel(name), i + 1, 0)
            self.paramsGrid.addWidget(self.paramInitialValueEdits[name], i + 1, 1)
            self.paramsGrid.addWidget(self.paramFixedCheckBoxes[name], i + 1, 2)
            self.paramsGrid.addWidget(self.paramLowerBoundEdits[name], i + 1, 3)
            self.paramsGrid.addWidget(self.paramUpperBoundEdits[name], i + 1, 4)
            self.paramInitialValueEdits[name].setVisible(True)
            self.paramFixedCheckBoxes[name].setVisible(True)
            self.paramLowerBoundEdits[name].setVisible(True)
            self.paramUpperBoundEdits[name].setVisible(True)
    
    def options(self):
        options = {}
        fitType = self.fitTypeSelectionBox.currentItem().text()
        options['fitType'] = fitType
        if fitType == 'Polynomial':
            options['degree'] = self.polynomialDegreeSpinBox.value()
        elif fitType == 'Spline':
            options['segments'] = self.splineNumSegmentsSpinBox.value()
        elif fitType in [name for name, equation in self.fitTypes.items() if equation != '' or name == 'Custom']:
            options['equation'] = self.equationEdit.text().strip()
            options['params'] = {}
            for name in self.paramNames:
                try:
                    value = float(self.paramInitialValueEdits[name].text())
                except:
                    value = None
                vary = not self.paramFixedCheckBoxes[name].isChecked()
                try:
                    lowerBound = float(self.paramLowerBoundEdits[name].text())
                except:
                    lowerBound = -np.inf
                try:
                    upperBound = float(self.paramUpperBoundEdits[name].text())
                except:
                    upperBound = np.inf
                options['params'][name] = {
                    'value': value,
                    'vary': vary,
                    'bounds': (lowerBound, upperBound)
                }
        options['optimizeWithinROIsOnly'] = self.optimizeWithinROIsOnlyCheckBox.isChecked()
        options['fitWithinROIsOnly'] = self.fitWithinROIsOnlyCheckBox.isChecked()
        options['resultName'] = self.resultNameLineEdit.text().strip()
        return options


def test_live():
    app = QApplication(sys.argv)

    ui = XarrayXYDataViewer2()
    ui.setWindowTitle('Xarray Waveform Analyzer')
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


# def test_combobox():
#     app = QApplication(sys.argv)

#     ui = QComboBox()
#     ui.addItems(['a', 'b', 'c', 'd'])
#     ui.show()

#     def refresh():
#         ui.blockSignals(True)
#         for i, v in enumerate(['d', 'e', 'f']):
#             if i < ui.count():
#                 ui.setItemText(i, v)
#             else:
#                 ui.addItem(v)
#         ui.setCurrentIndex(0)
#         while ui.count() > 3:
#             ui.removeItem(3)
#         ui.blockSignals(False)

#     b = QPushButton('refresh')
#     b.clicked.connect(refresh)
#     b.show()

#     status = app.exec()
#     sys.exit(status)


if __name__ == '__main__':
    test_live()
