""" PyQt widget for viewing/analyzing (x,y) slices of a Xarray DataTree.

TODO:
- move settings to popup dialog instead of in controls panel
- load multiple files as distinct branches
    - notes per branch?
- curve fitting
- baseline correction
- rundown correction
- measurements
- summary branches
- abf file support
- hide nonselected data_var filter checkboxes?
- plugin system?
"""

from __future__ import annotations
import os
from copy import deepcopy
from pathlib import Path
import datetime
import numpy as np
import xarray as xr
import pint
import zarr
import scipy as sp
import lmfit
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
from pyqt_ext.widgets import MultiValueSpinBox
import qtawesome as qta
from qtconsole.rich_jupyter_widget import RichJupyterWidget
from qtconsole.inprocess import QtInProcessKernelManager
import pyqtgraph as pg
import pyqt_ext.pyqtgraph_ext as pgx
from xarray_graph import XarrayTreeModel, XarrayDndTreeModel, XarrayTreeView, XarrayTreeViewer, AnnotationTreeModel, AnnotationDndTreeModel, AnnotationTreeView
from xarray_graph.io import *


# units
from pint import UnitRegistry
UREG = UnitRegistry()


# version info (stored in metadata in case needed later)
from importlib.metadata import version
XARRAY_GRAPH_VERSION = version('xarray-graph')


# Currently, color is handled by the widgets themselves.
# pg.setConfigOption('background', (240, 240, 240))
# pg.setConfigOption('foreground', (0, 0, 0))


DEBUG = 1
DEFAULT_ICON_SIZE = 32
DEFAULT_ICON_OPACITY = 0.5
DEFAULT_AXIS_LABEL_FONT_SIZE = 12
DEFAULT_AXIS_TICK_FONT_SIZE = 11
DEFAULT_TEXT_ITEM_FONT_SIZE = 10
DEFAULT_LINE_WIDTH = 1


filetype_extensions_map: dict[str, list[str]] = {
    'Zarr Directory': [''],
    'Zarr Zip': ['.zip'],
    'NetCDF': ['.nc'],
    'HDF5': ['.h5', '.hdf5'],
    'WinWCP': ['.wcp'],
    'Axon ABF': ['.abf'],
    'HEKA': ['.dat'],
    'LabChart MATLAB Conversion (GOLab)': ['.mat'],
}


class XarrayGraph(QMainWindow):
    """ PyQt widget for viewing/analyzing (x,y) slices of a Xarray DataTree. """

    def __init__(self, *args, **kwargs):
        QMainWindow.__init__(self, *args, **kwargs)

        self._datatree: xr.DataTree = xr.DataTree()
        self._xdim: str = None
        self._selected_regions: list[dict] = []

        self._init_ui()
    
    def __del__(self):
        self._shutdown_console()
    
    # public interface
    
    @property
    def datatree(self) -> xr.DataTree:
        return self._datatree
    
    @datatree.setter
    def datatree(self, datatree: xr.DataTree | xr.Dataset | xr.DataArray | np.ndarray | list[np.ndarray] | tuple[np.ndarray] | None) -> None:
        if DEBUG:
            print('datatree.setter()')
        
        root = xr.DataTree()
        if datatree is None:
            # empty root node
            pass
        elif isinstance(datatree, xr.DataTree):
            dt = datatree
            if dt.has_data:
                # root node should not have data
                name = dt.name or 'Data'
                root[name] = dt
            else:
                root = dt
        elif isinstance(datatree, xr.Dataset):
            ds = datatree
            name = ds.name or 'Data'
            root[name] = ds
        elif isinstance(datatree, xr.DataArray):
            da = datatree
            name = da.name or 'data'
            root['Data'] = xr.Dataset(data_vars={name: da})
        elif isinstance(datatree, np.ndarray):
            arr = datatree
            root['Data'] = xr.Dataset(data_vars={'data': arr})
        else:
            # assume list or tuple of two np.ndarrays (x, y)
            try:
                x, y = datatree
                root['Data'] = xr.Dataset(data_vars={'y': ('x', y)}, coords={'x': ('x', x)})
            except Exception:
                raise ValueError('XarrayGraph.datatree.setter: Invalid input.')

        self._datatree = root
        self.refresh()
    
    @property
    def xdim(self) -> str | None:
        return self._xdim
    
    @xdim.setter
    def xdim(self, xdim: str) -> None:
        if DEBUG:
            print('xdim.setter()')
        
        self._xdim = xdim
        self.refresh()
        self.autoscale()
    
    def windows(self) -> list[XarrayGraph]:
        windows = []
        for widget in qApp.topLevelWidgets():
            if isinstance(widget, XarrayGraph):
                windows.append(widget)
        return windows
    
    def newWindow(self) -> XarrayGraph:
        window = XarrayGraph()
        window.show()
        return window
    
    def load(self, filepath: str | os.PathLike = None, filetype: str = None) -> None:
        if filepath is None:
            if filetype == 'Zarr Directory':
                filepath = QFileDialog.getExistingDirectory(self, 'Open Zarr Directory')
            else:
                filepath, _ = QFileDialog.getOpenFileName(self, 'Open File')
            if not filepath:
                return
        if isinstance(filepath, str):
            filepath = Path(filepath)
        if not filepath.exists():
            QMessageBox.warning(self, 'File Not Found', f'File not found: {filepath}')
            return
        
        # get filetype
        if filepath.is_dir():
            filetype = 'Zarr Directory'
        elif filetype is None:
            # get filetype from file extension
            extension_filetype_map = {
                ext: filetype
                for filetype, extensions in filetype_extensions_map.items()
                for ext in extensions
            }
            filetype = extension_filetype_map.get(filepath.suffix, None)
        
        # read datatree from filesystem
        dt: xr.DataTree = None
        if filetype == 'Zarr Directory':
            with zarr.storage.LocalStore(filepath, mode='r') as store:
                dt = xr.open_datatree(store, engine='zarr')
        elif filetype == 'Zarr Zip':
            with zarr.storage.ZipStore(filepath, mode='r') as store:
                dt = xr.open_datatree(store, engine='zarr')
        elif filetype == 'NetCDF':
            dt: xr.DataTree = xr.open_datatree(filepath)#, engine='netcdf4')
        elif filetype == 'HDF5':
            dt: xr.DataTree = xr.open_datatree(filepath)#, engine='h5netcdf')
        elif filetype == 'WinWCP':
            dt: xr.DataTree = read_winwcp(filepath)
        elif filetype == 'Axon ABF':
            QMessageBox.warning(self, 'Under Construction', f'{filetype} support is in the works.')
            return
        elif filetype == 'HEKA':
            dt: xr.DataTree = read_heka(filepath)
        elif filetype == 'LabChart MATLAB Conversion (GOLab)':
            dt: xr.DataTree = read_adicht_mat(filepath)
        else:
            try:
                # see if xarray can open the file
                dt = xr.open_datatree(filepath)
            except:
                QMessageBox.warning(self, 'Invalid File Type', f'Opening {filetype} format files is not supported.')
                return
        
        if dt is None:
            QMessageBox.warning(self, 'Invalid File', f'Unable to open file: {filepath}')
            return
        
        # preprocess datatree
        dt = inherit_missing_data_vars(dt)
        restore_ordered_data_vars(dt)

        # root node name
        if dt.has_data:
            dt.name = filepath.stem
        
        self.datatree = dt
        # self.datatree.attrs['filepath'] = str(filepath)
        # self.setWindowTitle(filepath.name)
        self._filepath = filepath

        if not self._datatree_view.selectedPaths():
            try:
                nodes = list(self.datatree.children.values())[0].leaves
                if nodes:
                    paths = [node.path for node in nodes]
                    self._datatree_view.setSelectedPaths(paths)
            except:
                pass
    
    def save(self) -> None:
        # filepath = self.datatree.attrs.get('filepath', None)
        filepath = getattr(self, '_filepath', None)
        self.saveAs(filepath)
    
    def saveAs(self, filepath: str | os.PathLike = None, filetype: str = None) -> None:
        if filepath is None:
            filepath, _ = QFileDialog.getSaveFileName(self, 'Save File')
            if not filepath:
                return
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
                    for filetype, extensions in filetype_extensions_map.items()
                    for ext in extensions
                }
                filetype = extension_filetype_map.get(filepath.suffix, None)
        
        # ensure proper file extension for new files
        if not filepath.exists() and (filetype != 'Zarr Directory'):
            ext = filetype_extensions_map.get(filetype, [None])[0]
            if ext is not None:
                filepath = filepath.with_suffix(ext)

        # prepare datatree for storage
        dt = remove_inherited_data_vars(self.datatree)
        store_ordered_data_vars(dt)
        dt.attrs['xarray-graph-version'] = XARRAY_GRAPH_VERSION
        if 'filepath' in dt.attrs:
            del dt.attrs['filepath']

        # write datatree to filesystem
        if filetype == 'Zarr Directory':
            with zarr.storage.LocalStore(filepath, mode='w') as store:
                dt.to_zarr(store)
        elif filetype == 'Zarr Zip':
            if filepath.suffix != '.zip':
                filepath = filepath.with_suffix('.zip')
            with zarr.storage.ZipStore(filepath, mode='w') as store:
                dt.to_zarr(store)
        elif filetype == 'NetCDF':
            QMessageBox.warning(self, 'Under Construction', f'{filetype} support is in the works.')
            return
        elif filetype == 'HDF5':
            QMessageBox.warning(self, 'Under Construction', f'{filetype} support is in the works.')
            return
        else:
            QMessageBox.warning(self, 'Invalid File Type', f'Saving to {filetype} format is not supported.')
            return
        
        # self.datatree.attrs['filepath'] = str(filepath)
        # self.setWindowTitle(filepath.name)
        self._filepath = filepath
    
    def refresh(self) -> None:
        if DEBUG:
            print('refresh()')
        
        all_nodes = list(self.datatree.subtree)
        self._datatree_combined_coords: xr.Dataset = self._get_union_of_all_coords(all_nodes)
        self._datatree_combined_var_names = self._get_union_of_all_data_var_names(all_nodes)
        
        self._update_data_vars_filter_actions()
        # self._update_saved_selections_filter_list()
        self._update_datatree_view()
        self._update_control_panel_view()
        self._console.setVisible(self._toggle_console_action.isChecked())
        self._on_tree_selection_changed()
    
    def replot(self) -> None:
        self._update_graphs(item_types=[pgx.Graph])
    
    def tileDimension(self, dim: str, orientation: Qt.Orientation | None) -> None:
        if DEBUG:
            print(f'tileDimension({dim}, {orientation})')

        if getattr(self, '_vertical_tile_dimension', None) == dim:
            self._vertical_tile_dimension = None
        if getattr(self, '_horizontal_tile_dimension', None) == dim:
            self._horizontal_tile_dimension = None
        
        if orientation == Qt.Orientation.Vertical:
            self._vertical_tile_dimension = dim
        elif orientation == Qt.Orientation.Horizontal:
            self._horizontal_tile_dimension = dim
        
        if orientation is not None:
            selected_coords = self._selected_vars_visible_coords[dim]
            if selected_coords.size == 1:
                max_default_tile_size = 10
                dim_coords = self._selected_vars_combined_coords[dim]
                if dim_coords.size <= max_default_tile_size:
                    selected_coords = dim_coords
                else:
                    i = np.where(dim_coords == selected_coords[0])[0][0]
                    stop = min(i + max_default_tile_size, dim_coords.size)
                    start = max(0, stop - max_default_tile_size)
                    selected_coords = dim_coords[start:stop]
                self._dim_iter_things[dim]['widget'].setSelectedCoords(selected_coords.values)
        
        self.refresh()
    
    def autoscale(self) -> None:
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
                        xlinked_range.append(xlim)
                        if xlinked_view not in xlinked_views:
                            xlinked_views.append(xlinked_view)
                            xlim, ylim = xlinked_view.childrenBounds()
                            xlinked_range.append(xlim)
                    if ylinked_view is not None:
                        xlim, ylim = view.childrenBounds()
                        ylinked_range.append(ylim)
                        if ylinked_view not in ylinked_views:
                            ylinked_views.append(ylinked_view)
                            xlim, ylim = ylinked_view.childrenBounds()
                            ylinked_range.append(ylim)
            
            if ylinked_views:
                ymin = np.min(ylinked_range)
                ymax = np.max(ylinked_range)
                for view in ylinked_views:
                    view.setYRange(ymin, ymax)
        
        if xlinked_views:
            xmin = np.min(xlinked_range)
            xmax = np.max(xlinked_range)
            for view in xlinked_views:
                view.setXRange(xmin, xmax)
    
    def sizeHint(self) -> QSize:
        return QSize(1000, 800)
    
    # private methods
    
    def _get_union_of_all_data_var_names(self, objects: list[xr.DataTree | xr.Dataset | xr.DataArray]) -> list[str]:
        names = []
        for obj in objects:
            if isinstance(obj, xr.DataTree) or isinstance(obj, xr.Dataset):
                for name in obj.data_vars:
                    if name not in names:
                        names.append(name)
            elif isinstance(obj, xr.DataArray):
                name = obj.name
                if name not in names:
                    names.append(name)
        return names
    
    def _get_union_of_all_units(self, objects: list[xr.DataTree | xr.Dataset | xr.DataArray]) -> dict[str, str]:
        units = {}
        for obj in objects:
            if isinstance(obj, xr.DataTree) or isinstance(obj, xr.Dataset):
                for name, data_var in obj.data_vars.items():
                    if name not in units:
                        if 'units' in data_var.attrs:
                            units[name] = data_var.attrs['units']
            elif isinstance(obj, xr.DataArray):
                name = obj.name
                if name not in units:
                    if 'units' in obj.attrs:
                        units[name] = obj.attrs['units']
            for dim, coord in obj.coords.items():
                if dim not in units:
                    if 'units' in coord.attrs:
                        units[dim] = coord.attrs['units']
        return units
    
    def _get_union_of_all_coords(self, objects: list[xr.DataTree | xr.Dataset | xr.DataArray]) -> xr.Dataset:
        coords = []
        for i, obj in enumerate(objects):
            if isinstance(obj, xr.DataTree):
                obj = obj.to_dataset()
            coords.append(obj.reset_coords(drop=True).coords)
        
        return xr.merge(coords, compat='no_conflicts')
    
    def _get_ordered_dims(self, objects: list[xr.DataTree | xr.Dataset | xr.DataArray]) -> list[str]:
        dims = []
        for obj in objects:
            if isinstance(obj, xr.DataTree) or isinstance(obj, xr.Dataset):
                arrays = obj.data_vars.values()
            elif isinstance(obj, xr.DataArray):
                arrays = [obj]
            
            for array in arrays:
                # xr.DataArray dims are always ordered???
                for dim in array.dims:
                    if dim not in dims:
                        dims.append(dim)
        return dims
    
    def _get_current_data_var_filter(self) -> dict[str, bool]:
        menu = self._filter_menu
        widget_actions = menu.actions()
        before = widget_actions.index(self._before_filter_data_vars_action)
        after = widget_actions.index(self._after_filter_data_vars_action)
        widget_actions = widget_actions[before+1:after]

        data_var_filter = {}
        for action in widget_actions:
            checkbox = action.defaultWidget()
            data_var_filter[checkbox.text()] = checkbox.isChecked()
        return data_var_filter
    
    def _get_current_iter_coords(self) -> dict[str, np.ndarray]:
        coords = {}
        for dim in self._dim_iter_things:
            if self._dim_iter_things[dim]['active']:
                widget: DimIterWidget = self._dim_iter_things[dim]['widget']
                coords[dim] = widget.selectedCoords()
        return coords
    
    def _get_current_tile_dims(self) -> tuple[str | None, str | None, np.ndarray | None, np.ndarray | None]:
        vdim = getattr(self, '_vertical_tile_dimension', None)
        hdim = getattr(self, '_horizontal_tile_dimension', None)
        if (vdim not in self._selected_vars_visible_coords) or (self._selected_vars_visible_coords[vdim].size <= 1):
            vdim = None
        if (hdim not in self._selected_vars_visible_coords) or (self._selected_vars_visible_coords[hdim].size <= 1):
            hdim = None
        vcoords = None if vdim is None else self._selected_vars_visible_coords[vdim].values
        hcoords = None if hdim is None else self._selected_vars_visible_coords[hdim].values
        return vdim, hdim, vcoords, hcoords
    
    def _get_current_region_selection(self) -> list[dict]:
        if not self._view_ROIs_action.isChecked():
            return []
        return [region for region in self._selected_regions if self.xdim in region['position']]
    
    def _get_ROI_path(self, region: dict) -> str | None:
        for node in self.datatree.subtree:
            if region in node.attrs.get('regions', []):
                return node.path
    
    # def _get_annotation_plots(self, annotation: dict, parent: xr.DataTree | xr.DataArray) -> list[pgx.Plot]:
    #     pos = annotation.get('position', {})
    #     dims = tuple(pos.keys())
    #     try:
    #         xdim = dims[0]
    #     except IndexError:
    #         xdim = None
    #     if xdim != self.xdim:
    #         return []
    #     try:
    #         ydim = dims[1]
    #     except IndexError:
    #         ydim = None
        
    #     coords = annotation.get('coords', {})
    #     if coords:
    #         coords_ds = self._datatree_combined_coords.sel(coords)
        
    #     plots = []
    #     for plot in self._plots.flatten().tolist():
    #         if ydim is not None:
    #             if ydim not in plot._info['data_vars']:
    #                 continue
    #         if isinstance(parent, xr.DataArray):
    #             if parent.name not in plot._info['data_vars']:
    #                 continue
    #         if coords:
    #             a, b = xr.align([coords_ds, plot._info['coords']])
    #             if np.array(a.sizes.values()).prod() == 0:
    #                 continue
    #         plots.append(plot)
    #     return plots
    
    # def _get_regions_overlapping_current_selection(self, regions: list[dict]) -> list[dict]:
    #     overlapping_regions = []
    #     for region in regions:
    #         try:
    #             lims = region['position'][self.xdim]
    #         except:
    #             continue
    #         lims: dict[str, tuple] = region['region']
    #         if self.xdim not in region['position']:
    #             continue
    #         ok = True
    #         for dim in lims:
    #             if dim == self.xdim:
    #                 continue
    #             if dim in self._selected_vars_visible_coords:
    #                 coords = self._selected_vars_visible_coords[dim].values
    #                 if np.issubdtype(coords.dtype, np.number):
    #                     is_overlap = (coords >= lims[dim][0]) & (coords <= lims[dim][1])
    #                     if not np.any(is_overlap):
    #                         ok = False
    #                         break
    #                 else:
    #                     # string coord values
    #                     found = False
    #                     for lim in lims[dim]:
    #                         if lim in coords:
    #                             found = True
    #                             break
    #                     if not found:
    #                         ok = False
    #                         break
    #         if ok:
    #             overlapping_regions.append(region)
    #     return overlapping_regions
    
    def _is_ROIs_visible(self) -> bool:
        return self._view_ROIs_action.isChecked()
    
    def _set_ROIs_visible(self, is_visible: bool) -> None:
        self._view_ROIs_action.setChecked(is_visible)
        self._show_ROIs_checkbox.blockSignals(True)
        self._show_ROIs_checkbox.setChecked(is_visible)
        self._show_ROIs_checkbox.blockSignals(False)
        self._update_ROIs()
    
    def _is_masked_visible(self) -> bool:
        return self._view_masked_action.isChecked()
    
    def _set_masked_visible(self, is_visible: bool) -> None:
        self._view_masked_action.setChecked(is_visible)
        self._include_masked_checkbox.blockSignals(True)
        self._include_masked_checkbox.setChecked(is_visible)
        self._include_masked_checkbox.blockSignals(False)
        self.refresh()
    
    def _on_tree_selection_changed(self) -> None:
        if DEBUG:
            print('_on_tree_selection_changed()')
        
        var_filter = self._get_current_data_var_filter()
        
        # selected tree paths
        self._selected_paths: list[str] = self._datatree_view.selectedPaths()
        self._selected_node_paths: list[str] = []
        self._selected_var_paths: list[str] = []
        self._selected_coord_paths: list[str] = []
        for path in self._selected_paths:
            if self._datatree_model.dataTypeAtPath(path) == 'node':
                self._selected_node_paths.append(path)
                for var_name in self.datatree[path].data_vars:
                    if var_filter.get(var_name, True):
                        var_path = path + '/' + var_name
                        if var_path not in self._selected_var_paths:
                            self._selected_var_paths.append(var_path)
            elif self._datatree_model.dataTypeAtPath(path) == 'var':
                if path not in self._selected_var_paths:
                    if len(self._selected_paths) == 1:
                        # ignore the var filter if only a single data_var is selected
                        self._selected_var_paths.append(path)
                    else:
                        var_name = path.rstrip('/').split('/')[-1]
                        if var_filter.get(var_name, True):
                            self._selected_var_paths.append(path)
            elif self._datatree_model.dataTypeAtPath(path) == 'coord':
                if path not in self._selected_coord_paths:
                    self._selected_coord_paths.append(path)
        
        # map selected var paths to their respective branch root paths
        self._selected_branch_root_paths: list[str] = []
        self._selected_var_path_to_branch_root_path_map: dict[str: str] = {}
        for path in self._selected_var_paths:
            parent_node_path = '/'.join(path.rstrip('/').split('/')[:-1])
            parent_node = self.datatree[parent_node_path]
            branch_root = find_branch_root(parent_node)
            branch_root_path = branch_root.path
            self._selected_var_path_to_branch_root_path_map[path] = branch_root_path
            if branch_root_path not in self._selected_branch_root_paths:
                self._selected_branch_root_paths.append(branch_root_path)
        
        # try and ensure valid xdim
        ordered_dims = self._get_ordered_dims([self.datatree[path] for path in self._selected_var_paths])
        if self.xdim not in ordered_dims:
            if ordered_dims:
                self._xdim = ordered_dims[-1]
        
        # limit selection to variables with the xdim coordinate
        self._selected_var_paths = [path for path in self._selected_var_paths if self.xdim in self.datatree[path].dims]

        # combined coords, data_var names, and units for selection
        selected_data_vars = [self.datatree[path] for path in self._selected_var_paths]
        self._selected_vars_combined_coords: xr.Dataset = self._get_union_of_all_coords(selected_data_vars)
        self._selected_var_names = self._get_union_of_all_data_var_names(selected_data_vars)
        self._selected_var_units = self._get_union_of_all_units(selected_data_vars)
        
        # update toolbar dim iter widgets for selected variables
        self._update_dim_iter_things()

        # # flag plot grid for update
        # self._plot_grid_needs_update = True

        # update index selection (this will update the plot grids)
        self._on_index_selection_changed()

        # # update selected regions
        # # self._on_selected_region_labels_changed()

        # update ROI tree
        self._update_ROItree_view()

    def _on_index_selection_changed(self) -> None:
        if DEBUG:
            print('_on_index_selection_changed()')
        
        # get coords for current slice of selected variables
        iter_coords = self._get_current_iter_coords()
        if iter_coords:
            self._selected_vars_visible_coords: xr.Dataset = self._selected_vars_combined_coords.sel(iter_coords)#, method='nearest')
        else:
            self._selected_vars_visible_coords: xr.Dataset = self._selected_vars_combined_coords
        
        # update plot grids
        self._update_plot_grids()
    
    def _on_plot_item_changed(self, item: QGraphicsObject) -> None:
        data = getattr(item, '_ref', None)
        if data is None:
            return
        
        self._update_data_from_plot_item(item, data)

        if isinstance(item, pgx.XAxisRegion):
            for plot in self._plots.flatten().tolist():
                like_items = [item_ for item_ in plot.vb.allChildren() if type(item_) == type(item)]
                for like_item in like_items:
                    if getattr(like_item, '_ref', None) is data:
                        if like_item is not item:
                            self._update_plot_item_from_data(like_item, data)
                        break
    
    @Slot(QGraphicsObject)
    def _on_item_added_to_plot(self, item: QGraphicsObject) -> None:
        view: pgx.View = self.sender()
        # plot: pgx.Plot = view.parentItem()

        if isinstance(item, pgx.XAxisRegion):
            region = {
                'type': 'vregion',
                'position': {self.xdim: item.getRegion()},
                # 'xdim': self.xdim,
                # 'xdata': item.getRegion(),
            }

            # add region to datatree
            if 'ROIs' not in self.datatree.attrs:
                self.datatree.attrs['ROIs'] = []
            self.datatree.attrs['ROIs'].append(region)
            
            # remove initial region item (we'll add it to all plots with appropriate signals/slots during update later)
            view.removeItem(item)
            QTimer.singleShot(10, lambda item=item: item.deleteLater())  # slight delay avoids segfault!?

            # # if not previously showing ROIs, deselect all other ROIs before showing the new ROI
            if not self._is_ROIs_visible():
                self._ROItree_view.clearSelection()
            
            # draw one region at a time
            self._stop_drawing_items()
            
            # update ROI tree and ensure new ROI is selected
            self._update_ROItree_view()
            selectedROIs = self._ROItree_view.selectedAnnotations()
            if region not in selectedROIs:
                selectedROIs.append(region)
            self._ROItree_view.setSelectedAnnotations(selectedROIs)

            # update plots
            self._set_ROIs_visible(True)  # calls self._update_ROIs()

        if isinstance(item, pg.RectROI):
            # select points in ROI
            # TODO...
            
            # remove ROI
            view.removeItem(item)
            QTimer.singleShot(10, lambda item=item: item.deleteLater())
    
    def _update_datatree_view(self) -> None:
        self._datatree_view.setDataTree(self.datatree)
    
    def _update_ROItree_view(self) -> None:
        ROI_paths = ['/'] + self._selected_branch_root_paths
        # ROI_paths = ['/'] + self._selected_paths
        selected_ROIs = self._ROItree_view.selectedAnnotations()
        self._ROItree_view.storeState()
        self._ROItree_view.setDataTree(self.datatree, paths=ROI_paths, key='ROIs')
        self._ROItree_view.restoreState()
        self._ROItree_view.setSelectedAnnotations(selected_ROIs)
    
    def _update_control_panel_view(self) -> None:
        if self._datatree_view_action.isChecked():
            self._control_panels_stack.setCurrentWidget(self._datatree_viewer)
        elif self._notes_view_action.isChecked():
            self._control_panels_stack.setCurrentWidget(self._notes_edit)
        elif self._settings_panel_action.isChecked():
            self._control_panels_stack.setCurrentWidget(self._settings_panel)
        else:
            self._control_panels_stack.setVisible(False)
            return
        self._control_panels_stack.setVisible(True)
    
    def _update_dim_iter_things(self) -> None:
        if DEBUG:
            print('_update_dim_iter_things()')

        coords: xr.Dataset = self._selected_vars_combined_coords
        ordered_dims = self._get_ordered_dims([self.datatree[path] for path in self._selected_var_paths])

        # remove dim iter actions from toolbar
        # items are not deleted, so the current iteration state will be restored if the dim is reselected again
        for dim in self._dim_iter_things:
            # block spinbox signals so that _on_index_selection_changed is not called
            # if the spinbox had focus and loses it here
            if 'widget' in self._dim_iter_things[dim]:
                widget: DimIterWidget = self._dim_iter_things[dim]['widget']
                widget._spinbox.blockSignals(True)
            for value in self._dim_iter_things[dim].values():
                if isinstance(value, QAction):
                    self._top_toolbar.removeAction(value)
            self._dim_iter_things[dim]['active'] = False
        
        # update or create dim iter things and insert actions into toolbar
        iter_dims = [dim for dim in ordered_dims if (dim != self.xdim) and (coords.sizes[dim] > 1)]
        for dim in iter_dims:
            if dim not in self._dim_iter_things:
                widget = DimIterWidget()
                widget.setDim(dim)
                widget.setParentXarrayGraph(self)
                self._dim_iter_things[dim] = {'widget': widget}
            
            widget = self._dim_iter_things[dim]['widget']
            widget.setCoords(coords[dim].values)
            widget.updateTileButton()

            if 'separatorAction' in self._dim_iter_things[dim]:
                action = self._dim_iter_things[dim]['separatorAction']
                self._top_toolbar.insertAction(self._after_dim_iter_things_separator_action, action)
            else:
                action = self._top_toolbar.insertSeparator(self._after_dim_iter_things_separator_action)
                self._dim_iter_things[dim]['separatorAction'] = action

            if 'widgetAction' in self._dim_iter_things[dim]:
                action = self._dim_iter_things[dim]['widgetAction']
                self._top_toolbar.insertAction(self._after_dim_iter_things_separator_action, action)
            else:
                action = self._top_toolbar.insertWidget(self._after_dim_iter_things_separator_action, widget)
                self._dim_iter_things[dim]['widgetAction'] = action
            
            self._dim_iter_things[dim]['active'] = True
            widget._spinbox.blockSignals(False)
        
        self._before_dim_iter_things_spacer_action.setVisible(len(iter_dims) == 0)
    
    def _update_data_vars_filter_actions(self) -> None:
        menu = self._filter_menu
        widget_actions = menu.actions()
        before = widget_actions.index(self._before_filter_data_vars_action)
        after = widget_actions.index(self._after_filter_data_vars_action)
        widget_actions = widget_actions[before+1:after]

        checkboxes = [action.defaultWidget() for action in widget_actions]
        var_names = [checkbox.text() for checkbox in checkboxes]

        # remove old actions
        for action in widget_actions:
            menu.removeAction(action)
        
        # add new actions
        for var_name in self._datatree_combined_var_names:
            if var_name in var_names:
                i = var_names.index(var_name)
                menu.insertAction(self._after_filter_data_vars_action, widget_actions[i])
                # menu.addAction(widget_actions[i])
            else:
                checkbox = QCheckBox(var_name)
                checkbox.setChecked(True)
                checkbox.toggled.connect(lambda checked: self.refresh())
                action = QWidgetAction(self)
                action.setDefaultWidget(checkbox)
                menu.insertAction(self._after_filter_data_vars_action, action)
                # menu.addAction(action)
    
    # def _update_saved_selections_filter_list(self) -> None:
    #     paths = []
    #     for node in self.datatree.subtree:
    #         for region in node.attrs.get('regions', []):
    #             label = region.get('text', '').split('\n')[0].strip()
    #             if not label:
    #                 dim, lim = list(region['position'].items())[0]
    #                 lb, ub = lim
    #                 label = f'{dim}: ({lb: 0.2e}, {ub: 0.2e})'
    #             paths.append('/'.join([node.path, region.get('group', 'Ungrouped'), label]))
    #     self._saved_selections_list_widget.clear()
    #     self._saved_selections_list_widget.addItems(paths)
    #     print(paths)
    
    def _update_plot_grids(self) -> None:
        # one plot grid per selected variable
        n_vars = len(self._selected_var_names)
        while self._data_var_views_splitter.count() < n_vars:
            grid = pgx.PlotGrid()
            grid.setHasRegularLayout(True)
            self._data_var_views_splitter.addWidget(grid)
        while self._data_var_views_splitter.count() > n_vars:
            index = self._data_var_views_splitter.count() - 1
            widget = self._data_var_views_splitter.widget(index)
            widget.setParent(None)
            widget.deleteLater()
        
        # grid tiling
        vdim, hdim, vcoords, hcoords = self._get_current_tile_dims()
        n_grid_rows, n_grid_cols = 1, 1
        if vdim is not None:
            n_grid_rows = vcoords.size
        if hdim is not None:
            n_grid_cols = hcoords.size

        # tile grids and store plots in array (if needed)
        if not hasattr(self, '_plots') or self._plots.shape != (n_vars, n_grid_rows, n_grid_cols):
            self._plots = np.empty((n_vars, n_grid_rows, n_grid_cols), dtype=object)
            self._plot_grids = [self._data_var_views_splitter.widget(i) for i in range(n_vars)]
            for i, grid in enumerate(self._plot_grids):
                var_name = self._selected_var_names[i]
                if grid.rowCount() != n_grid_rows or grid.columnCount() != n_grid_cols:
                    grid.setGrid(n_grid_rows, n_grid_cols)
                for row in range(grid.rowCount()):
                    for col in range(grid.columnCount()):
                        plot = grid.getItem(row, col)
                        self._plots[i, row, col] = plot
                if i == n_vars - 1:
                    grid.setAxisLabelAndTickVisibility(xlabel_rows=[-1], xtick_rows=[-1], ylabel_columns=[0], ytick_columns=[0])
                else:
                    grid.setAxisLabelAndTickVisibility(xlabel_rows=[], xtick_rows=[-1], ylabel_columns=[0], ytick_columns=[0])
                QTimer.singleShot(250, lambda grid=grid: grid.applyRegularLayout())
        
        self._update_plot_info()
        self._update_axes_labels()
        self._update_axes_tick_font()
        self._update_axes_linking()
        self._update_graphs()
        self._update_ROIs()
    
    def _update_plot_info(self) -> None:
        vdim, hdim, vcoords, hcoords = self._get_current_tile_dims()
        n_vars, n_grid_rows, n_grid_cols = self._plots.shape
        for i in range(n_vars):
            var_name = self._selected_var_names[i]
            yunits = self._selected_var_units.get(var_name, None)
            var_coords = self._selected_vars_visible_coords.copy(deep=False)  # TODO: may include extra coords? get rid of these?
            
            for row in range(n_grid_rows):
                if vdim is not None:
                    row_coords = var_coords.sel({vdim: vcoords[row]})
                else:
                    row_coords = var_coords
                
                for col in range(n_grid_cols):
                    if hdim is not None:
                        col_coords = row_coords.sel({hdim: hcoords[col]})
                    else:
                        col_coords = row_coords
                    col_coords_dict = {dim: arr.values for dim, arr in col_coords.coords.items() if dim != self.xdim}
                    
                    plot = self._plots[i, row, col]
                    plot._info = {
                        'data_vars': [var_name],
                        'grid_row': row,
                        'grid_col': col,
                        'coords': col_coords,
                        'non_xdim_coord_permutations': permutations(col_coords_dict),
                    }
    
    def _update_axes_labels(self) -> None:
        xunits = self._selected_var_units.get(self.xdim, None)
        axis_label_style = {'color': 'rgb(0, 0, 0)', 'font-size': f'{self._axislabel_fontsize_spinbox.value()}pt'}

        vdim, hdim, vcoords, hcoords = self._get_current_tile_dims()
        n_vars, n_grid_rows, n_grid_cols = self._plots.shape
        for i in range(n_vars):
            var_name = self._selected_var_names[i]
            yunits = self._selected_var_units.get(var_name, None)
            for row in range(n_grid_rows):
                for col in range(n_grid_cols):
                    plot = self._plots[i, row, col]
                    if (i == n_vars - 1) and (row == n_grid_rows - 1):
                        label = self.xdim
                        if (hdim is not None) and (n_grid_cols > 1):
                            # label += f'[{hdim}={hcoords[col]}]'
                            label += f'[{hcoords[col]}]'
                        plot.setLabel('bottom', text=label, units=xunits, **axis_label_style)
                    if col == 0:
                        label = var_name
                        if (vdim is not None) and (n_grid_rows > 1):
                            # label += f'[{vdim}={vcoords[row]}]'
                            label += f'[{vcoords[row]}]'
                        plot.setLabel('left', text=label, units=yunits, **axis_label_style)
    
    def _update_axes_tick_font(self) -> None:
        axis_tick_font = QFont()
        axis_tick_font.setPointSize(self._axistick_fontsize_spinbox.value())
        
        for plot in self._plots.flatten().tolist():
            plot.getAxis('left').setTickFont(axis_tick_font)
            plot.getAxis('bottom').setTickFont(axis_tick_font)
    
    def _update_axes_linking(self) -> None:
        n_vars, n_grid_rows, n_grid_cols = self._plots.shape
        for i in range(n_vars):
            for row in range(n_grid_rows):
                for col in range(n_grid_cols):
                    plot = self._plots[i, row, col]
                    if (i != 0) or (row != 0) or (col != 0):
                        plot.setXLink(self._plots[0, 0, 0])
                    if (row > 0) or (col > 0):
                        plot.setYLink(self._plots[i, 0, 0])
    
    def _update_graphs(self, plots: list[pgx.Plot] = None) -> None:
        if plots is None:
            plots = self._plots.flatten().tolist()
        
        default_line_width = self._linewidth_spinbox.value()
        
        for plot in plots:
            view: pgx.View = plot.getViewBox()

            # categorical (string) xdim values?
            xticks = None  # will use default ticks
            xdata = self._selected_vars_combined_coords[self.xdim].values
            if not np.issubdtype(xdata.dtype, np.number):
                xtick_values = np.arange(len(xdata))
                xtick_labels = xdata  # str xdim values
                xticks = [list(zip(xtick_values, xtick_labels))]
            plot.getAxis('bottom').setTicks(xticks)
            
            # existing graphs in plot
            graphs = [item for item in plot.listDataItems() if isinstance(item, pgx.Graph)]
            
            # update graphs in plot
            count = 0
            color_index = 0
            for path in self._selected_var_paths:
                var_name = path.rstrip('/').split('/')[-1]
                if var_name not in plot._info['data_vars']:
                    continue
                data_var = self.datatree[path]
                if self.xdim not in data_var.coords:
                    continue
                
                non_xdim_coord_permutations = plot._info['non_xdim_coord_permutations']
                if len(non_xdim_coord_permutations) == 0:
                    non_xdim_coord_permutations = [{}]
                for coords in non_xdim_coord_permutations:
                    if not coords:
                        data_var_slice = data_var
                    else:
                        coords = {dim: values for dim, values in coords.items() if dim in data_var.coords}
                        if not coords:
                            continue
                        data_var_slice = data_var.sel(coords)
                    xdata = data_var_slice.coords[self.xdim].values
                    ydata = data_var_slice.values

                    # categorical xdim values?
                    if not np.issubdtype(xdata.dtype, np.number):
                        intersect, xdata_indices, xtick_labels_indices = np.intersect1d(xdata, xtick_labels, assume_unique=True, return_indices=True)
                        xdata = np.sort(xtick_labels_indices)
                    
                    # graph data in plot
                    if len(graphs) > count:
                        # update existing data in plot
                        graph = graphs[count]
                        graph.setData(x=xdata, y=ydata)
                    else:
                        # add new data to plot
                        graph = pgx.Graph(x=xdata, y=ydata)
                        plot.addItem(graph)
                        graphs.append(graph)
                        # graph.sigNameChanged.connect(lambda: self._update_plot_items(item_types=[Graph]))
                    
                    # graph properties
                    graph._xlabel = self.xdim
                    graph._xunits = data_var_slice.coords[self.xdim].attrs.get('units', None)
                    graph._ylabel = var_name
                    graph._yunits = data_var_slice.attrs.get('units', None)
                    graph._info = {
                        'path': path,
                        'coords': coords,
                    }

                    # graph style
                    style: pgx.GraphStyle = graph.graphStyle()
                    style['color'] = view.colorAtIndex(color_index)
                    style['lineWidth'] = default_line_width
                    if (len(ydata) == 1) or (np.sum(~np.isnan(ydata)) == 1):
                        if 'marker' not in style:
                            style['marker'] = 'o'
                    graph.setGraphStyle(style)
                    
                    # graph name (limit to max_char characters)
                    max_char = 75
                    name = path
                    if coords:
                        name += '[' + ','.join([f'{dim}={coords[dim]}' for dim in coords]) + ']'
                    if len(name) > max_char:
                        name = '...' + name[-(max_char-3):]
                    graph.blockSignals(True)
                    graph.setName(name)
                    graph.blockSignals(False)
                
                    # # graph context menu
                    # graph.contextMenu.addSeparator()
                    # action = QAction(parent=self, text=f'Mask Sweep', checkable=True, checked=is_masked)
                    # if is_masked:
                    #     action.triggered.connect(lambda checked, sweep=sweep: self.unmask_sweeps(sweep))
                    # else:
                    #     action.triggered.connect(lambda checked, sweep=sweep: self.mask_sweeps(sweep))
                    # graph.contextMenu.addAction(action)
                    
                    # next graph item
                    count += 1
                
                # next dataset (tree path)
                color_index += 1
            
            # remove extra graph items from plot
            while len(graphs) > count:
                graph = graphs.pop()
                plot.removeItem(graph)
                graph.deleteLater()
    
    def _update_ROIs(self, plots: list[pgx.Plot] = None) -> None:
        if plots is None:
            plots = self._plots.flatten().tolist()
        
        if not self._is_ROIs_visible():
            for plot in plots:
                ROI_items = [item for item in plot.vb.allChildren() if isinstance(item, pgx.XAxisRegion)]
                for item in ROI_items:
                    plot.vb.removeItem(item)
                    item.deleteLater()
            return
        
        selected_ROIs = self._ROItree_view.selectedAnnotations()
        
        for plot in plots:
            current_ROI_items = [item for item in plot.vb.allChildren() if isinstance(item, pgx.XAxisRegion)]
            current_ROIs = [item._ref for item in current_ROI_items]

            items_to_remove = [item for item in current_ROI_items if item._ref not in selected_ROIs]
            for item in items_to_remove:
                plot.vb.removeItem(item)
                item.deleteLater()
            
            items_to_update = [item for item in current_ROI_items if item._ref in selected_ROIs]
            for item in items_to_update:
                self._update_plot_item_from_data(item, item._ref)
            
            regions_to_add = [region for region in selected_ROIs if region not in current_ROIs]
            for region in regions_to_add:
                self._add_region_to_plot(region, plot)
    
    # def _update_selection(self, plots: list[pgx.Plot] = None) -> None:
    #     if plots is None:
    #         plots = self._plots.flatten().tolist()
        
    #     self._update_selection_regions()
    
    # def _update_selection_regions(self, plots: list[pgx.Plot] = None) -> None:
    #     if plots is None:
    #         plots = self._plots.flatten().tolist()
        
    #     selected_regions = self._get_current_region_selection()
        
    #     for plot in plots:
    #         current_region_items = [item for item in plot.vb.allChildren() if isinstance(item, pgx.XAxisRegion)]
    #         current_regions = [item._ref for item in current_region_items]

    #         items_to_remove = [item for item in current_region_items if item._ref not in selected_regions]
    #         for item in items_to_remove:
    #             plot.vb.removeItem(item)
    #             item.deleteLater()
            
    #         items_to_update = [item for item in current_region_items if item._ref in selected_regions]
    #         for item in items_to_update:
    #             self._update_plot_item_from_data(item, item._ref)
            
    #         regions_to_add = [region for region in selected_regions if region not in current_regions]
    #         for region in regions_to_add:
    #             self._add_region_to_plot(region, plot)
    
    # def _update_annotation_items(self) -> None:
    #     plots = self._plots.flatten().tolist()
    #     for plot in plots:
    #         plot._annotations = []

    #     if self._show_annotations_checkbox.isChecked():
    #         for path in getattr(self, '_selected_node_paths', []):
    #             node = self.datatree[path]
    #             annotations = node.attrs.get('annotations', [])
    #             for annotation in annotations:
    #                 for plot in self._get_annotation_plots(annotation, node):
    #                     plot._annotations.append(annotation)
            
    #         for path in getattr(self, '_selected_var_paths', []):
    #             var = self.datatree[path]
    #             annotations = var.attrs.get('annotations', [])
    #             for annotation in annotations:
    #                 for plot in self._get_annotation_plots(annotation, var):
    #                     plot._annotations.append(annotation)
        
    #     if self._show_selection_checkbox.isChecked():
    #         selection_regions = [region for region in self._selection if self.xdim in region['position']]
    #     else:
    #         selection_regions = []
        
    #     for plot in plots:
    #         current_annotation_items = [item for item in plot.vb.allChildren() if getattr(item, '_annotation', None)]
    #         current_annotations = [item._annotation for item in current_annotation_items]

    #         items_to_remove = [item for item in current_annotation_items if item._annotation not in plot._annotations + selection_regions]
    #         for item in items_to_remove:
    #             plot.vb.removeItem(item)
    #             item.deleteLater()
            
    #         items_to_update = [item for item in current_annotation_items if item._annotation in plot._annotations + selection_regions]
    #         for item in items_to_update:
    #             self._update_annotation_item_from_data(item, item._annotation)
            
    #         annotations_to_add = [annotation for annotation in plot._annotations + selection_regions if annotation not in current_annotations]
    #         for annotation in annotations_to_add:
    #             self._add_annotation_to_plot(annotation, plot)
    
    def _update_plot_item_from_data(self, item: QGraphicsObject, data: dict) -> None:
        if isinstance(item, pgx.XAxisRegion):
            item.setRegion(data['position'][self.xdim])
            item.setMovable(data.get('movable', True))
            item.setText(data.get('text', ''))
            # item.setFormat(data.get('format', {}))

    def _update_data_from_plot_item(self, item: QGraphicsObject, data: dict) -> None:
        if isinstance(item, pgx.XAxisRegion):
            data['position'] = {self.xdim: item.getRegion()}
            data['movable'] = item.movable
            data['text'] = item.text()
            # data['format'] = item.getFormat()
    
    def _update_text_item_font(self):
        for plot in self._plots.flatten().tolist():
            view: pgx.View = plot.getViewBox()
            for item in view.allChildren():
                if isinstance(item, pgx.XAxisRegion):
                    item.setFontSize(self._textitem_fontsize_spinbox.value())

    def _update_icon_size(self) -> None:
        size = self._toolbar_iconsize_spinbox.value()
        icon_size = QSize(size, size)
        for toolbar in [self._top_toolbar, self._left_toolbar]:
            toolbar.setIconSize(icon_size)
            # actions = toolbar.actions()
            # widgets = [toolbar.widgetForAction(action) for action in actions]
            # buttons = [widget for widget in widgets if isinstance(widget, QToolButton)]
            # for button in buttons:
            #     button.setIconSize(icon_size)
    
    def _add_region_to_plot(self, region: dict, plot: pgx.Plot) -> pgx.XAxisRegion:
        item = pgx.XAxisRegion()
        item._ref = region
        self._update_plot_item_from_data(item, item._ref)

        item.sigRegionChanged.connect(lambda item=item: self._on_plot_item_changed(item))
        item.sigRegionDragFinished.connect(lambda item=item: self._on_plot_item_changed(item))
        item.sigEditingFinished.connect(lambda item=item: self._on_plot_item_changed(item))
        item.sigDeletionRequested.connect(lambda item=item: self._delete_ROIs(item._ref))

        item.sigRegionDragFinished.connect(lambda: self._update_ROItree_view())
        item.sigEditingFinished.connect(lambda: self._update_ROItree_view())
        
        plot.vb.addItem(item)
        item.setZValue(0)
        return item
    
    def _delete_ROIs(self, ROIs: dict | list[dict]) -> None:
        if isinstance(ROIs, dict):
            ROIs = [ROIs]
        
        # remove ROIs from datatree
        for node in self.datatree.subtree:
            node_ROIs = node.attrs.get('ROIs', [])
            for ROI in ROIs:
                if ROI in node_ROIs:
                    node_ROIs.remove(ROI)

        # remove ROIs from plots
        for plot in self._plots.flatten().tolist():
            for item in plot.vb.allChildren():
                if isinstance(item, pgx.XAxisRegion) and getattr(item, '_ref', None) in ROIs:
                    plot.vb.removeItem(item)
                    item.deleteLater()
        
        self._update_ROItree_view()
    
    def _clear_ROI_selection(self, ask: bool = True) -> None:
        if ask:
            answer = QMessageBox.question(self, 'Clear ROI Selection', 'Clear ROI selection?\nROIs are not deleted.')
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._ROItree_view.clearSelection()
        self._update_ROIs()
    
    def _delete_selected_ROIs(self, ask: bool = True) -> None:
        if ask:
            answer = QMessageBox.question(self, 'Delete Selected ROIs', 'Delete selected ROIs?')
            if answer != QMessageBox.StandardButton.Yes:
                return
        selected_ROIs = self._ROItree_view.selectedAnnotations()
        self._delete_ROIs(selected_ROIs)
    
    def _save_selected_ROIs(self) -> None:
        selected_ROIs = self._ROItree_view.selectedAnnotations()

        if not selected_ROIs or not self._selected_branch_root_paths:
            QMessageBox.warning(self, 'Empty Selection', f'No ROIs selected. First select ROIs to save.')
            return
        
        dlg = QDialog(self)
        dlg.setWindowTitle('Save Selected ROIs')
        vbox = QVBoxLayout(dlg)

        vbox.addWidget(QLabel('Selection Group Name:'))
        group_edit = QLineEdit()
        group_edit.setPlaceholderText('Ungrouped')
        vbox.addWidget(group_edit)

        vbox.addSpacing(20)
        vbox.addWidget(QLabel('Save To:'))
        paths = [node.path for node in self.datatree.children.values()]
        model = QStringListModel(paths)
        view = QListView()
        view.setModel(model)
        # view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        # for path in self._selected_branch_root_paths:
        #     row = paths.index(path)
        #     index = model.index(row, 0)
        #     view.selectionModel().select(index, QItemSelectionModel.SelectionFlag.Select)
        if self._selected_branch_root_paths:
            path = self._selected_branch_root_paths[0]
            row = paths.index(path)
            view.setCurrentIndex(model.index(row, 0))
        else:
            view.setCurrentIndex(model.index(0, 0))
        vbox.addWidget(view)

        vbox.addSpacing(20)
        copyCheckBox = QCheckBox('Save As Copy')
        copyCheckBox.setChecked(False)
        vbox.addWidget(copyCheckBox)
        vbox.addWidget(QLabel('Copy instead of overwriting any existing saved selections.'))

        buttons = QDialogButtonBox()
        buttons.setStandardButtons(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        vbox.addWidget(buttons)

        if dlg.exec() != QDialog.Accepted:
            return
        
        group = group_edit.text().strip()
        if group == '':
            # group = group_edit.placeholderText()
            group = None
        
        indexes = view.selectionModel().selectedIndexes()
        paths = [index.data(Qt.DisplayRole) for index in indexes]
        if not paths:
            return
        
        path = paths[0]  # should only be one path selected
        node = self.datatree[path]
        if 'ROIs' not in node.attrs:
            node.attrs['ROIs'] = []
        
        for i, ROI in enumerate(selected_ROIs):
            ROI_path = self._get_ROI_path(ROI)
            if ROI_path is not None:
                # this is a currently saved region
                if copyCheckBox.isChecked() or ROI_path != node.path:
                    # save a copy of this region
                    ROI = deepcopy(ROI)
                    selected_ROIs[i] = ROI

            # ROI group
            if group is not None:
                ROI['group'] = group
            elif 'group' in ROI:
                del ROI['group']
            
            # save ROI to node
            if ROI not in node.attrs['ROIs']:
                node.attrs['ROIs'].append(ROI)
            
            # remove ROI from tmp ROIs in datatree root
            tmp_ROIs = self.datatree.attrs.get('ROIs', [])
            if ROI in tmp_ROIs:
                tmp_ROIs.remove(ROI)
        
        self._update_ROItree_view()
        self._ROItree_view.setSelectedAnnotations(selected_ROIs)

    def _group_selected_ROIs(self) -> None:
        pass # TODO
    
    def _format_selected_ROIs(self) -> None:
        pass # TODO
    
    def _start_drawing_items(self, item_type) -> None:
        for plot in self._plots.flatten().tolist():
            plot.vb.sigItemAdded.connect(self._on_item_added_to_plot)
            plot.vb.startDrawingItemsOfType(item_type)
    
    def _stop_drawing_items(self) -> None:
        for plot in self._plots.flatten().tolist():
            plot.vb.stopDrawingItems()
            plot.vb.sigItemAdded.disconnect(self._on_item_added_to_plot)
    
    def _init_ui(self) -> None:
        self.setWindowTitle(self.__class__.__name__)
        self._init_actions()
        self._init_menubar()
        self._init_top_toolbar()
        self._init_left_toolbar()
        self._init_console()
        self._init_control_panels()

        self._data_var_views_splitter = QSplitter(Qt.Orientation.Vertical)

        self._inner_vsplitter = QSplitter(Qt.Orientation.Vertical)
        self._inner_vsplitter.addWidget(self._data_var_views_splitter)
        self._inner_vsplitter.addWidget(self._console)
        self._inner_vsplitter.setSizes([self.sizeHint().height() - 250, 250])

        self._outer_hsplitter = QSplitter(Qt.Orientation.Horizontal)
        self._outer_hsplitter.addWidget(self._control_panels_stack)
        self._outer_hsplitter.addWidget(self._inner_vsplitter)
        self._outer_hsplitter.setSizes([250, self.sizeHint().width() - 250])

        self.setCentralWidget(self._outer_hsplitter)

        self._plots = np.empty((0,0,0), dtype=object)

        self.refresh()
    
    def _init_actions(self) -> None:
        self._datatree_view_action = QAction(
            parent=self, 
            icon=get_icon('mdi.file-tree'), 
            iconVisibleInMenu=True,
            text='Data Tree',
            toolTip='Data Tree',
            checkable=True, 
            checked=True,
            triggered=lambda checked: self._update_control_panel_view())

        self._notes_view_action = QAction(
            parent=self, 
            icon=get_icon('mdi6.text-box-edit-outline'), 
            iconVisibleInMenu=True,
            text='Metadata & Notes', 
            toolTip='Metadata & Notes', 
            checkable=True, 
            checked=False,
            triggered=lambda checked: self._update_control_panel_view())

        self._settings_panel_action = QAction(
            parent=self, 
            icon=get_icon('msc.gear'), 
            iconVisibleInMenu=True,
            text='Settings', 
            toolTip='Settings', 
            checkable=True, 
            checked=False,
            triggered=lambda checked: self._update_control_panel_view())

        self._toggle_console_action = QAction(
            parent=self, 
            icon=get_icon('mdi.console'), 
            iconVisibleInMenu=True,
            text='Console', 
            toolTip='Console', 
            checkable=True, 
            checked=False,
            triggered=lambda checked: self._console.setVisible(checked))

        self._control_panel_action_group = QActionGroup(self)
        self._control_panel_action_group.addAction(self._datatree_view_action)
        self._control_panel_action_group.addAction(self._notes_view_action)
        self._control_panel_action_group.addAction(self._settings_panel_action)
        self._control_panel_action_group.setExclusionPolicy(QActionGroup.ExclusionPolicy.ExclusiveOptional)

        self._home_action = QAction(
            parent = self, 
            icon = get_icon('mdi.home'), 
            iconVisibleInMenu = True,
            text = 'Autoscale', 
            toolTip = 'Autoscale',
            triggered = lambda: self.autoscale())

        # TODO: remove?
        # self._include_masked_action = QAction(
        #     parent = self, 
        #     text = 'Include Masked', 
        #     toolTip = 'Include Masked',
        #     shortcut = QKeySequence('I'),
        #     checkable=True, 
        #     checked=False,
        #     triggered = lambda: self.refresh())
    
    def _init_menubar(self) -> None:
        menubar = self.menuBar()

        self._file_menu = menubar.addMenu('File')
        self._file_menu.addAction('New Window', QKeySequence.StandardKey.New, self.newWindow)
        self._file_menu.addSeparator()
        self._file_menu.addAction(qta.icon('fa5.folder-open'), 'Open', QKeySequence.StandardKey.Open, self.load)
        self._import_menu = self._file_menu.addMenu('Import')
        self._file_menu.addSeparator()
        self._file_menu.addAction(qta.icon('fa5.save'), 'Save', QKeySequence.StandardKey.Save, self.save)
        self._file_menu.addAction(qta.icon('fa5.save'), 'Save As', QKeySequence.StandardKey.SaveAs, self.saveAs)
        self._export_menu = self._file_menu.addMenu('Export')
        self._file_menu.addSeparator()
        self._file_menu.addAction('Close Window', QKeySequence.StandardKey.Close, self.close)
        self._file_menu.addSeparator()
        self._file_menu.addAction('Quit', QKeySequence.StandardKey.Quit, qApp.quit)

        self._import_menu.addAction('Zarr Zip', lambda: self.load(filetype='Zarr Zip'))
        self._import_menu.addAction('Zarr Directory', lambda: self.load(filetype='Zarr Directory'))
        self._import_menu.addAction('NetCDF', lambda: self.load(filetype='NetCDF'))
        self._import_menu.addAction('HDF5', lambda: self.load(filetype='HDF5'))
        self._import_menu.addSeparator()
        self._import_menu.addAction('WinWCP', lambda: self.load(filetype='WinWCP'))
        self._import_menu.addAction('HEKA', lambda: self.load(filetype='HEKA'))
        self._import_menu.addAction('Axon ABF', lambda: self.load(filetype='Axon ABF'))
        self._import_menu.addAction('LabChart MATLAB Conversion (GOLab)', lambda: self.load(filetype='LabChart MATLAB Conversion (GOLab)'))

        self._export_menu.addAction('Zarr Zip', lambda: self.saveAs(filetype='Zarr Zip'))
        self._export_menu.addAction('Zarr Directory', lambda: self.saveAs(filetype='Zarr Directory'))
        self._export_menu.addAction('NetCDF', lambda: self.saveAs(filetype='NetCDF'))
        self._export_menu.addAction('HDF5', lambda: self.saveAs(filetype='HDF5'))

        # self._edit_menu = menubar.addMenu('Edit')
        # self._edit_menu.addAction('Mask Selection', QKeySequence('M'))
        # self._edit_menu.addAction('Unmask Selection', QKeySequence('U'))
        # self._edit_menu.addSeparator()

        self._selection_menu = menubar.addMenu('Selection')
        self._selection_menu.addAction('Select Range ROI', QKeySequence('R'), lambda: self._start_drawing_items(pgx.XAxisRegion))
        self._selection_menu.addSeparator()
        # self._selection_menu.addAction('Toggle Selection', QKeySequence('T'), lambda: self._show_selection_checkbox.setChecked(not self._show_selection_checkbox.isChecked()))
        self._selection_menu.addAction('Clear ROI Selection', QKeySequence('C'), self._clear_ROI_selection)
        self._selection_menu.addSeparator()
        self._selection_menu.addAction('Save Selected ROIs', self._save_selected_ROIs)
        self._selection_menu.addSeparator()
        self._selection_menu.addAction('Delete Selected ROIs', self._delete_selected_ROIs)
        self._selection_menu.addSeparator()
        self._selection_menu.addAction('Mask Selection', QKeySequence('M'))
        self._selection_menu.addAction('Unmask Selection', QKeySequence('U'))

        self._view_menu = menubar.addMenu('View')
        self._view_ROIs_action = self._view_menu.addAction('ROIs', QKeySequence('T'), lambda: self._set_ROIs_visible(self._view_ROIs_action.isChecked()))
        self._view_ROIs_action.setCheckable(True)
        self._view_ROIs_action.setChecked(True)
        # self._view_selection_action.triggered.connect(lambda checked: self._update_selection())
        self._view_masked_action = self._view_menu.addAction('Masked', lambda: self._set_masked_visible(self._view_masked_action.isChecked()))
        self._view_masked_action.setCheckable(True)
        self._view_masked_action.setChecked(False)
        # self._view_masked_action.triggered.connect(lambda checked: self.refresh())
        self._view_menu.addSeparator()
        self._view_menu.addAction('Console') # TODO: make checkable and use to show/hide console
        self._view_menu.addSeparator()
        self._view_menu.addAction('Settings') # TODO: popup settings dialog
        self._view_menu.addSeparator()
    
    def _init_top_toolbar(self) -> None:
        self._top_toolbar = QToolBar()
        self._top_toolbar.setOrientation(Qt.Orientation.Horizontal)
        self._top_toolbar.setStyleSheet("QToolBar{spacing:2px;}")
        self._top_toolbar.setIconSize(QSize(DEFAULT_ICON_SIZE, DEFAULT_ICON_SIZE))
        self._top_toolbar.setMovable(False)
        self._top_toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._top_toolbar)

        self._logo_button = QToolButton(
            icon=get_icon('fa5s.cubes'),
            toolTip='Refresh UI',
            pressed=self.refresh,
        )

        self._show_ROIs_checkbox = QCheckBox('ROIs', checked=self._view_ROIs_action.isChecked())
        self._show_ROIs_checkbox.checkStateChanged.connect(lambda state: self._set_ROIs_visible(state == Qt.CheckState.Checked))
        show_ROIs_widget_action = QWidgetAction(self)
        show_ROIs_widget_action.setDefaultWidget(self._show_ROIs_checkbox)

        self._include_masked_checkbox = QCheckBox('Masked', checked=self._view_masked_action.isChecked())
        self._include_masked_checkbox.checkStateChanged.connect(lambda state: self._set_masked_visible(state == Qt.CheckState.Checked))
        include_masked_widget_action = QWidgetAction(self)
        include_masked_widget_action.setDefaultWidget(self._include_masked_checkbox)

        # self._data_var_filter_menu = QMenu('data_vars')
        # self._before_filter_data_vars_action = self._data_var_filter_menu.addSeparator()
        # self._after_filter_data_vars_action = self._data_var_filter_menu.addSeparator()

        # self._saved_selections_list_widget = QListWidget()
        # self._saved_selections_list_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # saved_selections_list_widget_action = QWidgetAction(self)
        # saved_selections_list_widget_action.setDefaultWidget(self._saved_selections_list_widget)

        # self._saved_selections_filter_menu = QMenu('Saved Regions')
        # self._saved_selections_filter_menu.addAction(saved_selections_list_widget_action)

        self._filter_button = QToolButton(
            icon=get_icon('mdi6.filter-multiple-outline'), # 'fa6s.sliders'
            toolTip='Filter Options',
            popupMode=QToolButton.ToolButtonPopupMode.InstantPopup,
        )
        self._filter_menu = QMenu()
        self._filter_menu.addAction(show_ROIs_widget_action)
        self._filter_menu.addAction(include_masked_widget_action)
        self._filter_menu.addSeparator()
        self._before_filter_data_vars_action = self._filter_menu.addAction('Variables:')
        self._before_filter_data_vars_action.setEnabled(False)
        self._after_filter_data_vars_action = self._filter_menu.addSeparator()
        # self._filter_menu.addMenu(self._data_var_filter_menu)
        # self._filter_menu.addSeparator()
        # self._saved_selections_filter_menu_action = self._filter_menu.addMenu(self._saved_selections_filter_menu)
        self._filter_button.setMenu(self._filter_menu)

        self._before_dim_iter_things_spacer = QWidget()
        self._before_dim_iter_things_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        
        self._top_toolbar.addWidget(self._logo_button)
        self._top_toolbar.addSeparator()
        self._top_toolbar.addWidget(self._filter_button)
        self._before_dim_iter_things_spacer_action = self._top_toolbar.addWidget(self._before_dim_iter_things_spacer)
        self._after_dim_iter_things_separator_action = self._top_toolbar.addSeparator()
        self._top_toolbar.addAction(self._home_action)

        # for dynamic dimension iteration
        self._dim_iter_things: dict[str, dict] = {}

    def _init_left_toolbar(self) -> None:
        self._left_toolbar = QToolBar()
        self._left_toolbar.setOrientation(Qt.Orientation.Vertical)
        self._left_toolbar.setStyleSheet("QToolBar{spacing:2px;}")
        self._left_toolbar.setIconSize(QSize(DEFAULT_ICON_SIZE, DEFAULT_ICON_SIZE))
        self._left_toolbar.setMovable(False)
        self._left_toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self._left_toolbar)

        vspacer = QWidget()
        vspacer.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        self._left_toolbar.addAction(self._datatree_view_action)
        self._left_toolbar.addAction(self._notes_view_action)
        self._left_toolbar.addAction(self._settings_panel_action)
        self._left_toolbar.addWidget(vspacer)
        self._left_toolbar.addAction(self._toggle_console_action)
    
    def _init_console(self) -> None:
        self._console = RichJupyterWidget()
        self._console.kernel_manager = QtInProcessKernelManager()
        self._console.kernel_manager.start_kernel(show_banner=False)
        self._console.kernel_client = self._console.kernel_manager.client()
        self._console.kernel_client.start_channels()

        self._console.kernel_manager.kernel.shell.push({'self': self})

        self._console.execute('import numpy as np', hidden=True)
        self._console.execute('import xarray as xr', hidden=True)
        # self._console.execute('self', hidden=False)
        # self._console.execute('self.datatree', hidden=False)
        # self._console._set_input_buffer('') # seems silly to have to call this?

        self._console.executed.connect(self.refresh)

        QTimer.singleShot(250, self._print_console_intro_message)
    
    def _print_console_intro_message(self) -> None:
        self._console._append_plain_text('--------------------------------------------------\n', before_prompt=True)
        self._console._append_plain_text('Welcome to XarrayGraph console!\n', before_prompt=True)
        self._console._append_plain_text('self          => This instance of XarrayGraph\n', before_prompt=True)
        self._console._append_plain_text('self.datatree => The Xarray DataTree\n', before_prompt=True)
        self._console._append_plain_text("Access array data: self.datatree['/path/to/array']\n", before_prompt=True)
        self._console._append_plain_text("Modules loaded at startup: numpy as np, xarray as xr\n", before_prompt=True)
        self._console._append_plain_text('--------------------------------------------------\n', before_prompt=True)
    
    def _shutdown_console(self) -> None:
        if self._console is None:
            return
        self._console.kernel_client.stop_channels()
        self._console.kernel_manager.shutdown_kernel()
        self._console.deleteLater()
        self._console = None
    
    def _init_control_panels(self) -> None:
        self._init_datatree_panel()
        self._init_notes_panel()
        self._init_settings_panel()

        self._control_panels_stack = QStackedWidget()
        self._control_panels_stack.addWidget(self._datatree_viewer)
        self._control_panels_stack.addWidget(self._notes_edit)
        self._control_panels_stack.addWidget(self._settings_panel)
    
    def _init_datatree_panel(self) -> None:
        self._datatree_viewer = XarrayTreeViewer()
        self._datatree_view = self._datatree_viewer.view()
        self._datatree_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._datatree_view.setAlternatingRowColors(False)
        self._datatree_view.setVariablesVisible(False)
        self._datatree_view.setCoordinatesVisible(False)
        self._datatree_model: XarrayTreeModel = XarrayTreeModel(dt=self.datatree)
        self._datatree_model.setDetailsColumnVisible(False)
        self._datatree_view.setModel(self._datatree_model)
        self._datatree_view.expandAll()
        self._datatree_view.selectionWasChanged.connect(self._on_tree_selection_changed)
        self._datatree_viewer.setSizes([400, 400])

        self._ROItree_view = AnnotationTreeView()
        self._ROItree_model = AnnotationTreeModel()
        self._ROItree_view.setModel(self._ROItree_model)
        self._ROItree_view.setHeaderHidden(True)
        self._ROItree_view.selectionWasChanged.connect(lambda: self._set_ROIs_visible(True))
        self._datatree_viewer.metadata_tabs.addTab(self._ROItree_view, "ROIs")

        # # on attr changes
        # self._datatree_view.sigFinishedEditingAttrs.connect(self.refresh)
        # attrs_model: KeyValueTreeModel = self._datatree_viewer._attrs_view.model()
        # attrs_model.sigValueChanged.connect(self.refresh)
    
    def _init_notes_panel(self) -> None:
        self._notes_edit = QTextEdit()
        self._notes_edit.setToolTip('Notes')
        # self._notes_edit.textChanged.connect(lambda: self.metadata.update({'notes', self._notes_edit.toPlainText()}))
    
    def _init_settings_panel(self) -> None:
        # self._include_masked_checkbox = QCheckBox(checked=False)
        # self._include_masked_checkbox.stateChanged.connect(self.refresh)

        # self._apply_offsets_checkbox = QCheckBox(checked=False)
        # self._apply_offsets_checkbox.stateChanged.connect(self.refresh)

        # self._offsets_edit = QLineEdit()
        # self._offsets_edit.setPlaceholderText('dim: value units, ...')
        # self._offsets_edit.editingFinished.connect(self.replot)

        # format_separator = QFrame()
        # format_separator.setFrameShape(QFrame.HLine)
        # format_separator.setFrameShadow(QFrame.Sunken)
        # format_separator.setContentsMargins(0, 25, 0, 25)

        self._linewidth_spinbox = QSpinBox()
        self._linewidth_spinbox.setValue(DEFAULT_LINE_WIDTH)
        self._linewidth_spinbox.setMinimum(1)
        self._linewidth_spinbox.valueChanged.connect(self.replot)

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
        self._textitem_fontsize_spinbox.valueChanged.connect(self._update_text_item_font)

        self._toolbar_iconsize_spinbox = QSpinBox()
        self._toolbar_iconsize_spinbox.setValue(DEFAULT_ICON_SIZE)
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
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        # form.addRow('Include Masked', self._include_masked_checkbox)
        # form.addRow('Apply Offsets', self._apply_offsets_checkbox)
        # form.addRow('Offsets', self._offsets_edit)
        # form.addRow(format_separator)
        # form.addRow(' ', None)
        form.addRow('Line width', self._linewidth_spinbox)
        form.addRow('Axis label size', self._axislabel_fontsize_spinbox)
        form.addRow('Axis tick label size', self._axistick_fontsize_spinbox)
        form.addRow('Text item size', self._textitem_fontsize_spinbox)
        form.addRow('Icon size', self._toolbar_iconsize_spinbox)

        # self._settings_panel_scroll_area = QScrollArea()
        # self._settings_panel_scroll_area.setWidgetResizable(True)
        # self._settings_panel_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        # self._settings_panel_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        # self._settings_panel_scroll_area.setWidget(self._settings_panel)
    
    
class DimIterWidget(QWidget):

    def __init__(self, *args, **kwargs):
        QWidget.__init__(self, *args, **kwargs)

        self._xgraph = None

        self._pile_action = QAction(
            parent = self, 
            icon = get_icon('ph.stack'), 
            text = 'Pile Traces', 
            iconVisibleInMenu = True, 
            checkable = True, 
            checked = True,
            triggered = self.pile,
        )
        self._tile_vertically_action = QAction(
            parent = self, 
            icon = get_icon('mdi.reorder-horizontal'), 
            text = 'Tile Traces Vertically', 
            iconVisibleInMenu = True, 
            checkable = True, 
            checked = False,
            triggered = self.tileVertically,
        )
        self._tile_horizontally_action = QAction(
            parent = self, 
            icon = get_icon('mdi.reorder-vertical'), 
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
            icon=get_icon('ph.arrow-line-down'),
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
        if self._xgraph is not None:
            self.setParentXarrayGraph(self._xgraph)
    
    def coords(self) -> np.ndarray:
        return self._spinbox.indexedValues()
    
    def setCoords(self, coords: np.ndarray) -> None:
        self._spinbox.blockSignals(True)
        values = self._spinbox.selectedValues()
        self._spinbox.setIndexedValues(coords)
        if values.size > 0:
            self._spinbox.setSelectedValues(values)
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
    
    def setParentXarrayGraph(self, xgraph: XarrayGraph) -> None:
        self._xgraph = xgraph
        self._spinbox.indicesChanged.connect(self._xgraph._on_index_selection_changed)
        self.updateTileButton()
    
    def updateTileButton(self) -> None:
        if self._xgraph is None:
            return
        dim = self.dim()
        if getattr(self._xgraph, '_vertical_tile_dimension', None) == dim:
            self._tile_vertically_action.setChecked(True)
            self._tile_button.setIcon(self._tile_vertically_action.icon())
        elif getattr(self._xgraph, '_horizontal_tile_dimension', None) == dim:
            self._tile_horizontally_action.setChecked(True)
            self._tile_button.setIcon(self._tile_horizontally_action.icon())
        else:
            self._pile_action.setChecked(True)
            self._tile_button.setIcon(self._pile_action.icon())
    
    def setAsXDim(self) -> None:
        if self._xgraph is not None:
            self._xgraph.xdim = self.dim()
    
    def pile(self) -> None:
        self._pile_action.setChecked(True)
        self._tile_button.setIcon(self._pile_action.icon())
        if self._xgraph is not None:
            self._xgraph.tileDimension(self.dim(), None)
    
    def tileVertically(self) -> None:
        self._tile_vertically_action.setChecked(True)
        self._tile_button.setIcon(self._tile_vertically_action.icon())
        if self._xgraph is not None:
            self._xgraph.tileDimension(self.dim(), Qt.Orientation.Vertical)
    
    def tileHorizontally(self) -> None:
        self._tile_horizontally_action.setChecked(True)
        self._tile_button.setIcon(self._tile_horizontally_action.icon())
        if self._xgraph is not None:
            self._xgraph.tileDimension(self.dim(), Qt.Orientation.Horizontal)


def get_icon(name: str, opacity: float = DEFAULT_ICON_OPACITY, size: int | QSize = None) -> QIcon:
    icon = qta.icon(name, options=[{'opacity': opacity}])
    if size is not None:
        if isinstance(size, QSize):
            icon.setIconSize(size)
        elif isinstance(size, int):
            icon.setIconSize(QSize(size, size))
    return icon


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


def remove_inherited_data_vars(dt: xr.DataTree) -> xr.DataTree:
    dt = dt.copy()  # copy tree but not underlying data
    for node in reversed(list(dt.subtree)):
        if not node.parent:
            continue
        for key in list(node.parent.data_vars):
            if key in node.data_vars:
                if node.data_vars[key].values is node.parent.data_vars[key].values:
                    node.dataset = node.to_dataset().drop_vars(key)
    return dt


def inherit_missing_data_vars(dt: xr.DataTree) -> xr.DataTree:
    dt = dt.copy()  # copy tree but not underlying data
    for node in dt.subtree:
        if not node.parent:
            continue
        for key in list(node.parent.data_vars):
            if key not in node.data_vars:
                node.dataset = node.to_dataset().assign({key: node.parent.data_vars[key]})
    return dt


def store_ordered_data_vars(dt: xr.DataTree) -> None:
    for child in dt.children.values():
        child.attrs['ordered_data_vars'] = list(child.data_vars)


def restore_ordered_data_vars(dt: xr.DataTree) -> None:
    for child in dt.children.values():
        ordered_data_vars = child.attrs.get('ordered_data_vars', None)
        if ordered_data_vars is not None:
            for node in child.subtree:
                ds = node.to_dataset()
                node.dataset = xr.Dataset(
                    data_vars={key: ds[key] for key in ordered_data_vars},
                    coords=ds.coords,
                    attrs=ds.attrs,
                )


def find_branch_root(dt: xr.DataTree) -> xr.DataTree:
    # Xarray DataTree requires that data must be aligned within a tree branch.
    # Return the root of the branch containing dt above which nodes are no longer aligned.
    while dt.parent is not None:
        if not dt.parent.has_data:
            break
        try:
            xr.align(dt.dataset, dt.parent.dataset, join='exact')
            dt = dt.parent
        except:
            break
    return dt


def test_live():
    app = QApplication()

    xg = XarrayGraph()
    xg.show()

    dt: xr.DataTree = xr.open_datatree('examples/ERPdata.nc', engine='h5netcdf')
    dt.dataset = dt.to_dataset().assign({'GGE': dt['EEG']})

    ds2 = dt.to_dataset().rename({'condition': 'trial', 'GGE': 'BEE'})
    ds2['EEG'] += 1e-6
    ds2['BEE'] += 1e-6
    ds2['BEE'] *= 10

    root = xr.DataTree()
    root['Data'] = dt
    root['Data2'] = ds2

    # xg._regions = [
    #     {
    #         'region': {'time': [-0.5, 0.5], 'subject': [3, 5]}
    #     }
    # ]
    
    xg.datatree = root
    xg._datatree_view.setVariablesVisible(True)
    xg._datatree_view.expandAll()
    xg._datatree_view.setSelectedPaths(['/Data'])

    app.exec()


if __name__ == '__main__':
    test_live()
