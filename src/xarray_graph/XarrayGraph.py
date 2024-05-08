""" PySide/PyQt widget for analyzing (x,y) data series in a Xarray dataset or a tree of datasets.

TODO:
- datatree: edit var style attr with dialog from context menu

- fix bug: measure Min, Max, AbsMax
- fix bug: deleteing region item does not remove region from self.regions
- rename dims (implement in xarray_treeview?)
- drag items to rearrange tree heirarchy (implement in xarray_treeview)
- define all undefined coords by inheriting them (implement in xarray_tree)
- remove all unneeded coords that can be inherited (implement in xarray_tree)
- array math: update comboboxes on tree change
- array math: sanity checks needed
- array math: handle merging of results
- style: store user styling in metadata
- style: set style by trace, array, dataset, or variable name?
- style: store region styling in metadata
- style: set style for regions by label
- measure peaks: implement
- filter, smooth, etc.: implement
- add python console to UI
"""

from __future__ import annotations
import os, re
import numpy as np
import scipy as sp
import xarray as xr
from datatree import DataTree, open_datatree
import lmfit
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
from pyqt_ext.widgets import *
from pyqt_ext.graph import *
import pyqtgraph as pg
from pyqtgraph_ext import *
from xarray_treeview import *


# version info (stored in metadata in case needed later)
from importlib.metadata import version
XARRAY_GRAPH_VERSION = version('xarray-graph')


# Currently, color is handled by the widgets themselves.
# pg.setConfigOption('background', (240, 240, 240))
# pg.setConfigOption('foreground', (0, 0, 0))


DEBUG = 0
DEFAULT_ICON_SIZE = 24
DEFAULT_AXIS_LABEL_FONT_SIZE = 12
DEFAULT_AXIS_TICK_FONT_SIZE = 11
DEFAULT_TEXT_ITEM_FONT_SIZE = 10
DEFAULT_LINE_WIDTH = 1


metric_scale_factors = {
    'q': 1e-30, # quecto
    'r': 1e-27, # ronto
    'y': 1e-24, # yocto
    'z': 1e-21, # zepto
    'a': 1e-18, # atto
    'f': 1e-15, # femto
    'p': 1e-12, # pico
    'n': 1e-9, # nano
    u'\u00B5': 1e-6, # micro
    'm': 1e-3, # milli
    'k': 1e3, # kilo
    'M': 1e6, # mega
    'G': 1e9, # giga
    'T': 1e12, # tera
    'P': 1e15, # peta
    'E': 1e18, # exa
    'Z': 1e21, # zetta
    'Y': 1e24, # yotta
    'R': 1e27, # ronna
    'Q': 1e30, # quetta
}


class XarrayGraph(QMainWindow):
    """ PySide/PyQt widget for analyzing (x,y) data series in a Xarray dataset. """

    def __init__(self, *args, **kwargs):
        QMainWindow.__init__(self, *args, **kwargs)

        # xarray data tree
        self._data: DataTree = DataTree()

        # x-axis dimension to be plotted against
        self._xdim: str = 'time'

        # combined coords over entire tree
        self._combined_coords: xr.Dataset = xr.Dataset()

        # combined coords for current tree selection
        self._selected_coords: xr.Dataset = xr.Dataset()

        # combined coords for visible selection
        self._visible_coords: xr.Dataset = xr.Dataset()

        # setup the graphical user interface
        self._setup_ui()
    
    @property
    def data(self) -> DataTree:
        return self._data
    
    @data.setter
    def data(self, data: DataTree | xr.Dataset | xr.DataArray | np.ndarray | list[np.ndarray] | tuple[np.ndarray] | None):
        if not isinstance(data, DataTree):
            if data is None:
                data = DataTree()
            elif isinstance(data, xr.Dataset):
                data = DataTree(data=data)
            elif isinstance(data, xr.DataArray):
                data = DataTree(data=xr.Dataset(data_vars={data.name: data}))
            elif isinstance(data, np.ndarray):
                data = DataTree(data=xr.Dataset(data_vars={'data': data}))
            else:
                # assume list or tuple of two np.ndarrays (x, y)
                try:
                    x, y = data
                    data = DataTree(data=xr.Dataset(data_vars={'y': ('x', y)}, coords={'x': ('x', x)}))
                except Exception:
                    raise ValueError('XarrayGraph.data.setter: Invalid input.')
        
        # set xarray tree
        self._data = data
        
        # update data tree view
        self._data_treeview.setTree(self.data)

        # store the combined coords for the entire tree
        self._combined_coords: xr.Dataset = self._get_combined_coords()
        if DEBUG:
            print('self._combined_coords:', self._combined_coords)

        # reset xdim in case dims have changed.
        # This also updates selected coords, dim spinboxes and plot grid
        self.xdim = self.xdim

        # metadata
        self.attrs['xarray-graph-version'] = XARRAY_GRAPH_VERSION

        # regions tree view
        self._region_treeview.model().setRoot(AxisRegionTreeItem(self.regions))

        # notes
        self._notes_edit.setPlainText(self.attrs.get('notes', ''))

        # populate array math selections
        self._update_array_math_comboboxes()
    
    @property
    def dims(self) -> list[str]:
        dims = []
        for node in self.data.subtree:
            for dim in node.dims:
                if dim not in dims:
                    dims.append(dim)
        return dims
    
    @property
    def coords(self) -> dict[str, xr.DataArray]:
        return self._combined_coords.coords
    
    @property
    def selected_coords(self) -> dict[str, xr.DataArray]:
        return self._selected_coords.coords
    
    @property
    def visible_coords(self) -> dict[str, xr.DataArray]:
        return self._visible_coords.coords
    
    @property
    def attrs(self) -> dict:
        return self.data.attrs
    
    @attrs.setter
    def attrs(self, attrs: dict):
        self.data.attrs = attrs
    
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
        self._xdim_combobox.clear()
        if dims:
            self._xdim_combobox.addItems(dims)
            self._xdim_combobox.setCurrentIndex(dims.index(self.xdim))
        else:
            self._xdim_combobox.addItem(xdim)
            self._xdim_combobox.setCurrentIndex(0)
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
        self._row_tile_combobox.clear()
        self._row_tile_combobox.addItems(tile_dims)
        self._row_tile_combobox.setCurrentIndex(tile_dims.index(row_tile_dim))
        self._row_tile_combobox.blockSignals(False)
        
        col_tile_dim = self._col_tile_combobox.currentText()
        if col_tile_dim not in tile_dims or col_tile_dim == row_tile_dim:
            col_tile_dim = 'None'
        self._col_tile_combobox.blockSignals(True)
        self._col_tile_combobox.clear()
        self._col_tile_combobox.addItems(tile_dims)
        self._col_tile_combobox.setCurrentIndex(tile_dims.index(col_tile_dim))
        self._col_tile_combobox.blockSignals(False)
        
        # update dim iter spinboxes
        self._update_dim_iter_things()

        # update plots
        self._on_tree_selection_changed()
    
    def set_xdim(self, xdim: str):
        self.xdim = xdim
    
    @property
    def regions(self) -> list[dict]:
        if 'regions' not in self.attrs:
            self.attrs['regions'] = []
        return self.attrs['regions']
    
    @regions.setter
    def regions(self, regions: list[dict]):
        self.attrs['regions'] = regions
    
    # def is_tiling_enabled(self) -> bool:
    #     row_tile_dim = self._row_tile_combobox.currentText()
    #     col_tile_dim = self._col_tile_combobox.currentText()
    #     tiling_enabled: bool = row_tile_dim in self._iter_dims or col_tile_dim in self._iter_dims
    #     return tiling_enabled
    
    def clear(self) -> None:
        self.data = DataTree()
    
    def refresh(self) -> None:
        self.data = self.data
    
    def new_window(self) -> None:
        win = XarrayGraph()
        win.setWindowTitle(self.__class__.__name__)
        win.show()
    
    def load(self, filepath: str = '') -> None:
        if filepath == '':
            filepath = QFileDialog.getExistingDirectory(self, 'Open from Xarray data store...')
            if filepath == '':
                return None
        self.data = open_datatree(filepath, 'zarr')
        self._filepath = filepath
        self.setWindowTitle(os.path.split(filepath)[1])
    
    def save(self) -> None:
        if hasattr(self, '_filepath'):
            self.save_as(self._filepath)
        else:
            self.save_as()
    
    def save_as(self, filepath: str = '') -> None:
        if filepath == '':
            filepath, _filter = QFileDialog.getSaveFileName(self, 'Save to data Zarr heirarchy...')
            if filepath == '':
                return None
        self.data.to_zarr(filepath)
        self._filepath = filepath
        self.setWindowTitle(os.path.split(filepath)[1])
    
    def import_data(self, filepath: str = '', filetype: str = '') -> None:
        ds: xr.Dataset | None = None
        if filetype == 'pCLAMP':
            # TODO: implement
            QMessageBox.warning(self, 'Import pCLAMP', 'Importing pCLAMP files is not yet implemented.')
            return
        elif filetype == 'HEKA':
            # TODO: implement
            QMessageBox.warning(self, 'Import HEKA', 'Importing HEKA files is not yet implemented.')
            return
        elif filetype == 'GOLab TEVC':
            ds, filepath = import_golab_tevc(filepath)
        if ds is None:
            return
        self.data = ds
        self._filepath = os.path.splitext(filepath)[0]
        self.setWindowTitle(os.path.split(filepath)[1])
    
    def autoscale_plots(self, plots: list[Plot] = None) -> None:
        if plots is None:
            plots = self._plots()
        for plot in plots:
            plot.autoRange()
            plot.enableAutoRange()

    def add_region(self, region: dict) -> None:
        self._region_treeview.addRegion(region)
    
    def resizeEvent(self, event: QResizeEvent) -> None:
        QWidget.resizeEvent(self, event)
        self._update_grid_layout()
 
    def _get_combined_coords(self, nodes: list[DataTree] = None) -> xr.Dataset:
        # return the combined coords for the input tree nodes (defaults to the entire tree)
        # There should NOT be any missing dimensions in the returned dataset. 
        # TODO: inherit missing coords OR set them to their index range
        if nodes is None:
            # default to the entire tree
            nodes = list(self.data.subtree)
        combined_coords: xr.Dataset = xr.Dataset()
        for node in nodes:
            node_coords: xr.Dataset = xr.Dataset(coords=node.coords)
            combined_coords = xr.merge([combined_coords, node_coords], compat='no_conflicts')
        return combined_coords
    
    def _update_dim_iter_things(self) -> None:
        # remove dim iter actions from toolbar
        for dim in self._dim_iter_things:
            for value in self._dim_iter_things[dim].values():
                if isinstance(value, QAction):
                    self._plot_grid_toolbar.removeAction(value)
        
        # delete unneeded dim iter things
        for dim in list(self._dim_iter_things):
            if dim not in self.coords or len(self.coords[dim]) == 1:
                for value in self._dim_iter_things[dim].values():
                    value.deleteLater()
                del self._dim_iter_things[dim]
        
        # update or create dim iter things and insert actions into toolbar
        for dim in self.dims:
            if dim != self.xdim and dim in self.coords and len(self.coords[dim]) > 1:
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
                    spinbox.setIndexedValues(self.coords[dim])
                    spinbox.blockSignals(False)
                else:
                    spinbox: MultiValueSpinBox = MultiValueSpinBox()
                    spinbox.setToolTip(f'{dim} index/slice (+Shift: page up/down)')
                    spinbox.setIndexedValues(self.coords[dim])
                    spinbox.indicesChanged.connect(self._on_index_selection_changed)
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
        
        # if DEBUG:
        #     print('_dim_iter_things:', self._dim_iter_things)
    
    def _on_tree_selection_changed(self) -> None:
        # selected tree items
        self._selected_items: list[XarrayTreeItem] = self._data_treeview.selectedItems()
        self._selected_dataset_items = [item for item in self._selected_items if item.is_node()]
        self._selected_items = [item for item in self._selected_items if item.is_var()]
        if DEBUG:
            print('_selected_items:', [item.path for item in self._selected_items])
            print('_selected_dataset_items:', [item.path for item in self._selected_dataset_items])
        
        # update selected dataset info panels
        while self._main_area_layout.count() > 1:
            self._main_area_layout.takeAt(1).widget().deleteLater()
        for item in self._selected_dataset_items:
            widget = QGroupBox(item.path)
            layout = QVBoxLayout(widget)
            layout.setContentsMargins(5, 5, 5, 5)
            layout.setSpacing(5)
            textEdit = QTextEdit()
            textEdit.setPlainText(str(item.node.ds))
            textEdit.setReadOnly(True)
            layout.addWidget(textEdit)
            self._main_area_layout.addWidget(widget)
        self._plot_grid.setVisible(len(self._selected_items) > 0)
        
        # store the combined coords for the entire selection
        if self._selected_items:
            self._selected_coords: xr.Dataset = self._get_combined_coords([item.node for item in self._selected_items])
        else:
            self._selected_coords: xr.Dataset = xr.Dataset()
        if DEBUG:
            print('_selected_coords:', self._selected_coords)
        
        # store the dims for the entire selection
        dims = self.dims
        self._selected_dims = [dim for dim in dims if dim in self.selected_coords]
        self._selected_sizes: dict[str, int] = {dim: len(self.selected_coords[dim]) for dim in self._selected_dims}
        if DEBUG:
            print('_selected_sizes:', self._selected_sizes)
            print('_selected_dims:', self._selected_dims)

        # iterable dimensions with size > 1 (excluding xdim)
        self._iter_dims = [dim for dim in self._selected_dims if dim != self.xdim and self._selected_sizes[dim] > 1]
        if DEBUG:
            print('_iter_dims:', self._iter_dims)
        
        # update toolbar dim iter spin boxes (show/hide as needed)
        n_vis = 0
        for dim in self._dim_iter_things:
            isVisible = dim in self._selected_dims and dim != self.xdim # and self._selected_sizes[dim] > 1
            self._dim_iter_things[dim]['labelAction'].setVisible(isVisible)
            self._dim_iter_things[dim]['spinboxAction'].setVisible(isVisible)
            if isVisible:
                spinbox: MultiValueSpinBox = self._dim_iter_things[dim]['spinbox']
                spinbox.blockSignals(True)
                values = spinbox.selectedValues()
                spinbox.setIndexedValues(self._selected_coords[dim].values)
                spinbox.setSelectedValues(values)
                spinbox.blockSignals(False)
                n_vis += 1
        if n_vis == 0:
            self._dim_iter_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        else:
            self._dim_iter_spacer.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        # if DEBUG:
        #     print('_dim_iter_things:', self._dim_iter_things)

        # selected var names
        self._selected_var_names = []
        for item in self._selected_items:
            if item.is_var():
                if item.key not in self._selected_var_names:
                    self._selected_var_names.append(item.key)
        if DEBUG:
            print('_selected_var_names:', self._selected_var_names)

        # units for selected coords and vars
        self._selected_units = {}
        for dim in self.selected_coords:
            if 'units' in self.selected_coords[dim].attrs:
                self._selected_units[dim] = self.selected_coords[dim].attrs['units']
        for item in self._selected_items:
            if item.node is None:
                continue
            for name in self._selected_var_names:
                if name not in self._selected_units:
                    if name in item.node.ds.data_vars:
                        var = item.node.ds.data_vars[name]
                        if isinstance(var, xr.DataArray):
                            if 'units' in var.attrs:
                                self._selected_units[name] = var.attrs['units']
        if DEBUG:
            print('_selected_units:', self._selected_units)

        # flag plot grid for update
        self._plot_grid_needs_update = True

        # update index selection
        self._on_index_selection_changed()

        # update selected regions
        # self._on_selected_region_labels_changed()

    def _on_index_selection_changed(self) -> None:
        # selected coords for all non-x-axis dims (from toolbar spin boxes)
        self._visible_coords: xr.Dataset = xr.Dataset()
        for dim in self.selected_coords:
            if dim == self.xdim:
                continue
            if self._selected_sizes[dim] > 1:
                spinbox: MultiValueSpinBox = self._dim_iter_things[dim]['spinbox']
                values = spinbox.selectedValues()
                indices = np.searchsorted(self.selected_coords[dim].values, values)
                self._visible_coords.coords[dim] = self.selected_coords[dim].isel({dim: indices})
            else:
                # single index along this dim
                self._visible_coords.coords[dim] = self.selected_coords[dim]
        if DEBUG:
            print('_visible_coords:', self._visible_coords)
        
        # update plot grid
        self._update_plot_grid()
    
    def _new_plot(self) -> Plot:
        plot: Plot = Plot()
        view: View = plot.getViewBox()
        view.setMinimumSize(5, 5)
        view.sigItemAdded.connect(self._on_item_added_to_axes)
        return plot
    
    def _plots(self, grid_rows: list[int] = None, grid_cols: list[int] = None) -> list[Plot]:
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
    
    def _update_plot_grid(self) -> None:
        visible_coords = self.visible_coords.copy()
        
        # grid tile dimensions
        n_row_tiles = 1
        n_col_tiles = 1
        row_tile_dim = self._row_tile_combobox.currentText()
        col_tile_dim = self._col_tile_combobox.currentText()
        if col_tile_dim == row_tile_dim:
            col_tile_dim = 'None'
        if row_tile_dim not in visible_coords:
            row_tile_dim = 'None'
        if col_tile_dim not in visible_coords:
            col_tile_dim = 'None'
        if row_tile_dim != 'None':
            row_tile_coords = visible_coords[row_tile_dim]
            n_row_tiles = len(row_tile_coords)
            del visible_coords[row_tile_dim]
        if col_tile_dim != 'None':
            col_tile_coords = visible_coords[col_tile_dim]
            n_col_tiles = len(col_tile_coords)
            del visible_coords[col_tile_dim]
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
        
        # resize plot grid (only if needed)
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
            for row in range(rowmin, max(rowmax + 1, self._plot_grid.rowCount())):
                for col in range(colmin, max(colmax + 1, self._plot_grid.columnCount())):
                    item = self._plot_grid.getItem(row, col)
                    if rowmin <= row <= rowmax and colmin <= col <= colmax:
                        if item is not None and not issubclass(type(item), pg.PlotItem):
                            self._plot_grid.removeItem(item)
                            item.deleteLater()
                            item = None
                        if item is None:
                            item = self._new_plot()
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
            
            self._link_axes()
            self._update_axes_tick_font()
        
        # assign vars and coords to each plot
        rowmin, rowmax = self._grid_rowlim
        colmin, colmax = self._grid_collim
        for row in range(rowmin, rowmax + 1):
            var_name = self._selected_var_names[(row - rowmin) % n_vars]
            for col in range(colmin, colmax + 1):
                plot: Plot = self._plot_grid.getItem(row, col)
                coords = visible_coords.copy()
                if row_tile_dim != 'None':
                    tile_index = int((row - rowmin) / n_vars) % n_row_tiles
                    tile_coord = row_tile_coords.values[tile_index]
                    coords[row_tile_dim] = xr.DataArray(data=[tile_coord], dims=[row_tile_dim], attrs=row_tile_coords.attrs)
                if col_tile_dim != 'None':
                    tile_index = (col - colmin) % n_col_tiles
                    tile_coord = col_tile_coords.values[tile_index]
                    coords[col_tile_dim] = xr.DataArray(data=[tile_coord], dims=[col_tile_dim], attrs=col_tile_coords.attrs)
                if coords:
                    np_coords = {dim: coords[dim].values for dim in coords if dim != self.xdim}
                    coord_permutations = permutations(np_coords)
                else:
                    coord_permutations = [{}]
                plot._info = {
                    'data_vars': [var_name],
                    'coords': coords,
                    'coord_permutations': coord_permutations,
                }
                if DEBUG:
                    print(plot._info)
                plot._dims = [self.xdim, var_name]  # for region manager
        
        # axis labels
        self._update_axes_labels()
        
        # update plot items
        self._update_plot_items()

        # # ensure all plots have appropriate draw state
        # self.draw_region()

        # register all plots with region manager
        self._region_treeview.setPlots(self._plots())
        self._set_region_drawing_mode()  # resets region drawing mode to current mode for all plots

        # update plot grid (hopefully after everything has been redrawn)
        QTimer.singleShot(100, self._update_grid_layout)
    
    def _update_grid_layout(self) -> None:
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
    
    def _link_axes(self, xlink: bool | None = None, ylink: bool | None = None) -> None:
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

    def _update_axes_labels(self) -> None:
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
                row_label.deleteLater()
                row_label = None
            if row_tile_dim != 'None':
                tile_coord = plot._info['coords'][row_tile_dim].values[0]
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
                col_label.deleteLater()
                col_label = None
            if col_tile_dim != 'None':
                tile_coord = plot._info['coords'][col_tile_dim].values[0]
                label_text = f'{col_tile_dim}: {tile_coord}'
                if col_label is None:
                    col_label = pg.AxisItem('bottom')
                    col_label.setPen(pg.mkPen(width=0)) # hide axis lines
                    col_label.setStyle(showValues=False, tickLength=0) # hide tick labels
                    self._plot_grid.addItem(col_label, rowmax + 1, col)
                    col_label.setLabel(text=label_text, **tile_label_style)
                else:
                    col_label.setLabel(text=label_text, **tile_label_style)
        # clear row label for bottom left corner
        row_label = self._plot_grid.getItem(rowmax + 1, 0)
        if row_label is not None:
            self._plot_grid.removeItem(row_label)
            row_label.deleteLater()
    
    def _update_axes_tick_font(self) -> None:
        axis_tick_font = QFont()
        axis_tick_font.setPointSize(self._axistick_fontsize_spinbox.value())
        for plot in self._plots():
            plot.getAxis('left').setTickFont(axis_tick_font)
            plot.getAxis('bottom').setTickFont(axis_tick_font)
    
    def _update_plot_items(self, plots: list[Plot] = None, item_types: list = None) -> None:
        if plots is None:
            plots = self._plots()
        default_line_width = self._linewidth_spinbox.value()
        for plot in plots:
            if plot is None or not issubclass(type(plot), pg.PlotItem):
                continue
            view: View = plot.getViewBox()
                
            if item_types is None or Graph in item_types:
                # existing graph items in plot
                graphs = [item for item in plot.listDataItems() if isinstance(item, Graph)]
                
                # update graph items in plot
                count = 0
                color_index = 0
                for item in self._selected_items:
                    if not item.is_var():
                        continue
                    if 'data_vars' not in plot._info or item.key not in plot._info['data_vars']:
                        continue
                    try:
                        yarr = item.node.ds.data_vars[item.key]
                        xarr = item.node.ds.coords[self.xdim]
                        xdata: np.ndarray = xarr.values
                    except:
                        continue
                    style = yarr.attrs.get('style', {})
                    if 'linewidth' not in style:
                        style['linewidth'] = default_line_width
                    style = GraphStyle(style)
                    for coords in plot._info['coord_permutations']:
                        # x,y data
                        try:
                            ydata: np.ndarray = np.squeeze(yarr.sel(coords).values)
                            if len(ydata.shape) == 0:
                                ydata = ydata.reshape((1,))
                        except:
                            continue
                        
                        # graph data in plot
                        if len(graphs) > count:
                            # update existing data in plot
                            graph = graphs[count]
                            graph.setData(x=xdata, y=ydata)
                        else:
                            # add new data to plot
                            graph = Graph(x=xdata, y=ydata)
                            plot.addItem(graph)
                            graphs.append(graph)
                            graph.sigNameChanged.connect(lambda: self._update_plot_items(item_types=[Graph]))
                        
                        graph.blockSignals(True)
                        
                        # store tree info in graph
                        graph._info = {
                            'item': item,
                            'node': item.node,
                            'coords': coords,
                        }
                        
                        # graph style
                        graph.setGraphStyle(style, colorIndex=color_index)
                        if len(ydata) == 1:
                            if 'symbol' not in style:
                                graph.setSymbol('o')
                        
                        # graph name (limit to 50 characters)
                        name = item.path
                        if len(name) > 50:
                            name = '...' + name[-47:]
                        graph.setName(name)
                        
                        graph.blockSignals(False)
                        
                        # next graph item
                        count += 1
                    
                    # next dataset
                    color_index += 1
                
                # remove extra graph items from plot
                while len(graphs) > count:
                    graph = graphs.pop()
                    plot.removeItem(graph)
                    graph.deleteLater()
    
    @Slot(QGraphicsObject)
    def _on_item_added_to_axes(self, item: QGraphicsObject):
        view: View = self.sender()
        # plot: Plot = view.parentItem()
        if isinstance(item, XAxisRegion):
            region = {}
            item.toDict(region, dim=self.xdim)
            
            # remove the added region item and readd it so that it is added correctly as a region to all plots
            view.removeItem(item)
            item.deleteLater()
            self.add_region(region)
            
            # stop drawing regions (draw one at a time)?
            if self._draw_single_region_action.isChecked():
                self._set_region_drawing_mode(False)

    def _setup_ui(self) -> None:
        self._setup_menubar()

        self._control_panel_toolbar = QToolBar()
        self._control_panel_toolbar.setOrientation(Qt.Orientation.Vertical)
        self._control_panel_toolbar.setStyleSheet("QToolBar{spacing:2px;}")
        self._control_panel_toolbar.setIconSize(QSize(DEFAULT_ICON_SIZE, DEFAULT_ICON_SIZE))
        self._control_panel_toolbar.setMovable(False)
        self._control_panel_toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)

        self._plot_grid_toolbar = QToolBar()
        self._plot_grid_toolbar.setStyleSheet("QToolBar{spacing:2px;}")
        self._plot_grid_toolbar.setIconSize(QSize(DEFAULT_ICON_SIZE, DEFAULT_ICON_SIZE))
        self._plot_grid_toolbar.setMovable(False)
        self._plot_grid_toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        icon_button = QToolButton()
        icon_button.setIcon(qta.icon('fa5s.cubes', options=[{'opacity': 0.5}]))
        icon_button.pressed.connect(self.refresh)
        self._plot_grid_toolbar.addWidget(icon_button)

        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._plot_grid_toolbar)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self._control_panel_toolbar)

        self._control_panel = QStackedWidget()

        self._plot_grid = PlotGrid()
        self._grid_rowlim = ()
        self._grid_collim = ()

        self._main_area = QWidget()
        self._main_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._main_area_layout = QVBoxLayout(self._main_area)
        self._main_area_layout.setContentsMargins(0, 0, 0, 0)
        self._main_area_layout.setSpacing(0)
        self._main_area_layout.addWidget(self._plot_grid)

        hsplitter = QSplitter(Qt.Orientation.Horizontal)
        hsplitter.addWidget(self._control_panel)
        hsplitter.addWidget(self._main_area)
        hsplitter.setStretchFactor(0, 0)
        hsplitter.setStretchFactor(1, 1)
        hsplitter.setHandleWidth(1)
        hsplitter.setSizes([250])

        self.setCentralWidget(hsplitter)

        self._setup_control_panel_toolbar()
        self._setup_plot_grid_toolbar()

        self._control_panel.hide()
    
    def _setup_menubar(self) -> None:
        self._import_menu = QMenu(self.tr('&Import'))
        for data_type in ['pCLAMP', 'HEKA', 'GOLab TEVC']:
            self._import_menu.addAction(self.tr(f'Import {data_type}...'), lambda x=data_type: self.import_data(filetype=x))

        self._file_menu = self.menuBar().addMenu(self.tr('&File'))
        self._file_menu.addAction(self.tr('&New Window'), self.new_window, QKeySequence.New)
        self._file_menu.addSeparator()
        self._file_menu.addAction(qta.icon('fa5s.folder-open'), self.tr('&Open...'), self.load, QKeySequence.Open)
        self._file_menu.addSeparator()
        self._file_menu.addMenu(self._import_menu)
        self._file_menu.addSeparator()
        self._file_menu.addAction(qta.icon('fa5s.save'), self.tr('&Save'), self.save, QKeySequence.Save)
        self._file_menu.addAction(qta.icon('fa5s.save'), self.tr('Save &As...'), self.save_as, QKeySequence.SaveAs)
        self._file_menu.addSeparator()
        self._file_menu.addAction(self.tr('&Close Window'), self.close, QKeySequence.Close)
    
    def _setup_plot_grid_toolbar(self) -> None:
        # widgets and toolbar actions for iterating dimension indices
        self._dim_iter_things: dict[str, dict[str, QLabel | MultiValueSpinBox | QAction]] = {}

        # expanding empty widget so buttons are right-aligned in toolbar
        self._dim_iter_spacer = QWidget()
        self._dim_iter_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._plot_grid_toolbar.addWidget(self._dim_iter_spacer)

        self._region_button = QToolButton()
        self._region_button.setIcon(qta.icon('mdi.arrow-expand-horizontal', options=[{'opacity': 0.5}]))
        self._region_button.setToolTip('Draw X axis region')
        self._region_button.setCheckable(True)
        self._region_button.setChecked(False)
        self._region_button.clicked.connect(self._set_region_drawing_mode)
        self._action_after_dim_iter_things = self._plot_grid_toolbar.addWidget(self._region_button)

        self._region_button_menu = QMenu()
        self._draw_single_region_action = QAction('Draw single region', self._region_button_menu, checkable=True, checked=True)
        self._draw_multiple_regions_action = QAction('Draw multiple regions', self._region_button_menu, checkable=True, checked=False)
        self._region_button_menu.addAction(self._draw_single_region_action)
        self._region_button_menu.addAction(self._draw_multiple_regions_action)
        group = QActionGroup(self._region_button_menu)
        group.addAction(self._draw_single_region_action)
        group.addAction(self._draw_multiple_regions_action)
        group.setExclusive(True)
        self._region_button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._region_button.customContextMenuRequested.connect(lambda pos: self._region_button_menu.exec_(self._region_button.mapToGlobal(pos)))

        self._home_button = QToolButton()
        self._home_button.setIcon(qta.icon('mdi.home-outline', options=[{'opacity': 0.5}]))
        self._home_button.setToolTip('Autoscale all plots')
        self._home_button.clicked.connect(lambda: self.autoscale_plots())
        self._plot_grid_toolbar.addWidget(self._home_button)
    
    def _setup_control_panel_toolbar(self) -> None:
        # control panel toolbar
        # button order in toolbar reflects setup order
        self._setup_data_control_panel()
        self._setup_grid_control_panel()
        self._setup_region_control_panel()
        self._setup_math_control_panel()
        self._setup_measure_control_panel()
        self._setup_curve_fit_control_panel()
        self._setup_notes_control_panel()
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._control_panel_toolbar.addWidget(spacer)
        self._setup_settings_control_panel()
    
    def _toggle_control_panel_at(self, index: int) -> None:
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
    
    def _show_control_panel_at(self, index: int) -> None:
        actions = self._control_panel_toolbar.actions()
        widgets = [self._control_panel_toolbar.widgetForAction(action) for action in actions]
        buttons = [widget for widget in widgets if isinstance(widget, QToolButton)]
        buttons[index].setChecked(True)
        self._control_panel.setCurrentIndex(index)
        self._control_panel.setVisible(True)
        for i, button in enumerate(buttons):
            if i != index:
                button.setChecked(False)
    
    def _setup_data_control_panel(self) -> None:
        button = QToolButton()
        button.setIcon(qta.icon('ph.eye', options=[{'opacity': 0.5}]))
        button.setCheckable(True)
        button.setChecked(False)
        button.setToolTip('Data browser')
        button.released.connect(lambda i=self._control_panel.count(): self._toggle_control_panel_at(i))
        self._control_panel_toolbar.addWidget(button)

        self._data_treeviewer = XarrayTreeViewer()
        self._data_treeview = self._data_treeviewer.view()
        self._data_treeview.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        root: XarrayTreeItem = XarrayTreeItem(node=self.data, key=None)
        model: XarrayTreeModel = XarrayTreeModel(root)
        model.setShowDetailsColumn(False)
        self._data_treeview.setShowCoords(False)
        self._data_treeview.setModel(model)
        self._data_treeview.selectionWasChanged.connect(self._on_tree_selection_changed)
        self._data_treeviewer.setSizes([100, 1])
        self._data_treeviewer.metadata_tabs.setCurrentIndex(1)

        self._xdim_combobox = QComboBox()
        self._xdim_combobox.currentTextChanged.connect(self.set_xdim)

        panel = QWidget()
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        vbox.addWidget(self._data_treeviewer)

        form = QFormLayout()
        form.setContentsMargins(5, 3, 0, 3)
        form.setSpacing(0)
        form.setHorizontalSpacing(5)
        form.addRow('X axis', self._xdim_combobox)
        vbox.addLayout(form)

        self._control_panel.addWidget(panel)
    
    def _setup_grid_control_panel(self) -> None:
        button = QToolButton()
        button.setIcon(qta.icon('mdi.grid', options=[{'opacity': 0.5}]))
        button.setCheckable(True)
        button.setChecked(False)
        button.setToolTip('Plot grid')
        button.released.connect(lambda i=self._control_panel.count(): self._toggle_control_panel_at(i))
        self._control_panel_toolbar.addWidget(button)

        self._link_xaxis_checkbox = QCheckBox('Link X axes')
        self._link_xaxis_checkbox.setChecked(True)
        self._link_xaxis_checkbox.stateChanged.connect(lambda: self._link_axes())

        self._link_yaxis_checkbox = QCheckBox('Link Y axes (per variable)')
        self._link_yaxis_checkbox.setChecked(True)
        self._link_yaxis_checkbox.stateChanged.connect(lambda: self._link_axes())

        self._row_tile_combobox = QComboBox()
        self._row_tile_combobox.addItems(['None'])
        self._row_tile_combobox.setCurrentText('None')
        self._row_tile_combobox.currentTextChanged.connect(self._update_plot_grid)

        self._col_tile_combobox = QComboBox()
        self._col_tile_combobox.addItems(['None'])
        self._col_tile_combobox.setCurrentText('None')
        self._col_tile_combobox.currentTextChanged.connect(self._update_plot_grid)

        link_group = QGroupBox('Link axes')
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
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setWidget(panel)
        scroll_area.setWidgetResizable(True)

        self._control_panel.addWidget(scroll_area)
    
    def _setup_region_control_panel(self) -> None:
        button = QToolButton()
        button.setIcon(qta.icon('mdi.arrow-expand-horizontal', options=[{'opacity': 0.5}]))
        button.setCheckable(True)
        button.setChecked(False)
        button.setToolTip('X axis regions')
        button.released.connect(lambda i=self._control_panel.count(): self._toggle_control_panel_at(i))
        self._control_panel_toolbar.addWidget(button)

        root = AxisRegionTreeItem(self.regions)
        model = AxisRegionDndTreeModel(root)
        self._region_treeview = AxisRegionTreeView()
        self._region_treeview.setModel(model)

        panel = QWidget()
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(5, 5, 5, 5)
        vbox.setSpacing(20)
        vbox.addWidget(self._region_treeview)

        self._control_panel.addWidget(panel)
    
    def _setup_math_control_panel(self) -> None:
        button = QToolButton()
        button.setIcon(qta.icon('ph.math-operations', options=[{'opacity': 0.5}]))
        button.setCheckable(True)
        button.setChecked(False)
        button.setToolTip('Math')
        button.released.connect(lambda i=self._control_panel.count(): self._toggle_control_panel_at(i))
        self._control_panel_toolbar.addWidget(button)

        self._math_result_name_edit = QLineEdit()
        self._math_result_name_edit.setPlaceholderText('result')

        self._math_lhs_combobox = QComboBox()
        self._math_lhs_combobox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self._math_rhs_combobox = QComboBox()
        self._math_rhs_combobox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self._math_operator_combobox = QComboBox()
        self._math_operator_combobox.addItems(['+', '-', '*', '/'])
        self._math_operator_combobox.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)

        self._math_eval_button = QPushButton('Evaluate')
        self._math_eval_button.pressed.connect(self.eval_array_math)

        math_group = QGroupBox('Array math')
        grid = QGridLayout(math_group)
        grid.setContentsMargins(3, 3, 3, 3)
        grid.setSpacing(5)
        grid.addWidget(self._math_result_name_edit, 0, 0, 1, 2)
        equals_label = QLabel('=')
        equals_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(equals_label, 1, 0)
        grid.addWidget(self._math_lhs_combobox, 1, 1)
        grid.addWidget(self._math_operator_combobox, 2, 0)
        grid.addWidget(self._math_rhs_combobox, 2, 1)
        grid.addWidget(self._math_eval_button, 3, 0, 1, 2)

        panel = QWidget()
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(5, 5, 5, 5)
        vbox.setSpacing(20)
        vbox.addWidget(math_group)
        vbox.addStretch()

        scroll_area = QScrollArea()
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setWidget(panel)
        scroll_area.setWidgetResizable(True)

        self._control_panel.addWidget(scroll_area)
    
    def _setup_measure_control_panel(self) -> None:
        button = QToolButton()
        button.setIcon(qta.icon('mdi6.chart-scatter-plot', options=[{'opacity': 0.5}]))
        button.setCheckable(True)
        button.setChecked(False)
        button.setToolTip('Measure')
        button.released.connect(lambda i=self._control_panel.count(): self._toggle_control_panel_at(i))
        self._control_panel_toolbar.addWidget(button)

        self._measure_type_combobox = QComboBox()
        self._measure_type_combobox.addItems(['Mean', 'Median'])
        self._measure_type_combobox.insertSeparator(self._measure_type_combobox.count())
        self._measure_type_combobox.addItems(['Min', 'Max', 'AbsMax'])
        # self._measure_type_combobox.insertSeparator(self._measure_type_combobox.count())
        # self._measure_type_combobox.addItems(['Peaks'])
        self._measure_type_combobox.insertSeparator(self._measure_type_combobox.count())
        self._measure_type_combobox.addItems(['Standard Deviation', 'Variance'])
        self._measure_type_combobox.currentIndexChanged.connect(self._on_measure_type_changed)

        self._peak_half_width_spinbox = QSpinBox()
        self._peak_half_width_spinbox.setValue(0)

        self._peak_width_group = QGroupBox()
        form = QFormLayout(self._peak_width_group)
        form.setContentsMargins(3, 3, 3, 3)
        form.setSpacing(3)
        form.setHorizontalSpacing(5)
        form.addRow('Average +/- samples', self._peak_half_width_spinbox)

        self._peak_type_combobox = QComboBox()
        self._peak_type_combobox.addItems(['Min', 'Max'])
        self._peak_type_combobox.setCurrentText('Max')

        self._peak_threshold_edit = QLineEdit('0')

        self._peak_group = QGroupBox()
        form = QFormLayout(self._peak_group)
        form.setContentsMargins(3, 3, 3, 3)
        form.setSpacing(3)
        form.setHorizontalSpacing(5)
        form.addRow('Peak type', self._peak_type_combobox)
        form.addRow('Peak threshold', self._peak_threshold_edit)

        self._measure_in_visible_regions_only_checkbox = QCheckBox('Within selected regions')
        self._measure_in_visible_regions_only_checkbox.setChecked(True)

        self._measure_per_visible_region_checkbox = QCheckBox('Within each selected region')
        self._measure_per_visible_region_checkbox.setChecked(True)
        self._measure_in_visible_regions_only_checkbox.setEnabled(not self._measure_per_visible_region_checkbox.isChecked)
        self._measure_per_visible_region_checkbox.stateChanged.connect(lambda state: self._measure_in_visible_regions_only_checkbox.setEnabled(Qt.CheckState(state) == Qt.CheckState.Unchecked))

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
        vbox.addWidget(self._peak_group)
        vbox.addWidget(self._peak_width_group)
        vbox.addWidget(self._measure_in_visible_regions_only_checkbox)
        vbox.addWidget(self._measure_per_visible_region_checkbox)
        vbox.addWidget(self._measure_name_wrapper)
        vbox.addWidget(self._measure_button)
        self._on_measure_type_changed()

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
    
    def _setup_curve_fit_control_panel(self) -> None:
        button = QToolButton()
        button.setIcon(qta.icon('mdi.chart-bell-curve-cumulative', options=[{'opacity': 0.5}]))
        button.setCheckable(True)
        button.setChecked(False)
        button.setToolTip('Curve fit')
        button.released.connect(lambda i=self._control_panel.count(): self._toggle_control_panel_at(i))
        self._control_panel_toolbar.addWidget(button)

        self._curve_fit_type_combobox = QComboBox()
        self._curve_fit_type_combobox.addItems(['Mean', 'Median', 'Min', 'Max'])
        self._curve_fit_type_combobox.insertSeparator(self._curve_fit_type_combobox.count())
        self._curve_fit_type_combobox.addItems(['Line', 'Polynomial', 'Spline'])
        self._curve_fit_type_combobox.insertSeparator(self._curve_fit_type_combobox.count())
        self._curve_fit_type_combobox.addItems(['Equation'])
        self._curve_fit_type_combobox.setCurrentText('Equation')
        self._curve_fit_type_combobox.currentIndexChanged.connect(self._on_curve_fit_type_changed)

        self._polynomial_degree_spinbox = QSpinBox()
        self._polynomial_degree_spinbox.setValue(2)

        self._polynomial_group = QGroupBox()
        form = QFormLayout(self._polynomial_group)
        form.setContentsMargins(3, 3, 3, 3)
        form.setSpacing(3)
        form.setHorizontalSpacing(5)
        form.addRow('Polynomial degree', self._polynomial_degree_spinbox)

        self._spline_segments_spinbox = QSpinBox()
        self._spline_segments_spinbox.setValue(10)
        self._spline_segments_spinbox.setMinimum(1)

        self._spline_group = QGroupBox()
        form = QFormLayout(self._spline_group)
        form.setContentsMargins(3, 3, 3, 3)
        form.setSpacing(3)
        form.setHorizontalSpacing(5)
        form.addRow('Spline segments', self._spline_segments_spinbox)

        self._equation_edit = QLineEdit()
        self._equation_edit.setPlaceholderText('a * x + b')
        self._equation_edit.editingFinished.connect(self._on_curve_fit_equation_changed)

        self._equation_params = {}

        self._equation_params_table = QTableWidget(0, 5)
        self._equation_params_table.setHorizontalHeaderLabels(['Param', 'Value', 'Vary', 'Min', 'Max'])
        self._equation_params_table.verticalHeader().setVisible(False)
        self._equation_params_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._equation_params_table.model().dataChanged.connect(self._update_curve_fit_preview)

        self._equation_preview_checkbox = QCheckBox('Preview')
        self._equation_preview_checkbox.stateChanged.connect(self._update_curve_fit_preview)

        self._equation_group = QGroupBox()
        vbox = QVBoxLayout(self._equation_group)
        vbox.setContentsMargins(3, 3, 3, 3)
        vbox.setSpacing(3)
        vbox.addWidget(self._equation_edit)
        vbox.addWidget(self._equation_params_table)
        vbox.addWidget(self._equation_preview_checkbox)

        self._curve_fit_optimize_in_regions_checkbox = QCheckBox('Optimize within selected regions')
        self._curve_fit_optimize_in_regions_checkbox.setChecked(True)

        self._curve_fit_evaluate_in_regions_checkbox = QCheckBox('Evaluate within selected regions')
        self._curve_fit_evaluate_in_regions_checkbox.setChecked(False)

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
        vbox.addWidget(self._polynomial_group)
        vbox.addWidget(self._spline_group)
        vbox.addWidget(self._equation_group)
        vbox.addWidget(self._curve_fit_optimize_in_regions_checkbox)
        vbox.addWidget(self._curve_fit_evaluate_in_regions_checkbox)
        vbox.addWidget(self._curve_fit_name_wrapper)
        vbox.addWidget(self._curve_fit_button)
        self._on_curve_fit_type_changed()

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
    
    def _setup_notes_control_panel(self) -> None:
        button = QToolButton()
        button.setIcon(qta.icon('mdi.notebook-outline', options=[{'opacity': 0.5}]))
        button.setCheckable(True)
        button.setChecked(False)
        button.setToolTip('Notes')
        button.released.connect(lambda i=self._control_panel.count(): self._toggle_control_panel_at(i))
        self._control_panel_toolbar.addWidget(button)

        self._notes_edit = QTextEdit()
        self._notes_edit.setTabChangesFocus(False)
        self._notes_edit.setAcceptRichText(False)
        self._notes_edit.textChanged.connect(self._save_notes)

        self._control_panel.addWidget(self._notes_edit)
    
    def _setup_settings_control_panel(self) -> None:
        button = QToolButton()
        button.setIcon(qta.icon('msc.settings-gear', options=[{'opacity': 0.5}]))
        button.setCheckable(True)
        button.setChecked(False)
        button.setToolTip('Measure')
        button.released.connect(lambda i=self._control_panel.count(): self._toggle_control_panel_at(i))
        self._control_panel_toolbar.addWidget(button)

        self._linewidth_spinbox = QSpinBox()
        self._linewidth_spinbox.setValue(DEFAULT_LINE_WIDTH)
        self._linewidth_spinbox.setMinimum(1)
        self._linewidth_spinbox.valueChanged.connect(lambda: self._update_plot_items(item_types=[Graph]))

        self._axislabel_fontsize_spinbox = QSpinBox()
        self._axislabel_fontsize_spinbox.setValue(DEFAULT_AXIS_LABEL_FONT_SIZE)
        self._axislabel_fontsize_spinbox.setMinimum(1)
        self._axislabel_fontsize_spinbox.setSuffix('pt')
        self._axislabel_fontsize_spinbox.valueChanged.connect(self._update_axes_labels)

        self._axistick_fontsize_spinbox = QSpinBox()
        self._axistick_fontsize_spinbox.setValue(DEFAULT_AXIS_TICK_FONT_SIZE)
        self._axistick_fontsize_spinbox.setMinimum(1)
        self._axistick_fontsize_spinbox.setSuffix('pt')
        self._axistick_fontsize_spinbox.valueChanged.connect(self._update_axes_tick_font)

        self._textitem_fontsize_spinbox = QSpinBox()
        self._textitem_fontsize_spinbox.setValue(DEFAULT_TEXT_ITEM_FONT_SIZE)
        self._textitem_fontsize_spinbox.setMinimum(1)
        self._textitem_fontsize_spinbox.setSuffix('pt')
        self._textitem_fontsize_spinbox.valueChanged.connect(self._update_item_font)

        self._iconsize_spinbox = QSpinBox()
        self._iconsize_spinbox.setValue(DEFAULT_ICON_SIZE)
        self._iconsize_spinbox.setMinimum(16)
        self._iconsize_spinbox.setMaximum(64)
        self._iconsize_spinbox.setSingleStep(8)
        self._iconsize_spinbox.valueChanged.connect(self._update_icon_size)

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

        misc_group = QGroupBox('Misc')
        form = QFormLayout(misc_group)
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
        vbox.addWidget(misc_group)
        vbox.addStretch()

        scroll_area = QScrollArea()
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setWidget(panel)
        scroll_area.setWidgetResizable(True)

        self._control_panel.addWidget(scroll_area)
    
    def _set_region_drawing_mode(self, draw: bool | None = None) -> None:
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
    
    def _on_measure_type_changed(self) -> None:
        measure_type = self._measure_type_combobox.currentText()
        self._peak_group.setVisible(measure_type == 'Peaks')
        self._peak_width_group.setVisible(measure_type in ['Min', 'Max', 'AbsMax', 'Peaks'])
        self._measure_name_edit.setPlaceholderText(measure_type)
    
    def _on_curve_fit_type_changed(self) -> None:
        fit_type = self._curve_fit_type_combobox.currentText()
        self._polynomial_group.setVisible(fit_type == 'Polynomial')
        self._spline_group.setVisible(fit_type == 'Spline')
        self._equation_group.setVisible(fit_type == 'Equation')
        if self._equation_group.isVisible():
            self._equation_params_table.resizeColumnsToContents()
        self._curve_fit_name_edit.setPlaceholderText(fit_type)
    
    def _on_curve_fit_equation_changed(self) -> None:
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
    
    def _update_curve_fit_preview(self) -> None:
        show: bool = self._equation_preview_checkbox.isChecked()
        if show:
            self.preview_curve_fit()
        else:
            self._clear_tmp_curve_fits()
    
    def _clear_tmp_curve_fits(self, plots: list[Plot] = None) -> None:
        if plots is None:
            plots = self._plots()
        for plot in plots:
            if not hasattr(plot, '_tmp_fit_graphs'):
                continue
            for graph in plot._tmp_fit_graphs:
                try:
                    plot.removeItem(graph)
                    graph.deleteLater()
                except:
                    pass
            plot._tmp_fit_graphs = []
            # plot._tmp_fits = []
            # plot._tmp_fit_tree_items = []
    
    def _save_notes(self) -> None:
        notes = self._notes_edit.toPlainText()
        self.attrs['notes'] = notes
    
    def _load_notes(self, notes = None) -> None:
        if notes is None:
            notes = self.attrs.get('notes', '')
        self._notes_edit.setPlainText(notes)
    
    def _update_icon_size(self) -> None:
        size = self._iconsize_spinbox.value()
        icon_size = QSize(size, size)
        for toolbar in [self._control_panel_toolbar, self._plot_grid_toolbar]:
            toolbar.setIconSize(icon_size)
            actions = toolbar.actions()
            widgets = [toolbar.widgetForAction(action) for action in actions]
            buttons = [widget for widget in widgets if isinstance(widget, QToolButton)]
            for button in buttons:
                button.setIconSize(icon_size)
    
    def _update_item_font(self):
        for plot in self.plots():
            view: View = plot.getViewBox()
            for item in view.allChildren():
                if isinstance(item, XAxisRegion):
                    item.setFontSize(self._textitem_fontsize_spinbox.value())

    def _update_array_math_comboboxes(self) -> None:
        var_paths = [item.path for item in self._data_treeview.model().root().depth_first() if item.is_var()]
        for i in range(len(var_paths)):
            if len(var_paths[i]) > 100:
                var_paths[i] = '...' + var_paths[i][-97:]
        self._math_lhs_combobox.clear()
        self._math_rhs_combobox.clear()
        self._math_lhs_combobox.addItems(var_paths)
        self._math_rhs_combobox.addItems(var_paths)
    
    def eval_array_math(self) -> None:
        var_items = [item for item in self._data_treeview.model().root().depth_first() if item.is_var()]
        lhs_item = var_items[self._math_lhs_combobox.currentIndex()]
        rhs_item = var_items[self._math_rhs_combobox.currentIndex()]
        lhs: xr.DataArray = lhs_item.node[lhs_item.key]
        rhs: xr.DataArray = rhs_item.node[rhs_item.key]
        op = self._math_operator_combobox.currentText()
        if op == '+':
            result = lhs + rhs
        elif op == '-':
            result = lhs - rhs
        elif op == '*':
            result = lhs * rhs
        elif op == '/':
            result = lhs / rhs
        # append result as child of lhs_item
        result_name = self._math_result_name_edit.text().strip()
        if result_name == '':
            result_name = self._math_result_name_edit.placeholderText()
        result_ds = xr.Dataset(data_vars={result.name: result})
        result_node = DataTree(name=result_name, data=result_ds, parent=lhs_item.node)
        
        # update data tree
        self.data = self.data

        # make sure newly added fit nodes are selected and expanded
        model: XarrayTreeModel = self._data_treeview.model()
        for item in model.root().depth_first():
            if item.node is result_node and item.is_var():
                index: QModelIndex = model.createIndex(item.sibling_index, 0, item)
                self._data_treeview.selectionModel().select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
                self._data_treeview.setExpanded(model.parent(index), True)
    
    # # @Slot()
    # # def on_axes_item_changed(self):
    # #     item = self.sender()
    # #     if isinstance(item, XAxisRegion):
    # #         item._data['group'] = item.group()
    # #         item._data['region'] = list(item.getRegion())
    # #         item._data['text'] = item.text()
    # #         # update all regions in case the altered region appears in multiple plots
    # #         self.update_region_items()

    
    def measure(self, plots: list[Plot] = None) -> None:
        if plots is None:
            plots = self._plots()
        
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
        if measure_type in ['Min', 'Max', 'AbsMax', 'Peaks']:
            peak_width = self._peak_half_width_spinbox.value()
            if peak_width > 0:
                def get_peak_index_range(mask, center_index):
                    start, stop = center_index, center_index + 1
                    for w in range(peak_width):
                        if center_index - w >= 0 and mask[center_index - w] and start == center_index - w + 1:
                            start = center_index - w
                        if center_index + w < len(mask) and mask[center_index + w] and stop == center_index + w:
                            stop = center_index + w + 1
                    return start, stop
        if measure_type == 'Peaks':
            peak_threshold = float(self._peak_threshold_edit.text())
            peak_type = self._peak_type_combobox.currentText()
        
        # measure in each plot
        for plot in plots:
            graphs = [item for item in plot.listDataItems() if isinstance(item, Graph)]
            if not graphs:
                continue

            # regions
            view: View = plot.getViewBox()
            regions: list[tuple[float, float]] = [item.getRegion() for item in view.allChildren() if isinstance(item, XAxisRegion) and item.isVisible()]

            # measure for each graph
            plot._tmp_measures: list[xr.Dataset] = []
            plot._tmp_measure_tree_items: list[XarrayTreeItem] = []

            for graph in graphs:
                try:
                    tree_item: XarrayTreeItem = graph._info['item']
                    data_coords: dict = graph._info['coords']
                except:
                    # graph not associated with data tree item
                    continue

                # x,y data
                try:
                    yarr = tree_item.node.ds.data_vars[tree_item.key]
                    xarr = tree_item.node.ds.coords[self.xdim]
                    xdata: np.ndarray = xarr.values

                    # generally yarr_coords should be exactly data_coords, but just in case...
                    yarr_coords = {dim: dim_coords for dim, dim_coords in data_coords.items() if dim in yarr.dims}
                    ydata: np.ndarray = np.squeeze(yarr.sel(yarr_coords).values)
                    if len(ydata.shape) == 0:
                        ydata = ydata.reshape((1,))
                except:
                    continue
                
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
                        pass # TODO: find peaks
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
                    attrs = self._selected_coords[dim].attrs.copy()
                    if dim == self.xdim:
                        measure_coords[dim] = xr.DataArray(dims=[dim], data=xmeasure, attrs=attrs)
                    else:
                        coord_values = np.array(coord).reshape((1,))
                        measure_coords[dim] = xr.DataArray(dims=[dim], data=coord_values, attrs=attrs)
                if self.xdim not in measure_coords:
                    attrs = self._selected_coords[self.xdim].attrs.copy()
                    measure_coords[self.xdim] = xr.DataArray(dims=[self.xdim], data=xmeasure, attrs=attrs)
                attrs = yarr.attrs.copy()
                measure = xr.Dataset(
                    data_vars={
                        tree_item.key: xr.DataArray(dims=dims, data=ymeasure.reshape(shape), attrs=attrs)
                    },
                    coords=measure_coords
                )

                # store measure for preview
                plot._tmp_measures.append(measure)
                plot._tmp_measure_tree_items.append(tree_item)
        
        # preview measurements
        for plot in plots:
            plot._tmp_measure_graphs = []
            for measure in plot._tmp_measures:
                var_name = list(measure.data_vars)[0]
                var = measure.data_vars[var_name]
                xdata = measure.coords[self.xdim].values
                ydata = np.squeeze(var.values)
                if len(ydata.shape) == 0:
                    ydata = ydata.reshape((1,))
                pen = pg.mkPen(color=(255, 0, 0), width=2)
                measure_graph = Graph(x=xdata, y=ydata, pen=pen, symbol='o', symbolSize=10, symbolPen=pen, symbolBrush=(255, 0, 0, 0))
                plot.addItem(measure_graph)
                plot._tmp_measure_graphs.append(measure_graph)
        
        # query user to keep measures
        answer = QMessageBox.question(self, 'Keep Measures?', 'Keep measurements?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            for plot in plots:
                for graph in plot._tmp_measure_graphs:
                    plot.removeItem(graph)
                    graph.deleteLater()
                plot._tmp_measure_graphs = []
                plot._tmp_measures = []
                plot._tmp_measure_tree_items = []
            return
        
        # add measures to data tree
        measure_tree_nodes = []
        merge_approved = None
        for plot in plots:
            for tree_item, measure in zip(plot._tmp_measure_tree_items, plot._tmp_measures):
                parent_node: DataTree = tree_item.node
                # append measure as child tree node
                if result_name in parent_node.children:
                    if merge_approved is None:
                        answer = QMessageBox.question(self, 'Merge Result?', 'Merge measures with existing datasets of same name?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                        merge_approved = (answer == QMessageBox.Yes)
                    if not merge_approved:
                        continue
                    # merge measurement with existing child dataset (use measurement for any overlap)
                    existing_child_node: DataTree = parent_node.children[result_name]
                    existing_child_node.ds = measure.combine_first(existing_child_node.to_dataset())
                    measure_tree_nodes.append(existing_child_node)
                else:
                    # append measurement as new child node
                    node = DataTree(name=result_name, data=measure, parent=parent_node)
                    measure_tree_nodes.append(node)
        
        # update data tree
        self.data = self.data

        # make sure newly added measure nodes are selected and expanded
        model: XarrayTreeModel = self._data_treeview.model()
        for item in model.root().depth_first():
            for node in measure_tree_nodes:
                if item.node is node and item.is_var():
                    index: QModelIndex = model.createIndex(item.sibling_index, 0, item)
                    self._data_treeview.selectionModel().select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
                    self._data_treeview.setExpanded(model.parent(index), True)

    def preview_curve_fit(self, plots: list[Plot] = None) -> None:
        self.curve_fit(plots=plots, eval_equation_only=True)
    
    def curve_fit(self, plots: list[Plot] = None, eval_equation_only: bool = False) -> None:
        if plots is None:
            plots = self._plots()
        
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

        # clear any temporary fits
        self._clear_tmp_curve_fits(plots)
        
        # fit in each plot
        for plot in plots:
            graphs = [item for item in plot.listDataItems() if isinstance(item, Graph)]
            if not graphs:
                continue

            # regions
            view: View = plot.getViewBox()
            regions: list[tuple[float, float]] = [item.getRegion() for item in view.allChildren() if isinstance(item, XAxisRegion) and item.isVisible()]

            # fit for each data item
            plot._tmp_fits: list[xr.Dataset] = []
            plot._tmp_fit_tree_items: list[XarrayTreeItem] = []

            for graph in graphs:
                try:
                    tree_item: XarrayTreeItem = graph._info['item']
                    data_coords: dict = graph._info['coords']
                except:
                    # graph not associated with data tree item
                    continue

                # x,y data
                try:
                    yarr = tree_item.node.ds.data_vars[tree_item.key]
                    xarr = tree_item.node.ds.coords[self.xdim]
                    xdata: np.ndarray = xarr.values

                    # generally yarr_coords should be exactly data_coords, but just in case...
                    yarr_coords = {dim: dim_coords for dim, dim_coords in data_coords.items() if dim in yarr.dims}
                    ydata: np.ndarray = np.squeeze(yarr.sel(yarr_coords).values)
                    if len(ydata.shape) == 0:
                        ydata = ydata.reshape((1,))
                except:
                    continue
                
                # dimensions
                dims = yarr.dims
                
                # region mask for fit optimization and/or evaluation
                if regions and (self._curve_fit_optimize_in_regions_checkbox.isChecked() or self._curve_fit_evaluate_in_regions_checkbox.isChecked()):
                    # mask for combined regions
                    regions_mask = np.full(xdata.shape, False)
                    for region in regions:
                        xmin, xmax = region
                        regions_mask[(xdata >= xmin) & (xdata <= xmax)] = True

                if regions and self._curve_fit_optimize_in_regions_checkbox.isChecked():
                    xinput = xdata[regions_mask]
                    yinput = ydata[regions_mask]
                else:
                    xinput = xdata
                    yinput = ydata

                if regions and self._curve_fit_evaluate_in_regions_checkbox.isChecked():
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
                    if eval_equation_only:
                        youtput = self._curve_fit_model.eval(params=params, x=xoutput)
                    else:
                        result = self._curve_fit_model.fit(yinput, params=params, x=xinput)
                        if DEBUG:
                            print(result.fit_report())
                        youtput = self._curve_fit_model.eval(params=result.params, x=xoutput)

                # fit as xarray dataset
                shape =[1] * len(dims)
                shape[dims.index(self.xdim)] = len(xoutput)
                fit_coords = {}
                for dim, coord in data_coords.items():
                    attrs = self._selected_coords[dim].attrs.copy()
                    if dim == self.xdim:
                        fit_coords[dim] = xr.DataArray(dims=[dim], data=xoutput, attrs=attrs)
                    else:
                        coord_values = np.array(coord).reshape((1,))
                        fit_coords[dim] = xr.DataArray(dims=[dim], data=coord_values, attrs=attrs)
                if self.xdim not in fit_coords:
                    attrs = self._selected_coords[self.xdim].attrs.copy()
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
            plot._tmp_fit_graphs = []
            for fit in plot._tmp_fits:
                var_name = list(fit.data_vars)[0]
                var = fit.data_vars[var_name]
                xdata = fit.coords[self.xdim].values
                ydata = np.squeeze(var.values)
                if len(ydata.shape) == 0:
                    ydata = ydata.reshape((1,))
                pen = pg.mkPen(color=(255, 0, 0), width=2)
                fit_graph = Graph(x=xdata, y=ydata, pen=pen)
                plot.addItem(fit_graph)
                plot._tmp_fit_graphs.append(fit_graph)
        
        # update equation params table with final fit params
        if fit_type == 'Equation':
            if eval_equation_only:
                return
            for row in range(self._equation_params_table.rowCount()):
                name = self._equation_params_table.item(row, 0).text()
                if result.params[name].vary:
                    value_item = self._equation_params_table.item(row, 1)
                    value_item.setText(f'{result.params[name].value:.6g}')
            self._equation_params_table.resizeColumnToContents(1)
        
        # query user to keep fits
        answer = QMessageBox.question(self, 'Keep Fits?', 'Keep fits?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            for plot in plots:
                if not self._equation_preview_checkbox.isChecked():
                    for graph in plot._tmp_fit_graphs:
                        plot.removeItem(graph)
                        graph.deleteLater()
                    plot._tmp_fit_graphs = []
                plot._tmp_fits = []
                plot._tmp_fit_tree_items = []
            return
        
        # add fits to data tree
        fit_tree_nodes = []
        merge_approved = None
        for plot in plots:
            for tree_item, fit in zip(plot._tmp_fit_tree_items, plot._tmp_fits):
                parent_node: DataTree = tree_item.node
                # append measure as child tree node
                if result_name in parent_node.children:
                    if merge_approved is None:
                        answer = QMessageBox.question(self, 'Merge Result?', 'Merge fits with existing datasets of same name?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                        merge_approved = (answer == QMessageBox.Yes)
                    if not merge_approved:
                        continue
                    # merge measurement with existing child dataset (use measurement for any overlap)
                    existing_child_node: DataTree = parent_node.children[result_name]
                    existing_child_node.ds = fit.combine_first(existing_child_node.to_dataset())
                    fit_tree_nodes.append(existing_child_node)
                else:
                    # append measurement as new child node
                    node = DataTree(name=result_name, data=fit, parent=parent_node)
                    fit_tree_nodes.append(node)
        
        # update data tree
        self.data = self.data

        # make sure newly added fit nodes are selected and expanded
        model: XarrayTreeModel = self._data_treeview.model()
        for item in model.root().depth_first():
            for node in fit_tree_nodes:
                if item.node is node and item.is_var():
                    index: QModelIndex = model.createIndex(item.sibling_index, 0, item)
                    self._data_treeview.selectionModel().select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
                    self._data_treeview.setExpanded(model.parent(index), True)
        
        # disable preview checkbox
        self._equation_preview_checkbox.setChecked(False)


def permutations(coords: dict) -> list[dict]:
    """ return list of all permutations of coords along each dimension

    Example:
        coords = {'subject': [0, 1], 'trial': [0, 1, 2]}
        permutations(coords) = [
            {'subject': 0, 'trial': 0},
            {'subject': 0, 'trial': 1},
            {'subject': 0, 'trial': 2},
            {'subject': 1, 'trial': 0},
            {'subject': 1, 'trial': 1},
            {'subject': 1, 'trial': 2},
        ]
    """
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


def import_golab_tevc(filepath: str = '', parent: QWidget = None) -> tuple[xr.Dataset, str]:
    if filepath == '':
        filepath, _filter = QFileDialog.getOpenFileName(parent, 'Import GoLab TEVC', '', 'GoLab TEVC (*.mat)')
        if filepath == '':
            return None
    matdict = sp.io.loadmat(filepath, simplify_cells=True)
    # print(matdict)
    current = matdict['current']
    current_units = matdict['current_units']
    if len(current_units) > 1:
        prefix = current_units[0]
        if prefix in metric_scale_factors:
            current *= metric_scale_factors[prefix]
            current_units = current_units[1:]
    time = np.arange(len(current)) * matdict['time_interval_sec']
    ds = xr.Dataset(
        data_vars={
            'current': (['time'], current, {'units': current_units}),
        },
        coords={
            'time': (['time'], time, {'units': 's'}),
        },
    )
    if 'events' in matdict and matdict['events']:
        ds.attrs['regions'] = []
        for event in matdict['events']:
            time = event['time_sec']
            text = event['text']
            ds.attrs['regions'].append({
                'region': {'time': [time, time]},
                'text': text,
            })
    if 'notes' in matdict:
        ds.attrs['notes'] = matdict['notes']
    return ds, filepath


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
            'series': ('series', np.arange(3)),
            'sweep': ('sweep', np.arange(10)),
            'time': ('time', np.arange(n) * 0.01, {'units': 's'}),
        },
    )

    baselined_ds = xr.Dataset(
        data_vars={
            'current': (['series', 'sweep', 'time'], np.random.rand(3, 10, n) * 1e-9, {'units': 'A'}),
        },
        coords={
            'series': ('series', np.arange(3)),
            'sweep': ('sweep', np.arange(10)),
            'time': ('time', np.arange(n) * 0.01, {'units': 's'}),
        },
    )

    scaled_ds = xr.Dataset(
        data_vars={
            'current': (['series', 'sweep', 'time'], np.random.rand(1, 2, n) * 1e-9, {'units': 'A'}),
        },
        coords={
            'series': ('series', [1]),
            'sweep': ('sweep', [5,8]),
            'time': ('time', np.arange(n) * 0.01, {'units': 's'}),
        },
    )
    
    root_node = DataTree()
    raw_node = DataTree(name='raw', data=raw_ds, parent=root_node)
    baselined_node = DataTree(name='baselined', data=baselined_ds, parent=raw_node)
    scaled_node = DataTree(name='scaled', data=scaled_ds, parent=baselined_node)

    ui.data = root_node

    app.exec()


if __name__ == '__main__':
    test_live()
