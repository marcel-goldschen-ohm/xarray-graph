""" PySide/PyQt widget for analyzing (x,y) data series in a Xarray dataset or a tree of datasets.

TODO:
- bug fix: non-numeric coordinate values not working in UI correctly.
- link all axes for each variable.
- color by selected coord(s)?
- spinboxes with user editable ranges and step sizes/precision?
- rename dims (implement in xarray_treeview?)
- missing coords: define all undefined coords by inheriting them (implement in xarray_tree)
- missing coords: remove all unneeded coords that can be inherited (implement in xarray_tree)
- array math: sanity checks needed
- array math: handle merging of results?
- array math: what to do with attrs for array math? at least keep same units.
- style: store user styling in metadata
- style: set style by trace, array, dataset, or variable name?
- style: store region styling in metadata
- style: set style for regions by label
- measure peaks: implement
- handle 2D images: implement
    - a global Y axis selector? overridden by local X-Y dims?
    - how to handle more generic multi-dimensional regions?
"""

from __future__ import annotations
import os
import numpy as np
import scipy as sp
import xarray as xr
from datatree import DataTree, open_datatree
import lmfit
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
from pyqt_ext.tree import *
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
DEFAULT_ICON_SIZE = 32
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

        # init data tree selection
        self._on_tree_selection_changed()
    
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
        self._data_treeview.setDataTree(data)

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
    
    def _set_xdim(self, xdim: str):
        self.xdim = xdim
    
    @property
    def regions(self) -> list[dict]:
        if 'regions' not in self.attrs:
            self.attrs['regions'] = []
        return self.attrs['regions']
    
    @regions.setter
    def regions(self, regions: list[dict]):
        self.attrs['regions'] = regions
    
    def is_tiling_enabled(self) -> bool:
        row_tile_dim = self._row_tile_combobox.currentText()
        col_tile_dim = self._col_tile_combobox.currentText()
        tiling_enabled: bool = row_tile_dim in self._iter_dims or col_tile_dim in self._iter_dims
        return tiling_enabled
    
    def clear(self) -> None:
        self.data = DataTree()
    
    def refresh(self) -> None:
        self.data = self.data
    
    def new_window(self) -> None:
        win = XarrayGraph()
        win.setWindowTitle(self.__class__.__name__)
        win.show()
    
    def load(self, filepath: str = '', format: str = 'zarr') -> None:
        if filepath == '':
            filepath = QFileDialog.getExistingDirectory(self, 'Open from Xarray data store...')
            if filepath == '':
                return None
        if format == 'zarr':
            self.data = open_datatree(filepath, 'zarr')
        else:
            raise ValueError("Invalid format '{format}'.")
        self._filepath = filepath
        path, filename = os.path.split(filepath)
        self.setWindowTitle(filename)
    
    def save(self, format: str = 'zarr') -> None:
        if hasattr(self, '_filepath'):
            self.save_as(self._filepath, format=format)
        else:
            self.save_as(format=format)
    
    def save_as(self, filepath: str = '', format: str = 'zarr') -> None:
        if filepath == '':
            filepath, _filter = QFileDialog.getSaveFileName(self, 'Save to data Zarr heirarchy...')
            if filepath == '':
                return None
        if format == 'zarr':
            self.data.to_zarr(filepath)
        else:
            raise ValueError("Invalid format '{format}'.")
        self._filepath = filepath
        path, filename = os.path.split(filepath)
        self.setWindowTitle(filename)
    
    def import_data(self, filepath: str = '', format: str = '') -> None:
        ds: xr.Dataset | None = None
        if format == 'pCLAMP':
            # TODO: implement
            QMessageBox.warning(self, 'Import pCLAMP', 'Importing pCLAMP files is not yet implemented.')
            return
        elif format == 'HEKA':
            ds, filepath = import_heka(filepath)
        elif format == 'GOLab TEVC':
            ds, filepath = import_golab_tevc(filepath)
        if ds is None:
            return
        self.data = ds
        self._filepath, ext = os.path.splitext(filepath)
        path, filename = os.path.split(filepath)
        self.setWindowTitle(filename)
    
    def autoscale_plots(self, plots: list[Plot] = None) -> None:
        if plots is None:
            plots = self._plots()
        
        if self.is_tiling_enabled():
            is_xlink = self._link_xaxis_checkbox.isChecked()
            is_ylink = self._link_yaxis_checkbox.isChecked()
            if is_xlink or is_ylink:
                # get combined bounds for all plots
                grid_shape = self._plot_grid.rowCount(), self._plot_grid.columnCount()
                xmin = np.empty(grid_shape)
                xmax = np.empty(grid_shape)
                ymin = {var_name: np.empty(grid_shape) for var_name in self._selected_var_names}
                ymax = {var_name: np.empty(grid_shape) for var_name in self._selected_var_names}
                xmin[:] = np.nan
                xmax[:] = np.nan
                for var_name in self._selected_var_names:
                    ymin[var_name][:] = np.nan
                    ymax[var_name][:] = np.nan
                for row in range(self._plot_grid.rowCount()):
                    for col in range(self._plot_grid.columnCount()):
                        plot = self._plot_grid.getItem(row, col)
                        if plot is not None and issubclass(type(plot), pg.PlotItem):
                            try:
                                xlim, ylim = plot.getViewBox().childrenBounds()
                                xmin[row, col] = xlim[0]
                                xmax[row, col] = xlim[1]
                                var_name = plot._info['data_vars'][0]
                                ymin[var_name][row, col] = ylim[0]
                                ymax[var_name][row, col] = ylim[1]
                            except:
                                pass
                xmin = np.nanmin(xmin)
                xmax = np.nanmax(xmax)
                print('xmin:', xmin, 'xmax:', xmax)
                for var_name in self._selected_var_names:
                    ymin[var_name] = np.nanmin(ymin[var_name])
                    ymax[var_name] = np.nanmax(ymax[var_name])
                    print(f'ymin[{var_name}]:', ymin[var_name], f'ymax[{var_name}]:', ymax[var_name])
                for plot in plots:
                    var_name = plot._info['data_vars'][0]
                    if is_xlink and is_ylink:
                        plot.setXRange(xmin, xmax)
                        plot.setYRange(ymin[var_name], ymax[var_name])
                    elif is_xlink:
                        plot.autoRange()
                        plot.setXRange(xmin, xmax)
                    elif is_ylink:
                        plot.autoRange()
                        plot.setYRange(ymin[var_name], ymax[var_name])
                return
        
        # no tiling or no axis linking
        for plot in plots:
            plot.autoRange()
            plot.enableAutoRange()

    def add_region(self, region: dict) -> None:
        self._region_treeview.addRegion(region)
    
    def resizeEvent(self, event: QResizeEvent) -> None:
        QWidget.resizeEvent(self, event)
        self._update_grid_layout()
 
    def toggle_console(self) -> None:
        self._console.setVisible(not self._console.isVisible())
        if (not self._console.isVisible()) or (len(self._selected_var_paths) + len(self._selected_node_paths) > 0):
            self._main_area.setVisible(True)
        elif self._console.isVisible():
            self._main_area.setVisible(False)
        if self._console.isVisible() and getattr(self, '_console_never_shown', True):
            self._console_never_shown = False
            self._console._append_plain_text('-----------------------------------------\n', before_prompt=True)
            self._console._append_plain_text('Variables:\n', before_prompt=True)
            self._console._append_plain_text('self      => This instance of XarrayGraph\n', before_prompt=True)
            self._console._append_plain_text('self.data => The Xarray DataTree\n', before_prompt=True)
            self._console._append_plain_text('-----------------------------------------\n', before_prompt=True)
    
    def _get_combined_coords(self, objects: list[DataTree | xr.Dataset | xr.DataArray] = None) -> xr.Dataset:
        # return the combined coords for the input objects (defaults to the entire tree)
        # There should NOT be any missing dimensions in the returned dataset. 
        # TODO: inherit missing coords
        if objects is None:
            # default to the entire tree
            objects = list(self.data.subtree)
        combined_coords: xr.Dataset = xr.Dataset()
        for obj in objects:
            obj_coords: xr.Dataset = xr.Dataset(coords=obj.coords)
            for dim, size in obj.sizes.items():
                if dim not in obj_coords:
                    # TODO: inherit missing coords if possible?
                    obj_coords[dim] = xr.DataArray(data=np.arange(size), dims=[dim])
            combined_coords = xr.merge([combined_coords, obj_coords], compat='no_conflicts')
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
        self._selected_paths: list[str] = [item.path for item in self._data_treeview.selectedItems()]
        self._selected_node_paths = [path for path in self._selected_paths if self._data_treemodel.dataTypeAtPath(path) == 'node']
        self._selected_var_paths = [path for path in self._selected_paths if self._data_treemodel.dataTypeAtPath(path) == 'var']
        self._selected_coord_paths = [path for path in self._selected_paths if self._data_treemodel.dataTypeAtPath(path) == 'coord']
        if DEBUG:
            print('_selected_paths:', [path for path in self._selected_paths])
            print('_selected_node_paths:', [path for path in self._selected_node_paths])
            print('_selected_var_paths:', [path for path in self._selected_var_paths])
            print('_selected_coord_paths:', [path for path in self._selected_coord_paths])
        
        # limit selection to variables with the xdim coordinate
        n_selected_vars = len(self._selected_var_paths)
        self._selected_var_paths = [path for path in self._selected_var_paths if self.xdim in self.data[path].dims]
        
        # update plot grid visibility based on selection
        self._plot_grid.setVisible(len(self._selected_var_paths) > 0)

        # ???
        if (not self._console.isVisible()) or (len(self._selected_var_paths) > 0):
            self._main_area.setVisible(True)
        elif self._console.isVisible():
            self._main_area.setVisible(False)
        
        # store the combined coords for all selected variables
        if self._selected_var_paths:
            self._selected_coords: xr.Dataset = self._get_combined_coords([self.data[path] for path in self._selected_var_paths])
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
        for path in self._selected_var_paths:
            var_name = path.rstrip('/').split('/')[-1]
            if var_name not in self._selected_var_names:
                self._selected_var_names.append(var_name)
        if DEBUG:
            print('_selected_var_names:', self._selected_var_names)

        # units for selected coords and vars
        self._selected_units = {}
        for dim in self.selected_coords:
            if 'units' in self.selected_coords[dim].attrs:
                self._selected_units[dim] = self.selected_coords[dim].attrs['units']
        for path in self._selected_var_paths:
            var = self.data[path]
            var_name = path.rstrip('/').split('/')[-1]
            if var_name not in self._selected_units:
                if 'units' in var.attrs:
                    self._selected_units[var_name] = var.attrs['units']
        if DEBUG:
            print('_selected_units:', self._selected_units)

        # flag plot grid for update
        self._plot_grid_needs_update = True

        # update index selection
        self._on_index_selection_changed()

        # update selected regions
        # self._on_selected_region_labels_changed()

        if not self._selected_var_paths and n_selected_vars > 0:
            QMessageBox.warning(self, f'Empty Selection', f'No variables selected with coordinate {self.xdim}')

    def _on_index_selection_changed(self) -> None:
        # selected coords for all non-x-axis dims (from toolbar spin boxes)
        self._visible_coords: xr.Dataset = xr.Dataset()
        for dim in self.selected_coords:
            if dim == self.xdim:
                continue
            if self._selected_sizes[dim] > 1:
                spinbox: MultiValueSpinBox = self._dim_iter_things[dim]['spinbox']
                values = spinbox.selectedValues()
                if np.issubdtype(values.dtype, np.integer) or np.issubdtype(values.dtype, np.floating):
                    indices = np.searchsorted(self.selected_coords[dim].values, values)
                else:
                    indices = np.array([np.where(self.selected_coords[dim].values == value)[0][0] for value in values], dtype=int)
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
            axis_tick_font.setPointSize(self._settings_axistick_fontsize_spinbox.value())
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
                    'row': row,
                    'col': col,
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
        axis_label_style = {'color': 'rgb(0, 0, 0)', 'font-size': f'{self._settings_axislabel_fontsize_spinbox.value()}pt'}
        tile_label_style = {'color': 'rgb(128, 128, 128)', 'font-size': f'{self._settings_axislabel_fontsize_spinbox.value()}pt'}
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
        # clear extra row labels
        for row in range(rowmax + 1, self._plot_grid.rowCount()):
            row_label = self._plot_grid.getItem(row, 0)
            if row_label is not None:
                self._plot_grid.removeItem(row_label)
                row_label.deleteLater()
    
    def _update_axes_tick_font(self) -> None:
        axis_tick_font = QFont()
        axis_tick_font.setPointSize(self._settings_axistick_fontsize_spinbox.value())
        for plot in self._plots():
            plot.getAxis('left').setTickFont(axis_tick_font)
            plot.getAxis('bottom').setTickFont(axis_tick_font)
    
    def _update_plot_items(self, plots: list[Plot] = None, item_types: list = None) -> None:
        if plots is None:
            plots = self._plots()
        default_line_width = self._settings_linewidth_spinbox.value()
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
                for path in self._selected_var_paths:
                    var_name = path.rstrip('/').split('/')[-1]
                    if 'data_vars' not in plot._info or var_name not in plot._info['data_vars']:
                        continue
                    var = self.data[path]
                    node_path = path[:path.rstrip('/').rfind('/')]
                    node = self.data[node_path]
                    try:
                        yarr = var
                        xarr = node.ds.coords[self.xdim]
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
                            'path': path,
                            'coords': coords,
                        }
                        
                        # graph style
                        graph.setGraphStyle(style, colorIndex=color_index)
                        if (len(ydata) == 1) or (np.sum(~np.isnan(ydata)) == 1):
                            if 'symbol' not in style:
                                graph.setSymbol('o')
                        
                        # graph name (limit to max_char characters)
                        max_char = 75
                        name = path + '[' + ','.join([f'{dim}={coords[dim]}' for dim in coords]) + ']'
                        if len(name) > max_char:
                            name = '...' + name[-(max_char-3):]
                        graph.setName(name)
                        # graph.setToolTip(name)  # !!! ONLY shows for top graph ???
                        
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
                
                # remove any invalidated measurement and curve fit preview refs and stop previewing
                plot._tmp_measure_graphs = []
                plot._tmp_curve_fit_graphs = []
                self._measure_preview_checkbox.setChecked(False)
                self._curve_fit_preview_checkbox.setChecked(False)
    
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
            
            # update measurement and curve fit previews
            self._update_measure_preview()
            self._update_curve_fit_preview()

    def _setup_ui(self) -> None:
        self._setup_ui_components()
        self._setup_menubar()
        self._setup_toolbars()

        # layout
        self._main_area = QWidget()
        self._main_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._main_area_layout = QVBoxLayout(self._main_area)
        self._main_area_layout.setContentsMargins(0, 0, 0, 0)
        self._main_area_layout.setSpacing(0)
        self._main_area_layout.addWidget(self._plot_grid)

        vsplitter = QSplitter(Qt.Orientation.Vertical)
        vsplitter.addWidget(self._main_area)
        vsplitter.addWidget(self._console)
        vsplitter.setHandleWidth(1)
        vsplitter.setCollapsible(0, False)
        vsplitter.setCollapsible(1, False)

        hsplitter = QSplitter(Qt.Orientation.Horizontal)
        hsplitter.addWidget(self._control_panel)
        hsplitter.addWidget(vsplitter)
        hsplitter.setStretchFactor(0, 0)
        hsplitter.setStretchFactor(1, 1)
        hsplitter.setHandleWidth(1)
        hsplitter.setCollapsible(0, False)
        hsplitter.setCollapsible(1, False)
        hsplitter.setSizes([250])

        self.setCentralWidget(hsplitter)

        # set initial state
        self._show_control_panel_at(0)
        self._console.hide()
    
    def _setup_ui_components(self) -> None:
        # left toolbar
        self._control_panel_toolbar = QToolBar()
        self._control_panel_toolbar.setOrientation(Qt.Orientation.Vertical)
        self._control_panel_toolbar.setStyleSheet("QToolBar{spacing:2px;}")
        self._control_panel_toolbar.setIconSize(QSize(DEFAULT_ICON_SIZE, DEFAULT_ICON_SIZE))
        self._control_panel_toolbar.setMovable(False)
        self._control_panel_toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)

        # top toolbar
        self._plot_grid_toolbar = QToolBar()
        self._plot_grid_toolbar.setStyleSheet("QToolBar{spacing:2px;}")
        self._plot_grid_toolbar.setIconSize(QSize(DEFAULT_ICON_SIZE, DEFAULT_ICON_SIZE))
        self._plot_grid_toolbar.setMovable(False)
        self._plot_grid_toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        
        # upper left button
        self._main_icon_button = QToolButton()
        self._main_icon_button.setIcon(qta.icon('fa5s.cubes', options=[{'opacity': 0.5}]))
        self._main_icon_button.pressed.connect(self.refresh)
        self._plot_grid_toolbar.addWidget(self._main_icon_button)

        # control panel
        self._control_panel = QStackedWidget()

        # plot grid
        self._plot_grid = PlotGrid()
        self._grid_rowlim = ()
        self._grid_collim = ()

        # xarray tree viewer
        self._data_treeviewer = XarrayTreeViewer()
        self._data_treeview = self._data_treeviewer.view()
        self._data_treeview.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._data_treeview.setAlternatingRowColors(False)
        self._data_treeview.setVariablesVisible(True)
        self._data_treeview.setCoordinatesVisible(False)
        self._data_treemodel: XarrayDndTreeModel = XarrayDndTreeModel(dt=self.data)
        self._data_treemodel.setDetailsColumnVisible(False)
        self._data_treeview.setModel(self._data_treemodel)
        self._data_treeview.selectionWasChanged.connect(self._on_tree_selection_changed)
        self._data_treeviewer.setSizes([100, 1])
        self._data_treemodel.dataChanged.connect(self._update_array_math_comboboxes)
        self._data_treeview.sigFinishedEditingAttrs.connect(self._on_tree_selection_changed)  # overkill, but needed to update units
        # TODO: respond to attr changes
        # attrs_model: KeyValueTreeModel = self._data_treeviewer._attrs_view.model()
        # attrs_model.sigValueChanged.connect(self._on_tree_selection_changed)  # overkill, but needed to update units

        # xdim combobox
        self._xdim_combobox = QComboBox()
        self._xdim_combobox.currentTextChanged.connect(self._set_xdim)

        # link axis checkboxes
        self._link_xaxis_checkbox = QCheckBox('Link column X axes')
        self._link_xaxis_checkbox.setChecked(True)
        self._link_xaxis_checkbox.stateChanged.connect(lambda: self._link_axes())

        self._link_yaxis_checkbox = QCheckBox('Link row Y axes')
        self._link_yaxis_checkbox.setChecked(True)
        self._link_yaxis_checkbox.stateChanged.connect(lambda: self._link_axes())

        # tile plot grid comboboxes
        self._row_tile_combobox = QComboBox()
        self._row_tile_combobox.addItems(['None'])
        self._row_tile_combobox.setCurrentText('None')
        self._row_tile_combobox.currentTextChanged.connect(self._update_plot_grid)

        self._col_tile_combobox = QComboBox()
        self._col_tile_combobox.addItems(['None'])
        self._col_tile_combobox.setCurrentText('None')
        self._col_tile_combobox.currentTextChanged.connect(self._update_plot_grid)

        # axis regions tree view
        root = AxisRegionTreeItem(self.regions)
        model = AxisRegionDndTreeModel(root)
        self._region_treeview = AxisRegionTreeView()
        self._region_treeview.setModel(model)
        self._region_treeview.sigRegionChangeFinished.connect(self._update_preview)

        # array math widgets
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

        # measurement widgets
        self._measure_type_combobox = QComboBox()
        self._measure_type_combobox.addItems(['Mean', 'Median'])
        self._measure_type_combobox.insertSeparator(self._measure_type_combobox.count())
        self._measure_type_combobox.addItems(['Min', 'Max', 'AbsMax'])
        # self._measure_type_combobox.insertSeparator(self._measure_type_combobox.count())
        # self._measure_type_combobox.addItems(['Peaks'])
        self._measure_type_combobox.insertSeparator(self._measure_type_combobox.count())
        self._measure_type_combobox.addItems(['Standard Deviation', 'Variance'])
        self._measure_type_combobox.currentIndexChanged.connect(self._on_measure_type_changed)

        self._measure_in_visible_regions_only_checkbox = QCheckBox('Measure within selected regions')
        self._measure_in_visible_regions_only_checkbox.setChecked(True)
        self._measure_in_visible_regions_only_checkbox.stateChanged.connect(lambda state: self._update_preview())

        self._measure_per_visible_region_checkbox = QCheckBox('Measure for each selected region')
        self._measure_per_visible_region_checkbox.setChecked(True)
        self._measure_in_visible_regions_only_checkbox.setEnabled(not self._measure_per_visible_region_checkbox.isChecked)
        self._measure_per_visible_region_checkbox.stateChanged.connect(lambda state: self._measure_in_visible_regions_only_checkbox.setEnabled(Qt.CheckState(state) == Qt.CheckState.Unchecked))
        self._measure_per_visible_region_checkbox.stateChanged.connect(lambda state: self._update_preview())

        self._measure_result_name_edit = QLineEdit()

        self._measure_preview_checkbox = QCheckBox('Preview')
        self._measure_preview_checkbox.setChecked(True)
        self._measure_preview_checkbox.stateChanged.connect(lambda state: self._update_preview())

        self._measure_button = QPushButton('Measure')
        self._measure_button.pressed.connect(self.measure)

        self._measure_keep_xdim_checkbox = QCheckBox('Keep X axis dimension')
        self._measure_keep_xdim_checkbox.setChecked(False)

        self._measure_peak_type_combobox = QComboBox()
        self._measure_peak_type_combobox.addItems(['Min', 'Max'])
        self._measure_peak_type_combobox.setCurrentText('Max')
        self._measure_peak_type_combobox.currentIndexChanged.connect(lambda index: self._update_preview())

        self._measure_peak_avg_half_width_spinbox = QSpinBox()
        self._measure_peak_avg_half_width_spinbox.setValue(0)
        self._measure_peak_avg_half_width_spinbox.valueChanged.connect(lambda value: self._update_preview())

        self._measure_peak_threshold_edit = QLineEdit('0')
        self._measure_peak_threshold_edit.editingFinished.connect(self._update_preview)

        # curve fit widgets
        self._curve_fit_type_combobox = QComboBox()
        self._curve_fit_type_combobox.addItems(['Mean', 'Median', 'Min', 'Max'])
        self._curve_fit_type_combobox.insertSeparator(self._curve_fit_type_combobox.count())
        self._curve_fit_type_combobox.addItems(['Line', 'Polynomial', 'Spline'])
        self._curve_fit_type_combobox.insertSeparator(self._curve_fit_type_combobox.count())
        self._curve_fit_type_combobox.addItems(['Equation'])
        self._curve_fit_type_combobox.setCurrentText('Equation')
        self._curve_fit_type_combobox.currentIndexChanged.connect(self._on_curve_fit_type_changed)

        self._curve_fit_optimize_in_regions_checkbox = QCheckBox('Optimize within selected regions')
        self._curve_fit_optimize_in_regions_checkbox.setChecked(True)
        self._curve_fit_optimize_in_regions_checkbox.stateChanged.connect(lambda state: self._update_preview())

        self._curve_fit_evaluate_in_regions_checkbox = QCheckBox('Evaluate within selected regions')
        self._curve_fit_evaluate_in_regions_checkbox.setChecked(False)
        self._curve_fit_evaluate_in_regions_checkbox.stateChanged.connect(lambda state: self._update_preview())

        self._curve_fit_result_name_edit = QLineEdit()

        self._curve_fit_preview_checkbox = QCheckBox('Preview')
        self._curve_fit_preview_checkbox.setChecked(True)
        self._curve_fit_preview_checkbox.stateChanged.connect(lambda state: self._update_preview())

        self._curve_fit_button = QPushButton('Fit')
        self._curve_fit_button.pressed.connect(self.curve_fit)

        self._curve_fit_polynomial_degree_spinbox = QSpinBox()
        self._curve_fit_polynomial_degree_spinbox.setValue(2)
        self._curve_fit_polynomial_degree_spinbox.valueChanged.connect(lambda value: self._update_preview())

        self._curve_fit_spline_segments_spinbox = QSpinBox()
        self._curve_fit_spline_segments_spinbox.setValue(10)
        self._curve_fit_spline_segments_spinbox.setMinimum(1)
        self._curve_fit_spline_segments_spinbox.valueChanged.connect(lambda value: self._update_preview())

        self._curve_fit_equation_edit = QLineEdit()
        self._curve_fit_equation_edit.setPlaceholderText('a * x + b')
        self._curve_fit_equation_edit.editingFinished.connect(self._on_curve_fit_equation_changed)

        self._curve_fit_equation_params = {}

        self._curve_fit_equation_params_table = QTableWidget(0, 5)
        self._curve_fit_equation_params_table.setHorizontalHeaderLabels(['Param', 'Value', 'Vary', 'Min', 'Max'])
        self._curve_fit_equation_params_table.verticalHeader().setVisible(False)
        self._curve_fit_equation_params_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._curve_fit_equation_params_table.model().dataChanged.connect(lambda model_index: self._update_preview())

        # function widgets
        self._function_type_combobox = QComboBox()
        self._function_type_combobox.addItems(['Gaussian Filter', 'Median Filter', 'Bessel Filter', 'Butterworth Filter', 'Chebyshev Filter', 'Elliptic Filter', 'Savitzky-Golay Filter', 'Kalman Filter'])
        # self._function_type_combobox.insertSeparator(self._function_type_combobox.count())
        self._function_type_combobox.setCurrentIndex(0)
        for i in range(4, self._function_type_combobox.count()):
            self._function_type_combobox.model().item(i).setEnabled(False)
        self._function_type_combobox.currentIndexChanged.connect(self._on_function_type_changed)

        self._function_evaluate_in_regions_checkbox = QCheckBox('Evaluate within selected regions')
        self._function_evaluate_in_regions_checkbox.setChecked(False)
        self._function_evaluate_in_regions_checkbox.stateChanged.connect(lambda state: self._update_preview())

        self._function_result_name_edit = QLineEdit()

        self._function_preview_checkbox = QCheckBox('Preview')
        self._function_preview_checkbox.setChecked(False)
        self._function_preview_checkbox.stateChanged.connect(lambda state: self._update_preview())

        self._function_apply_button = QPushButton('Apply')
        self._function_apply_button.pressed.connect(self.apply_function)

        self._function_gaussian_filter_sigma_edit = QLineEdit('1')
        self._function_gaussian_filter_sigma_edit.editingFinished.connect(self._update_preview)

        self._function_median_filter_window_edit = QLineEdit('5')
        self._function_median_filter_window_edit.editingFinished.connect(self._update_preview)

        self._function_filter_order_spinbox = QSpinBox()
        self._function_filter_order_spinbox.setMinimum(2)
        self._function_filter_order_spinbox.setMaximum(100)
        self._function_filter_order_spinbox.setSingleStep(2)
        self._function_filter_order_spinbox.setValue(8)
        self._function_filter_order_spinbox.valueChanged.connect(lambda value: self._update_preview())

        self._function_filter_bandtype_combobox = QComboBox()
        self._function_filter_bandtype_combobox.addItems(['lowpass', 'highpass', 'bandpass', 'bandstop'])
        self._function_filter_bandtype_combobox.setCurrentIndex(0)
        self._function_filter_bandtype_combobox.currentIndexChanged.connect(lambda index: self._update_preview())

        self._function_filter_cutoffs_edit = QLineEdit()
        self._function_filter_cutoffs_edit.setPlaceholderText('0.5 [, 0.7]')
        self._function_filter_cutoffs_edit.setToolTip('Comma-separated normalized cutoff frequencies in (0,1).\nAs in scipy.signal.butter.')
        self._function_filter_cutoffs_edit.editingFinished.connect(self._update_preview)

        # notes editor
        self._notes_edit = QTextEdit()
        self._notes_edit.setTabChangesFocus(False)
        self._notes_edit.setAcceptRichText(False)
        self._notes_edit.textChanged.connect(self._save_notes)

        # settings widgets
        self._settings_linewidth_spinbox = QSpinBox()
        self._settings_linewidth_spinbox.setValue(DEFAULT_LINE_WIDTH)
        self._settings_linewidth_spinbox.setMinimum(1)
        self._settings_linewidth_spinbox.valueChanged.connect(lambda: self._update_plot_items(item_types=[Graph]))

        self._settings_axislabel_fontsize_spinbox = QSpinBox()
        self._settings_axislabel_fontsize_spinbox.setValue(DEFAULT_AXIS_LABEL_FONT_SIZE)
        self._settings_axislabel_fontsize_spinbox.setMinimum(1)
        self._settings_axislabel_fontsize_spinbox.setSuffix('pt')
        self._settings_axislabel_fontsize_spinbox.valueChanged.connect(self._update_axes_labels)

        self._settings_axistick_fontsize_spinbox = QSpinBox()
        self._settings_axistick_fontsize_spinbox.setValue(DEFAULT_AXIS_TICK_FONT_SIZE)
        self._settings_axistick_fontsize_spinbox.setMinimum(1)
        self._settings_axistick_fontsize_spinbox.setSuffix('pt')
        self._settings_axistick_fontsize_spinbox.valueChanged.connect(self._update_axes_tick_font)

        self._settings_textitem_fontsize_spinbox = QSpinBox()
        self._settings_textitem_fontsize_spinbox.setValue(DEFAULT_TEXT_ITEM_FONT_SIZE)
        self._settings_textitem_fontsize_spinbox.setMinimum(1)
        self._settings_textitem_fontsize_spinbox.setSuffix('pt')
        self._settings_textitem_fontsize_spinbox.valueChanged.connect(self._update_item_font)

        self._settings_iconsize_spinbox = QSpinBox()
        self._settings_iconsize_spinbox.setValue(DEFAULT_ICON_SIZE)
        self._settings_iconsize_spinbox.setMinimum(16)
        self._settings_iconsize_spinbox.setMaximum(64)
        self._settings_iconsize_spinbox.setSingleStep(8)
        self._settings_iconsize_spinbox.valueChanged.connect(self._update_icon_size)
    
    def _setup_menubar(self) -> None:
        self._import_menu = QMenu(self.tr('&Import'))
        for data_type in ['pCLAMP', 'HEKA', 'GOLab TEVC']:
            self._import_menu.addAction(self.tr(f'Import {data_type}...'), lambda x=data_type: self.import_data(format=x))

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
    
    def _setup_toolbars(self) -> None:
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._plot_grid_toolbar)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self._control_panel_toolbar)
        self._setup_control_panel_toolbar()
        self._setup_plot_grid_toolbar()
    
    def _setup_control_panel_toolbar(self) -> None:
        # control panel toolbar
        # button order in toolbar reflects setup order
        self._setup_data_control_panel()
        self._setup_grid_control_panel()
        self._setup_region_control_panel()
        self._setup_math_control_panel()
        self._setup_measure_control_panel()
        self._setup_curve_fit_control_panel()
        self._setup_function_control_panel()
        self._setup_notes_control_panel()
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._control_panel_toolbar.addWidget(spacer)
        self._setup_settings_control_panel()
        self._setup_console()
    
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
    
    def _toggle_control_panel_at(self, index: int) -> None:
        actions = self._control_panel_toolbar.actions()
        widgets = [self._control_panel_toolbar.widgetForAction(action) for action in actions]
        buttons = [widget for widget in widgets if isinstance(widget, QToolButton) and (widget is not self._console_button)]
        show = buttons[index].isChecked()
        if show:
            self._control_panel.setCurrentIndex(index)
        self._control_panel.setVisible(show)
        for i, button in enumerate(buttons):
            if i != index:
                button.setChecked(False)
        self._update_preview()
    
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
        self._update_preview()
    
    def _setup_data_control_panel(self) -> None:
        button = QToolButton()
        button.setIcon(qta.icon('ph.eye', options=[{'opacity': 0.5}]))
        button.setCheckable(True)
        button.setChecked(False)
        button.setToolTip('Data browser')
        button.released.connect(lambda i=self._control_panel.count(): self._toggle_control_panel_at(i))
        self._control_panel_toolbar.addWidget(button)

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
        self._measure_control_panel_index = self._control_panel.count()
        button.released.connect(lambda i=self._control_panel.count(): self._toggle_control_panel_at(i))
        self._control_panel_toolbar.addWidget(button)

        # self._keep_xdim_group = QGroupBox()
        # form = QFormLayout(self._keep_xdim_group)
        # form.setContentsMargins(3, 3, 3, 3)
        # form.setSpacing(3)
        # form.setHorizontalSpacing(5)
        # form.addRow(self._measure_keep_xdim_checkbox)

        self._peak_width_group = QGroupBox()
        form = QFormLayout(self._peak_width_group)
        form.setContentsMargins(3, 3, 3, 3)
        form.setSpacing(3)
        form.setHorizontalSpacing(5)
        form.addRow('Average +/- samples', self._measure_peak_avg_half_width_spinbox)

        self._peak_group = QGroupBox()
        form = QFormLayout(self._peak_group)
        form.setContentsMargins(3, 3, 3, 3)
        form.setSpacing(3)
        form.setHorizontalSpacing(5)
        form.addRow('Peak type', self._measure_peak_type_combobox)
        form.addRow('Peak threshold', self._measure_peak_threshold_edit)

        self._measure_name_wrapper = QWidget()
        form = QFormLayout(self._measure_name_wrapper)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(0)
        form.setHorizontalSpacing(5)
        form.addRow('Result name', self._measure_result_name_edit)

        measure_group = QGroupBox('Measure')
        vbox = QVBoxLayout(measure_group)
        vbox.setContentsMargins(3, 3, 3, 3)
        vbox.setSpacing(5)
        vbox.addWidget(self._measure_type_combobox)
        # vbox.addWidget(self._keep_xdim_group)
        vbox.addWidget(self._peak_group)
        vbox.addWidget(self._peak_width_group)
        vbox.addWidget(self._measure_in_visible_regions_only_checkbox)
        vbox.addWidget(self._measure_per_visible_region_checkbox)
        vbox.addWidget(self._measure_name_wrapper)
        vbox.addWidget(self._measure_preview_checkbox)
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
        self._curve_fit_control_panel_index = self._control_panel.count()
        button.released.connect(lambda i=self._control_panel.count(): self._toggle_control_panel_at(i))
        self._control_panel_toolbar.addWidget(button)

        self._polynomial_group = QGroupBox()
        form = QFormLayout(self._polynomial_group)
        form.setContentsMargins(3, 3, 3, 3)
        form.setSpacing(3)
        form.setHorizontalSpacing(5)
        form.addRow('Polynomial degree', self._curve_fit_polynomial_degree_spinbox)

        self._spline_group = QGroupBox()
        form = QFormLayout(self._spline_group)
        form.setContentsMargins(3, 3, 3, 3)
        form.setSpacing(3)
        form.setHorizontalSpacing(5)
        form.addRow('Spline segments', self._curve_fit_spline_segments_spinbox)

        self._equation_group = QGroupBox()
        vbox = QVBoxLayout(self._equation_group)
        vbox.setContentsMargins(3, 3, 3, 3)
        vbox.setSpacing(3)
        vbox.addWidget(self._curve_fit_equation_edit)
        vbox.addWidget(self._curve_fit_equation_params_table)

        self._curve_fit_name_wrapper = QWidget()
        form = QFormLayout(self._curve_fit_name_wrapper)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(0)
        form.setHorizontalSpacing(5)
        form.addRow('Result name', self._curve_fit_result_name_edit)

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
        vbox.addWidget(self._curve_fit_preview_checkbox)
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
    
    def _setup_function_control_panel(self) -> None:
        button = QToolButton()
        button.setIcon(qta.icon('mdi.function', options=[{'opacity': 0.5}]))
        button.setCheckable(True)
        button.setChecked(False)
        button.setToolTip('Function')
        self._function_control_panel_index = self._control_panel.count()
        button.released.connect(lambda i=self._control_panel.count(): self._toggle_control_panel_at(i))
        self._control_panel_toolbar.addWidget(button)

        reult_name_wrapper = QWidget()
        form = QFormLayout(reult_name_wrapper)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(0)
        form.setHorizontalSpacing(5)
        form.addRow('Result name', self._function_result_name_edit)

        self._gauss_filter_group = QGroupBox()
        form = QFormLayout(self._gauss_filter_group)
        form.setContentsMargins(3, 3, 3, 3)
        form.setSpacing(3)
        form.setHorizontalSpacing(5)
        form.addRow('Sigma', self._function_gaussian_filter_sigma_edit)

        self._median_filter_group = QGroupBox()
        form = QFormLayout(self._median_filter_group)
        form.setContentsMargins(3, 3, 3, 3)
        form.setSpacing(3)
        form.setHorizontalSpacing(5)
        form.addRow('Window size (# samples)', self._function_median_filter_window_edit)

        self._band_filter_group = QGroupBox()
        form = QFormLayout(self._band_filter_group)
        form.setContentsMargins(3, 3, 3, 3)
        form.setSpacing(3)
        form.setHorizontalSpacing(5)
        form.addRow('Order', self._function_filter_order_spinbox)
        form.addRow('Bandtype', self._function_filter_bandtype_combobox)
        form.addRow('Cutoffs', self._function_filter_cutoffs_edit)

        func_group = QGroupBox('Function')
        vbox = QVBoxLayout(func_group)
        vbox.setContentsMargins(3, 3, 3, 3)
        vbox.setSpacing(5)
        vbox.addWidget(self._function_type_combobox)
        vbox.addWidget(self._gauss_filter_group)
        vbox.addWidget(self._median_filter_group)
        vbox.addWidget(self._band_filter_group)
        vbox.addWidget(self._function_evaluate_in_regions_checkbox)
        vbox.addWidget(reult_name_wrapper)
        vbox.addWidget(self._function_preview_checkbox)
        vbox.addWidget(self._function_apply_button)
        self._on_function_type_changed()

        panel = QWidget()
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(5, 5, 5, 5)
        vbox.setSpacing(20)
        vbox.addWidget(func_group)
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

        self._control_panel.addWidget(self._notes_edit)
    
    def _setup_settings_control_panel(self) -> None:
        button = QToolButton()
        button.setIcon(qta.icon('msc.settings-gear', options=[{'opacity': 0.5}]))
        button.setCheckable(True)
        button.setChecked(False)
        button.setToolTip('Measure')
        button.released.connect(lambda i=self._control_panel.count(): self._toggle_control_panel_at(i))
        self._control_panel_toolbar.addWidget(button)

        style_group = QGroupBox('Default plot style')
        form = QFormLayout(style_group)
        form.setContentsMargins(3, 3, 3, 3)
        form.setSpacing(3)
        form.setHorizontalSpacing(5)
        form.addRow('Line width', self._settings_linewidth_spinbox)

        font_group = QGroupBox('Font')
        form = QFormLayout(font_group)
        form.setContentsMargins(3, 3, 3, 3)
        form.setSpacing(3)
        form.setHorizontalSpacing(5)
        form.addRow('Axis label size', self._settings_axislabel_fontsize_spinbox)
        form.addRow('Axis tick label size', self._settings_axistick_fontsize_spinbox)
        form.addRow('Text item size', self._settings_textitem_fontsize_spinbox)

        misc_group = QGroupBox('Misc')
        form = QFormLayout(misc_group)
        form.setContentsMargins(3, 3, 3, 3)
        form.setSpacing(3)
        form.setHorizontalSpacing(5)
        form.addRow('Icon size', self._settings_iconsize_spinbox)

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
    
    def _setup_console(self) -> None:
        button = QToolButton()
        button.setIcon(qta.icon('msc.terminal', options=[{'opacity': 0.5}]))
        button.setCheckable(True)
        button.setChecked(False)
        button.setToolTip('Console')
        button.pressed.connect(self.toggle_console)
        self._console_button = button
        self._control_panel_toolbar.addWidget(button)

        from qtconsole.rich_jupyter_widget import RichJupyterWidget
        from qtconsole.inprocess import QtInProcessKernelManager

        self._console_kernel_manager = QtInProcessKernelManager()
        self._console_kernel_manager.start_kernel(show_banner=False)

        self._console_kernel_client = self._console_kernel_manager.client()
        self._console_kernel_client.start_channels()

        self._console = RichJupyterWidget()
        self._console.kernel_manager = self._console_kernel_manager
        self._console.kernel_client = self._console_kernel_client

        from qtpy.QtWidgets import QApplication
        app = QApplication.instance()
        app.aboutToQuit.connect(self._shutdown_console)

        self._console_kernel_manager.kernel.shell.push({'self': self})
    
    def _shutdown_console(self) -> None:
        self._console_kernel_client.stop_channels()
        self._console_kernel_manager.shutdown_kernel()
    
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
        # self._keep_xdim_group.setVisible(measure_type in ['Mean', 'Median', 'Standard Deviation', 'Variance'])
        self._peak_group.setVisible(measure_type == 'Peaks')
        self._peak_width_group.setVisible(measure_type in ['Min', 'Max', 'AbsMax', 'Peaks'])
        self._measure_result_name_edit.setPlaceholderText(measure_type)
        self._update_preview()
    
    def _on_curve_fit_type_changed(self) -> None:
        fit_type = self._curve_fit_type_combobox.currentText()
        self._polynomial_group.setVisible(fit_type == 'Polynomial')
        self._spline_group.setVisible(fit_type == 'Spline')
        self._equation_group.setVisible(fit_type == 'Equation')
        if self._equation_group.isVisible():
            self._curve_fit_equation_params_table.resizeColumnsToContents()
        self._curve_fit_result_name_edit.setPlaceholderText(fit_type)
        self._update_preview()
    
    def _on_curve_fit_equation_changed(self) -> None:
        equation = self._curve_fit_equation_edit.text().strip()
        if equation == '':
            self._curve_fit_model = None
            param_names = []
        else:
            self._curve_fit_model = lmfit.models.ExpressionModel(equation, independent_vars=['x'])
            param_names = self._curve_fit_model.param_names
            for name in param_names:
                if name not in self._curve_fit_equation_params:
                    self._curve_fit_equation_params[name] = {
                        'value': 0,
                        'vary': True,
                        'min': -np.inf,
                        'max': np.inf
                    }
            self._curve_fit_equation_params = {name: params for name, params in self._curve_fit_equation_params.items() if name in param_names}
        self._curve_fit_equation_params_table.clearContents()
        self._curve_fit_equation_params_table.setRowCount(len(param_names))
        for row, name in enumerate(param_names):
            value = self._curve_fit_equation_params[name]['value']
            vary = self._curve_fit_equation_params[name]['vary']
            value_min = self._curve_fit_equation_params[name]['min']
            value_max = self._curve_fit_equation_params[name]['max']

            name_item = QTableWidgetItem(name)
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            value_item = QTableWidgetItem(f'{value:.6g}')
            vary_item = QTableWidgetItem()
            vary_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            vary_item.setCheckState(Qt.CheckState.Checked if vary else Qt.CheckState.Unchecked)
            min_item = QTableWidgetItem(str(value_min))
            max_item = QTableWidgetItem(str(value_max))

            for col, item in enumerate([name_item, value_item, vary_item, min_item, max_item]):
                self._curve_fit_equation_params_table.setItem(row, col, item)

        self._curve_fit_equation_params_table.resizeColumnsToContents()
        self._update_preview()
    
    def _update_curve_fit_model(self) -> None:
        for row in range(self._curve_fit_equation_params_table.rowCount()):
            name = self._curve_fit_equation_params_table.item(row, 0).text()
            try:
                value = float(self._curve_fit_equation_params_table.item(row, 1).text())
            except:
                value = 0
            vary = self._curve_fit_equation_params_table.item(row, 2).checkState() == Qt.CheckState.Checked
            try:
                value_min = float(self._curve_fit_equation_params_table.item(row, 3).text())
            except:
                value_min = -np.inf
            try:
                value_max = float(self._curve_fit_equation_params_table.item(row, 4).text())
            except:
                value_max = np.inf
            self._curve_fit_equation_params[name] = {
                'value': value,
                'vary': vary,
                'min': value_min,
                'max': value_max
            }
            self._curve_fit_model.set_param_hint(name, **self._curve_fit_equation_params[name])
    
    def _on_function_type_changed(self) -> None:
        func_type = self._function_type_combobox.currentText()
        self._gauss_filter_group.setVisible(func_type == 'Gaussian Filter')
        self._median_filter_group.setVisible(func_type == 'Median Filter')
        self._band_filter_group.setVisible(func_type in ['Bessel Filter', 'Butterworth Filter'])
        self._function_result_name_edit.setPlaceholderText(func_type)
        self._update_preview()
    
    def _save_notes(self) -> None:
        notes = self._notes_edit.toPlainText()
        self.attrs['notes'] = notes
    
    def _load_notes(self, notes = None) -> None:
        if notes is None:
            notes = self.attrs.get('notes', '')
        self._notes_edit.setPlainText(notes)
    
    def _update_icon_size(self) -> None:
        size = self._settings_iconsize_spinbox.value()
        icon_size = QSize(size, size)
        for toolbar in [self._control_panel_toolbar, self._plot_grid_toolbar]:
            toolbar.setIconSize(icon_size)
            actions = toolbar.actions()
            widgets = [toolbar.widgetForAction(action) for action in actions]
            buttons = [widget for widget in widgets if isinstance(widget, QToolButton)]
            for button in buttons:
                button.setIconSize(icon_size)
    
    def _update_item_font(self):
        for plot in self._plots():
            view: View = plot.getViewBox()
            for item in view.allChildren():
                if isinstance(item, XAxisRegion):
                    item.setFontSize(self._settings_textitem_fontsize_spinbox.value())

    def _update_array_math_comboboxes(self) -> None:
        var_paths = [item.path for item in self._data_treeview.model().root().depth_first() if self._data_treeview.model().dataTypeAtPath(item.path) == 'var']
        for i in range(len(var_paths)):
            if len(var_paths[i]) > 100:
                var_paths[i] = '...' + var_paths[i][-97:]
        self._math_lhs_combobox.clear()
        self._math_rhs_combobox.clear()
        self._math_lhs_combobox.addItems(var_paths)
        self._math_rhs_combobox.addItems(var_paths)
    
    def eval_array_math(self) -> None:
        var_paths = [item.path for item in self._data_treeview.model().root().depth_first() if self._data_treeview.model().dataTypeAtPath(item.path) == 'var']
        lhs_path = var_paths[self._math_lhs_combobox.currentIndex()]
        rhs_path = var_paths[self._math_rhs_combobox.currentIndex()]
        lhs: xr.DataArray = self.data[lhs_path]
        rhs: xr.DataArray = self.data[rhs_path]
        
        op = self._math_operator_combobox.currentText()
        if op == '+':
            result: xr.DataArray = lhs + rhs
        elif op == '-':
            result: xr.DataArray = lhs - rhs
        elif op == '*':
            result: xr.DataArray = lhs * rhs
        elif op == '/':
            result: xr.DataArray = lhs / rhs
        
        # append result as child of lhs parent node
        result_name = self._math_result_name_edit.text().strip()
        if result_name == '':
            result_name = self._math_result_name_edit.placeholderText()
        result_node_path = lhs_path[:lhs_path.rfind('/')] + '/' + result_name
        result_ds = xr.Dataset(data_vars={result.name: result})
        result_tree = DataTree()
        result_tree[result_node_path] = DataTree(data=result_ds)
        self._add_data_tree(result_tree)
    
    # @Slot()
    # def on_axes_item_changed(self):
    #     item = self.sender()
    #     if isinstance(item, XAxisRegion):
    #         item._data['group'] = item.group()
    #         item._data['region'] = list(item.getRegion())
    #         item._data['text'] = item.text()
    #         # update all regions in case the altered region appears in multiple plots
    #         self.update_region_items()

    def measure(self, plots: list[Plot] = None, preview_only: bool = False) -> None:
        if plots is None:
            plots = self._plots()
        
        # result name
        result_name = self._measure_result_name_edit.text().strip()
        if not result_name:
            result_name = self._measure_result_name_edit.placeholderText()

        # operation
        op = {
            'plots': plots,
            'op_type': 'measure',
            'op_name': self._measure_type_combobox.currentText(),
            'in_regions': self._measure_in_visible_regions_only_checkbox.isChecked(),
            'per_region': self._measure_per_visible_region_checkbox.isChecked(),
            'result_name': result_name,
            'preview': True,
            'preview_only': preview_only,
        }
        if op['in_regions'] or op['per_region']:
            # this will be updated per plot
            op['regions'] = []
        op_name = op['op_name'].lower()
        if op_name in ['min', 'max', 'absmax', 'peaks']:
            op['peak_width'] = self._measure_peak_avg_half_width_spinbox.value()
        if op_name == 'peaks':
            op['peak_type'] = self._measure_peak_type_combobox.currentText()
            op['peak_threshold'] = float(self._measure_peak_threshold_edit.text())
        
        # do operation
        results: DataTree = self._apply_operation(op)

        if preview_only:
            return
        
        # query user to keep measures
        answer = QMessageBox.question(self, 'Keep Measures?', 'Keep measurements?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            # clear previews if not in preview mode
            if not self._measure_preview_checkbox.isChecked():
                self._clear_preview(plots)
            return
        
        # add results to data tree
        self._add_data_tree(results)
        
        # stop preview
        self._measure_preview_checkbox.setChecked(False)
        self._clear_preview(plots)
    
    def curve_fit(self, plots: list[Plot] = None, preview_only: bool = False) -> None:
        if plots is None:
            plots = self._plots()
        
        # result name
        result_name = self._curve_fit_result_name_edit.text().strip()
        if not result_name:
            result_name = self._curve_fit_result_name_edit.placeholderText()

        # operation
        op = {
            'plots': plots,
            'op_type': 'curve fit',
            'op_name': self._curve_fit_type_combobox.currentText(),
            'opt_in_regions': self._curve_fit_optimize_in_regions_checkbox.isChecked(),
            'eval_in_regions': self._curve_fit_evaluate_in_regions_checkbox.isChecked(),
            'result_name': result_name,
            'preview': True,
            'preview_only': preview_only,
        }
        if op['opt_in_regions'] or op['eval_in_regions']:
            # this will be updated per plot
            op['regions'] = []
        op_name = op['op_name'].lower()
        if op_name == 'polynomial':
            op['degree'] = self._curve_fit_polynomial_degree_spinbox.value()
        elif op_name == 'spline':
            op['segments'] = self._curve_fit_spline_segments_spinbox.value()
        elif op_name == 'equation':
            self._update_curve_fit_model()
            op['params'] = self._curve_fit_model.make_params()
        
        # do operation
        results: DataTree = self._apply_operation(op)

        if preview_only:
            return
        
        # query user to keep measures
        answer = QMessageBox.question(self, 'Keep Fits?', 'Keep fits?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            # clear previews if not in preview mode
            if not self._curve_fit_preview_checkbox.isChecked():
                self._clear_preview(plots)
            return
        
        # add results to data tree
        self._add_data_tree(results)
        
        # stop preview
        self._curve_fit_preview_checkbox.setChecked(False)
        self._clear_preview(plots)
    
    def apply_function(self, plots: list[Plot] = None, preview_only: bool = False) -> None:
        if plots is None:
            plots = self._plots()
        
        # result name
        result_name = self._function_result_name_edit.text().strip()
        if not result_name:
            result_name = self._function_result_name_edit.placeholderText()

        # operation
        op = {
            'plots': plots,
            'op_type': 'function',
            'op_name': self._function_type_combobox.currentText(),
            'eval_in_regions': self._function_evaluate_in_regions_checkbox.isChecked(),
            'result_name': result_name,
            'preview': True,
            'preview_only': preview_only,
        }
        if op['eval_in_regions']:
            # this will be updated per plot
            op['regions'] = []

        op_name = op['op_name'].lower()
        if op_name == 'gaussian filter':
            op['sigma'] = float(self._function_gaussian_filter_sigma_edit.text())
        elif op_name == 'median filter':
            op['window_size'] = int(self._function_median_filter_window_edit.text())
        elif op_name in ['bessel filter', 'butterworth filter']:
            op['order'] = self._function_filter_order_spinbox.value()
            op['bandtype'] = self._function_filter_bandtype_combobox.currentText()
            ok = True
            try:
                cutoffs = [float(cutoff) for cutoff in self._function_filter_cutoffs_edit.text().split(',')]
                if np.any(np.array(cutoffs) <= 0) or np.any(np.array(cutoffs) > 1):
                    ok = False
                if op['bandtype'] in ['lowpass', 'highpass']:
                    cutoffs = cutoffs[0]
                elif op['bandtype'] in ['bandpass', 'bandstop']:
                    cutoffs = [cutoffs[0], cutoffs[1]]
                op['cutoffs'] = cutoffs
            except (ValueError, IndexError):
                ok = False
            if not ok:
                QMessageBox.warning(self, 'Invalid Cutoffs', 'Please enter a comma-separated list of normalized cutoff frequencies in the range (0,1) as in scipy.signal.butter.', QMessageBox.StandardButton.Ok)
                return
        
        # do operation
        results: DataTree = self._apply_operation(op)

        if preview_only:
            return
        
        # query user to keep measures
        answer = QMessageBox.question(self, 'Keep Results?', 'Keep results?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            # clear previews if not in preview mode
            if not self._function_preview_checkbox.isChecked():
                self._clear_preview(plots)
            return
        
        # add results to data tree
        self._add_data_tree(results)
        
        # stop preview
        self._function_preview_checkbox.setChecked(False)
        self._clear_preview(plots)
    
    def _apply_operation(self, op: dict) -> DataTree:
        
        # plots in which to apply operation
        plots = op.get('plots', None)
        if plots is None:
            # default is all plots
            plots = self._plots()
        
        # clear any preview graphs from the plots
        self._clear_preview(plots)

        # results
        results: DataTree = DataTree()
        result_name = op['result_name']
        
        # apply operation in each plot
        for plot in plots:
            # apply operation to all visible graphs in this plot
            graphs = [item for item in plot.listDataItems() if isinstance(item, Graph)]
            if not graphs:
                continue

            if 'regions' in op:
                # visible x-axis regions
                view: View = plot.getViewBox()
                regions: list[tuple[float, float]] = [item.getRegion() for item in view.allChildren() if isinstance(item, XAxisRegion) and item.isVisible()]
                op['regions'] = regions

            # results DataTree for all graphs in this plot
            plot._tmp_results = DataTree()
            for graph in graphs:
                result: xr.Dataset = self._apply_operation_to_graph(op, graph)
                if result is None:
                    continue
                var_path: str = graph._info['path'].rstrip('/')
                pos = var_path.rfind('/')
                node_path: str = var_path[:pos]
                result_path = node_path + '/' + result_name
                try:
                    node = plot._tmp_results[result_path]
                    node.ds = node.to_dataset().combine_first(result)
                except:
                    plot._tmp_results[result_path] = DataTree(data=result)
            # add plot results to overall results
            for tmp_node in plot._tmp_results.subtree:
                if len(list(tmp_node.data_vars)):
                    try:
                        node = results[tmp_node.path]
                        node.ds = node.to_dataset().combine_first(tmp_node)
                    except:
                        results[tmp_node.path] = tmp_node
        
        # preview results
        if op.get('preview', False):
            for plot in plots:
                for result in plot._tmp_results.subtree:
                    for var_name, var in result.data_vars.items():
                        xdata = var.coords[self.xdim].values
                        ydata = var.values
                        xreps = list(ydata.shape)
                        xreps[list(var.dims).index(self.xdim)] = 1
                        xdata = np.tile(xdata, xreps)
                        xdata = np.squeeze(xdata)
                        ydata = np.squeeze(ydata)
                        if ydata.size == 0:
                            continue
                        if len(xdata.shape) == 0:
                            xdata = xdata.reshape((1,))
                        if len(ydata.shape) == 0:
                            ydata = ydata.reshape((1,))
                        pen = pg.mkPen(color=(255, 0, 0), width=2)
                        if (op['op_type'] == 'measure') or len(ydata) == 1:
                            result_graph = Graph(x=xdata, y=ydata, pen=pen, symbol='o', symbolSize=10, symbolPen=pen, symbolBrush=(255, 0, 0, 0))
                        else:
                            result_graph = Graph(x=xdata, y=ydata, pen=pen)
                        result_graph._info = {
                            'path': result.path + '/' + var_name,
                            'preview': True,
                        }
                        plot.addItem(result_graph)
        
        return results
    
    def _apply_operation_to_graph(self, op: dict, graph: Graph) -> xr.Dataset | None:
        
        var_path: str = graph._info['path'].rstrip('/')
        pos = var_path.rfind('/')
        node_path: str = var_path[:pos]
        var_name: str = var_path[pos+1:]
        node: DataTree = self.data[node_path]
        var: xr.DataArray = self.data[var_path]
        coords: dict = graph._info['coords']

        # x,y data
        yarr = var
        xarr = yarr.coords[self.xdim]
        xdata: np.ndarray = xarr.values
        # generally yarr_coords should be exactly data_coords, but just in case...
        yarr_coords = {dim: dim_coords for dim, dim_coords in coords.items() if dim in yarr.dims}
        ydata: np.ndarray = np.squeeze(yarr.sel(yarr_coords).values)
        if len(xdata.shape) == 0:
            xdata = xdata.reshape((1,))
        if len(ydata.shape) == 0:
            ydata = ydata.reshape((1,))
        
        # input/output data for operation
        xinput = xdata
        yinput = ydata
        xoutput = xinput
        if (xinput.size == 0) or (xoutput.size == 0):
            return None

        # apply operation to graph (x,y) data
        op_type = op['op_type'].lower()
        op_name = op['op_name'].lower()
        regions = op.get('regions', [])
        if op_type == 'measure':
            # mask for each measurement point
            region_masks = []
            if regions:
                if op['per_region']:
                    # one mask per region
                    for region in regions:
                        xmin, xmax = region
                        mask = (xinput >= xmin) & (xinput <= xmax)
                        region_masks.append(mask)
                elif op['in_regions']:
                    # mask for combined regions
                    mask = np.full(xinput.shape, False)
                    for region in regions:
                        xmin, xmax = region
                        mask[(xinput >= xmin) & (xinput <= xmax)] = True
                    region_masks = [mask]
            if not region_masks:
                # mask for everything
                mask = np.full(xinput.shape, True)
                region_masks = [mask]
                
            # measure in each mask
            xmeasure = []
            ymeasure = []
            for mask in region_masks:
                if not np.any(mask):
                    continue
                x = xinput[mask]
                y = yinput[mask]
                if (x.size == 0) or (y.size == 0):
                    continue

                if op_name == 'mean':
                    xmeasure.append(XarrayGraph.existing_median(x))
                    ymeasure.append(np.mean(y))
                elif op_name == 'median':
                    xmeasure.append(XarrayGraph.existing_median(x))
                    ymeasure.append(np.median(y))
                elif op_name == 'min':
                    i = np.argmin(y)
                    xmeasure.append(x[i])
                    if op['peak_width'] == 0:
                        ymeasure.append(y[i])
                    else:
                        center_index = np.where(mask)[0][i]
                        start, stop = XarrayGraph.get_peak_index_range(mask, center_index, op['peak_width'])
                        ymeasure.append(np.mean(ydata[start:stop]))
                elif op_name == 'max':
                    i = np.argmax(y)
                    xmeasure.append(x[i])
                    if op['peak_width'] == 0:
                        ymeasure.append(y[i])
                    else:
                        center_index = np.where(mask)[0][i]
                        start, stop = XarrayGraph.get_peak_index_range(mask, center_index, op['peak_width'])
                        ymeasure.append(np.mean(ydata[start:stop]))
                elif op_name == 'absmax':
                    i = np.argmax(np.abs(y))
                    xmeasure.append(x[i])
                    if op['peak_width'] == 0:
                        ymeasure.append(y[i])
                    else:
                        center_index = np.where(mask)[0][i]
                        start, stop = XarrayGraph.get_peak_index_range(mask, center_index, op['peak_width'])
                        ymeasure.append(np.mean(ydata[start:stop]))
                elif op_name == 'peaks':
                    pass # TODO: find peaks
                elif op_name == 'standard deviation':
                    xmeasure.append(XarrayGraph.existing_median(x))
                    ymeasure.append(np.std(y))
                elif op_name == 'variance':
                    xmeasure.append(XarrayGraph.existing_median(x))
                    ymeasure.append(np.var(y))
                
            if not ymeasure:
                return None
            
            # order measures by x
            xoutput = np.array(xmeasure)
            youtput = np.array(ymeasure)
            order = np.argsort(xoutput)
            xoutput = xoutput[order]
            youtput = youtput[order]
        
        elif op_type == 'curve fit':
            # regions mask?
            if regions:
                if op['opt_in_regions'] or op['eval_in_regions']:
                    # mask for combined regions
                    regions_mask = np.full(xinput.shape, False)
                    for region in regions:
                        xmin, xmax = region
                        regions_mask[(xinput >= xmin) & (xinput <= xmax)] = True
                    if op['opt_in_regions']:
                        xinput = xinput[regions_mask]
                        yinput = yinput[regions_mask]
                    if op['eval_in_regions']:
                        if op['opt_in_regions']:
                            xoutput = xinput
                        else:
                            xoutput = xinput[regions_mask]
            if (xinput.size == 0) or (xoutput.size == 0):
                return None
            
            if op_name == 'mean':
                youtput = np.full(len(xoutput), np.mean(yinput))
            elif op_name == 'median':
                youtput = np.full(len(xoutput), np.median(yinput))
            elif op_name == 'min':
                youtput = np.full(len(xoutput), np.min(yinput))
            elif op_name == 'max':
                youtput = np.full(len(xoutput), np.max(yinput))
            elif op_name == 'line':
                coef = np.polyfit(xinput, yinput, 1)
                youtput = np.polyval(coef, xoutput)
            elif op_name == 'polynomial':
                coef = np.polyfit(xinput, yinput, op['degree'])
                youtput = np.polyval(coef, xoutput)
            elif op_name == 'spline':
                segment_length = max(1, int(len(xinput) / op['segments']))
                knots = xinput[segment_length:-segment_length:segment_length]
                if len(knots) < 2:
                    knots = xinput[[1, -2]]
                knots, coef, degree = sp.interpolate.splrep(xinput, yinput, t=knots)
                youtput = sp.interpolate.splev(xoutput, (knots, coef, degree), der=0)
            elif op_name == 'equation':
                params = op['params']
                if op['preview_only']:
                    youtput = self._curve_fit_model.eval(params=params, x=xoutput)
                else:
                    result = self._curve_fit_model.fit(yinput, params=params, x=xinput)
                    if DEBUG:
                        print(result.fit_report())
                    youtput = self._curve_fit_model.eval(params=result.params, x=xoutput)
        
        elif op_type == 'function':
            # regions mask?
            if regions:
                if op['eval_in_regions']:
                    # mask for combined regions
                    regions_mask = np.full(xinput.shape, False)
                    for region in regions:
                        xmin, xmax = region
                        regions_mask[(xinput >= xmin) & (xinput <= xmax)] = True
                    xinput = xinput[regions_mask]
                    yinput = yinput[regions_mask]
                    xoutput = xinput
            if (xinput.size == 0) or (xoutput.size == 0):
                return None
            
            # apply function
            if op_name == 'gaussian filter':
                youtput = sp.ndimage.gaussian_filter1d(yinput, op['sigma'])
            elif op_name == 'median filter':
                youtput = sp.ndimage.median_filter(yinput, op['window_size'])
            elif op_name == 'bessel filter':
                b, a = sp.signal.bessel(op['order'] / 2, op['cutoffs'], op['bandtype'])
                youtput = sp.signal.filtfilt(b, a, yinput)
            elif op_name == 'butterworth filter':
                b, a = sp.signal.butter(op['order'] / 2, op['cutoffs'], op['bandtype'])
                youtput = sp.signal.filtfilt(b, a, yinput)
        
        else:
            raise Exception(f'Unknown operation: {op_type}: {op_name}')

        # convert result of operation to xarray Dataset
        dims = yarr.dims
        shape =[1] * len(dims)
        shape[dims.index(self.xdim)] = len(xoutput)
        result_coords = {}
        for dim, coord in coords.items():
            attrs = self._selected_coords[dim].attrs.copy()
            if dim == self.xdim:
                result_coords[dim] = xr.DataArray(dims=[dim], data=xoutput, attrs=attrs)
            else:
                coord_values = np.array(coord).reshape((1,))
                result_coords[dim] = xr.DataArray(dims=[dim], data=coord_values, attrs=attrs)
        if self.xdim not in result_coords:
            attrs = self._selected_coords[self.xdim].attrs.copy()
            result_coords[self.xdim] = xr.DataArray(dims=[self.xdim], data=xoutput, attrs=attrs)
        attrs = yarr.attrs.copy()
        result = xr.Dataset(
            data_vars={
                var_name: xr.DataArray(dims=dims, data=youtput.reshape(shape), attrs=attrs)
            },
            coords=result_coords
        )
        return result
    
    def _add_data_tree(self, dt: DataTree, overlap_mode: str = None) -> None:
        data = self.data
        for node in dt.subtree:
            try:
                existing_node = data[node.path]
                is_overlap = False
                for var_name in list(node.data_vars):
                    if var_name in list(existing_node.data_vars):
                        is_overlap = True
                        break
                if is_overlap:
                    if overlap_mode is None:
                        overlap_mode, ok = QInputDialog.getItem(self, 'Overlap with existing data', 'Handle overlaps:', ['Merge with existing', 'Overwrite existing', 'Keep both', 'Keep existing'], 0, False)
                        if not ok:
                            overlap_mode = None
                    if overlap_mode == 'Merge with existing':
                        existing_node.ds = existing_node.to_dataset().combine_first(node.to_dataset())
                    elif overlap_mode == 'Overwrite existing':
                        existing_node.ds = node.to_dataset()
                    elif overlap_mode == 'Keep both':
                        i = 2
                        while existing_node.path + f'_{i}' in data:
                            i += 1
                        unique_path = existing_node.path + f'_{i}'
                        data[unique_path] = node
                    elif overlap_mode == 'Keep existing':
                        pass
            except:
                data[node.path] = node
        
        # update data tree
        self.data = data

        # make sure newly added nodes are selected and expanded
        model: XarrayDndTreeModel = self._data_treeview.model()
        for node in dt.subtree:
            node_path: str = node.path
            for var_name in list(node.data_vars):
                var_path = node_path + '/' + var_name
                index: QModelIndex = model.indexFromPath(var_path)
                self._data_treeview.selectionModel().select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
                self._data_treeview.setExpanded(model.parent(index), True)
    
    def _update_preview(self, plots: list[Plot] = None) -> None:
        if plots is None:
            plots = self._plots()
        
        if self._measure_preview_checkbox.isChecked() and self._control_panel.isVisible() and (self._control_panel.currentIndex() == self._measure_control_panel_index):
            self.measure(plots, preview_only=True)
        elif self._curve_fit_preview_checkbox.isChecked() and self._control_panel.isVisible() and (self._control_panel.currentIndex() == self._curve_fit_control_panel_index):
            self.curve_fit(plots, preview_only=True)
        elif self._function_preview_checkbox.isChecked() and self._control_panel.isVisible() and (self._control_panel.currentIndex() == self._function_control_panel_index):
            self.apply_function(plots, preview_only=True)
        else:
            self._clear_preview(plots)
    
    def _clear_preview(self, plots: list[Plot] = None) -> None:
        if plots is None:
            plots = self._plots()
        for plot in plots:
            graphs = [item for item in plot.listDataItems() if isinstance(item, Graph)]
            for graph in graphs:
                if hasattr(graph, '_info') and graph._info.get('preview', False):
                    try:
                        plot.removeItem(graph)
                        graph.deleteLater()
                    except:
                        pass
    
    @staticmethod
    def existing_median(arr):
        # ensures picking an existing data point for the central value
        i = np.argpartition(arr, len(arr) // 2)[len(arr) // 2]
        return arr[i]

    @staticmethod
    def get_peak_index_range(mask, center_index, num_indices_either_side_of_peak = 0):
        """ get start and stop indices for peak of width peak_width centered at center_index within local mask region """
        start, stop = center_index, center_index + 1
        for w in range(1, num_indices_either_side_of_peak + 1):
            if center_index - w >= 0 and mask[center_index - w] and start == center_index - w + 1:
                start = center_index - w
            if center_index + w < len(mask) and mask[center_index + w] and stop == center_index + w:
                stop = center_index + w + 1
        return start, stop


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


def import_heka(filepath: str = '', parent: QWidget = None) -> tuple[xr.Dataset, str]:
    if filepath == '':
        filepath, _filter = QFileDialog.getOpenFileName(parent, 'Import HEKA', '', 'HEKA (*.dat)')
        if filepath == '':
            return None
    
    from xarray_graph.io import heka2xarray
    dt = heka2xarray(filepath)
    return dt, filepath


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

    other_ds = xr.Dataset(
        data_vars={
            'temperature': (['lat', 'lon'], np.random.rand(360, 360) * 15 + 15, {'units': 'C'}),
        },
        coords={
            'lat': ('lat', np.arange(360)),
            'lon': ('lon', np.arange(360)),
        },
    )
    
    dt = DataTree()
    raw_node = DataTree(name='raw', data=raw_ds, parent=dt)
    baselined_node = DataTree(name='baselined', data=baselined_ds, parent=raw_node)
    scaled_node = DataTree(name='scaled', data=scaled_ds, parent=baselined_node)
    other_node = DataTree(name='other', data=other_ds, parent=dt)

    # import pandas as pd
    # df = pd.read_csv('examples/ERPdata.csv')
    # subjects = np.array(df['subject'].unique(), dtype=int)
    # conditions = np.array(df['condition'].unique(), dtype=int)
    # df0 = df[df['subject'] == subjects[0]]
    # df00 = df0[df0['condition'] == conditions[0]]
    # time_ms = df00['time_ms'].values
    # channels = np.array(df.columns[2:-1].values, dtype=str)
    # n_subjects = len(subjects)
    # n_conditions = len(conditions)
    # n_channels = len(channels)
    # n_timepts = len(time_ms)
    # eeg = np.zeros((n_subjects, n_conditions, n_channels, n_timepts))
    # for i in range(n_subjects):
    #     subject = df[(df['subject'] == subjects[i])]
    #     for j in range(n_conditions):
    #         condition = subject[(subject['condition'] == conditions[j])]
    #         for k in range(n_channels):
    #             eeg[i, j, k] = condition[channels[k]].values * 1e-6  # uV -> V
    # ds = xr.Dataset(
    #     data_vars={
    #         'EEG': (['subject', 'condition', 'channel', 'time'], eeg, {'units': 'V'}),
    #     },
    #     coords={
    #         'subject': ('subject', subjects),
    #         'condition': ('condition', conditions),
    #         'channel': ('channel', channels),
    #         'time': ('time', time_ms * 1e-3, {'units': 's'}),
    #     },
    #     attrs={
    #         'source': 'https://www.kaggle.com/datasets/broach/button-tone-sz?select=ERPdata.csv',
    #     },
    # )
    # dt = DataTree(data=ds)
    # print(dt)

    ui.data = dt
    ui._data_treeview.expandAll()

    app.exec()


if __name__ == '__main__':
    test_live()
