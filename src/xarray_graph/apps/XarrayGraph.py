""" PyQt widget for viewing/analyzing (x,y) slices of a Xarray DataTree.

TODO:
- warn if mutating data array directly?
"""

from __future__ import annotations
from copy import deepcopy
from functools import reduce
import textwrap
import numpy as np
# import pandas as pd
import cftime
# to be able to read unit attributes following the CF conventions
# import cf_xarray.units  # noqa: F401  # must be imported before pint_xarray
import xarray as xr
# import pint_xarray
import pint
from pint.facets.plain import ScaleConverter
import cmap
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
import pyqtgraph as pg
from xarray_graph.utils import xarray_utils
from xarray_graph.apps import XarrayDataTreeViewer
from xarray_graph.tree import XarrayDataTreeItem, XarrayDataTreeModel, AnnotationTreeItem, AnnotationTreeModel, AnnotationTreeView
from xarray_graph.graph import *
from xarray_graph.widgets import MultiValueSpinBox, CollapsibleSectionsSplitter


ROI_KEY = '_XG_ROI'
MASK_KEY = '_XG_MASK'
NOTES_KEY = '_XG_NOTES'
TO_DISPLAY_UNITS_KEY = '_XG_TO_DISPLAY_UNITS_FACTOR'
MASK_COLOR = (200, 200, 200)
PREVIEW_COLOR = (255, 0, 0)


class XarrayGraph(XarrayDataTreeViewer):
    """ PyQt widget for viewing/analyzing (x,y) slices of a Xarray DataTree.
    """

    # ureg = pint_xarray.unit_registry
    ureg = pint.UnitRegistry()#auto_reduce_dimensions=True)
    ureg.formatter.default_format = "~P"

    _default_settings = {
        'icon size': 24,
        'colormap': cmap.Colormap('seaborn:tab10_colorblind').to_pyqtgraph()
    }
    _settings = deepcopy(_default_settings)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.refresh()

    def setDatatree(self, datatree: xr.DataTree) -> None:
        super().setDatatree(datatree)
        self._notes_view.setPlainText(datatree.attrs.get(NOTES_KEY, ''))

    def xdim(self) -> str | None:
        try:
            return self._xdim
        except AttributeError:
            return None
    
    def setXDim(self, xdim: str | None) -> None:
        try:
            self._prev_xdim = self._xdim
        except AttributeError:
            pass
        self._xdim = xdim
        self.refresh()
    
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
                    plot: pg.PlotItem = self._plots[i, row, col]
                    view: pg.ViewBox = plot.getViewBox()
                    xlinked_view: pg.ViewBox = view.linkedView(view.XAxis)
                    ylinked_view: pg.ViewBox = view.linkedView(view.YAxis)
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
    
    def notes(self) -> None:
        self._notes_view.show()
    
    def rois(self) -> list[dict]:
        """ Get list of ROI annotations.
        """
        dt = self.datatree()
        if ROI_KEY not in dt.attrs:
            dt.attrs[ROI_KEY] = []
        return dt.attrs[ROI_KEY]
    
    def setRois(self, rois: list[dict]) -> None:
        """ Set list of ROI annotations.
        """
        dt = self.datatree()
        dt.attrs[ROI_KEY] = rois
    
    def selectedRois(self) -> list[dict]:
        return self._ROIs_view.selectedAnnotations()
    
    def setSelectedRois(self, rois: list[dict]) -> None:
        self._ROIs_view.setSelectedAnnotations(rois)
    
    def visibleRois(self) -> list[dict]:
        if self.isRoisVisible():
            return self.selectedRois()
        else:
            return []
    
    def visibleXRanges(self) -> list[tuple[float, float]]:
        xranges: list[tuple[float, float]] = []
        xdim = self.xdim()
        for roi in self.visibleRois():
            if roi['type'] != 'region':
                continue
            try:
                lb, ub = roi['position'][xdim]
            except:
                continue
            xranges.append((lb, ub))
        return xranges

    def addRoisToPlots(self, rois: list[dict], plots: list[Plot] = None) -> None:
        if plots is None:
            plots = self._plots.flatten().tolist()
        for plot in plots:
            for roi in rois:
                atype = roi.get('type', None)
                if atype == 'region':
                    pos = roi['position'].get(self.xdim())
                    if pos is None:
                        continue
                    if isinstance(pos, (list, tuple)) and len(pos) == 2:
                        item = XAxisRegion()
                    elif np.isscalar(pos):
                        item = VLine()
                    else:
                        continue
                    item._ROI = roi
                    self._updateRoiPlotItemFromData(item, roi)
                    self._setupRoiPlotItem(item)
                    plot.vb.addItem(item)
    
    def removeRoisFromPlots(self, rois: list[dict] = None, plots: list[Plot] = None) -> None:
        if plots is None:
            plots = self._plots.flatten().tolist()
        for plot in plots:
            roi_items = [item for item in plot.vb.allChildren() if hasattr(item, '_ROI')]
            for item in roi_items:
                if rois is None or item._ROI in rois:
                    plot.vb.removeItem(item)
                    item.deleteLater()

    def selectedRoiType(self) -> str:
        return self._ROI_action_group.checkedAction().text()
    
    def isRoisVisible(self) -> bool:
        return self._view_ROIs_action.isChecked()
    
    def setIsRoisVisible(self, visible: bool) -> None:
        self._view_ROIs_action.setChecked(visible)
        self.replot()

    def mask(self) -> None:
        """ Mask selected traces or ROIs within selected traces.
        """
        xranges = self.visibleXRanges()
        xdim = self.xdim()
        for node in self._branch_root_nodes_for_selected_data_vars:
            dims = tuple(node.sizes.keys())
            sizes = tuple(node.sizes.values())
            if MASK_KEY not in node.data_vars:
                node.dataset = node.to_dataset().assign({MASK_KEY: xr.DataArray(np.full(sizes, False, dtype=bool), dims=dims)})
            coords = {dim: values for dim, values in self._selection_visible_coords.coords.items() if dim in node.dims}
            if xranges:
                xdata = node[xdim].values
                xmask = np.full(xdata.shape, False, dtype=bool)
                for xrange in xranges:
                    lb, ub = xrange
                    xmask[(xdata >= lb) & (xdata <= ub)] = True
                coords[xdim] = xdata[xmask]
            node.data_vars[MASK_KEY].loc[coords] = True
        
        self.refresh()

    def unmask(self) -> None:
        """ Unmask selected traces or ROIs within selected traces.
        """
        xranges = self.visibleXRanges()
        xdim = self.xdim()
        for node in self._branch_root_nodes_for_selected_data_vars:
            dims = tuple(node.sizes.keys())
            sizes = tuple(node.sizes.values())
            if MASK_KEY not in node.data_vars:
                continue
            coords = {dim: values for dim, values in self._selection_visible_coords.coords.items() if dim in node.dims}
            if xranges:
                xdata = node[xdim].values
                xmask = np.full(xdata.shape, False, dtype=bool)
                for xrange in xranges:
                    lb, ub = xrange
                    xmask[(xdata >= lb) & (xdata <= ub)] = True
                coords[xdim] = xdata[xmask]
            node.data_vars[MASK_KEY].loc[coords] = False
            if not np.any(node.data_vars[MASK_KEY].values):
                node.dataset = node.to_dataset().drop_vars(MASK_KEY)
        
        self.replot()

    def isMaskedVisible(self) -> bool:
        return self._view_masked_action.isChecked()
    
    def setIsMaskedVisible(self, visible: bool) -> None:
        self._view_masked_action.setChecked(visible)
        self.refresh()

    def zero(self) -> None:
        xranges = self.visibleXRanges()
        xdim = self.xdim()
        for item, plot_data_var in zip(self._selected_data_var_items, self._selected_data_vars):
            node: xr.DataTree = item.node()
            data_var: xr.DataArray = item.data()
            coords = {dim: values for dim, values in self._selection_visible_coords.coords.items() if dim in node.dims}
            if xranges:
                xdata = node[xdim].values
                xmask = np.full(xdata.shape, False, dtype=bool)
                for xrange in xranges:
                    lb, ub = xrange
                    xmask[(xdata >= lb) & (xdata <= ub)] = True
                coords[xdim] = xdata[xmask]
            data_var.loc[coords] = 0
            if plot_data_var is not data_var:
                plot_data_var.loc[coords] = 0
        
        self.replot()

    def setConstant(self, constant = None) -> None:
        if constant is None:
            constant, ok = QInputDialog.getText(self, "Set Constant", "Enter constant value (and units if applicable):", text="1.0 units")
            if not ok:
                return
        
        try:
            qconstant = pint.Quantity(constant)
        except:
            return

        xranges = self.visibleXRanges()
        xdim = self.xdim()
        for item, plot_data_var in zip(self._selected_data_var_items, self._selected_data_vars):
            node: xr.DataTree = item.node()
            data_var: xr.DataArray = item.data()
            coords = {dim: values for dim, values in self._selection_visible_coords.coords.items() if dim in node.dims}
            if xranges:
                xdata = node[xdim].values
                xmask = np.full(xdata.shape, False, dtype=bool)
                for xrange in xranges:
                    lb, ub = xrange
                    xmask[(xdata >= lb) & (xdata <= ub)] = True
                coords[xdim] = xdata[xmask]
            
            units = data_var.attrs.get('units', None)
            if units is not None:
                data_var.loc[coords] = qconstant.to(units).magnitude
            else:
                data_var.loc[coords] = qconstant.magnitude
            
            if plot_data_var is not data_var:
                units = plot_data_var.attrs.get('units', None)
                if units is not None:
                    plot_data_var.loc[coords] = qconstant.to(units).magnitude
                else:
                    plot_data_var.loc[coords] = qconstant.magnitude
        
        self.replot()

    def interpolate(self) -> None:
        xranges = self.visibleXRanges()
        if not xranges:
            return
        
        xdim = self.xdim()
        for plot in self._plots.flatten().tolist():
            graphs = [item for item in plot.listDataItems() if isinstance(item, PlotCurve)]
            data_graphs = [graph for graph in graphs if hasattr(graph, '_metadata') and graph._metadata.get('type', None) == 'data']
            for graph in data_graphs:
                item: XarrayDataTreeItem = graph._metadata.get('data_var_item', None)
                if item is None:
                    continue
                data_var: xr.DataArray = item.data()
                coords = graph._metadata['coords']
                coords[xdim] = data_var[xdim]
                ydata = data_var.sel(coords).squeeze(drop=True).data
                xdata = graph.xData
                for xrange in xranges:
                    lb, ub = xrange
                    li = np.searchsorted(xdata, lb, side='left')
                    ui = np.searchsorted(xdata, ub, side='right') - 1
                    if li >= ui:
                        continue
                    
                    lx = xdata[li]
                    ux = xdata[ui]
                    ly = ydata[li]
                    uy = ydata[ui]
                    ydata[li:ui+1] = np.interp(xdata[li:ui+1], [lx, ux], [ly, uy])
                data_var.loc[coords] = ydata
        
        self.refresh() # overkill?

    def filter(self) -> None:
        self.startPreview('filter')

    def curveFit(self) -> None:
        self.startPreview('curve fit')

    def measure(self) -> None:
        self.startPreview('measure')
    
    def startPreview(self, operation: str) -> None:
        for name, panel in self._preview_control_panels.items():
            if name == operation:
                panel.show()
                panel.raise_()
            else:
                panel.hide()
        
        self.updatePreview()
    
    def activePreview(self) -> str | None:
        for name, panel in self._preview_control_panels.items():
            if panel.isVisible():
                return name
    
    def isPreview(self) -> bool:
        for name, panel in self._preview_control_panels.items():
            if panel.isVisible():
                return panel.isPreview()
        return False

    def replot(self) -> None:
        """ Update all plots.
        """
        self.updatePlotData()
    
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
    
    def tiledDimensions(self) -> tuple[str | None, str | None, np.ndarray | None, np.ndarray | None]:
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
    
    def isDataPanelVisible(self) -> bool:
        return self._datatree_ROIs_splitter.isVisible()
    
    def setDataPanelVisible(self, visible: bool) -> None:
        self._datatree_ROIs_splitter.setVisible(visible)
        self._data_action.setChecked(visible)
    
    def onDataTreeSelectionChanged(self) -> None:
        print('\n\nonDataTreeSelectionChanged...')

        # selected data_vars
        selected_items = self._datatree_view.selectedItems(ordered=True)
        self._selected_data_var_items: list[XarrayDataTreeItem] = []
        item: XarrayDataTreeItem
        for item in selected_items:
            if item.isNode():
                child_item: XarrayDataTreeItem
                for child_item in item.children:
                    if child_item.isDataVar():
                        if child_item not in self._selected_data_var_items:
                            self._selected_data_var_items.append(child_item)
            elif item.isDataVar():
                if item not in self._selected_data_var_items:
                    self._selected_data_var_items.append(item)
        if not self._selected_data_var_items:
            self._invalidSelection(
                '''
                Empty Selection

                No data variables selected.
                
                Please select at least one data variable to plot.
                '''
            )
            return
        self._selected_data_vars: list[xr.DataArray] = [item.data() for item in self._selected_data_var_items]
        print(f'  _selected_data_var_items:')
        for item in self._selected_data_var_items:
            print(f'    {item.abspath()}')

        self._nodes_with_selected_data_vars: list[xr.DataTree] = []
        for item in self._selected_data_var_items:
            node: xr.DataTree = item.node()
            if xarray_utils.index_by_identity(self._nodes_with_selected_data_vars, node) == -1:
                self._nodes_with_selected_data_vars.append(node)
        print(f'  _nodes_with_selected_data_vars:')
        for node in self._nodes_with_selected_data_vars:
            print(f'    {node.path}')

        self._branch_root_nodes_for_selected_data_vars: list[xr.DataTree] = []
        for node in self._nodes_with_selected_data_vars:
            branch_root_node = xarray_utils.aligned_root(node)
            if xarray_utils.index_by_identity(self._branch_root_nodes_for_selected_data_vars, branch_root_node) == -1:
                self._branch_root_nodes_for_selected_data_vars.append(branch_root_node)
        print(f'  _branch_root_nodes_for_selected_data_vars:')
        for node in self._branch_root_nodes_for_selected_data_vars:
            print(f'    {node.path}')

        # shared dimensions across selection
        dims_per_data_var = [np.array(list(data_var.dims)) for data_var in self._selected_data_vars]
        self._selection_shared_dims = reduce(np.intersect1d, dims_per_data_var).tolist() if dims_per_data_var else []
        if not self._selection_shared_dims:
            self._invalidSelection(
                '''
                Alignment Conflict

                There is no single dimension that is shared by all selected data variables. Variables must share at least one common dimension in order to be plotted together.
                
                Please select data variables that share a common dimension.
                '''
            )
            return
        print(f'  _selection_shared_dims: {self._selection_shared_dims}')
        
        # ordered dimensions
        self._selection_ordered_dims = list(xarray_utils.ordered_dims_iter(self._selected_data_vars)) if self._selected_data_vars else []
        shared_dims = self._selection_shared_dims
        self._selection_shared_dims = [dim for dim in self._selection_ordered_dims if dim in shared_dims]
        print(f'  _selection_ordered_dims: {self._selection_ordered_dims}')

        # ensure xdim is one of the shared dimensions
        xdim = self.xdim()
        if xdim not in self._selection_shared_dims:
            # try to preserve previous xdim
            prev_xdim = getattr(self, '_prev_xdim', None)
            if prev_xdim in self._selection_shared_dims:
                xdim = self._xdim = prev_xdim
            else:
                self._prev_xdim = xdim
                try:
                    xdim = self._xdim = self._selection_shared_dims[0]
                except IndexError:
                    xdim = None
        print(f'  xdim: {xdim}')

        # convert selection to non-prefixed units for plotting in pyqtgraph
        self._selection_units: dict[str, str] = {}
        for i, data_var in enumerate(self._selected_data_vars):
            name = data_var.name
            data_var_changed = False
            units = data_var.attrs.get('units', None)
            # print(f'  {name}: {units}')
            if units is not None:
                try:
                    qdata = self.ureg.Quantity(data_var.data, units)
                    # qbase = qdata.to_base_units()
                    qbase = XarrayGraph.drop_prefixes(qdata)
                    base_units = str(qbase.units)
                    # print(f'  {name}: {units} -> {base_units}')
                    data_var = data_var.copy(deep=False, data=qbase.magnitude)
                    data_var.attrs['units'] = base_units
                    conversion_factor = self.ureg.Quantity(1, units).to(base_units).magnitude
                    data_var.attrs[TO_DISPLAY_UNITS_KEY] = conversion_factor
                    data_var_changed = True
                    units = base_units
                except:
                    pass
            
            if units is not None:
                if name not in self._selection_units:
                    self._selection_units[name] = units
                elif units != self._selection_units[name]:
                    self._invalidSelection(
                        f'''
                        Units Conflict

                        All variables and their coordinates of the same name across the selection must have the same units in order to be plotted together. If units differ, pint will attempt to convert to base units, but if conversion fails then the selection is considered invalid.

                        Data variables "{name}" have conflicting units.
                        '''
                    )
                    return
            
            for name, coord in tuple(data_var.coords.items()):
                units = coord.attrs.get('units', None)
                if np.issubdtype(coord.dtype, np.datetime64) or isinstance(coord.data[0], cftime.datetime):
                    # convert datetime objects to datetime64[s] integers as required by pyqtgraph DateAxisItem
                    datetime_values_for_pyqtgraph = coord.values.astype('datetime64[s]').astype(int)
                    coord = coord.copy(data=datetime_values_for_pyqtgraph)
                    coord.attrs['units'] = 'datetime64[s]'
                    data_var = data_var.assign_coords({name: coord})
                    data_var_changed = True
                    units = 'datetime64[s]'
                elif units is not None:
                    try:
                        qdata = self.ureg.Quantity(coord.data, units)
                        # qbase = qdata.to_base_units()
                        qbase = XarrayGraph.drop_prefixes(qdata)
                        base_units = str(qbase.units)
                        # print(f'  {name}: {units} -> {base_units}')
                        coord = coord.copy(deep=False, data=qbase.magnitude)
                        coord.attrs['units'] = base_units
                        conversion_factor = self.ureg.Quantity(1, units).to(base_units).magnitude
                        coord.attrs[TO_DISPLAY_UNITS_KEY] = conversion_factor
                        data_var = data_var.assign_coords({name: coord})
                        data_var_changed = True
                        units = base_units
                    except:
                        pass
                
                if units is not None:    
                    if name not in self._selection_units:
                        self._selection_units[name] = units
                    elif units != self._selection_units[name]:
                        self._invalidSelection(
                            f'''
                            Units Conflict

                            All variables and their coordinates of the same name across the selection must have the same units in order to be plotted together. If units differ, pint will attempt to convert to base units, but if conversion fails then the selection is considered invalid.

                            Coordinate "{name}" of variable "{data_var.name}" has conflicting units.
                            '''
                        )
                        return
            
            if data_var_changed:
                self._selected_data_vars[i] = data_var

        # # common units across selection
        # # if units conflict, attempt to convert to base units using pint
        # self._selection_units: dict[str, str] = {}
        # names_with_units_conflict = set()
        # for i, data_var in enumerate(self._selected_data_vars):
        #     units = data_var.attrs.get('units', None)
        #     if units is not None:
        #         existing_units = self._selection_units.get(data_var.name, None)
        #         if existing_units is None:
        #             self._selection_units[data_var.name] = units
        #         elif units != existing_units:
        #             names_with_units_conflict.add(data_var.name)
        #     coord: xr.DataArray
        #     for name, coord in tuple(data_var.coords.items()):
        #         if np.issubdtype(coord.dtype, np.datetime64) or isinstance(coord.data[0], cftime.datetime):
        #             # convert datetime objects to datetime64[s] integers as required by pyqtgraph DateAxisItem
        #             datetime_values_for_pyqtgraph = coord.values.astype('datetime64[s]').astype(int)
        #             coord = coord.copy(data=datetime_values_for_pyqtgraph)
        #             coord.attrs['units'] = 'datetime64[s]'
        #             self._selected_data_vars[i] = data_var.assign_coords({name: coord})
        #         # check units for conflict
        #         units = coord.attrs.get('units', None)
        #         if units is not None:
        #             existing_units = self._selection_units.get(name, None)
        #             if existing_units is None:
        #                 self._selection_units[name] = units
        #             elif units != existing_units:
        #                 names_with_units_conflict.add(name)
        # if names_with_units_conflict:
        #     for i, data_var in enumerate(self._selected_data_vars):
        #         if (data_var.name in names_with_units_conflict) and ('units' in data_var.attrs):
        #             try:
        #                 # print('DATA_VAR UNITS CONFLICT:', data_var.name, data_var.attrs.get('units', None))
        #                 data = data_var.data
        #                 units = data_var.attrs.get('units', None)
        #                 qdata = self.ureg.Quantity(data, units)
        #                 # print('QVAR UNITS:', qdata.units)
        #                 qdata = qdata.to_base_units()
        #                 # print('BASE UNITS:', qdata.units)
        #                 units = str(qdata.units)
        #                 data_var = data_var.copy(deep=False, data=qdata.magnitude)
        #                 data_var.attrs['units'] = units
        #                 self._selected_data_vars[i] = data_var
        #                 self._selection_units[data_var.name] = units
        #                 # print('CONVERTED UNITS:', data_var.name, units)
        #             except:
        #                 item = self._selected_data_var_items[i]
        #                 self._invalidSelection(
        #                     f'''
        #                     Units Conflict

        #                     All variables and their coordinates of the same name across the selection must have the same units in order to be plotted together. If units differ, pint will attempt to convert to base units, but if conversion fails then the selection is considered invalid.

        #                     Failed to convert data variable "{item.abspath()}" to base units.
        #                     '''
        #                 )
        #                 return
        #         coord: xr.DataArray
        #         for coord in data_var.coords.values():
        #             if coord.name in names_with_units_conflict and 'units' in coord.attrs:
        #                 try:
        #                     # print('COORD UNITS CONFLICT:', coord.name, coord.attrs.get('units', None))
        #                     data = coord.data
        #                     units = coord.attrs.get('units', None)
        #                     qdata = self.ureg.Quantity(data, units)
        #                     # print('QVAR UNITS:', qdata.units)
        #                     qdata = qdata.to_base_units()
        #                     # print('BASE UNITS:', qdata.units)
        #                     units = str(qdata.units)
        #                     coord = coord.copy(deep=False, data=qdata.magnitude)
        #                     coord.attrs['units'] = units
        #                     data_var = data_var.assign_coords({coord.name: coord})
        #                     self._selected_data_vars[i] = data_var
        #                     self._selection_units[coord.name] = units
        #                     # print('CONVERTED UNITS:', coord.name, units)
        #                 except:
        #                     item = self._selected_data_var_items[i]
        #                     self._invalidSelection(
        #                         f'''
        #                         Units Conflict

        #                         All variables and their coordinates of the same name across the selection must have the same units in order to be plotted together. If units differ, pint will attempt to convert to base units, but if conversion fails then the selection is considered invalid.

        #                         Failed to convert coordinate "{coord.name}" in data variable "{item.abspath()}" to base units.
        #                         '''
        #                     )
        #                     return
        # # print(f'_selection_units: {self._selection_units}')

        # selection combined coords (index (dim) coords only)
        selected_coords = []
        for data_var in self._selected_data_vars:
            non_index_coords = [name for name in data_var.coords.keys() if name not in data_var.dims]
            coords_ds = xr.Dataset(
                coords=data_var.coords
            ).drop_vars(non_index_coords)
            for dim in data_var.dims:
                if dim not in coords_ds.coords:
                    coords_ds = coords_ds.assign_coords({dim: range(data_var.sizes[dim])})
            selected_coords.append(coords_ds)
        if selected_coords:
            try:
                self._selection_combined_coords: xr.Dataset = xr.merge(selected_coords, compat='no_conflicts', join='outer')
            except Exception as err:
                self._invalidSelection(
                    f'''
                    Alignment Conflict

                    All selected data variables must align in order to be plotted together. If there are any alignment conflicts between coordinates of the same name across the selection, then the selection is considered invalid.

                    Failed to merge combined coordinates for entire selection: {err}
                    '''
                )
                return
        else:
            self._selection_combined_coords = None
        # print(f'  _selection_combined_coords: {self._selection_combined_coords}')
        
        # unique data_var names
        self._selected_data_var_unique_names = np.unique([var.name for var in self._selected_data_vars]).tolist()
        print(f'  _selected_data_var_unique_names: {self._selected_data_var_unique_names}')

        # if we got here, we have a valid selection
        self._data_var_views_splitter.setVisible(True)
        self._message_label.setVisible(False)
        self.updateDimItersInToolbar()
        self.updateROIsView()
        self.onDataSliceChanged()
   
    def _invalidSelection(self, msg: str) -> None:
        self._selected_data_var_items = []
        self._selected_data_vars = []
        self._selection_ordered_dims = []
        self._selection_units = {}
        self._selection_combined_coords = None
        self._selected_data_var_unique_names = []

        self._data_var_views_splitter.setVisible(False)
        msg = textwrap.dedent(msg).strip()
        self._message_label.setText(msg)
        self._message_label.setVisible(True)

        self.updateDimItersInToolbar()
        self.updateROIsView()
        self.onDataSliceChanged()
    
    def onDataSliceChanged(self) -> None:
        """ Handle selection changes in dimension iterators.
        """
        print('\n'*2, 'onDataSliceChanged...')

        # get coords for current slice of selected variables
        if self._selection_combined_coords is None:
            self._selection_visible_coords = None
        else:
            iter_coords = {}
            for dim in self._dim_iter_widgets:
                if self._dim_iter_widgets[dim]['active']:
                    widget: DimIterWidget = self._dim_iter_widgets[dim]['widget']
                    iter_coords[dim] = widget.selectedCoords()
            if iter_coords:
                self._selection_visible_coords: xr.Dataset = self._selection_combined_coords.sel(iter_coords)#, method='nearest')
            else:
                self._selection_visible_coords: xr.Dataset = self._selection_combined_coords
        # print(f'_selection_visible_coords: {self._selection_visible_coords}')
        
        self.updatePlotGrid()
    
    def onRoiSelectionChanged(self) -> None:
        self.updatePlotRois()
   
    def onRoiTypeChanged(self) -> None:
        self._ROI_selection_button.setIcon(self._ROI_action_group.checkedAction().icon())
        self.stopDrawingRois()
        self.startDrawingRois()
    
    def onRoiAdded(self, roiItem: QGraphicsObject) -> None:
        if type(roiItem) is XAxisRegion:
            roi = {
                'type': 'region',
                'position': {
                    self.xdim(): sorted(roiItem.getRegion())
                },
                'movable': True
            }
        elif type(roiItem) is VLine:
            roi = {
                'type': 'region',
                'position': {
                    self.xdim(): roiItem.value()
                },
                'movable': True
            }
        else:
            return
        
        roiItem._ROI = roi
        # view: View = roiItem.getViewBox()
        # view.removeItem(roiItem)
        # roiItem.deleteLater()

        rois = self.rois()
        rois.append(roi)
        self.stopDrawingRois()
        selectedROIs: list[dict] = self._ROIs_view.selectedAnnotations()
        selectedROIs.append(roi)
        # Defer tree/model selection updates until the current graphics-scene event stack returns.
        QTimer.singleShot(0, lambda selectedROIs=selectedROIs: self._finishAddingRoi(selectedROIs))

    def _finishAddingRoi(self, selectedROIs: list[dict]) -> None:
        self.updateROIsView() # overkill, but works for now
        with QSignalBlocker(self._ROIs_view):
            self._ROIs_view.setSelectedAnnotations(selectedROIs)
        self.updatePlotRois() # overkill, but works for now
        if self.isPreview():
            self.updatePreview()

    def _onRoiPlotItemChanged(self, roiItem: QGraphicsObject) -> None:
        """ Handle changes to ROI plot object.
        """
        roi = getattr(roiItem, '_ROI', None)
        if roi is None:
            return
        
        self._updateRoiDataFromPlotItem(roiItem, roi)

        # update same ROI in other plots
        for plot in self._plots.flatten().tolist():
            like_items = [item for item in plot.vb.allChildren() if (getattr(item, '_ROI', None) is roi) and (item is not roiItem)]
            for like_item in like_items:
                self._updateRoiDataFromPlotItem(like_item, roi)
        
        # update ROI tree view (only item for ROI)
        model: AnnotationTreeModel = self._ROIs_view.model()
        for item in model.rootItem().subtree_depth_first():
            if getattr(item, '_data', None) is roi:
                index: QModelIndex = model.indexFromItem(item)
                model.dataChanged.emit(index, index)
                break
        
        if self.isPreview():
            self.updatePreview()

    def _onNotesChanged(self) -> None:
        """ Handle the event when the notes text edit is changed.

        !!! This is overkill, but it works for now.
        """
        dt = self.datatree()
        dt.attrs[NOTES_KEY] = self._notes_view.toPlainText()

    def updateDimItersInToolbar(self) -> None:
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
            # self._before_dim_iters_spacer.setText('Selected data variables are not aligned.')
            self._before_dim_iters_separator_action.setVisible(True)
            self._dim_iters_spacer_action.setVisible(True)
            return
        # else:
        #     self._before_dim_iters_spacer.setText('')
        
        # update or create dim iter widgets and insert actions into toolbar
        iter_dims = [dim for dim in ordered_dims if (dim != self.xdim()) and (coords.sizes[dim] > 1)]
        for dim in iter_dims:
            if dim not in self._dim_iter_widgets:
                widget = DimIterWidget()
                widget.setDim(dim)
                widget._spinbox.indicesChanged.connect(lambda: self.onDataSliceChanged())
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
        
        self._dim_iters_spacer_action.setVisible(len(iter_dims) == 0)
        self._before_dim_iters_separator_action.setVisible(len(iter_dims) == 0)
    
    def updatePlotGrid(self) -> None:
        """ Update plot grids for selected variables and current plot tiling.
        """
        print('\n'*2, 'updatePlotGrid...')

        # one plot grid per selected variable
        n_data_var_names = len(self._selected_data_var_unique_names)
        while self._data_var_views_splitter.count() < n_data_var_names:
            grid = PlotGrid()
            grid.setHasRegularLayout(True)
            self._data_var_views_splitter.addWidget(grid)
        while self._data_var_views_splitter.count() > n_data_var_names:
            index = self._data_var_views_splitter.count() - 1
            widget = self._data_var_views_splitter.widget(index)
            widget.setParent(None)
            widget.deleteLater()
        
        # grid tiling
        vdim, hdim, vcoords, hcoords = self.tiledDimensions()
        n_grid_rows, n_grid_cols = 1, 1
        if vdim is not None:
            n_grid_rows = vcoords.size
        if hdim is not None:
            n_grid_cols = hcoords.size

        # tile grids and store plots in array (if needed)
        if not hasattr(self, '_plots') or self._plots.shape != (n_data_var_names, n_grid_rows, n_grid_cols):
            self._plots = np.empty((n_data_var_names, n_grid_rows, n_grid_cols), dtype=object)
            self._plot_grids: list[PlotGrid] = [self._data_var_views_splitter.widget(i) for i in range(n_data_var_names)]
            for i, grid in enumerate(self._plot_grids):
                data_var_name = self._selected_data_var_unique_names[i]
                if grid.rowCount() != n_grid_rows or grid.columnCount() != n_grid_cols:
                    grid.setGrid(n_grid_rows, n_grid_cols)
                for row in range(grid.rowCount()):
                    for col in range(grid.columnCount()):
                        plot: Plot = grid.getItem(row, col)
                        self._plots[i, row, col] = plot
                if i == n_data_var_names - 1:
                    grid.setAxisLabelAndTickVisibility(xlabel_rows=[-1], xtick_rows=[-1], ylabel_columns=[0], ytick_columns=[0])
                else:
                    grid.setAxisLabelAndTickVisibility(xlabel_rows=[], xtick_rows=[-1], ylabel_columns=[0], ytick_columns=[0])
                grid.applyRegularLayout()
        
        self.updatePlotMetadata()
        self.updatePlotAxisLabels()
        self.updatePlotAxisTickFont()
        self.updatePlotAxisLinks()
        self.replot()
    
    def updatePlotMetadata(self) -> None:
        """ Update metadata stored in each plot.
        """
        print('updatePlotMetadata...')
        vdim, hdim, vcoords, hcoords = self.tiledDimensions()
        n_vars, n_grid_rows, n_grid_cols = self._plots.shape
        for i in range(n_vars):
            var_name = self._selected_data_var_unique_names[i]
            # yunits = self._selection_units.get(var_name, None)
            vis_coords = self._selection_visible_coords.copy(deep=False)
            
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
                    
                    # print(f'var_name: {var_name}')
                    # print(f'plot_coords: {plot_coords}')
                    # print(f'plot_coords_dict: {plot_coords_dict}')
                    
                    plot = self._plots[i, row, col]
                    plot._metadata = {
                        'data_vars': [var_name],
                        'grid_row': row,
                        'grid_col': col,
                        'coords': plot_coords,
                        'non_xdim_coord_permutations': coord_permutations(plot_coords_dict),
                    }
    
    def updatePlotAxisLabels(self) -> None:
        """ Update axis labels for each plot (use settings font).
        """
        print('updatePlotAxisLabels...')
        xunits = self._selection_units.get(self.xdim(), None)
        axis_label_fontsize = 12 #self._axis_label_fontsize_spinbox.value()
        axis_label_style = {'color': 'rgb(0, 0, 0)', 'font-size': f'{axis_label_fontsize}pt'}

        vdim, hdim, vcoords, hcoords = self.tiledDimensions()
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

    def updatePlotAxisTickFont(self) -> None:
        """ Update axis tick labels for each plot (use settings font).
        """
        print('updatePlotAxisTickFont...')
        axis_tick_font = QFont()
        axis_tick_fontsize = 10 #self._axis_tick_fontsize_spinbox.value()
        axis_tick_font.setPointSize(axis_tick_fontsize)
        
        for plot in self._plots.flatten().tolist():
            plot.getAxis('left').setTickFont(axis_tick_font)
            plot.getAxis('bottom').setTickFont(axis_tick_font)

    def updatePlotAxisLinks(self) -> None:
        """ Update axis linking for selected variables and current plot tiling.
        """
        print('updatePlotAxisLinks...')
        n_vars, n_grid_rows, n_grid_cols = self._plots.shape
        for i in range(n_vars):
            for row in range(n_grid_rows):
                for col in range(n_grid_cols):
                    plot = self._plots[i, row, col]
                    if (i != 0) or (row != 0) or (col != 0):
                        plot.setXLink(self._plots[0, 0, 0])
                    if (row > 0) or (col > 0):
                        plot.setYLink(self._plots[i, 0, 0])

    def updatePlotData(self, plots: list[Plot] = None) -> None:
        """ Update graphs in each plot to show current datatree selection.
        """
        print('\n'*2, 'updatePlotData...')
        if plots is None:
            plots = self._plots.flatten().tolist()

        dt: xr.DataTree = self.datatree()
        xdim: str = self.xdim()
        if (xdim is None) or (self._selection_combined_coords is None) or (xdim not in self._selection_combined_coords):
            return
        
        # datetime xdim values?
        is_xdim_datetime = self._selection_units.get(xdim, None) == 'datetime64[s]'

        # categorical (string) xdim values?
        is_xdim_categorical = False
        all_xticks = None  # will use default ticks
        all_xdata = self._selection_combined_coords[xdim].values
        if not is_xdim_datetime and not np.issubdtype(all_xdata.dtype, np.number):
            is_xdim_categorical = True
            all_xtick_values = np.arange(len(all_xdata))
            all_xtick_labels = all_xdata  # str xdim values
            all_xticks = [list(zip(all_xtick_values, all_xtick_labels))]
        
        cmap = self._settings['colormap']

        bottomAxisChanged = False
        for plot in plots:
            view: View = plot.getViewBox()

            # update bottom axis (datetime or not)
            bottomAxis: pg.AxisItem = plot.getAxis('bottom')
            if is_xdim_datetime and not isinstance(bottomAxis, pg.DateAxisItem):
                bottomAxis = pg.DateAxisItem(orientation='bottom')
                plot.setAxisItems({'bottom': bottomAxis})
                bottomAxisChanged = True
            elif not is_xdim_datetime and isinstance(bottomAxis, pg.DateAxisItem):
                bottomAxis = pg.AxisItem(orientation='bottom')
                plot.setAxisItems({'bottom': bottomAxis})
                bottomAxisChanged = True

            # set xticks (in case change between numerical and categorical)
            bottomAxis.setTicks(all_xticks)
            
            # existing graphs in plot
            graphs = [item for item in plot.listDataItems() if isinstance(item, PlotCurve)]
            data_graphs = [graph for graph in graphs if hasattr(graph, '_metadata') and graph._metadata.get('type', None) == 'data']
            masked_graphs = [graph for graph in graphs if hasattr(graph, '_metadata') and graph._metadata.get('type', None) == 'masked']

            data_count = 0
            masked_count = 0
            color_index = 0
            color = cmap[color_index]
            item: XarrayDataTreeItem
            data_var: xr.DataArray
            for item, data_var in zip(self._selected_data_var_items, self._selected_data_vars):
                # print(f'Plotting data variable: {item.abspath()}...')
                var_name = data_var.name
                if var_name not in plot._metadata['data_vars']:
                    continue
                node: xr.DataTree = item.node()
                
                # search ancestors for mask data
                mask = None
                if var_name != MASK_KEY:
                    branch_root_node = xarray_utils.aligned_root(node)
                    node_ = node
                    while node_:
                        if MASK_KEY in node_.data_vars:
                            mask = node_.data_vars[MASK_KEY]
                            break
                        if node_ is branch_root_node:
                            break
                        node_ = node_.parent
                    mask_node = node_
                
                non_xdim_coord_permutations = plot._metadata['non_xdim_coord_permutations']
                if len(non_xdim_coord_permutations) == 0:
                    non_xdim_coord_permutations = [{}]
                for coords in non_xdim_coord_permutations:
                    # print(f'  coords: {coords}...')
                    index_coords = {dim: values for dim, values in coords.items() if dim in data_var.dims}
                    nonindex_coords = {dim: values for dim, values in coords.items() if dim in data_var.coords and dim not in data_var.dims}
                    if index_coords:
                        data_var_slice = data_var.sel(index_coords)
                    else:
                        data_var_slice = data_var
                    for name, coord in nonindex_coords.items():
                        try:
                            data_var_slice = data_var_slice.where(data_var_slice.coords[name] == coord, drop=True)
                        except:
                            pass
                    data_var_slice = data_var_slice.reset_coords(drop=True).squeeze(drop=True)
                    if xdim in data_var_slice.coords:
                        xdim_coord_slice = data_var_slice.coords[xdim]
                        xdata: np.ndarray = xdim_coord_slice.values
                    else:
                        xdata: np.ndarray = np.arange(data_var_slice.sizes[xdim])
                    ydata: np.ndarray = data_var_slice.values
                    if np.all(np.isnan(ydata)):
                        continue
                    # print(f'    xdata: {xdata}')
                    # print(f'    ydata: {ydata}')

                    # categorical xdim values?
                    if is_xdim_categorical:
                        intersect, xdata_indices, all_xtick_labels_indices = np.intersect1d(xdata, all_xtick_labels, assume_unique=True, return_indices=True)
                        xdata = np.sort(all_xtick_labels_indices)
                        # xdim_coord_slice = data_var_slice.coords[xdim].copy(data=xdata)

                    # graph name is path plus non-xdim coords
                    name = item.abspath()
                    if index_coords:
                        name += '[' + ','.join([f'{dim}={index_coords[dim]}' for dim in index_coords]) + ']'
                    
                    # mask data?
                    mask_slice = None
                    if (mask is not None) and (var_name != MASK_KEY):
                        if index_coords:
                            mask_slice = mask.sel(index_coords)
                        else:
                            mask_slice = mask
                        for name, coord in nonindex_coords.items():
                            try:
                                mask_slice = mask_slice.where(mask_slice.coords[name] == coord, drop=True)
                            except:
                                pass
                        mask_slice = mask_slice.reset_coords(drop=True).squeeze(drop=True)
                        raw_ydata = ydata
                        ydata = ydata.copy() # don't overwrite original data
                        ydata[mask_slice.values] = np.nan

                        # graph masked data
                        if self.isMaskedVisible():
                            if len(masked_graphs) > masked_count:
                                # update existing data in plot
                                masked_graph = masked_graphs[masked_count]
                                masked_graph.setData(x=xdata, y=raw_ydata)
                            else:
                                # add new data to plot
                                masked_graph = PlotCurve(x=xdata, y=raw_ydata)
                                plot.addItem(masked_graph)
                                masked_graphs.append(masked_graph)
                            masked_count += 1
                            masked_graph._metadata = {
                                'type': 'masked',
                                'mask_node': mask_node,
                                'data_var_item': item,
                                'plot_data_var': data_var,
                                'coords': coords,
                            }
                            masked_graph.setZValue(0)
                            masked_graph.setName(name + ' masked')
                            masked_graph.setPen(pg.mkPen(color=MASK_COLOR, width=1))
                    
                    # graph data
                    if len(data_graphs) > data_count:
                        # update existing data in plot
                        data_graph = data_graphs[data_count]
                        data_graph.setData(x=xdata, y=ydata)
                    else:
                        # add new data to plot
                        data_graph = PlotCurve(x=xdata, y=ydata)
                        plot.addItem(data_graph)
                        data_graphs.append(data_graph)
                    data_count += 1
                    data_graph._metadata = {
                        'type': 'data',
                        'data_var_item': item,
                        'plot_data_var': data_var,
                        'coords': coords,
                        'units': data_var.attrs.get('units', None)
                    }
                    data_graph.setZValue(1)
                    data_graph.setName(name)
                    data_graph.setPen(pg.mkPen(color=color, width=1))
                
                # to next data_var in datatree
                color_index += 1
                color = cmap[color_index]
            
            # remove extra graph items from plot
            cleanup_graphs = [(data_graphs, data_count), (masked_graphs, masked_count)]
            for graphs, count in cleanup_graphs:
                while len(graphs) > count:
                    graph = graphs.pop()
                    plot.removeItem(graph)
                    graph.deleteLater()

        if bottomAxisChanged:
            # print('Bottom axis type changed, updating axis links...')
            self.updatePlotAxisLabels()
            self.updatePlotAxisTickFont()
            self.updatePlotAxisLinks()
        
        self.updatePreview(plots)
    
    def updatePreview(self, plots: list[Plot] = None, force: bool = False) -> None:
        if plots is None:
            plots = self._plots.flatten().tolist()

        preview_type = self.activePreview()
        if preview_type is None:
            is_preview = False
        else:
            preview_control_panel = self._preview_control_panels[preview_type]
            is_preview = force or preview_control_panel.isPreview()
            if is_preview:
                xranges = self.visibleXRanges()
        
        for plot in plots:
            xaxis: pg.AxisItem = plot.getAxis('bottom')
            if isinstance(xaxis, pg.DateAxisItem):
                xunits = 's'
            else:
                xunits = xaxis.labelUnits
            
            # existing graphs in plot
            graphs = [item for item in plot.listDataItems() if isinstance(item, PlotCurve)]
            data_graphs = [graph for graph in graphs if hasattr(graph, '_metadata') and graph._metadata.get('type', None) == 'data']
            preview_graphs = [graph for graph in graphs if hasattr(graph, '_metadata') and graph._metadata.get('type', None) == 'preview']

            for graph in data_graphs:
                graph._metadata['preview'] = None

            preview_count = 0
            if is_preview:
                for graph in data_graphs:
                    xdata = graph.xData
                    ydata = graph.yData
                    # data_var_item = graph._metadata['data_var_item']
                    if preview_type == 'filter':
                        xpreview = xdata
                        ypreview = preview_control_panel.filter(xdata, ydata, self.ureg, xunits)
                    elif preview_type == 'curve fit':
                        xpreview = xdata
                        fit_params = preview_control_panel.fit(xdata, ydata, xranges)
                        ypreview = preview_control_panel.predict(xdata, fit_params, xranges)
                        if preview_control_panel.isResiduals():
                            ypreview = ydata - ypreview
                    elif preview_type == 'measure':
                        xy = preview_control_panel.measure(xdata, ydata, xranges)
                        xpreview = xy[:,0]
                        ypreview = xy[:,1]
                    else:
                        # not handled
                        continue

                    if len(preview_graphs) > preview_count:
                        # update existing data in plot
                        preview_graph = preview_graphs[preview_count]
                        preview_graph.setData(x=xpreview, y=ypreview)
                    else:
                        # add new data to plot
                        preview_graph = PlotCurve(x=xpreview, y=ypreview)
                        plot.addItem(preview_graph)
                        preview_graphs.append(preview_graph)
                    preview_count += 1
                    preview_graph._metadata = {
                        'type': 'preview',
                        'operation': preview_type,
                        'data_var_item': graph._metadata['data_var_item'],
                        'coords': graph._metadata['coords'],
                        'units': graph._metadata['units'],
                    }
                    preview_graph.setZValue(2)
                    preview_graph.setName(graph.name() + f" ({preview_type})")
                    if preview_type == 'measure':
                        preview_graph.setPen(None)
                        preview_graph.setSymbol('o')
                        preview_graph.setSymbolSize(8)
                        preview_graph.setSymbolPen(pg.mkPen(color=PREVIEW_COLOR, width=2))
                    else:
                        preview_graph.setPen(pg.mkPen(color=PREVIEW_COLOR, width=2))
                    graph._metadata['preview'] = preview_graph
            
            # remove extra graph items from plot
            cleanup_graphs = [(preview_graphs, preview_count)]
            for graphs, count in cleanup_graphs:
                while len(graphs) > count:
                    graph = graphs.pop()
                    plot.removeItem(graph)
                    graph.deleteLater()
    
    def savePreview(self, plots: list[Plot] = None, result_name: str = None) -> None:
        print('\n'*2, 'savePreview...')
        if plots is None:
            plots = self._plots.flatten().tolist()
        
        if result_name is None:
            preview_type = self.activePreview()
            preview_panel = self._preview_control_panels[preview_type]
            if preview_type == 'filter':
                filter_type = preview_panel.filterType()
                cutoff = preview_panel.cutoffString()
                result_name = f'{filter_type} {cutoff} Filter'
            elif preview_type == 'curve fit':
                fit_type = preview_panel.fitType()
                result_name = f'{fit_type} Fit'
            elif preview_type == 'measure':
                measure_type = preview_panel.measureType()
                result_name = f'{measure_type}'
            result_name, ok = QInputDialog.getText(self, 'Save Preview', 'Result Name:', text=result_name)
            result_name = result_name.strip()
            if not ok or not result_name:
                return
        
        if not self.isPreview():
            self.updatePreview(force=True)
        
        dt = self.datatree()
        xdim = self.xdim()
        result_paths: list[str] = []
        
        for plot in plots:
            xaxis: pg.AxisItem = plot.getAxis('bottom')
            if isinstance(xaxis, pg.DateAxisItem):
                xunits = 's'
            else:
                xunits = xaxis.labelUnits
            yaxis: pg.AxisItem = plot.getAxis('left')
            yunits = yaxis.labelUnits
            
            # existing graphs in plot
            graphs = [item for item in plot.listDataItems() if isinstance(item, PlotCurve)]
            data_graphs: list[PlotCurve] = [graph for graph in graphs if hasattr(graph, '_metadata') and graph._metadata.get('type', None) == 'data']
            for graph in data_graphs:
                preview_graph: PlotCurve = graph._metadata.get('preview', None)
                if preview_graph is None:
                    continue
                data_var_item: XarrayDataTreeItem = graph._metadata['data_var_item']
                data_var: xr.DataArray = data_var_item.data()
                data_var_units = data_var.attrs.get('units', None)
                plot_data_var: xr.DataArray = graph._metadata['plot_data_var']
                plot_data_var_units = plot_data_var.attrs.get('units', None)
                result_path = data_var_item.node().path.rstrip('/') + f'/{result_name}/{data_var.name}'
                print(result_path, plot_data_var_units, data_var_units)
                if result_path not in result_paths:
                    result_paths.append(result_path)
                coords: XarrayDataTreeItem = graph._metadata['coords']
                try:
                    result_var = dt[result_path]
                except KeyError:
                    blank = np.full(data_var.shape, np.nan)
                    result_var = data_var.copy(data=blank)
                    dt[result_path] = result_var
                if data_var_units and (plot_data_var_units != data_var_units):
                    conversion_factor = (1.0 * self.ureg(plot_data_var_units)).to(data_var_units).magnitude
                    result_var.loc[coords] = preview_graph.yData * conversion_factor
                else:
                    result_var.loc[coords] = preview_graph.yData
        
        self.refresh() # overkill?
        selected_items: list[XarrayDataTreeItem] = self._datatree_view.selectedItems(ordered=True)
        selected_paths = [item.abspath() for item in selected_items]
        new_selection = False
        model: XarrayDataTreeModel = self._datatree_view.model()
        root_item = model.rootItem()
        for path in result_paths:
            if path not in selected_paths:
                selected_items.append(root_item[path])
                new_selection = True
        if new_selection:
            self._datatree_view.setSelectedItems(selected_items)

    def updatePlotRois(self, plots: list[Plot] = None) -> None:
        if plots is None:
            plots = self._plots.flatten().tolist()
        selectedRois = self._ROIs_view.selectedAnnotations()

        # remove all current ROI objects
        self.removeRoisFromPlots(plots=plots)

        if self.isRoisVisible():
            # add selected ROI objects
            self.addRoisToPlots(selectedRois, plots)

    def _updateRoiPlotItemFromData(self, roiItem: QGraphicsObject, data: dict) -> None:
        """ Apply ROI data to plotted ROI object.
        """
        if isinstance(roiItem, XAxisRegion):
            region = data['position'][self.xdim()]
            # print(f"Setting region: {region}")
            roiItem.setRegion(region)
            roiItem.setMovable(data.get('movable', False))
            roiItem.setText(data.get('text', ''))
            # item.setFormat(data.get('format', {}))
        elif isinstance(roiItem, VLine):
            pos = data['position'][self.xdim()]
            # print(f"Setting position: {pos}")
            roiItem.setValue(pos)
            roiItem.setMovable(data.get('movable', False))
            # roiItem.setText(data.get('text', ''))
            # item.setFormat(data.get('format', {}))

    def _updateRoiDataFromPlotItem(self, roiItem: QGraphicsObject, data: dict) -> None:
        """ Update ROI data from plotted ROI object.
        """
        if isinstance(roiItem, XAxisRegion):
            data['position'] = {self.xdim(): sorted(roiItem.getRegion())}
            data['movable'] = roiItem.movable
            data['text'] = roiItem.text()
            # data['format'] = item.getFormat()
        elif isinstance(roiItem, VLine):
            data['position'] = {self.xdim(): roiItem.value()}
            data['movable'] = roiItem.movable
            # data['text'] = roiItem.text()
            # data['format'] = item.getFormat()

    def _setupRoiPlotItem(self, item) -> None:
        """ Signals/Slots and properties for ROI plot item.
        """
        if isinstance(item, XAxisRegion):
            item.sigRegionChanged.connect(lambda item=item: self._onRoiPlotItemChanged(item))
            item.sigRegionDragFinished.connect(lambda item=item: self._onRoiPlotItemChanged(item))
            item.sigEditingFinished.connect(lambda item=item: self._onRoiPlotItemChanged(item))
            # item.sigDeletionRequested.connect(lambda item=item: self.deleteROIs(item._ROI))
            item.sigRegionDragFinished.connect(lambda: self.updateROIsView())
            item.sigEditingFinished.connect(lambda: self.updateROIsView())
            item.setZValue(0)
        elif isinstance(item, VLine):
            item.sigPositionChanged.connect(lambda item=item: self._onRoiPlotItemChanged(item))
            # item.sigPositionDragFinished.connect(lambda item=item: self._onRoiPlotItemChanged(item))
            # item.sigEditingFinished.connect(lambda item=item: self._onRoiPlotItemChanged(item))
            # item.sigDeletionRequested.connect(lambda item=item: self.deleteROIs(item._ROI))
            # item.sigPositionDragFinished.connect(lambda: self.updateROIsView())
            # item.sigEditingFinished.connect(lambda: self.updateROIsView())
            item.setZValue(0)

    def updateROIsView(self) -> None:
        rois = self.rois()
        selectedRois = [roi for roi in self._ROIs_view.selectedAnnotations() if roi in rois]
        self._ROIs_view.setAnnotations(rois)
        self._ROIs_view.setSelectedAnnotations(selectedRois)
    
    def startDrawingRois(self) -> None:
        roiType = self.selectedRoiType()
        roiToGraphicsItemTypeMap = {
            'Event': VLine,
            'Range': XAxisRegion,
        }
        graphicsItemType = roiToGraphicsItemTypeMap.get(roiType, None)
        if graphicsItemType is None:
            return
        for plot in self._plots.flatten().tolist():
            view: View = plot.getViewBox()
            view.sigItemAdded.connect(self.onRoiAdded)
            view.startDrawingItemsOfType(graphicsItemType)
        with QSignalBlocker(self._ROI_selection_button):
            self._ROI_selection_button.setChecked(True)
    
    def stopDrawingRois(self) -> None:
        for plot in self._plots.flatten().tolist():
            view: View = plot.getViewBox()
            view.stopDrawingItems()
            view.sigItemAdded.disconnect(self.onRoiAdded)
        with QSignalBlocker(self._ROI_selection_button):
            self._ROI_selection_button.setChecked(False)

    def _initActions(self) -> None:
        super()._initActions()

        text_color = QApplication.palette().color(QPalette.ColorRole.Text)
        faded_text_color = QColor(text_color)
        faded_text_color.setAlpha(100)
        # highlight_color = QApplication.palette().color(QPalette.ColorRole.Highlight)
        
        self._data_action = QAction(
            icon=qta.icon('mdi.file-tree', color=faded_text_color, color_on=text_color),
            iconVisibleInMenu=False,
            text='Data',
            toolTip='DataTree & ROIs',
            checkable=True, 
            checked=True,
            triggered=lambda checked: self.setDataPanelVisible(checked)
        )

        self._home_action = QAction(
            icon=qta.icon('mdi.home'),
            iconVisibleInMenu=False,
            text='Home',
            toolTip='Autoscale',
            shortcut=QKeySequence('A'),
            triggered=lambda: self.autoscale()
        )

        self._notes_action = QAction(
            icon=qta.icon('mdi6.text-box-edit-outline'),
            iconVisibleInMenu=True,
            text='Notes',
            toolTip='Notes',
            checkable=False,
            # shortcut=QKeySequence('N'),
            # shortcutVisibleInContextMenu=True,
            triggered=lambda checked: self.notes()
        )

        self._view_ROIs_action = QAction(
            text='ROIs',
            toolTip='Show ROIs',
            checkable=True,
            checked=True,
            shortcut=QKeySequence('W'),
            shortcutVisibleInContextMenu=True,
            triggered=lambda checked: self.updatePlotRois()
        )
        
        self._ROI_event_action = QAction(
            icon=qta.icon('fa6s.arrow-down-long'),
            iconVisibleInMenu=True,
            text='Event',
            toolTip='Create event ROI with mouse click',
            checkable=True,
            checked=False,
            shortcut=QKeySequence('E'),
            shortcutVisibleInContextMenu=True,
            triggered=lambda checked: self.onRoiTypeChanged()
        )
        self._ROI_event_icon = qta.icon('fa6s.arrow-down-long', color=faded_text_color, color_on=text_color)

        self._ROI_xrange_action = QAction(
            icon=qta.icon('mdi.arrow-expand-horizontal'),
            iconVisibleInMenu=True,
            text='Range',
            toolTip='Create range ROI with mouse click+drag',
            checkable=True,
            checked=True,
            shortcut=QKeySequence('R'),
            shortcutVisibleInContextMenu=True,
            triggered=lambda checked: self.onRoiTypeChanged()
        )
        self._ROI_xrange_icon = qta.icon('mdi.arrow-expand-horizontal', color=faded_text_color, color_on=text_color)

        self._mask_action = QAction(
            text='Mask',
            toolTip='Mask',
            checkable=False,
            shortcut=QKeySequence('M'),
            shortcutVisibleInContextMenu=True,
            triggered=lambda checked: self.mask()
        )

        self._unmask_action = QAction(
            text='Unmask',
            toolTip='Unmask',
            checkable=False,
            shortcut=QKeySequence('U'),
            shortcutVisibleInContextMenu=True,
            triggered=lambda checked: self.unmask()
        )

        self._view_masked_action = QAction(
            text='Masked',
            toolTip='Show Masked',
            checkable=True,
            checked=False,
            shortcut=QKeySequence('Y'),
            shortcutVisibleInContextMenu=True,
            triggered=lambda checked: self.refresh()
        )

        self._interpolate_action = QAction(
            text='Interpolate',
            toolTip='Interpolate',
            checkable=False,
            shortcut=QKeySequence('I'),
            shortcutVisibleInContextMenu=True,
            triggered=lambda checked: self.interpolate()
        )

        self._zero_action = QAction(
            text='Zero',
            toolTip='Zero',
            checkable=False,
            shortcut=QKeySequence('Z'),
            shortcutVisibleInContextMenu=True,
            triggered=lambda checked: self.zero()
        )

        self._set_constant_action = QAction(
            text='Constant',
            toolTip='Set to Constant',
            checkable=False,
            shortcut=QKeySequence('C'),
            shortcutVisibleInContextMenu=True,
            triggered=lambda checked: self.setConstant()
        )

        self._filter_action = QAction(
            icon=qta.icon('mdi.sine-wave'),
            iconVisibleInMenu=True,
            text='Filter',
            toolTip='Filter',
            # checkable=True,
            # checked=False,
            triggered=lambda checked: self.filter()
        )

        self._curve_fit_action = QAction(
            icon=qta.icon('mdi.chart-bell-curve-cumulative'),
            iconVisibleInMenu=True,
            text='Curve Fit',
            toolTip='Curve Fit',
            # checkable=True,
            # checked=False,
            triggered=lambda checked: self.curveFit()
        )

        self._measure_action = QAction(
            parent=self, 
            icon=qta.icon('mdi.chart-scatter-plot'),
            iconVisibleInMenu=True,
            text='Measure',
            toolTip='Measure',
            # checkable=True,
            # checked=False,
            triggered=lambda checked: self.measure()
        )

        # self._opertions_action_group = QActionGroup(self)
        # self._opertions_action_group.addAction(self._filter_action)
        # self._opertions_action_group.addAction(self._curve_fit_action)
        # self._opertions_action_group.addAction(self._measure_action)
        # self._opertions_action_group.setExclusionPolicy(QActionGroup.ExclusionPolicy.ExclusiveOptional)
    
    def _initMenubar(self) -> None:
        super()._initMenubar()

        self._view_menu.insertAction(self.console._console_action, self._notes_action)
        sep = self._view_menu.insertSeparator(self._notes_action)
        self._view_menu.insertAction(sep, self._view_masked_action)
        self._view_menu.insertAction(self._view_masked_action, self._view_ROIs_action)

        self._selection_menu = QMenu('Selection')
        self._selection_menu.addAction(self._mask_action)
        self._selection_menu.addAction(self._unmask_action)
        self._selection_menu.addSeparator()
        self._selection_menu.addAction(self._interpolate_action)
        self._selection_menu.addAction(self._zero_action)
        self._selection_menu.addAction(self._set_constant_action)
        self.menuBar().insertMenu(self._view_menu.menuAction(), self._selection_menu)

        self._operations_menu = QMenu('Operations')
        self._operations_menu.addAction(self._filter_action)
        self._operations_menu.addAction(self._curve_fit_action)
        # self._operations_menu.addSeparator()
        self._operations_menu.addAction(self._measure_action)
        self.menuBar().insertMenu(self._view_menu.menuAction(), self._operations_menu)
    
    def _initUI(self) -> None:
        """ Initialize UI elements and layout.
        """
        # datatree view
        self._datatree_view.setDataVarsVisible(True)
        self._datatree_view.setCoordsVisible(False)
        self._datatree_view.setInfoColumnsVisible(True)

        # ROIs view
        self._ROIs_view = AnnotationTreeView()
        model = AnnotationTreeModel()
        model.setColumnLabels(['ROI'])
        self._ROIs_view.setModel(model)
        self._ROIs_view.selectionWasChanged.connect(self.onRoiSelectionChanged)

        # datatree and ROI views splitter
        self._datatree_ROIs_splitter = QSplitter(Qt.Orientation.Vertical)
        self._datatree_ROIs_splitter.addWidget(self._datatree_view)
        self._datatree_ROIs_splitter.addWidget(self._ROIs_view)

        # data_var plot views splitter
        self._data_var_views_splitter = QSplitter(Qt.Orientation.Vertical)
        self._plots = np.empty((0, 0, 0), dtype=object)

        # invalid selection label
        self._message_label = QLabel()
        self._message_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._message_label.setWordWrap(True)

        # toolbar dimension iterators
        self._dim_iter_widgets: dict[str, dict] = {}

        # right side vbox
        panel = QWidget()
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)
        vbox.addWidget(self._data_var_views_splitter)
        vbox.addWidget(self._message_label)

        # toolbars
        self._initTopToolbar()

        # main layout
        hsplitter = QSplitter(Qt.Orientation.Horizontal)
        hsplitter.addWidget(self._datatree_ROIs_splitter)
        hsplitter.addWidget(panel)
        self.setCentralWidget(hsplitter)

        # notes
        self._notes_view = QTextEdit()
        self._notes_view.setWindowTitle('Notes')
        self._notes_view.textChanged.connect(self._onNotesChanged)

        # filter
        self._filter_control_panel = FilterControlPanel()
        self._filter_control_panel.filterChanged.connect(self.updatePreview)
        self._filter_control_panel.previewToggled.connect(self.updatePreview)
        self._filter_control_panel.panelClosed.connect(self.updatePreview)
        self._filter_control_panel.filterRequested.connect(self.savePreview)

        # curve fit
        self._curve_fit_control_panel = CurveFitControlPanel()
        self._curve_fit_control_panel.fitChanged.connect(self.updatePreview)
        self._curve_fit_control_panel.previewToggled.connect(self.updatePreview)
        self._curve_fit_control_panel.panelClosed.connect(self.updatePreview)
        self._curve_fit_control_panel.fitRequested.connect(self.savePreview)

        # measure
        self._measure_control_panel = MeasureControlPanel()
        self._measure_control_panel.measureChanged.connect(self.updatePreview)
        self._measure_control_panel.previewToggled.connect(self.updatePreview)
        self._measure_control_panel.panelClosed.connect(self.updatePreview)
        self._measure_control_panel.measureRequested.connect(self.savePreview)

        # preview
        self._preview_control_panels = {
            'filter': self._filter_control_panel,
            'curve fit': self._curve_fit_control_panel,
            'measure': self._measure_control_panel
        }
    
    def _initTopToolbar(self) -> None:
        icon_size = self._settings.get('icon size', 24)

        # spacer
        self._dim_iters_spacer = QLabel()
        self._dim_iters_spacer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._dim_iters_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # ROI selector
        self._ROI_menu = QMenu()
        self._ROI_menu.addAction(self._ROI_event_action)
        self._ROI_menu.addAction(self._ROI_xrange_action)

        self._ROI_action_group = QActionGroup(self)
        self._ROI_action_group.addAction(self._ROI_event_action)
        self._ROI_action_group.addAction(self._ROI_xrange_action)
        self._ROI_action_group.setExclusionPolicy(QActionGroup.ExclusionPolicy.Exclusive)

        self._ROI_selection_button = QToolButton()
        self._ROI_selection_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self._ROI_selection_button.setText('ROI')
        # self._ROI_selection_button.setIcon(self._ROI_action_group.checkedAction().icon())
        self._ROI_selection_button.setCheckable(True)
        self._ROI_selection_button.setMenu(self._ROI_menu)
        self._ROI_selection_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.onRoiTypeChanged() # set initial icon
        self._ROI_selection_button.setChecked(False)
        self._ROI_selection_button.toggled.connect(lambda checked: self.startDrawingRois() if checked else self.stopDrawingRois())

        # toolbar
        self._top_toolbar = QToolBar()
        self._top_toolbar.setOrientation(Qt.Orientation.Horizontal)
        self._top_toolbar.setStyleSheet("QToolBar{spacing:2px;}")
        self._top_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self._top_toolbar.setIconSize(QSize(icon_size, icon_size))
        self._top_toolbar.setMovable(False)
        self._top_toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        # self._top_toolbar.setStyleSheet(
        #     """QToolButton:checked {
        #         font-weight: bold;
        #     }""")

        self._top_toolbar.addAction(self._data_action)
        self._before_dim_iters_separator_action = self._top_toolbar.addSeparator()
        self._dim_iters_spacer_action = self._top_toolbar.addWidget(self._dim_iters_spacer)
        self._after_dim_iters_separator_action = self._top_toolbar.addSeparator()
        self._top_toolbar.addAction(self._notes_action)
        self._top_toolbar.addWidget(self._ROI_selection_button)
        self._top_toolbar.addAction(self._home_action)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._top_toolbar)
    
    @staticmethod
    def drop_prefixes(qty: pint.Quantity, ureg = None) -> pint.Quantity:
        if ureg is None:
            ureg = XarrayGraph.ureg

        newunit = ureg.Unit("dimensionless")
        conversion_factor = 1

        for unit_name, power in qty._units.items():
            unit = ureg._units[unit_name]
            converter = unit.converter

            if not isinstance(converter, ScaleConverter):
                # this sample is assuming everything's in terms of scale conversion,
                # but it seems possible there might be some affine transformation
                # between a unit and its reference. Left as an exercise to the reader :)
                raise ValueError(f"Unexpected converter type: {converter!r}")

            if converter.scale == 1:
                # no conversion necessary, just carry this unit along
                newunit *= unit**power
            else:
                for name, p in unit.reference.items():
                    newunit *= ureg.Unit(name)**power
                conversion_factor *= converter.scale

        return qty.m * conversion_factor * newunit
    

class DimIterWidget(QWidget):

    xdimChanged = Signal(str)
    tileChanged = Signal(str, object)

    def __init__(self, *args, **kwargs):
        QWidget.__init__(self, *args, **kwargs)

        color_on: QColor = QApplication.palette().color(QPalette.ColorRole.Text)
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
        self._spinbox.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._spinbox.editingFinished.connect(lambda: self._spinbox.clearFocus())

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

    dt = xr.DataTree()
    dt['air_temperature'] = xr.tutorial.load_dataset('air_temperature')
    dt['air_temperature/twice air'] = dt['air_temperature/air'] * 2
    dt['air_temperature/inherits'] = xr.tutorial.load_dataset('air_temperature')
    dt['air_temperature/inherits/again'] = xr.tutorial.load_dataset('air_temperature')
    dt['child'] = xr.DataTree()
    dt['child/grandchild/greatgrandchild'] = xr.DataTree()
    dt['child/grandchild/tiny'] = xr.tutorial.load_dataset('tiny')
    dt['rasm'] = xr.tutorial.load_dataset('rasm')
    dt['rasm/rasm'] = xr.tutorial.load_dataset('rasm')
    dt['air_temperature_gradient'] = xr.tutorial.load_dataset('air_temperature_gradient')
    dt['test'] = xr.tutorial.load_dataset('air_temperature')
    dt['test/air'].attrs['units'] = 'degC'
    dt['test/lon'].attrs['units'] = 'degE'

    
    # window = XarrayGraph()
    # window.setDatatree(dt)
    # window._datatree_view.showAll()
    # window.show()

    XarrayGraph.open('examples/WinWCP.wcp')

    app.exec()


if __name__ == '__main__':
    test_live()