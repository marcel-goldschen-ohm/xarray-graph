""" PyQt widget for viewing/analyzing (x,y) slices of a Xarray DataTree.

TODO:
- handle different units for same variable (e.g., A vs. mA)
- apply preview filter before curve fit or measurement?
- how to handle selecting non-aligned data?
- measurement dims/coords (deal with reductions)?
- measure multiple peaks
- align traces on onset of impulse response in signal
- fix bugs where preview does not update as it should
- centralize preview update logic? right now its all over the place
- rename nodes in datatree view
- move nodes within datatree view?
- limit branch ROIs to their branch
- skip entirely masked traces when not showing masked
- window/branch management:
    - notes per branch?
    - per branch default xdim?
    - open branch in new window
    - merge/concat branches/windows
    - split branches into separate windows
- implement other (non-gaussian) filters
- refactor to make functionality more modular, extensible, maintainable, and clear
- add extensive comments
- add unit tests
- manage settings via hashable dict vs qt componenets
- format selected ROIs
- persistant format settings for graphs and ROIs
- make loading adicht labchart matlab conversion generic (right now specific to golab dual TEV recordings)
- abf file support
- other file support? neurodata without borders?
- checkbox for selecting/deselecting all data_vars in filter menu
- hide nonselected data_var filter checkboxes?
- plugin system?
"""

from __future__ import annotations
import os
from copy import copy, deepcopy
from pathlib import Path
import textwrap
import numpy as np
import xarray as xr
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

# from xarray_graph.xarray_utils import *
from xarray_graph import XarrayDataTreeModel, XarrayDataTreeView, XarrayDataTreeViewer
from xarray_graph.tree import *
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


# global variables
ROI_KEY = '_ROI_'
MASK_KEY = '_mask_'
CURVE_FIT_KEY = '_curve_fit_'
NOTES_KEY = '_notes_'
MASK_COLOR = '(200, 200, 200)'

filetype_extensions_map: dict[str, list[str]] = {
    'Zarr Directory': [''],
    'Zarr Zip': ['.zip'],
    'NetCDF': ['.nc'],
    'HDF5': ['.h5', '.hdf5'],
    'WinWCP': ['.wcp'],
    'Axon ABF': ['.abf'],
    'HEKA': ['.dat'],
    'MATLAB (GOLab TEVC)': ['.mat'],
}

default_settings = {
    'icon size': 32,
    'icon opacity': 0.5,
    'axis label font size': 12,
    'axis tick font size': 11,
    'ROI font size': 10,
    'line width': 1,
}
settings = deepcopy(default_settings)


class XarrayGraph(QMainWindow):
    """ PyQt widget for viewing/analyzing (x,y) slices of a Xarray DataTree. """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._datatree: xr.DataTree = xr.DataTree()
        # self._previewtree: xr.DataTree = xr.DataTree()
        self._xdim: str = None

        # plot grid [variable, row, column]
        self._plots = np.empty((0,0,0), dtype=object)

        # for dynamic dimension iteration
        self._dim_iter_things: dict[str, dict] = {}

        self._init_UI()
    
    @property
    def datatree(self) -> xr.DataTree:
        """ Get the data tree. """
        return self._datatree
    
    @datatree.setter
    def datatree(self, data: xr.DataTree | xr.Dataset | xr.DataArray | np.ndarray | list[np.ndarray] | tuple[np.ndarray] | None) -> None:
        """ Set the data tree. """
        self._datatree = self._to_valid_datatree(data)
        self._on_datatree_changed()
    
    @property
    def xdim(self) -> str | None:
        """ Get the current x-axis dimension. """
        return self._xdim
    
    @xdim.setter
    def xdim(self, xdim: str) -> None:
        """ Set the current x-axis dimension. """
        self._xdim = xdim
        self._on_xdim_changed()
    
    def setXDim(self, xdim: str) -> None:
        """ For Qt signals/slots. """
        self.xdim = xdim
    
    def __getitem__(self, path: str) -> xr.DataTree | xr.DataArray:
        """ For convenient path-based access to the datatree. """
        return self._datatree[path]
    
    def __setitem__(self, path: str, value: xr.DataTree | xr.DataArray):
        """ For convenient path-based access to the datatree. """
        self._datatree[path] = value
    
    def sizeHint(self) -> QSize:
        """ Default window size. """
        return QSize(1000, 800)

    def about(self) -> None:
        """ Popup about message dialog. """

        text = f"""
        {self.__class__.__name__}
        
        PyQt widget for viewing/analyzing (x,y) slices of a Xarray DataTree.

        Author: Marcel Goldschen-Ohm

        Repository: https://github.com/marcel-goldschen-ohm/xarray-graph
        PyPI: https://pypi.org/project/xarray-graph
        """
        text = textwrap.dedent(text).strip()
        
        QMessageBox.about(self, f'About {self.__class__.__name__}', text)

    def settings(self) -> None:
        """ Popup settings panel. """
        self._settings_panel.show()
    
    def windows(self) -> list[XarrayGraph]:
        """ Get list of all XarrayGraph top level windows. """
        windows = []
        for widget in QApplication.isinstance().topLevelWidgets():
            if isinstance(widget, XarrayGraph):
                windows.append(widget)
        return windows
    
    def newWindow(self) -> XarrayGraph:
        """ Create new XarrayGraph top level window. """
        window = XarrayGraph()
        window.show()
        return window
    
    def load(self, filepath: str | os.PathLike = None, filetype: str = None, action: str = 'overwrite') -> None:
        """ Read data tree from file. """

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
            # filepath is a sequence of multiple filepaths
            actions = [action] + ['merge'] * (len(filepath) - 1)
            for path, action in zip(filepath, actions):
                self.load(path, action=action)
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
            # get filetype from file extension
            extension_filetype_map = {
                ext: filetype
                for filetype, extensions in filetype_extensions_map.items()
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
        elif filetype == 'WinWCP':
            datatree: xr.DataTree = read_winwcp(filepath)
        elif filetype == 'Axon ABF':
            QMessageBox.warning(self, 'Under Construction', f'{filetype} support is in the works.')
            return
        elif filetype == 'HEKA':
            datatree: xr.DataTree = read_heka(filepath)
        elif filetype == 'MATLAB (GOLab TEVC)':
            datatree: xr.DataTree = read_adicht_mat(filepath)
        else:
            try:
                # see if xarray can open the file
                datatree = xr.open_datatree(filepath)
            except:
                QMessageBox.warning(self, 'Invalid File Type', f'Opening {filetype} format files is not supported.')
                return
        
        if datatree is None:
            QMessageBox.warning(self, 'Invalid File', f'Unable to open file: {filepath}')
            return

        # use filename for root node with data (will become the first child node)
        # e.g., when loading from file type such as WinWCP, etc.
        if datatree.has_data:
            datatree.name = filepath.stem
        
        # preprocess datatree
        datatree = inherit_missing_data_vars(datatree)
        restore_ordered_data_vars(datatree)
        
        if (action == 'overwrite') or self.datatree.equals(xr.DataTree()):
            self.datatree = datatree
            self._filepath = filepath
        elif action == 'merge':
            if datatree.has_data:
                roots = [datatree]
            else:
                roots = list(datatree.children.values())
            for root in roots:
                name = get_unique_name(root.name, list(self.datatree.children.keys()))
                if not name.startswith(filepath.stem):
                    name = f'{filepath.stem} {name}'
                root.orphan()
                root.name = name
                self.datatree[f'/{name}'] = root
            notes = datatree.attrs.get(NOTES_KEY, '')
            if notes:
                old_notes = self.datatree.attrs.get(NOTES_KEY, '')
                self.datatree.attrs[NOTES_KEY] = old_notes + f'\n\n{filepath.stem}:\n' + notes
            self._filepath = None  # datatree is no longer for a single file
            self.refresh()
        
        # update notes editor
        notes = self.datatree.attrs.get(NOTES_KEY, '')
        self._notes_edit.setPlainText(notes)

        # if nothing is selected in the datatree, select the leaves of the first child
        if not self._datatree_view.selectedPaths():
            try:
                nodes = list(self.datatree.children.values())[0].leaves
                if nodes:
                    paths = [node.path for node in nodes]
                    self._datatree_view.setSelectedPaths(paths)
            except:
                pass
    
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
        datatree = remove_inherited_data_vars(self.datatree)
        store_ordered_data_vars(datatree)
        datatree.attrs['xarray-graph-version'] = XARRAY_GRAPH_VERSION

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
    
    def refresh(self) -> None:
        """ Refresh the entire UI based on the current data. """

        # combined coords (and masks) for entire data tree
        all_coords = []
        root_nodes = find_subtree_alignment_roots(self.datatree)
        for node in root_nodes:
            vars_to_drop = list(node.data_vars)
            coords_ds = node.to_dataset().reset_coords(drop=True).drop_vars(vars_to_drop)
            coords_ds = to_base_units(coords_ds)
            all_coords.append(coords_ds)
        self._datatree_combined_coords: xr.Dataset = xr.merge(all_coords, compat='no_conflicts', join='outer')

        # update UI
        self._update_datatree_view()
        self._update_filter_menu()
        self._update_left_panel()
        self._console.setVisible(self._toggle_console_action.isChecked())
        self._on_datatree_selection_changed()
    
    def replot(self) -> None:
        """ Update all plots. """
        self._update_plot_data()
        self._update_plot_ROIs()
    
    def tileDimension(self, dim: str, orientation: Qt.Orientation | None) -> None:
        """ Tile plots along coordinate dimension. """

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
                max_default_tile_size = 10
                dim_coords = self._selection_combined_coords[dim]
                if dim_coords.size <= max_default_tile_size:
                    selected_coords = dim_coords
                else:
                    i = np.where(dim_coords == selected_coords[0])[0][0]
                    stop = min(i + max_default_tile_size, dim_coords.size)
                    start = max(0, stop - max_default_tile_size)
                    selected_coords = dim_coords[start:stop]
                dim_iter_widget: DimIterWidget = self._dim_iter_things[dim]['widget']
                dim_iter_widget.setSelectedCoords(selected_coords.values)
        
        self.refresh()
    
    def autoscale(self) -> None:
        """ Autoscale all plots while preserving axis linking. """
        
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
    
    def isConsoleVisible(self) -> bool:
        return self._console.isVisible()
    
    def setConsoleVisible(self, isVisible: bool) -> None:
        self._console.setVisible(isVisible)
        self._toggle_console_action.setChecked(isVisible)
    
    def isROIsVisible(self) -> bool:
        return self._view_ROIs_action.isChecked()
    
    def setROIsVisible(self, isVisible: bool) -> None:
        self._view_ROIs_action.setChecked(isVisible)
        self._view_ROIs_checkbox.blockSignals(True)
        self._view_ROIs_checkbox.setChecked(isVisible)
        self._view_ROIs_checkbox.blockSignals(False)

        self._on_ROI_selection_changed()

        if self._curve_fit_live_preview_enabled() and self._curve_fit_depends_on_ROIs() and not self.isROIsVisible() and self.selectedROIs():
            self._update_curve_fit_preview()
    
    def isMaskedVisible(self) -> bool:
        return self._view_masked_action.isChecked()
    
    def setMaskedVisible(self, isVisible: bool) -> None:
        self._view_masked_action.setChecked(isVisible)
        self._view_masked_checkbox.blockSignals(True)
        self._view_masked_checkbox.setChecked(isVisible)
        self._view_masked_checkbox.blockSignals(False)
        self.refresh()
    
    def selectedROIs(self) -> list[dict]:
        return self._ROItree_view.selectedAnnotations()
    
    def setSelectedROIs(self, ROIs: list[dict]) -> None:
        self._ROItree_view.setSelectedAnnotations(ROIs)
    
    def clearROISelection(self, ask: bool = False) -> None:
        if ask:
            answer = QMessageBox.question(self, 'Clear ROI Selection', 'Clear ROI selection?\nROIs are not deleted.')
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._ROItree_view.clearSelection()
        self._update_plot_ROIs()
    
    def addROIs(self, ROIs: dict | list[dict] = None, dst: xr.DataTree | xr.DataArray = None, select: bool = False) -> None:
        if ROIs is None:
            self._start_drawing_ROIs()
            return
        
        if isinstance(ROIs, dict):
            ROIs = [ROIs]
        
        if dst is None:
            dst = self.datatree
        
        if ROI_KEY not in dst.attrs:
            dst.attrs[ROI_KEY] = []
        
        dst.attrs[ROI_KEY].extend(ROIs)

        self._update_ROItree_view()

        if select:
            selected_ROIs = self.selectedROIs()
            for ROI in ROIs:
                if ROI not in selected_ROIs:
                    selected_ROIs.append(ROI)
            self.setSelectedROIs(ROIs)
            self._update_plot_ROIs()
    
    def deleteROIs(self, ROIs: dict | list[dict]) -> None:
        if isinstance(ROIs, dict):
            ROIs = [ROIs]
        
        # remove ROIs from datatree
        for node in self.datatree.subtree:
            node_ROIs = node.attrs.get(ROI_KEY, [])
            if node_ROIs:
                for ROI in ROIs:
                    if ROI in node_ROIs:
                        node_ROIs.remove(ROI)

        # remove ROIs from plots
        for plot in self._plots.flatten().tolist():
            for item in plot.vb.allChildren():
                if isinstance(item, pgx.XAxisRegion) and getattr(item, '_ROI', None) in ROIs:
                    plot.vb.removeItem(item)
                    item.deleteLater()
        
        self._update_ROItree_view()
    
    def groupROIs(self, ROIs: dict | list[dict], group: str | None = None, dialogTitle: str = 'Group ROIs') -> None:
        if isinstance(ROIs, dict):
            ROIs = [ROIs]
        
        if not ROIs:
            return
        
        if group is None:
            group, ok = QInputDialog.getText(self, dialogTitle, 'Group Name:')
            if not ok:
                return
            group = group.strip()
        
        if not group:
            for ROI in ROIs:
                if 'group' in ROI:
                    del ROI['group']
        else:
            for ROI in ROIs:
                ROI['group'] = group
        
        self._update_ROItree_view()
    
    def moveROIs(self, ROIs: dict | list[dict], dst: xr.DataTree | xr.DataArray = None, copy: bool = False, dialogTitle: str = 'Move ROIs') -> None:
        if isinstance(ROIs, dict):
            ROIs = [ROIs]
        
        if not ROIs:
            return
        
        if dst is None:
            dlg = QDialog(self)
            dlg.setWindowTitle(dialogTitle)
            vbox = QVBoxLayout(dlg)

            vbox.addSpacing(20)
            vbox.addWidget(QLabel('Move To:'))
            paths = ['/'] + [node.path for node in self.datatree.children.values()]
            model = QStringListModel(paths)
            view = QListView()
            view.setModel(model)
            # view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            # for path in self._selected_branch_root_paths:
            #     row = paths.index(path)
            #     index = model.index(row, 0)
            #     view.selectionModel().select(index, QItemSelectionModel.SelectionFlag.Select)
            default_selected_row = 0
            branch_root_paths = [node.path for node in find_subtree_alignment_roots(self.datatree)]
            if branch_root_paths:
                path = branch_root_paths[0]
                if path in paths:
                    default_selected_row = paths.index(path)
            view.setCurrentIndex(model.index(default_selected_row, 0))
            vbox.addWidget(view)

            vbox.addSpacing(20)
            copyCheckBox = QCheckBox('Create a copy')
            copyCheckBox.setChecked(copy)
            vbox.addWidget(copyCheckBox)

            buttons = QDialogButtonBox()
            buttons.setStandardButtons(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
            buttons.accepted.connect(dlg.accept)
            buttons.rejected.connect(dlg.reject)
            vbox.addWidget(buttons)

            if dlg.exec() != QDialog.Accepted:
                return
        
            indexes = view.selectionModel().selectedIndexes()
            paths = [index.data(Qt.DisplayRole) for index in indexes]
            if not paths:
                return
        
            path = paths[0]  # should only be one path selected
            dst = self.datatree[path]
            isCopy = copyCheckBox.isChecked()

        if ROI_KEY not in dst.attrs:
            dst.attrs[ROI_KEY] = []
        
        selectedROIs = self.selectedROIs()
        
        for i, ROI in enumerate(ROIs):
            if isCopy:
                copyOfROI = deepcopy(ROI)
                ROIs[i] = copyOfROI
                if ROI in selectedROIs:
                    j = selectedROIs.index(ROI)
                    selectedROIs[j] = copyOfROI
                ROI = copyOfROI
            else:
                srcPath = ''
                for node in self.datatree.subtree:
                    nodeROIs = node.attrs.get(ROI_KEY, [])
                    if ROI in nodeROIs:
                        srcPath = node.path
                        break
                    for var_name, var in node.data_vars.items():
                        varROIs = var.attrs.get(ROI_KEY, [])
                        if ROI in varROIs:
                            srcPath = f'{node.path}/{var_name}'
                            break
                if srcPath:
                    src = self.datatree[srcPath]
                    src.attrs[ROI_KEY].remove(ROI)
            
            dst.attrs[ROI_KEY].append(ROI)
        
        self._update_ROItree_view()

        # ensure same ROIs are selected after move
        self.setSelectedROIs(selectedROIs)

    def deleteSelectedROIs(self, ask: bool = True) -> None:
        if ask:
            answer = QMessageBox.question(self, 'Delete Selected ROIs', 'Delete selected ROIs?')
            if answer != QMessageBox.StandardButton.Yes:
                return
        ROIs = self.selectedROIs()
        self.deleteROIs(ROIs)
    
    def groupSelectedROIs(self, group: str | None = None) -> None:
        ROIs = self.selectedROIs()
        self.groupROIs(ROIs, group, 'Group Selected ROIs')
    
    def moveSelectedROIs(self, dst: xr.DataTree | xr.DataArray = None, copy: bool = False) -> None:
        ROIs = self.selectedROIs()
        self.moveROIs(ROIs, dst, copy, 'Move Selected ROIs')

    def maskSelection(self) -> None:
        """ Mask selected traces or ROIs within selected traces. """

        if self.isROIsVisible():
            ROIs = self.selectedROIs()
        else:
            ROIs = []
        
        # assign masks to branch root nodes of selected vars
        nodes = []
        for path in self._selected_var_paths:
            node_path = '/'.join(path.rstrip('/').split('/')[:-1])
            node = self.datatree[node_path]
            branch_root_node = find_aligned_root(node)
            if branch_root_node not in nodes:
                nodes.append(branch_root_node)
        
        for node in nodes:
            dims = tuple(node.sizes.keys())
            sizes = tuple(node.sizes.values())
            if MASK_KEY not in node.data_vars:
                node.dataset = node.to_dataset().assign({MASK_KEY: xr.DataArray(np.full(sizes, False, dtype=bool), dims=dims)})
            coords = {dim: values for dim, values in self._selection_visible_coords.coords.items() if dim in node.dims}
            if ROIs:
                xdata = node[self.xdim].values
                xmask = np.full(xdata.shape, False, dtype=bool)
                for ROI in ROIs:
                    lb, ub = ROI['position'][self.xdim]
                    xmask[(xdata >= lb) & (xdata <= ub)] = True
                coords[self.xdim] = xdata[xmask]
            node.data_vars[MASK_KEY].loc[coords] = True
        
        self.refresh()

    def unmaskSelection(self) -> None:
        """ Unmask selected traces or ROIs within selected traces. """
        
        if self.isROIsVisible():
            ROIs = self.selectedROIs()
        else:
            ROIs = []
        
        # assign masks to branch root nodes of selected vars
        nodes = []
        for path in self._selected_var_paths:
            node_path = '/'.join(path.rstrip('/').split('/')[:-1])
            node = self.datatree[node_path]
            branch_root_node = find_aligned_root(node)
            if branch_root_node not in nodes:
                nodes.append(branch_root_node)
        
        for node in nodes:
            dims = tuple(node.sizes.keys())
            sizes = tuple(node.sizes.values())
            if MASK_KEY not in node.data_vars:
                continue
            coords = {dim: values for dim, values in self._selection_visible_coords.coords.items() if dim in node.dims}
            if ROIs:
                xdata = node[self.xdim].values
                xmask = np.full(xdata.shape, False, dtype=bool)
                for ROI in ROIs:
                    lb, ub = ROI['position'][self.xdim]
                    xmask[(xdata >= lb) & (xdata <= ub)] = True
                coords[self.xdim] = xdata[xmask]
            node.data_vars[MASK_KEY].loc[coords] = False
            if not np.any(node.data_vars[MASK_KEY].values):
                node.dataset = node.to_dataset().drop_vars(MASK_KEY)
        
        self.refresh()
    
    def saveFilteredData(self) -> None:
        """ Save the current filtered data to the datatree. """

        # get the node name under which to save the filtered data
        filterType = self._filter_type_combobox.currentText()
        result_name, ok = QInputDialog.getText(self, 'Save Filtered Data As', 'Filtered dataset name:', text=f'{filterType}')
        if not ok or not result_name:
            return

        # ensure curve fit has not been zeroed to show residuals
        if self._fitPreviewResidualsCheckbox.isChecked():
            self._update_curve_fit_preview(no_residuals=True)
        
        # gather filter results and associated paths
        result_var_paths = []
        result_node_paths = []
        new_result_vars = []
        for plot in self._plots.flatten().tolist():
            # existing graphs in plot
            graphs = [item for item in plot.listDataItems() if isinstance(item, pgx.Graph)]
            data_graphs = [graph for graph in graphs if hasattr(graph, '_metadata') and graph._metadata.get('type', None) == 'data']
            
            for data_graph in data_graphs:
                path = data_graph._metadata.get('path', None)
                if path is None:
                    continue

                var_name = path.rstrip('/').split('/')[-1]
                parent_node_path = '/'.join(path.rstrip('/').split('/')[:-1])
                parent_node = self.datatree[parent_node_path]

                if result_name in parent_node.data_vars or result_name in parent_node.coords:
                    QMessageBox.warning(self, 'Error', 'Filter dataset name cannot be the name of a variable or dimension.')
                    return
                
                result_node_path = f'{parent_node_path}/{result_name}'
                result_var_path = f'{result_node_path}/{var_name}'
                
                parent_var = parent_node.data_vars[var_name]
                parent_var_slice = data_graph._metadata.get('data', None)
                xfiltered, yfiltered = data_graph.getOriginalDataset()

                new_result_var = parent_var.copy(data=np.full(parent_var.values.shape, np.nan))
                new_result_var.loc[parent_var_slice.coords] = yfiltered

                result_var_paths.append(result_var_path)
                result_node_paths.append(result_node_path)
                new_result_vars.append(new_result_var)

        # save filtered data to datatree
        for result_node_path, result_var_path, new_result_var in zip(result_node_paths, result_var_paths, new_result_vars):
            var_name = new_result_var.name
            try:
                result_node = self._datatree[result_node_path]
            except KeyError:
                result_node = None
            if result_node is None:
                # create new result node
                self._datatree[result_node_path] = xr.Dataset(data_vars={var_name: new_result_var})
            elif var_name not in result_node.data_vars:
                # create new result data_var in existing node
                result_node.dataset = result_node.to_dataset().assign({var_name: new_result_var})
            else:
                # update existing result data_var
                existing_result_var = result_node[var_name]
                new_result_mask = ~(new_result_var.isnull().values)
                existing_result_var.values[new_result_mask] = new_result_var.values[new_result_mask]
        
        # turn off filter preview
        self._filterLivePreviewCheckbox.setChecked(False)
        
        # switch to datatree panel
        self._toggle_datatree_panel_action.setChecked(True)

        # update datatree view and plots (in case we added new nodes/data_vars)
        self.refresh()

        # ensure result nodes are expanded
        for result_node_path in result_node_paths:
            item = self._datatree_view.model().root()
            item = item[result_node_path.lstrip('/')]
            index = self._datatree_view.model().indexFromItem(item)
            if not self._datatree_view.isExpanded(index):
                self._datatree_view.setExpanded(index, True)
        
        # ensure new results are selected in datatree view
        selectedPaths = self._datatree_view.selectedPaths()
        selectionChanged = False
        for result_path in result_var_paths:
            if result_path not in selectedPaths:
                selectedPaths.append(result_path)
                selectionChanged = True
        if selectionChanged:
            self._datatree_view.setSelectedPaths(selectedPaths)
    
    def saveCurveFit(self) -> None:
        """ Save the current curve fit preview to the datatree. """

        # get the node name under which to save the fits
        fitType = self._fitTypeComboBox.currentText()
        result_name, ok = QInputDialog.getText(self, 'Save Curve Fit As', 'Fit dataset name:', text=f'{fitType}')
        if not ok or not result_name:
            return

        # ensure curve fit has not been zeroed to show residuals
        if self._fitPreviewResidualsCheckbox.isChecked():
            self._update_curve_fit_preview(force_preview=True, no_residuals=True)
        
        # gather fit results (preview) and associated paths
        result_var_paths = []
        result_node_paths = []
        new_result_vars = []
        new_result_coords = []
        new_result_fits = []
        for plot in self._plots.flatten().tolist():
            # existing graphs in plot
            graphs = [item for item in plot.listDataItems() if isinstance(item, pgx.Graph)]
            preview_graphs = [graph for graph in graphs if hasattr(graph, '_metadata') and graph._metadata.get('type', None) == 'preview']
            
            for preview_graph in preview_graphs:
                path = preview_graph._metadata.get('path', None)
                if path is None:
                    continue

                var_name = path.rstrip('/').split('/')[-1]
                parent_node_path = '/'.join(path.rstrip('/').split('/')[:-1])
                parent_node = self.datatree[parent_node_path]

                if result_name in parent_node.data_vars or result_name in parent_node.coords:
                    QMessageBox.warning(self, 'Error', 'Fit dataset name cannot be the name of a variable or dimension.')
                    return
                
                result_node_path = f'{parent_node_path}/{result_name}'
                result_var_path = f'{result_node_path}/{var_name}'
                
                parent_var = parent_node.data_vars[var_name]
                parent_var_slice = preview_graph._metadata.get('data', None)
                xfit, yfit = preview_graph.getOriginalDataset()

                new_result_var = parent_var.copy(data=np.full(parent_var.values.shape, np.nan))
                new_result_var.loc[parent_var_slice.coords] = yfit

                result_var_paths.append(result_var_path)
                result_node_paths.append(result_node_path)
                new_result_vars.append(new_result_var)
                new_result_coords.append(preview_graph._metadata.get('coords', None))
                new_result_fits.append(preview_graph._metadata.get('fit', None))

        # save fits to datatree
        for result_node_path, result_var_path, new_result_var, new_result_coord, new_result_fit in zip(result_node_paths, result_var_paths, new_result_vars, new_result_coords, new_result_fits):
            var_name = new_result_var.name
            try:
                result_node = self._datatree[result_node_path]
            except KeyError:
                result_node = None
            if result_node is None:
                # create new result node
                self._datatree[result_node_path] = xr.Dataset(data_vars={var_name: new_result_var})
                result_node = self._datatree[result_node_path]
            elif var_name not in result_node.data_vars:
                # create new result data_var in existing node
                result_node.dataset = result_node.to_dataset().assign({var_name: new_result_var})
            else:
                # update existing result data_var
                existing_result_var = result_node[var_name]
                new_result_mask = ~(new_result_var.isnull().values)
                existing_result_var.values[new_result_mask] = new_result_var.values[new_result_mask]
            if new_result_fit is not None:
                coords_key = ', '.join([f'{name}: {str(coord)}' for name, coord in new_result_coord.items()])
                if new_result_fit['type'] == 'Expression':
                    result: lmfit.model.ModelResult = new_result_fit['result']
                    model: lmfit.models.ExpressionModel = result.model
                    params = self._getEquationTableParams()
                    for name in result.params:
                        params[name]['value'] = float(result.params[name].value)
                    new_result_fit = {
                        'type': new_result_fit['type'],
                        'expression': model.expr,
                        'params': params,
                    }
                for key, value in new_result_fit.items():
                    if isinstance(value, np.ndarray):
                        new_result_fit[key] = tuple(value.tolist())
                print('-'*82)
                print('Curve fit result for', result_var_path)
                print(coords_key)
                print(new_result_fit)
                print('-'*82)
                var = result_node[var_name]
                if CURVE_FIT_KEY not in var.attrs:
                    var.attrs[CURVE_FIT_KEY] = {}
                var.attrs[CURVE_FIT_KEY][coords_key] = new_result_fit
        
        # switch to datatree panel (also stops any live preview/residuals)
        self._toggle_datatree_panel_action.setChecked(True)

        # update datatree view and plots (in case we added new nodes/data_vars)
        self.refresh()

        # ensure result nodes are expanded
        for result_node_path in result_node_paths:
            item = self._datatree_view.model().root()
            item = item[result_node_path.lstrip('/')]
            index = self._datatree_view.model().indexFromItem(item)
            if not self._datatree_view.isExpanded(index):
                self._datatree_view.setExpanded(index, True)
        
        # ensure new results are selected in datatree view
        selectedPaths = self._datatree_view.selectedPaths()
        selectionChanged = False
        for result_path in result_var_paths:
            if result_path not in selectedPaths:
                selectedPaths.append(result_path)
                selectionChanged = True
        if selectionChanged:
            self._datatree_view.setSelectedPaths(selectedPaths)
    
    def saveMeasurement(self) -> None:
        """ Save the current measurement preview to the datatree. """

        # get the node name under which to save the measurements
        measureType = self._measure_type_combobox.currentText()
        result_name, ok = QInputDialog.getText(self, 'Save Measurement As', 'Measurement dataset name:', text=f'{measureType}')
        if not ok or not result_name:
            return
        
        # gather measurement results (preview) and associated paths
        result_var_paths = []
        result_node_paths = []
        new_result_vars = []
        for plot in self._plots.flatten().tolist():
            # existing graphs in plot
            graphs = [item for item in plot.listDataItems() if isinstance(item, pgx.Graph)]
            preview_graphs = [graph for graph in graphs if hasattr(graph, '_metadata') and graph._metadata.get('type', None) == 'preview']
            
            for preview_graph in preview_graphs:
                path = preview_graph._metadata.get('path', None)
                if path is None:
                    continue

                var_name = path.rstrip('/').split('/')[-1]
                parent_node_path = '/'.join(path.rstrip('/').split('/')[:-1])
                parent_node = self.datatree[parent_node_path]

                if result_name in parent_node.data_vars or result_name in parent_node.coords:
                    QMessageBox.warning(self, 'Error', 'Dataset name cannot be the name of a variable or dimension.')
                    return
                
                result_node_path = f'/{result_name}'
                result_var_path = f'{result_node_path}/{var_name}'
                
                xmeasure, ymeasure = preview_graph.getOriginalDataset()

                new_result_var = xr.DataArray(data=ymeasure, dims=[self.xdim], coords={self.xdim: xmeasure}, name=var_name)

                result_var_paths.append(result_var_path)
                result_node_paths.append(result_node_path)
                new_result_vars.append(new_result_var)

        # save fits to datatree
        for result_node_path, result_var_path, new_result_var in zip(result_node_paths, result_var_paths, new_result_vars):
            var_name = new_result_var.name
            try:
                result_node = self._datatree[result_node_path]
            except KeyError:
                result_node = None
            if result_node is None:
                # create new result node
                self._datatree[result_node_path] = xr.Dataset(data_vars={var_name: new_result_var})
            elif var_name not in result_node.data_vars:
                # create new result data_var in existing node
                result_node.dataset = result_node.to_dataset().assign({var_name: new_result_var})
            else:
                # update existing result data_var
                existing_result_var = result_node[var_name]
                new_result_mask = ~(new_result_var.isnull().values)
                existing_result_var.values[new_result_mask] = new_result_var.values[new_result_mask]
        
        # switch to datatree panel (also stops any live preview)
        self._toggle_datatree_panel_action.setChecked(True)

        # update datatree view and plots (in case we added new nodes/data_vars)
        print(self.datatree)
        self.refresh()

        # ensure result nodes are expanded
        for result_node_path in result_node_paths:
            item = self._datatree_view.model().root()
            item = item[result_node_path.lstrip('/')]
            index = self._datatree_view.model().indexFromItem(item)
            if not self._datatree_view.isExpanded(index):
                self._datatree_view.setExpanded(index, True)
        
        # ensure new results are selected in datatree view
        selectedPaths = self._datatree_view.selectedPaths()
        selectionChanged = False
        for result_path in result_var_paths:
            if result_path not in selectedPaths:
                selectedPaths.append(result_path)
                selectionChanged = True
        if selectionChanged:
            self._datatree_view.setSelectedPaths(selectedPaths)
    
    def _on_datatree_changed(self) -> None:
        """ Handle changes to the data tree. """
        self.refresh()
    
    def _on_xdim_changed(self) -> None:
        """ Handle xdim change. """
        self.refresh()
        self.autoscale()
    
    def _on_datatree_selection_changed(self) -> None:
        """ Handle selection changes in data tree view. """

        # for filtering selected data_vars
        var_filter = self._get_data_var_filter()
        
        # selected datatree paths
        unordered_selected_datatree_paths: list[str] = self._datatree_view.selectedPaths()
        self._selected_datatree_paths: list[str] = []
        for node in self.datatree.subtree:
            if node.path in unordered_selected_datatree_paths:
                self._selected_datatree_paths.append(node.path)
            for var_name in node.data_vars:
                var_path = f'{node.path}/{var_name}'
                if var_path in unordered_selected_datatree_paths:
                    self._selected_datatree_paths.append(var_path)
            for coord_name in node.coords:
                coord_path = f'{node.path}/{coord_name}'
                if coord_path in unordered_selected_datatree_paths:
                    self._selected_datatree_paths.append(coord_path)
        self._selected_node_paths: list[str] = []
        self._selected_var_paths: list[str] = []
        self._selected_coord_paths: list[str] = []
        for path in self._selected_datatree_paths:
            if isinstance(self.datatree[path], xr.DataTree):
                # node selected
                self._selected_node_paths.append(path)
                # select all data_vars for this node
                for var_name in self.datatree[path].data_vars:
                    if var_filter.get(var_name, True):
                        var_path = path + '/' + var_name
                        if var_path not in self._selected_var_paths:
                            self._selected_var_paths.append(var_path)
            elif isinstance(self.datatree[path], xr.DataArray):
                node_path = '/'.join(path.rstrip('/').split('/')[:-1])
                node: xr.DataTree = self.datatree[node_path]
                array_name = path.rstrip('/').split('/')[-1]
                if array_name in node.data_vars:
                    # var selected
                    if path not in self._selected_var_paths:
                        if len(self._selected_datatree_paths) == 1:
                            # ignore the var filter if only a single data_var is selected
                            self._selected_var_paths.append(path)
                        else:
                            if var_filter.get(array_name, True):
                                self._selected_var_paths.append(path)
                elif array_name in node.coords:
                    # coord selected
                    if path not in self._selected_coord_paths:
                        self._selected_coord_paths.append(path)
        
        # try and ensure valid xdim
        self._selection_ordered_dims = get_ordered_dims([self.datatree[path] for path in self._selected_var_paths])
        if self.xdim not in self._selection_ordered_dims:
            if self._selection_ordered_dims:
                self._xdim = self._selection_ordered_dims[-1]
        
        # limit selection to variables with the xdim coordinate
        self._selected_var_paths = [path for path in self._selected_var_paths if self.xdim in self.datatree[path].dims]

        # combined coords, data_var names, and units for selection
        selected_vars = [self.datatree[path] for path in self._selected_var_paths]
        selected_coords = []#var.reset_coords(drop=True).coords for var in selected_vars]
        for var in selected_vars:
            coords_ds = xr.Dataset(
                coords={name: to_base_units(coord) for name, coord in var.coords.items()}
            )
            selected_coords.append(coords_ds)
        self._selection_combined_coords: xr.Dataset = xr.merge(selected_coords, compat='no_conflicts', join='outer')
        self._selected_var_names = []
        self._selection_units = {}
        for var in selected_vars:
            if var.name not in self._selected_var_names:
                self._selected_var_names.append(var.name)
            if var.name not in self._selection_units:
                if 'units' in var.attrs:
                    self._selection_units[var.name] = var.attrs['units']
            for dim, coord in var.coords.items():
                if dim not in self._selection_units:
                    if 'units' in coord.attrs:
                        self._selection_units[dim] = coord.attrs['units']
        
        # update toolbar dim iter widgets for selected variables
        self._update_dim_iter_things()

        # update ROI tree
        self._update_ROItree_view()

        # update dimension slice selection (this will update the plot grids)
        self._on_dimension_slice_changed()
    
    def _on_dimension_slice_changed(self) -> None:
        """ Handle selection changes in dimension iterators. """

        # get coords for current slice of selected variables
        iter_coords = {}
        for dim in self._dim_iter_things:
            if self._dim_iter_things[dim]['active']:
                widget: DimIterWidget = self._dim_iter_things[dim]['widget']
                iter_coords[dim] = widget.selectedCoords()
        if iter_coords:
            self._selection_visible_coords: xr.Dataset = self._selection_combined_coords.sel(iter_coords)#, method='nearest')
        else:
            self._selection_visible_coords: xr.Dataset = self._selection_combined_coords
        
        # update plot grids
        self._update_plot_grids()

    def _on_ROI_selection_changed(self) -> None:
        """ Handle selection changes in ROI tree view. """
        self._update_plot_ROIs()

        if self._curve_fit_live_preview_enabled() and self._curve_fit_depends_on_ROIs() and self.isROIsVisible() and self.selectedROIs():
            self._update_curve_fit_preview()

    def _on_finished_drawing_ROI(self, item: pgx.XAxisRegion) -> None:
        """ Handle adding ROI after user has drawn it. """

        view: pgx.View = self.sender()

        ROI = {
            'type': 'vregion',
            'position': {self.xdim: item.getRegion()},
        }

        # link ROI dict to region item
        item._ROI = ROI

        # setup ROI plot item signals/slots, etc.
        self._setup_ROI_plot_item(item)

        # add ROI to datatree root
        if ROI_KEY not in self.datatree.attrs:
            self.datatree.attrs[ROI_KEY] = []
        self.datatree.attrs[ROI_KEY].append(ROI)
            
        # draw one ROI at a time
        self._stop_drawing_ROIs()

        # if not previously showing ROIs, deselect all other ROIs before showing the new ROI
        if not self._view_ROIs_action.isChecked():
            self._ROItree_view.clearSelection()
        
        # update ROI tree and ensure new ROI is selected
        self._update_ROItree_view()
        selected_ROIs = self._ROItree_view.selectedAnnotations()
        if ROI not in selected_ROIs:
            selected_ROIs.append(ROI)
        self._ROItree_view.setSelectedAnnotations(selected_ROIs)

        # ensure ROIs visible
        # update checkbox which will also update the associated action (the reverse does not work)
        self._view_ROIs_checkbox.setChecked(True)

        # update ROIs in plots
        self._update_plot_ROIs()
        
        if self._curve_fit_live_preview_enabled() and self._curve_fit_depends_on_ROIs():
            self._update_curve_fit_preview()

    def _on_ROI_plot_item_changed(self, item: pgx.XAxisRegion) -> None:
        """ Handle changes to ROI region item in the plot. """

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
        
        # update ROI tree view (only item for ROI)
        for item in self._ROItree_model.root().depthFirst():
            if getattr(item, '_data', None) is ROI:
                item.name = self._ROItree_model._get_annotation_label(ROI)
                index: QModelIndex = self._ROItree_model.indexFromItem(item)
                self._ROItree_model.dataChanged.emit(index, index)
                break
        
        if self._curve_fit_live_preview_enabled() and self._curve_fit_depends_on_ROIs():
            self._update_curve_fit_preview()

    def _on_filter_changed(self) -> None:
        if self._filterLivePreviewCheckbox.isChecked():
            self._update_plot_data()
    
    def _on_filter_type_changed(self) -> None:
        self._update_filter_control_panel()
        self._on_filter_changed()
    
    def _on_curve_fit_changed(self) -> None:
        if self._curve_fit_live_preview_enabled():
            self._update_curve_fit_preview()

    def _on_curve_fit_type_changed(self) -> None:
        fitType = self._fitTypeComboBox.currentText()
        isNamedExpression = fitType in list(self._namedExpressions.keys())
        if isNamedExpression:
            namedExpression = self._namedExpressions[fitType]
            self._expressionEdit.setText(namedExpression['expression'])
            self._on_curve_fit_expression_changed()
            if 'params' in namedExpression:
                params = self._getEquationTableParams()
                for param_name, param_dict in namedExpression['params'].items():
                    for param_type, param_value in param_dict.items():
                        params[param_name][param_type] = param_value
                self._setEquationTableParams(params)
        
        self._update_curve_fit_control_panel()
        self._on_curve_fit_changed()
    
    def _on_curve_fit_expression_changed(self) -> None:
        expression = self._expressionEdit.text().strip()     
        if expression == '':
            self._setEquationTableParams({})
        else:
            model = lmfit.models.ExpressionModel(expression, independent_vars=['x'])
            old_params = self._getEquationTableParams()
            new_params = {}
            for name in model.param_names:
                if name in old_params:
                    new_params[name] = old_params[name]
                else:
                    new_params[name] = {
                        'value': 0,
                        'vary': True,
                        'min': -np.inf,
                        'max': np.inf
                    }
            self._setEquationTableParams(new_params)
        
        self._on_curve_fit_changed()
    
    def _on_curve_fit_ROI_dependence_changed(self) -> None:
        if self.isROIsVisible() and self.selectedROIs():
            self._on_curve_fit_changed()
    
    def _on_measurement_changed(self) -> None:
        if self._measurement_live_preview_enabled():
            self._update_measurement_preview()

    def _on_measure_type_changed(self) -> None:
        self._update_measurement_control_panel()
        self._on_measurement_changed()
    
    def _on_notes_changed(self) -> None:
        notes = self._notes_edit.toPlainText()
        if notes.strip() == '':
            if NOTES_KEY in self.datatree.attrs:
                del self.datatree.attrs[NOTES_KEY]
            return
        self.datatree.attrs[NOTES_KEY] = notes
    
    def closeEvent(self, event):
        # Actions to perform before the application quits.
        # Clearing the datatree prevents a segfault during quiting the QApplication.
        # This segfault seems to occur when _on_datatree_selection_changed is called during the quiting process.
        self.datatree = None
        
        # Accept the close event to allow the application to quit.
        # If you want to prevent the application from closing, use event.ignore()
        event.accept()

    # def _get_trace(self, path_to_data_var: str, slice_coords, raw: bool = False) -> xr.DataArray:

    #     trace: xr.DataArray = self.datatree[path_to_data_var].sel(slice_coords)

    #     if raw:
    #         return trace
                    
    #     if self._filterLivePreviewCheckbox.isChecked():
    #         trace = self._apply_filter(trace, self.xdim)
        
    #     return trace
    
    def _get_data_var_filter(self) -> dict[str, bool]:
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
    
    def _get_tile_dims(self) -> tuple[str | None, str | None, np.ndarray | None, np.ndarray | None]:
        vdim = getattr(self, '_vertical_tile_dimension', None)
        hdim = getattr(self, '_horizontal_tile_dimension', None)
        coords = self._selection_visible_coords
        if (vdim not in coords) or (coords[vdim].size <= 1):
            vdim = None
        if (hdim not in coords) or (coords[hdim].size <= 1):
            hdim = None
        vcoords = None if vdim is None else coords[vdim].values
        hcoords = None if hdim is None else coords[hdim].values
        return vdim, hdim, vcoords, hcoords
    
    def _toggle_drawing_ROIs(self) -> None:
        if self._draw_ROI_action.isChecked():
            self._start_drawing_ROIs()
        else:
            self._stop_drawing_ROIs()
    
    def _start_drawing_ROIs(self) -> None:
        """ Start drawing ROI regions in each plot view box. """
        for plot in self._plots.flatten().tolist():
            plot.vb.sigItemAdded.connect(self._on_finished_drawing_ROI)
            plot.vb.startDrawingItemsOfType(pgx.XAxisRegion)
    
    def _stop_drawing_ROIs(self) -> None:
        """ Stop drawing ROI regions in each plot view box. """
        for plot in self._plots.flatten().tolist():
            plot.vb.stopDrawingItems()
            plot.vb.sigItemAdded.disconnect(self._on_finished_drawing_ROI)
        self._draw_ROI_action.setChecked(False)
    
    def _add_ROI_to_plot(self, ROI: dict, plot: pgx.Plot) -> pgx.XAxisRegion:
        """ Add ROI region item to plot. """

        item = pgx.XAxisRegion()
        item._ROI = ROI
        self._update_ROI_plot_item_from_data(item, item._ROI)
        self._setup_ROI_plot_item(item)
        plot.vb.addItem(item)
        return item
    
    def _setup_ROI_plot_item(self, item: pgx.XAxisRegion) -> None:
        """ Signals/Slots and properties for ROI plot item. """

        item.sigRegionChanged.connect(lambda item=item: self._on_ROI_plot_item_changed(item))
        item.sigRegionDragFinished.connect(lambda item=item: self._on_ROI_plot_item_changed(item))
        item.sigEditingFinished.connect(lambda item=item: self._on_ROI_plot_item_changed(item))
        item.sigDeletionRequested.connect(lambda item=item: self.deleteROIs(item._ROI))

        item.sigRegionDragFinished.connect(lambda: self._update_ROItree_view())
        item.sigEditingFinished.connect(lambda: self._update_ROItree_view())
        
        item.setZValue(0)
    
    def _filter(self, x: xr.DataArray, y: xr.DataArray) -> xr.DataArray:

        filterType = self._filter_type_combobox.currentText()
        bandType = self._filter_band_type_combobox.currentText()
        cutoffs = [float(fc) for fc in self._filter_cutoff_edit.text().split(',') if fc.strip() != '']
        if not cutoffs:
            return
        cutoff_units = self._filter_cutoff_units_edit.text().strip()
        
        y = y.copy(deep=False) # do NOT copy y.values
        dx = (x.values[1] - x.values[0])  # !!! assumes constant sample rate
        xunits = x.attrs.get('units', None)

        if filterType == 'Gaussian':
            # must be lowpass
            lowpass_cutoff = cutoffs[0]
            if cutoff_units and xunits:
                lowpass_cutoff *= UREG(cutoff_units)
                dx *= UREG(xunits)
                lowpass_cycles_per_sample = (lowpass_cutoff.to(f'1/{xunits}') * dx).magnitude
            else:
                lowpass_cycles_per_sample = lowpass_cutoff
            sigma = 1 / (2 * np.pi * lowpass_cycles_per_sample)
            y.values = sp.ndimage.gaussian_filter1d(y.values, sigma)
        
        return y
    
    def _fit(self, x: np.ndarray, y: np.ndarray):
        """ Fit y(x) """

        # remove NaN
        mask = np.isnan(x) | np.isnan(y)
        if np.any(mask):
            x = x[~mask]
            y = y[~mask]
        
        fitType = self._fitTypeComboBox.currentText()
        if fitType == 'Mean':
            return {
                'type': fitType,
                'value': np.mean(y)
            }
        elif fitType == 'Median':
            return {
                'type': fitType,
                'value': np.median(y)
            }
        elif fitType == 'Min':
            return {
                'type': fitType,
                'value': np.min(y)
            }
        elif fitType == 'Max':
            return {
                'type': fitType,
                'value': np.max(y)
            }
        elif fitType == 'AbsMax':
            return {
                'type': fitType,
                'value': np.max(np.abs(y))
            }
        elif fitType == 'Line':
            return {
                'type': fitType,
                'coef': np.polyfit(x, y, 1)
            }
        elif fitType == 'Polynomial':
            degree = self._polynomialDegreeSpinBox.value()
            return {
                'type': fitType,
                'degree': degree,
                'coef': np.polyfit(x, y, degree)
            }
        # elif fitType == 'BSpline':
        #     # !!! this is SLOW for even slightly large arrays
        #     n_pts = len(x)
        #     degree = self._bsplineDegreeSpinBox.value()
        #     smoothing = self._bsplineSmoothingSpinBox.value()
        #     if smoothing == 0:
        #         smoothing = n_pts
        #     n_knots = self._bsplineNumberOfKnotsSpinBox.value()
        #     if n_knots == 0:
        #         n_knots = None
        #     else:
        #         # ensure valid number of knots
        #         n_knots = min(max(2 * degree + 2, n_knots), n_pts + degree + 1)
        #     bspline: sp.interpolate.BSpline = sp.interpolate.make_splrep(x, y, s=smoothing, nest=n_knots)
        #     return bspline
        elif fitType == 'Spline':
            n_segments = self._splineNumberOfSegmentsSpinbox.value()
            segment_length = max(3, int(len(x) / n_segments))
            knots = x[segment_length:-segment_length:segment_length]
            # knots = x[::segment_length]
            # if len(knots) < 2:
            #     knots = x[[1, -2]]
            knots, coef, degree = sp.interpolate.splrep(x, y, t=knots)
            return {
                'type': fitType,
                'knots': knots,
                'coef': coef,
                'degree': degree,
            }
        elif fitType == 'Expression' or fitType in list(self._namedExpressions.keys()):
            model: lmfit.models.ExpressionModel = self._getExpressionModel()
            if model is None:
                return None
            result: lmfit.model.ModelResult = model.fit(y, params=model.make_params(), x=x)
            # print(result.fit_report())
            return {
                'type': fitType,
                'result': result,
            }
        
    def _predict(self, x: np.ndarray, fit_result) -> np.ndarray:
        """ Eval fit(x) """

        fitType = self._fitTypeComboBox.currentText()
        if fitType in ['Mean', 'Median', 'Min', 'Max', 'AbsMax']:
            value = fit_result['value']
            return np.full(len(x), value)
        elif fitType in ['Line', 'Polynomial']:
            coef = fit_result['coef']
            return np.polyval(coef, x)
        # elif fitType == 'BSpline':
        #     bspline: sp.interpolate.BSpline = fit_result
        #     return bspline(x)
        elif fitType == 'Spline':
            knots, coef, degree = [fit_result[key] for key in ['knots', 'coef', 'degree']]
            return sp.interpolate.splev(x, (knots, coef, degree ), der=0)
        elif fitType == 'Expression' or fitType in list(self._namedExpressions.keys()):
            if fit_result is None:
                model = self._getExpressionModel()
                if model is None:
                    return None
                params = model.make_params()
            else:
                result: lmfit.model.ModelResult = fit_result['result']
                model: lmfit.models.ExpressionModel = result.model
                params = result.params
            return model.eval(params=params, x=x)
    
    def _getExpressionModel(self) -> lmfit.models.ExpressionModel | None:
        expression = self._expressionEdit.text().strip()
        if 'x' not in expression:
            return None
        model = lmfit.models.ExpressionModel(expression, independent_vars=['x'])
        params = self._getEquationTableParams()
        for name in model.param_names:
            model.set_param_hint(name, **params[name])
        return model
    
    def _getEquationTableParams(self) -> dict:
        params = {}
        for row in range(self._expressionParamsTable.rowCount()):
            name = self._expressionParamsTable.item(row, 0).text()
            try:
                value = float(self._expressionParamsTable.item(row, 1).text())
            except:
                value = 0
            vary = self._expressionParamsTable.item(row, 2).checkState() == Qt.CheckState.Checked
            try:
                value_min = float(self._expressionParamsTable.item(row, 3).text())
            except:
                value_min = -np.inf
            try:
                value_max = float(self._expressionParamsTable.item(row, 4).text())
            except:
                value_max = np.inf
            params[name] = {
                'value': value,
                'vary': vary,
                'min': value_min,
                'max': value_max
            }
        return params
    
    def _setEquationTableParams(self, params: dict | lmfit.Parameters) -> None:
        if isinstance(params, lmfit.Parameters):
            params = params.valuesdict()

        self._expressionParamsTable.model().dataChanged.disconnect()  # needed because blockSignals not working!?
        self._expressionParamsTable.blockSignals(True)  # not working!?
        self._expressionParamsTable.clearContents()
        
        self._expressionParamsTable.setRowCount(len(params))
        row = 0
        for name, attrs in params.items():
            value = attrs.get('value', 0)
            vary = attrs.get('vary', True)
            value_min = attrs.get('min', -np.inf)
            value_max = attrs.get('max', np.inf)

            name_item = QTableWidgetItem(name)
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            value_item = QTableWidgetItem(f'{value:.6g}')
            vary_item = QTableWidgetItem()
            vary_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            vary_item.setCheckState(Qt.CheckState.Checked if vary else Qt.CheckState.Unchecked)
            min_item = QTableWidgetItem(str(value_min))
            max_item = QTableWidgetItem(str(value_max))

            for col, item in enumerate([name_item, value_item, vary_item, min_item, max_item]):
                self._expressionParamsTable.setItem(row, col, item)
            row += 1
        
        self._expressionParamsTable.resizeColumnsToContents()
        self._expressionParamsTable.blockSignals(False)
        self._expressionParamsTable.model().dataChanged.connect(lambda model_index: self._update_plot_data())  # needed because blockSignals not working!? TODO: wasteful to update all plot data
    
    def _curve_fit_live_preview_enabled(self) -> bool:
        return self._toggle_curve_fit_panel_action.isChecked() and self._fitLivePreviewCheckbox.isChecked()
    
    def _curve_fit_depends_on_ROIs(self) -> bool:
        return self._limitFitInputToROIsCheckbox.isChecked() or self._limitFitOutputToROIsCheckbox.isChecked()
    
    def _measure(self, x: np.ndarray, y: np.ndarray) -> tuple[float | np.ndarray, float | np.ndarray]:
        """ Measurement (reduction) for y(x) """

        # remove NaN
        mask = np.isnan(x) | np.isnan(y)
        if np.any(mask):
            xoriginal = x
            yoriginal = y
            x = x[~mask]
            y = y[~mask]
        
        measureType = self._measure_type_combobox.currentText()
        if measureType == 'Mean':
            return np.mean(x), np.mean(y)
        elif measureType == 'Median':
            return np.mean(x), np.median(y)
        elif measureType == 'Min':
            i = np.argmin(y)
            return x[i], y[i]
        elif measureType == 'Max':
            i = np.argmax(y)
            return x[i], y[i]
        elif measureType == 'AbsMax':
            i = np.argmax(np.abs(y))
            return x[i], y[i]
        elif measureType == 'Peaks':
            peakType = self._measure_peak_type_combobox.currentText()
            maxPeaks = self._max_num_peaks_per_region_spinbox.value()
            npts = self._measure_peak_avg_half_width_spinbox.value()
            
            if peakType == 'Positive':
                if maxPeaks == 1:
                    # single peak
                    peak_indices = [np.argmax(y)]
                else:
                    # multiple peaks
                    pass # TODO
            elif peakType == 'Negative':
                if maxPeaks == 1:
                    # single peak
                    peak_indices = [np.argmin(y)]
                else:
                    # multiple peaks
                    pass # TODO
            
            if npts == 0:
                # value at peak
                return x[peak_indices], y[peak_indices]
            else:
                # average around peak
                xmeasure = []
                ymeasure = []
                for i, peak_index in enumerate(peak_indices):
                    unmasked_indices = np.where(~mask)[0]
                    within_peak_indices = unmasked_indices[max(0, peak_index - npts):min(peak_index + npts + 1, len(mask))]
                    within_peak_indices = [i for i in within_peak_indices if ~mask[i]]
                    xmeasure.append(np.mean(x[within_peak_indices]))
                    ymeasure.append(np.mean(y[within_peak_indices]))
                if len(ymeasure) == 1:
                    return xmeasure[0], ymeasure[0]
                else:
                    return np.array(xmeasure), np.array(ymeasure)
    
    def _measurement_live_preview_enabled(self) -> bool:
        return self._toggle_measurement_panel_action.isChecked() and self._measureLivePreviewCheckbox.isChecked()
    
    def _update_datatree_view(self) -> None:
        """ Update the datatree view for the current datatree. """
        self._datatree_view.setDatatree(self.datatree)
    
    def _update_ROItree_view(self) -> None:
        """ Update the ROI tree view for the current datatree selection. """

        # limit paths to selected objects that have ROIs (and their ancestor nodes)
        ROI_paths = []
        for path in self._selected_datatree_paths:
            obj = self.datatree[path]
            if ROI_KEY in obj.attrs:
                ROI_paths.append(path)
            if path == '/':
                continue
            if isinstance(obj, xr.DataTree):
                parent_node = obj.parent
            elif isinstance(obj, xr.DataArray):
                parent_path = '/'.join(path.rstrip('/').split('/')[:-1])
                parent_node = self.datatree[parent_path]
            while parent_node is not None:
                if ROI_KEY in parent_node.attrs and parent_node.path not in ROI_paths:
                    ROI_paths.append(parent_node.path)
                parent_node = parent_node.parent
        
        # order paths according to datatree
        ordered_ROI_paths = []
        if ROI_paths:
            for node in self.datatree.subtree:
                if node.path in ROI_paths:
                    ordered_ROI_paths.append(node.path)
                for name in node.data_vars:
                    path = f'{node.path}/{name}'
                    if path in ROI_paths:
                        ordered_ROI_paths.append(path)
                # for name in node.coords:
                #     path = f'{node.path}/{name}'
                #     if path in ROI_paths:
                #         ordered_ROI_paths.append(path)
        
        # always include the root datatree node
        if '/' not in ordered_ROI_paths:
            ordered_ROI_paths = ['/'] + ordered_ROI_paths
        
        selected_ROIs = self._ROItree_view.selectedAnnotations()
        self._ROItree_view.blockSignals(True)
        self._ROItree_view.storeState()
        self._ROItree_view.setDataTree(self.datatree, paths=ordered_ROI_paths, key=ROI_KEY)
        self._ROItree_view.restoreState()
        self._ROItree_view.setSelectedAnnotations(selected_ROIs)
        self._ROItree_view.blockSignals(False)
    
    def _update_filter_menu(self) -> None:
        """ Update the dropdown filter menu in the top toolbar. """

        menu = self._filter_menu
        widget_actions = menu.actions()
        before = widget_actions.index(self._before_filter_data_vars_action)
        after = widget_actions.index(self._after_filter_data_vars_action)
        widget_actions = widget_actions[before+1:after]

        existing_checkboxes = [action.defaultWidget() for action in widget_actions]
        existing_var_names = [checkbox.text() for checkbox in existing_checkboxes]

        # remove old actions
        for action in widget_actions:
            menu.removeAction(action)
        
        # get all data_var names in datatree
        var_names = []
        for node in self.datatree.subtree:
            for name in list(node.data_vars.keys()):
                if name not in var_names:
                    var_names.append(name)
        has_mask = MASK_KEY in var_names
        if has_mask:
            var_names.remove(MASK_KEY)
        var_names.append(MASK_KEY)
        
        # add new actions
        for var_name in var_names:
            if var_name in existing_var_names:
                i = existing_var_names.index(var_name)
                action = widget_actions[i]
            else:
                checkbox = QCheckBox(var_name)
                checkbox.setChecked(var_name != MASK_KEY)
                checkbox.toggled.connect(lambda checked: self._on_datatree_selection_changed())
                action = QWidgetAction(self)
                action.setDefaultWidget(checkbox)
            menu.insertAction(self._after_filter_data_vars_action, action)
            if var_name == MASK_KEY:
                action.setEnabled(has_mask)
    
    def _update_dim_iter_things(self) -> None:
        """ Update dimension iterator widgets in the top toolbar. """

        coords: xr.Dataset = self._selection_combined_coords
        selected_vars = [self.datatree[path] for path in self._selected_var_paths]
        ordered_dims = self._selection_ordered_dims
        vdim = getattr(self, '_vertical_tile_dimension', None)
        hdim = getattr(self, '_horizontal_tile_dimension', None)

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
                widget._spinbox.indicesChanged.connect(lambda: self._on_dimension_slice_changed())
                widget.xdimChanged.connect(self.setXDim)
                widget.tileChanged.connect(self.tileDimension)
                self._dim_iter_things[dim] = {'widget': widget}
            
            widget = self._dim_iter_things[dim]['widget']
            widget.setCoords(coords[dim].values)
            widget.updateTileButton(vdim, hdim)

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
    
    def _update_left_panel(self) -> None:
        """ show/hide left control panel based on action group in left toolbar """

        action = self._left_panel_action_group.checkedAction()
        if action is None:
            self._left_panels_stack.setVisible(False)
            return
        
        action2widget = {
            self._toggle_datatree_panel_action: self._datatree_viewer,
            self._toggle_filter_panel_action: self._filter_panel,
            self._toggle_curve_fit_panel_action: self._curve_fit_panel,
            self._toggle_measurement_panel_action: self._measurement_panel,
            self._toggle_notes_panel_action: self._notes_edit,
        }
        widget = action2widget[action]
        self._left_panels_stack.setCurrentWidget(widget)
        self._left_panels_stack.setVisible(True)
    
    def _update_filter_control_panel(self) -> None:
        filterType = self._filter_type_combobox.currentText()
        if filterType == 'Gaussian':
            self._filter_band_type_combobox.blockSignals(True)
            self._filter_band_type_combobox.setCurrentText('Lowpass')
            self._filter_band_type_combobox.setEnabled(False)
            # for i in range(self._filter_band_type_combobox.count()):
            #     item = self._filter_band_type_combobox.model().item(i)
            #     if item.text() == 'Lowpass':
            #         item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEnabled)
            #     else:
            #         item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self._filter_band_type_combobox.blockSignals(False)
        
        bandType = self._filter_band_type_combobox.currentText()
        if bandType == 'Lowpass':
            self._filter_cutoff_edit.setPlaceholderText('lowpass frequency')
        elif bandType == 'Highpass':
            self._filter_cutoff_edit.setPlaceholderText('highpass frequency')
        elif bandType == 'Bandpass':
            self._filter_cutoff_edit.setPlaceholderText('low, high band frequencies')
    
    def _update_curve_fit_control_panel(self) -> None:
        fitTypes = [self._fitTypeComboBox.itemText(i) for i in range(self._fitTypeComboBox.count())]
        fitType = self._fitTypeComboBox.currentText()
        self._polynomialGroupBox.setVisible(fitType == 'Polynomial')
        self._splineGroupBox.setVisible(fitType == 'Spline')
        isExpression = self._fitTypeComboBox.currentIndex() >= fitTypes.index('Expression')
        self._expressionGroupBox.setVisible(isExpression)
        if isExpression:
            self._fitControlsSpacer.changeSize(0, 0, QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
        else:
            self._fitControlsSpacer.changeSize(0, 0, QSizePolicy.Policy.Ignored, QSizePolicy.Policy.MinimumExpanding)
    
    def _update_measurement_control_panel(self) -> None:
        measureType = self._measure_type_combobox.currentText()
        self._measure_peak_group.setVisible(measureType == 'Peaks')
    
    def _update_plot_grids(self) -> None:
        """ Update plot grids for selected variables and current plot tiling. """

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
        vdim, hdim, vcoords, hcoords = self._get_tile_dims()
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
        
        self._update_plot_metadata()
        self._update_plot_axis_labels()
        self._update_plot_axis_tick_font()
        self._update_plot_axis_links()
        self.replot()

    def _update_plot_metadata(self) -> None:
        """ Update metadata stored in each plot. """

        vdim, hdim, vcoords, hcoords = self._get_tile_dims()
        n_vars, n_grid_rows, n_grid_cols = self._plots.shape
        for i in range(n_vars):
            var_name = self._selected_var_names[i]
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
                    plot_coords_dict = {dim: arr.values for dim, arr in plot_coords.coords.items() if dim != self.xdim}
                    
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

        xunits = self._selection_units.get(self.xdim, None)
        axis_label_style = {'color': 'rgb(0, 0, 0)', 'font-size': f'{self._axis_label_fontsize_spinbox.value()}pt'}

        vdim, hdim, vcoords, hcoords = self._get_tile_dims()
        n_vars, n_grid_rows, n_grid_cols = self._plots.shape
        for i in range(n_vars):
            var_name = self._selected_var_names[i]
            yunits = self._selection_units.get(var_name, None)
            for row in range(n_grid_rows):
                for col in range(n_grid_cols):
                    plot = self._plots[i, row, col]
                    if (i == n_vars - 1) and (row == n_grid_rows - 1):
                        label = self.xdim
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
        """ Update graphs in each plot to show current datatree selection. """

        if (self.xdim is None) or (self.xdim not in self._selection_combined_coords):
            return
        
        default_line_width = self._linewidth_spinbox.value()

        # categorical (string) xdim values?
        is_xdim_categorical = False
        all_xticks = None  # will use default ticks
        all_xdata = self._selection_combined_coords[self.xdim].values
        if not np.issubdtype(all_xdata.dtype, np.number):
            is_xdim_categorical = True
            all_xtick_values = np.arange(len(all_xdata))
            all_xtick_labels = all_xdata  # str xdim values
            all_xticks = [list(zip(all_xtick_values, all_xtick_labels))]
        
        for plot in self._plots.flatten().tolist():
            view: pgx.View = plot.getViewBox()

            # set xticks (in case change between numerical and categorical)
            plot.getAxis('bottom').setTicks(all_xticks)
            
            # existing graphs in plot
            graphs = [item for item in plot.listDataItems() if isinstance(item, pgx.Graph)]
            data_graphs = [graph for graph in graphs if hasattr(graph, '_metadata') and graph._metadata.get('type', None) == 'data']
            masked_graphs = [graph for graph in graphs if hasattr(graph, '_metadata') and graph._metadata.get('type', None) == 'masked']
            preview_graphs = [graph for graph in graphs if hasattr(graph, '_metadata') and graph._metadata.get('type', None) == 'preview']
            
            # update graphs in plot
            data_count = 0
            masked_count = 0
            preview_count = 0
            color_index = 0
            for var_path in self._selected_var_paths:
                var_name = var_path.rstrip('/').split('/')[-1]
                if var_name not in plot._metadata['data_vars']:
                    continue
                
                data_var = self.datatree[var_path].reset_coords(drop=True)
                if self.xdim not in data_var.coords:
                    continue
                data_var = to_base_units(data_var)

                node_path = var_path.rstrip('/').rstrip(var_name).rstrip('/')
                node = self.datatree[node_path]
                
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
                    if not coords:
                        data_var_slice = data_var
                    else:
                        coords = {dim: values for dim, values in coords.items() if dim in data_var.coords}
                        if not coords:
                            data_var_slice = data_var
                        else:
                            data_var_slice = data_var.sel(coords)
                    xdim_coord_slice = data_var_slice.coords[self.xdim]
                    xdata = xdim_coord_slice.values
                    ydata = data_var_slice.values

                    if np.all(np.isnan(ydata)):
                        continue
                    
                    # categorical xdim values?
                    if not np.issubdtype(xdata.dtype, np.number):
                        intersect, xdata_indices, all_xtick_labels_indices = np.intersect1d(xdata, all_xtick_labels, assume_unique=True, return_indices=True)
                        xdata = np.sort(all_xtick_labels_indices)
                        xdim_coord_slice = data_var_slice.coords[self.xdim].copy(data=xdata)
                    
                    # filter data?
                    if self._filterLivePreviewCheckbox.isChecked():
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
            if not self._curve_fit_live_preview_enabled() and not self._measurement_live_preview_enabled():
                cleanup_graphs += [(preview_graphs, preview_count)]
            for graphs, count in cleanup_graphs:
                while len(graphs) > count:
                    graph = graphs.pop()
                    plot.removeItem(graph)
                    graph.deleteLater()
        
        if self._curve_fit_live_preview_enabled():
            self._update_curve_fit_preview()
        elif self._measurement_live_preview_enabled():
            self._update_measurement_preview()

    def _update_preview(self) -> None:
        if self._toggle_curve_fit_panel_action.isChecked():
            self._update_curve_fit_preview()
        else:
            self._update_measurement_preview()
    
    def _update_curve_fit_preview(self, force_preview: bool = False, update_data: bool = False, no_residuals: bool = False) -> None:
        """ Update curve fit preview of currently plotted data. """

        if not force_preview and not self._curve_fit_live_preview_enabled() and self._fitPreviewResidualsCheckbox.isChecked():
            # this will clear all previews and reset data graphs
            self._update_plot_data()
            return

        ROIs = self.selectedROIs()
        
        for plot in self._plots.flatten().tolist():
            # existing graphs in plot
            graphs = [item for item in plot.listDataItems() if isinstance(item, pgx.Graph)]
            data_graphs = [graph for graph in graphs if hasattr(graph, '_metadata') and graph._metadata.get('type', None) == 'data']
            preview_graphs = [graph for graph in graphs if hasattr(graph, '_metadata') and graph._metadata.get('type', None) == 'preview']

            # clear all preview graphs
            if not force_preview and not self._curve_fit_live_preview_enabled():
                for graph in preview_graphs:
                    plot.removeItem(graph)
                    graph.deleteLater()
                continue
            
            # update graphs in plot
            preview_count = 0
            for data_graph in data_graphs:
                # xdata, ydata = data_graph.getOriginalDataset()
                
                # we need the references to the actual data in case we are looking at resiuduals
                data: xr.DataArray = data_graph._metadata.get('data', None)
                if data is None:
                    continue
                
                xdata: np.ndarray = data.coords[self.xdim].values
                ydata: np.ndarray = data.values
                    
                # categorical xdim values?
                if not np.issubdtype(xdata.dtype, np.number):
                    xdata, _ = data_graph.getOriginalDataset()
                
                mask: xr.DataArray = data_graph._metadata.get('mask', None)
                if (mask is not None) and not self.isMaskedVisible():
                    xdata = xdata.copy() # don't overwrite original data
                    ydata = ydata.copy() # don't overwrite original data
                    xdata[mask.values] = np.nan
                    ydata[mask.values] = np.nan

                xin: np.ndarray = xdata
                yin: np.ndarray = ydata

                if (mask is not None) and self.isMaskedVisible():
                    # even thogh mask is visible, do not use it for the fit
                    xin = xin.copy() # don't overwrite original data
                    yin = yin.copy() # don't overwrite original data
                    xin[mask.values] = np.nan
                    yin[mask.values] = np.nan

                if self._limitFitInputToROIsCheckbox.isChecked() and self.isROIsVisible() and ROIs:
                    ROI_mask = np.full(xin.shape, False, dtype=bool)
                    for ROI in ROIs:
                        xmin, xmax = ROI['position'][self.xdim]
                        ROI_mask[(xin >= xmin) & (xin <= xmax)] = True
                    yin = yin.copy()
                    yin[~ROI_mask] = np.nan
                
                fit_result = self._fit(xin, yin)
                if fit_result is None:
                    continue

                xout: np.ndarray = xdata
                
                if self._limitFitOutputToROIsCheckbox.isChecked() and self.isROIsVisible() and ROIs:
                    ROI_mask = np.full(xout.shape, False, dtype=bool)
                    for ROI in ROIs:
                        xmin, xmax = ROI['position'][self.xdim]
                        ROI_mask[(xout >= xmin) & (xout <= xmax)] = True
                    xout = xout.copy()
                    xout[~ROI_mask] = np.nan
                
                yout: np.ndarray = np.full(xout.shape, np.nan)
                out_mask = ~np.isnan(xout)
                prediction: np.ndarray = self._predict(xout[out_mask], fit_result)
                if prediction is None:
                    continue
                yout[out_mask] = prediction

                # show (or stop showing) residuals?
                if update_data or (self._fitLivePreviewCheckbox.isChecked() and self._fitPreviewResidualsCheckbox.isChecked() and not no_residuals):
                    ymasked = None
                    masked_graph: pgx.Graph = data_graph._metadata.get('masked graph', None)
                    if masked_graph is not None:
                        ymasked: np.ndarray = data.values
                        if mask is not None:
                            ymasked = ymasked.copy() # don't overwrite original data
                            ymasked[~mask.values] = np.nan
                    if self._fitPreviewResidualsCheckbox.isChecked():
                        ydata = ydata.copy()
                        ydata -= yout
                        if ymasked is not None:
                            ymasked = ymasked.copy()
                            ymasked -= yout
                        yout -= yout
                    data_graph.setData(x=xdata, y=ydata)
                    if ymasked is not None:
                        masked_graph.setData(x=xdata, y=ymasked)
                
                # graph fit
                if len(preview_graphs) > preview_count:
                    # update existing data in plot
                    preview_graph = preview_graphs[preview_count]
                    preview_graph.setData(x=xout, y=yout)
                else:
                    # add new data to plot
                    preview_graph = pgx.Graph(x=xout, y=yout)
                    plot.addItem(preview_graph)
                    preview_graphs.append(preview_graph)
                preview_count += 1
                        
                preview_graph._metadata = copy(data_graph._metadata)
                preview_graph._metadata['type'] = 'preview'
                preview_graph._metadata['fit'] = fit_result
                preview_graph.setZValue(2)
                preview_graph.setName(data_graph.name() + ' preview')
                style: pgx.GraphStyle = data_graph.graphStyle()
                style['linewidth'] = 2
                style['color'] = '(255, 0, 0)'
                preview_graph.setGraphStyle(style)
            
            # remove extra graph items from plot
            for graphs, count in [(preview_graphs, preview_count)]:
                while len(graphs) > count:
                    graph = graphs.pop()
                    plot.removeItem(graph)
                    graph.deleteLater()
    
    def _update_measurement_preview(self, force_preview: bool = False) -> None:
        """ Update measurement preview of currently plotted data. """

        ROIs = self.selectedROIs()
        has_ROIs = self.isROIsVisible() and ROIs
        
        for plot in self._plots.flatten().tolist():
            # existing graphs in plot
            graphs = [item for item in plot.listDataItems() if isinstance(item, pgx.Graph)]
            data_graphs = [graph for graph in graphs if hasattr(graph, '_metadata') and graph._metadata.get('type', None) == 'data']
            preview_graphs = [graph for graph in graphs if hasattr(graph, '_metadata') and graph._metadata.get('type', None) == 'preview']

            # clear all preview graphs
            if not force_preview and not self._measurement_live_preview_enabled():
                for graph in preview_graphs:
                    plot.removeItem(graph)
                    graph.deleteLater()
                continue
            
            # update graphs in plot
            preview_count = 0
            for data_graph in data_graphs:
                xdata, ydata = data_graph.getOriginalDataset()

                # get measurement
                if has_ROIs and self._measure_per_ROI_checkbox.isChecked():
                    xmeasure = []
                    ymeasure = []
                    for ROI in ROIs:
                        xmin, xmax = ROI['position'][self.xdim]
                        ROI_mask = (xdata >= xmin) & (xdata <= xmax)
                        x, y = self._measure(xdata[ROI_mask], ydata[ROI_mask])
                        if isinstance(y, np.ndarray):
                            xmeasure += x.tolist()
                            ymeasure += y.tolist()
                        else:
                            xmeasure.append(x)
                            ymeasure.append(y)
                    xmeasure, ymeasure = np.array(xmeasure), np.array(ymeasure)
                elif has_ROIs and self._measure_in_ROIs_only_checkbox.isChecked():
                    ROI_mask = np.full(xdata.shape, False, dtype=bool)
                    for ROI in ROIs:
                        xmin, xmax = ROI['position'][self.xdim]
                        ROI_mask[(xdata >= xmin) & (xdata <= xmax)] = True
                    xdata = xdata.copy()
                    ydata = ydata.copy()
                    xdata[~ROI_mask] = np.nan
                    ydata[~ROI_mask] = np.nan
                    xmeasure, ymeasure = self._measure(xdata, ydata)
                else:
                    xmeasure, ymeasure = self._measure(xdata, ydata)
                
                if not isinstance(ymeasure, np.ndarray):
                    xmeasure, ymeasure = np.array([xmeasure]), np.array([ymeasure])
                
                # graph measurement
                if len(preview_graphs) > preview_count:
                    # update existing data in plot
                    preview_graph = preview_graphs[preview_count]
                    preview_graph.setData(x=xmeasure, y=ymeasure)
                else:
                    # add new data to plot
                    preview_graph = pgx.Graph(x=xmeasure, y=ymeasure)
                    plot.addItem(preview_graph)
                    preview_graphs.append(preview_graph)
                preview_count += 1
                        
                preview_graph._metadata = copy(data_graph._metadata)
                preview_graph._metadata['type'] = 'preview'
                preview_graph.setZValue(2)
                preview_graph.setName(data_graph.name() + ' preview')
                style: pgx.GraphStyle = data_graph.graphStyle()
                style['marker'] = 'o'
                style['linestyle'] = 'none'
                style['markeredgewidth'] = 2
                style['color'] = '(255, 0, 0)'
                preview_graph.setGraphStyle(style)
            
            # remove extra graph items from plot
            for graphs, count in [(preview_graphs, preview_count)]:
                while len(graphs) > count:
                    graph = graphs.pop()
                    plot.removeItem(graph)
                    graph.deleteLater()
    
    def _update_plot_ROIs(self) -> None:
        """ Update ROI regions in each plot to show current ROItree selection. """

        plots = self._plots.flatten().tolist()
        
        if not self.isROIsVisible():
            for plot in plots:
                ROI_items = [item for item in plot.vb.allChildren() if isinstance(item, pgx.XAxisRegion) and hasattr(item, '_ROI')]
                for item in ROI_items:
                    plot.vb.removeItem(item)
                    item.deleteLater()
            return
        
        selected_ROIs = self._ROItree_view.selectedAnnotations()
        
        for plot in plots:
            current_ROI_items = [item for item in plot.vb.allChildren() if isinstance(item, pgx.XAxisRegion) and hasattr(item, '_ROI')]
            current_ROIs = [item._ROI for item in current_ROI_items]

            items_to_remove = [item for item in current_ROI_items if item._ROI not in selected_ROIs]
            for item in items_to_remove:
                plot.vb.removeItem(item)
                item.deleteLater()
            
            items_to_update = [item for item in current_ROI_items if item._ROI in selected_ROIs]
            for item in items_to_update:
                self._update_ROI_plot_item_from_data(item, item._ROI)
            
            ROIs_to_add = [ROI for ROI in selected_ROIs if ROI not in current_ROIs]
            for ROI in ROIs_to_add:
                self._add_ROI_to_plot(ROI, plot)

    def _update_ROI_plot_item_from_data(self, item: pgx.XAxisRegion, data: dict) -> None:
        """ Apply ROI data to plotted ROI region. """

        item.setRegion(data['position'][self.xdim])
        item.setMovable(data.get('movable', True))
        item.setText(data.get('text', ''))
        # item.setFormat(data.get('format', {}))

    def _update_ROI_data_from_plot_item(self, item: pgx.XAxisRegion, data: dict) -> None:
        """ Update ROI data from plotted ROI region. """

        data['position'] = {self.xdim: item.getRegion()}
        data['movable'] = item.movable
        data['text'] = item.text()
        # data['format'] = item.getFormat()
    
    def _update_ROI_font(self) -> None:
        """ Use settings font for all ROI regions in each plot. """

        for plot in self._plots.flatten().tolist():
            view: pgx.View = plot.getViewBox()
            for item in view.allChildren():
                if isinstance(item, pgx.XAxisRegion):
                    item.setFontSize(self._ROI_fontsize_spinbox.value())

    def _update_icons(self) -> None:
        """ Apply settings icon options to all toolbar icons. """

        size = self._toolbar_iconsize_spinbox.value()
        icon_size = QSize(size, size)
        for toolbar in [self._top_toolbar, self._left_toolbar]:
            toolbar.setIconSize(icon_size)

    def _init_UI(self) -> None:
        """ Initialize all UI components. """

        self.setWindowTitle(self.__class__.__name__)

        self._init_console()
        self._init_actions()
        self._init_menubar()
        self._init_top_toolbar()
        self._init_left_toolbar()
        self._init_settings()
        self._init_datatree_viewer()
        self._init_filter_panel()
        self._init_curve_fit_panel()
        self._init_measurement_panel()
        self._init_notes_edit()

        self._data_var_views_splitter = QSplitter(Qt.Orientation.Vertical)

        self._left_panels_stack = QStackedWidget()
        self._left_panels_stack.addWidget(self._datatree_viewer)
        self._left_panels_stack.addWidget(self._filter_panel)
        self._left_panels_stack.addWidget(self._curve_fit_panel)
        self._left_panels_stack.addWidget(self._measurement_panel)
        self._left_panels_stack.addWidget(self._notes_edit)

        self._inner_vsplitter = QSplitter(Qt.Orientation.Vertical)
        self._inner_vsplitter.addWidget(self._data_var_views_splitter)
        self._inner_vsplitter.addWidget(self._console)
        self._inner_vsplitter.setSizes([self.sizeHint().height() - 250, 250])

        self._outer_hsplitter = QSplitter(Qt.Orientation.Horizontal)
        self._outer_hsplitter.addWidget(self._left_panels_stack)
        self._outer_hsplitter.addWidget(self._inner_vsplitter)
        self._outer_hsplitter.setSizes([250, self.sizeHint().width() - 250])

        self.setCentralWidget(self._outer_hsplitter)

        self.refresh()
    
    def _init_console(self) -> None:
        """ Embedded IPython console """

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
        """ Inform user how to access data in console. """

        msg = """
        ----------------------------------------------------
        Welcome to XarrayGraph console!
          self          -> This instance of XarrayGraph
          self.datatree -> The Xarray DataTree
        Array access: self.datatree['/path/to/array']
            shortcut: self['/path/to/array']
        Modules loaded at startup: numpy as np, xarray as xr
        ----------------------------------------------------
        """
        msg = textwrap.dedent(msg).strip()
        self._console._append_plain_text(msg, before_prompt=True)
    
    def _shutdown_console(self) -> None:
        """ Shutdown the embedded console. """

        if self._console is None:
            return
        self._console.kernel_client.stop_channels()
        self._console.kernel_manager.shutdown_kernel()
        self._console.deleteLater()
        self._console = None
    
    def _init_actions(self) -> None:
        """ UI actions """

        self._refresh_action = QAction(
            parent=self, 
            icon=get_icon('mdi.refresh'), 
            iconVisibleInMenu=False,
            text='Refresh UI',
            toolTip='Refresh UI',
            shortcut = QKeySequence('Ctrl+R'),
            triggered=lambda checked: self.refresh())

        self._about_action = QAction(
            parent=self, 
            icon=get_icon('fa5s.cubes'), 
            iconVisibleInMenu=False,
            text='About XarrayGraph', 
            toolTip='About XarrayGraph', 
            triggered=lambda checked: self.about())

        self._settings_action = QAction(
            parent=self, 
            icon=get_icon('msc.gear'), 
            iconVisibleInMenu=False,
            text='Settings', 
            toolTip='Settings', 
            triggered=lambda checked: self.settings())

        self._toggle_console_action = QAction(
            parent=self, 
            icon=get_icon('mdi.console'), 
            iconVisibleInMenu=False,
            text='Console', 
            toolTip='Console', 
            checkable=True, 
            checked=True,
            shortcut = QKeySequence('`'),
            triggered=lambda checked: self._console.setVisible(checked))

        self._draw_ROI_action = QAction(
            parent = self, 
            icon = get_icon('mdi.arrow-expand-horizontal'), 
            iconVisibleInMenu = False,
            text = 'Select Range ROI', 
            toolTip = 'Create range ROI with mouse click+drag.',
            checkable=True, 
            checked=False,
            shortcut = QKeySequence('R'),
            triggered = lambda: self._toggle_drawing_ROIs())

        self._home_action = QAction(
            parent = self, 
            icon = get_icon('mdi.home'), 
            iconVisibleInMenu = False,
            text = 'Autoscale', 
            toolTip = 'Autoscale',
            triggered = lambda: self.autoscale())

        self._view_masked_action = QAction(
            parent = self, 
            text = 'Masked', 
            toolTip = 'Show Masked',
            checkable = True, 
            checked = False,
            triggered = lambda checked: self.setMaskedVisible(checked))

        self._view_ROIs_action = QAction(
            parent = self, 
            icon = get_icon('mdi.arrow-expand-horizontal'),
            iconVisibleInMenu = False,
            text = 'ROIs', 
            toolTip = 'Show ROIs',
            checkable = True, 
            checked = False,
            shortcut = QKeySequence('T'),
            triggered = lambda checked: self.setROIsVisible(checked))
        
        self._toggle_datatree_panel_action = QAction(
            parent=self, 
            icon=get_icon('mdi.file-tree'), 
            iconVisibleInMenu=False,
            text='Data Tree',
            toolTip='Data Tree',
            checkable=True, 
            checked=True)

        self._toggle_filter_panel_action = QAction(
            parent=self, 
            icon=get_icon('mdi.sine-wave'), 
            # icon=get_icon('ph.waves'), 
            # icon=get_icon('mdi.waveform'), 
            iconVisibleInMenu=False,
            text='Filter', 
            toolTip='Filter', 
            checkable=True, 
            checked=False)

        self._toggle_curve_fit_panel_action = QAction(
            parent=self, 
            icon=get_icon('mdi.chart-bell-curve-cumulative'), 
            iconVisibleInMenu=False,
            text='Curve Fit', 
            toolTip='Curve Fit', 
            checkable=True, 
            checked=False)

        self._toggle_measurement_panel_action = QAction(
            parent=self, 
            icon=get_icon('mdi.chart-scatter-plot'), 
            iconVisibleInMenu=False,
            text='Measure', 
            toolTip='Measure', 
            checkable=True, 
            checked=False)

        self._toggle_notes_panel_action = QAction(
            parent=self, 
            icon=get_icon('mdi6.text-box-edit-outline'), 
            iconVisibleInMenu=False,
            text='Notes', 
            toolTip='Notes', 
            checkable=True, 
            checked=False)

        self._left_panel_action_group = QActionGroup(self)
        self._left_panel_action_group.addAction(self._toggle_datatree_panel_action)
        self._left_panel_action_group.addAction(self._toggle_filter_panel_action)
        self._left_panel_action_group.addAction(self._toggle_curve_fit_panel_action)
        self._left_panel_action_group.addAction(self._toggle_measurement_panel_action)
        self._left_panel_action_group.addAction(self._toggle_notes_panel_action)
        self._left_panel_action_group.setExclusionPolicy(QActionGroup.ExclusionPolicy.ExclusiveOptional)
        self._left_panel_action_group.triggered.connect(lambda checked: self._update_left_panel())
        self._left_panel_action_group.triggered.connect(lambda checked: self._update_preview())

        self._group_selected_ROIs_action = QAction(
            parent=self, 
            text='Group Selected ROIs', 
            toolTip='Group Selected ROIs', 
            shortcut=QKeySequence('G'),
            triggered=lambda checked: self.groupSelectedROIs())

        self._move_selected_ROIs_action = QAction(
            parent=self, 
            text='Move Selected ROIs', 
            toolTip='Move Selected ROIs', 
            triggered=lambda checked: self.moveSelectedROIs())

        self._delete_selected_ROIs_action = QAction(
            parent=self, 
            text='Delete Selected ROIs', 
            toolTip='Delete Selected ROIs', 
            triggered=lambda checked: self.deleteSelectedROIs())

        self._clear_ROI_selection_action = QAction(
            parent=self, 
            text='Clear ROI Selection', 
            toolTip='Clear ROI Selection', 
            shortcut=QKeySequence('C'),
            triggered=lambda checked: self.clearROISelection())

        self._mask_selection_action = QAction(
            parent=self, 
            text='Mask Selection', 
            toolTip='Mask Selection', 
            shortcut=QKeySequence('M'),
            triggered=lambda checked: self.maskSelection())

        self._unmask_selection_action = QAction(
            parent=self, 
            text='Unmask Selection', 
            toolTip='Unmask Selection', 
            shortcut=QKeySequence('U'),
            triggered=lambda checked: self.unmaskSelection())
    
    def _init_menubar(self) -> None:
        """ Main menubar. """
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
        self._file_menu.addAction('Quit', QKeySequence.StandardKey.Quit, QApplication.instance().quit)

        self._import_menu.addAction('Zarr Zip', lambda: self.load(filetype='Zarr Zip'))
        self._import_menu.addAction('Zarr Directory', lambda: self.load(filetype='Zarr Directory'))
        self._import_menu.addAction('NetCDF', lambda: self.load(filetype='NetCDF'))
        self._import_menu.addAction('HDF5', lambda: self.load(filetype='HDF5'))
        self._import_menu.addSeparator()
        self._import_menu.addAction('WinWCP', lambda: self.load(filetype='WinWCP'))
        self._import_menu.addAction('HEKA', lambda: self.load(filetype='HEKA'))
        self._import_menu.addAction('Axon ABF', lambda: self.load(filetype='Axon ABF'))
        self._import_menu.addAction('MATLAB (GOLab TEVC)', lambda: self.load(filetype='MATLAB (GOLab TEVC)'))

        self._export_menu.addAction('Zarr Zip', lambda: self.saveAs(filetype='Zarr Zip'))
        self._export_menu.addAction('Zarr Directory', lambda: self.saveAs(filetype='Zarr Directory'))
        self._export_menu.addAction('NetCDF', lambda: self.saveAs(filetype='NetCDF'))
        self._export_menu.addAction('HDF5', lambda: self.saveAs(filetype='HDF5'))

        self._selection_menu = menubar.addMenu('Selection')
        self._selection_menu.addAction(self._draw_ROI_action)
        self._selection_menu.addSeparator()
        self._selection_menu.addAction(self._group_selected_ROIs_action)
        self._selection_menu.addAction(self._move_selected_ROIs_action)
        self._selection_menu.addAction(self._delete_selected_ROIs_action)
        self._selection_menu.addAction(self._clear_ROI_selection_action)
        self._selection_menu.addSeparator()
        self._selection_menu.addAction(self._mask_selection_action)
        self._selection_menu.addAction(self._unmask_selection_action)

        self._view_menu = menubar.addMenu('View')
        self._view_menu.addAction(self._view_ROIs_action)
        self._view_menu.addAction(self._view_masked_action)
        self._view_menu.addSeparator()
        self._view_menu.addAction(self._toggle_console_action)
        self._view_menu.addSeparator()
        self._view_menu.addAction(self._refresh_action)
        self._view_menu.addSeparator()
        self._view_menu.addAction(self._about_action)
        self._view_menu.addSeparator()
        self._view_menu.addAction(self._settings_action)
        self._view_menu.addSeparator()
    
    def _init_top_toolbar(self) -> None:
        """ Initialize top toolbar. """

        self._top_toolbar = QToolBar()
        self._top_toolbar.setOrientation(Qt.Orientation.Horizontal)
        self._top_toolbar.setStyleSheet("QToolBar{spacing:2px;}")
        self._top_toolbar.setIconSize(QSize(settings['icon size'], settings['icon size']))
        self._top_toolbar.setMovable(False)
        self._top_toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._top_toolbar)

        self._view_ROIs_checkbox = QCheckBox('ROIs', checked=self._view_ROIs_action.isChecked())
        self._view_ROIs_checkbox.checkStateChanged.connect(lambda state: self.setROIsVisible(state == Qt.CheckState.Checked))

        self._view_masked_checkbox = QCheckBox('Masked', checked=self._view_masked_action.isChecked())
        self._view_masked_checkbox.checkStateChanged.connect(lambda state: self.setMaskedVisible(state == Qt.CheckState.Checked))

        self._filter_button = QToolButton(
            icon=get_icon('mdi6.filter-multiple-outline'),
            toolTip='Filter Options',
            popupMode=QToolButton.ToolButtonPopupMode.InstantPopup,
        )
        self._filter_menu = QMenu()
        action = QWidgetAction(self)
        action.setDefaultWidget(self._view_ROIs_checkbox)
        self._filter_menu.addAction(action)
        action = QWidgetAction(self)
        action.setDefaultWidget(self._view_masked_checkbox)
        self._filter_menu.addAction(action)
        self._filter_menu.addSeparator()
        self._before_filter_data_vars_action = self._filter_menu.addAction('Variables:')
        self._before_filter_data_vars_action.setEnabled(False)
        self._after_filter_data_vars_action = self._filter_menu.addSeparator()
        self._filter_button.setMenu(self._filter_menu)

        self._before_dim_iter_things_spacer = QWidget()
        self._before_dim_iter_things_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        
        self._top_toolbar.addAction(self._about_action)
        self._top_toolbar.addWidget(self._filter_button)
        self._before_dim_iter_things_spacer_action = self._top_toolbar.addWidget(self._before_dim_iter_things_spacer)
        self._after_dim_iter_things_separator_action = self._top_toolbar.addSeparator()
        self._top_toolbar.addAction(self._draw_ROI_action)
        self._top_toolbar.addAction(self._home_action)

    def _init_left_toolbar(self) -> None:
        """ Initialize left toolbar. """

        self._left_toolbar = QToolBar()
        self._left_toolbar.setOrientation(Qt.Orientation.Vertical)
        self._left_toolbar.setStyleSheet("QToolBar{spacing:2px;}")
        self._left_toolbar.setIconSize(QSize(settings['icon size'], settings['icon size']))
        self._left_toolbar.setMovable(False)
        self._left_toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self._left_toolbar)

        vspacer = QWidget()
        vspacer.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)

        self._left_toolbar.addAction(self._toggle_datatree_panel_action)
        self._left_toolbar.addAction(self._toggle_filter_panel_action)
        self._left_toolbar.addAction(self._toggle_curve_fit_panel_action)
        self._left_toolbar.addAction(self._toggle_measurement_panel_action)
        self._left_toolbar.addAction(self._toggle_notes_panel_action)
        self._left_toolbar.addWidget(vspacer)
        self._left_toolbar.addAction(self._settings_action)
        self._left_toolbar.addAction(self._toggle_console_action)
    
    def _init_settings(self) -> None:
        """ Initialize settings panel. """

        self._linewidth_spinbox = QSpinBox()
        self._linewidth_spinbox.setValue(settings['line width'])
        self._linewidth_spinbox.setMinimum(1)
        self._linewidth_spinbox.valueChanged.connect(self._update_plot_data)

        self._axis_label_fontsize_spinbox = QSpinBox()
        self._axis_label_fontsize_spinbox.setValue(settings['axis label font size'])
        self._axis_label_fontsize_spinbox.setMinimum(1)
        self._axis_label_fontsize_spinbox.setSuffix('pt')
        self._axis_label_fontsize_spinbox.valueChanged.connect(self._update_plot_axis_labels)

        self._axis_tick_fontsize_spinbox = QSpinBox()
        self._axis_tick_fontsize_spinbox.setValue(settings['axis tick font size'])
        self._axis_tick_fontsize_spinbox.setMinimum(1)
        self._axis_tick_fontsize_spinbox.setSuffix('pt')
        self._axis_tick_fontsize_spinbox.valueChanged.connect(self._update_plot_axis_tick_font)

        self._ROI_fontsize_spinbox = QSpinBox()
        self._ROI_fontsize_spinbox.setValue(settings['ROI font size'])
        self._ROI_fontsize_spinbox.setMinimum(1)
        self._ROI_fontsize_spinbox.setSuffix('pt')
        self._ROI_fontsize_spinbox.valueChanged.connect(self._update_ROI_font)

        self._toolbar_iconsize_spinbox = QSpinBox()
        self._toolbar_iconsize_spinbox.setValue(settings['icon size'])
        self._toolbar_iconsize_spinbox.setMinimum(16)
        self._toolbar_iconsize_spinbox.setMaximum(64)
        self._toolbar_iconsize_spinbox.setSingleStep(8)
        self._toolbar_iconsize_spinbox.valueChanged.connect(self._update_icons)
        
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

        # self._settings_panel_scroll_area = QScrollArea()
        # self._settings_panel_scroll_area.setWidgetResizable(True)
        # self._settings_panel_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        # self._settings_panel_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        # self._settings_panel_scroll_area.setWidget(self._settings_panel)
    
    def _init_datatree_viewer(self) -> None:
        """ Initialize datatree viewer. """

        self._datatree_viewer = XarrayDataTreeViewer()
        self._datatree_view = self._datatree_viewer.view()
        self._datatree_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._datatree_view.setAlternatingRowColors(False)
        self._datatree_model: XarrayDataTreeModel = XarrayDataTreeModel(self.datatree)
        self._datatree_model.setDataVarsVisible(True)
        self._datatree_model.setCoordsVisible(False)
        self._datatree_model.setDetailsColumnVisible(False)
        self._datatree_view.setModel(self._datatree_model)
        self._datatree_view.expandAll()
        self._datatree_view.selectionWasChanged.connect(self._on_datatree_selection_changed)
        self._datatree_viewer.setSizes([400, 400])

        self._ROItree_view = AnnotationTreeView()
        self._ROItree_model = AnnotationTreeModel()
        self._ROItree_view.setModel(self._ROItree_model)
        self._ROItree_view.setHeaderHidden(True)
        self._ROItree_view.selectionWasChanged.connect(lambda: self.setROIsVisible(True))
        self._datatree_viewer._tabs.addTab(self._ROItree_view, "ROIs")

        # # on attr changes
        # self._datatree_view.sigFinishedEditingAttrs.connect(self.refresh)
        # attrs_model: KeyValueTreeModel = self._datatree_viewer._attrs_view.model()
        # attrs_model.sigValueChanged.connect(self.refresh)
    
    def _init_filter_panel(self) -> None:

        self._filter_type_combobox = QComboBox()
        self._filter_type_combobox.addItems(['Gaussian', 'Median', 'Bessel', 'Butterworth', 'FIR'])
        self._filter_type_combobox.setCurrentText('Gaussian')
        self._filter_type_combobox.currentIndexChanged.connect(self._on_filter_type_changed)
        self._filter_type_combobox.setEnabled(False) # only Gaussian filter working at the moment

        self._filter_band_type_combobox = QComboBox()
        self._filter_band_type_combobox.addItems(['Lowpass', 'Bandpass', 'Highpass'])
        self._filter_band_type_combobox.currentIndexChanged.connect(self._on_filter_type_changed)

        self._filter_cutoff_edit = QLineEdit('')
        self._filter_cutoff_edit.setPlaceholderText('single [, band]')
        self._filter_cutoff_edit.editingFinished.connect(self._on_filter_changed)

        self._filter_cutoff_units_edit = QLineEdit('')
        self._filter_cutoff_units_edit.setPlaceholderText('cylces / \u0394x')
        self._filter_cutoff_units_edit.editingFinished.connect(self._on_filter_changed)

        self._filter_band_group = QGroupBox()
        form = QFormLayout(self._filter_band_group)
        form.setContentsMargins(3, 3, 3, 3)
        form.setSpacing(3)
        form.setHorizontalSpacing(5)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.addRow(self._filter_band_type_combobox)
        form.addRow('Cutoff', self._filter_cutoff_edit)
        form.addRow('Cutoff units', self._filter_cutoff_units_edit)

        # options and buttons
        self._filterLivePreviewCheckbox = QCheckBox('Live Preview', checked=False)
        self._filterLivePreviewCheckbox.stateChanged.connect(lambda state: self._update_plot_data())

        self._filterButton = QPushButton('Filter')
        self._filterButton.pressed.connect(lambda: self._update_plot_data())

        self._saveFilteredDataButton = QPushButton('Save Filtered')
        self._saveFilteredDataButton.pressed.connect(self.saveFilteredData)

        # layout
        vbox = QVBoxLayout()
        vbox.setContentsMargins(5, 5, 5, 5)
        vbox.setSpacing(5)
        vbox.addWidget(self._filter_type_combobox)
        vbox.addWidget(self._filter_band_group)
        vbox.addSpacing(10)
        vbox.addWidget(self._filterLivePreviewCheckbox)
        vbox.addSpacing(10)
        vbox.addWidget(self._filterButton)
        vbox.addWidget(self._saveFilteredDataButton)
        vbox.addStretch()

        # scroll area
        self._filter_panel = QScrollArea()
        self._filter_panel.setFrameShape(QFrame.Shape.NoFrame)
        self._filter_panel.setLayout(vbox)
        self._filter_panel.setWidgetResizable(True)

        self._update_filter_control_panel()
    
    def _init_curve_fit_panel(self) -> None:
        """ Initialize curve fit control panel. """

        self._fitTypeComboBox = QComboBox()
        self._fitTypeComboBox.addItems(['Mean', 'Median', 'Min', 'Max'])
        self._fitTypeComboBox.insertSeparator(self._fitTypeComboBox.count())
        self._fitTypeComboBox.addItems(['Line', 'Polynomial', 'Spline'])
        self._fitTypeComboBox.insertSeparator(self._fitTypeComboBox.count())
        self._fitTypeComboBox.addItems(['Expression'])
        self._fitTypeComboBox.setCurrentText('Expression')
        self._fitTypeComboBox.currentIndexChanged.connect(lambda index: self._on_curve_fit_type_changed())

        self._namedExpressions = {
            'Gaussian': {
                'expression': 'a * exp(-(x-b)**2 / (2 * c**2))',
                'params': {
                    'a': {'value': 1, 'vary': True, 'min': 0, 'max': np.inf},
                    'b': {'value': 0, 'vary': True, 'min': -np.inf, 'max': np.inf},
                    'c': {'value': 1, 'vary': True, 'min': 0, 'max': np.inf},
                },
            },
            'Hill Equation': {
                'expression': 'Y0 + Y1 / (1 + (EC50 / x)**n)',
                'params': {
                    'Y0': {'value': 0, 'vary': False, 'min': -np.inf, 'max': np.inf},
                    'Y1': {'value': 1, 'vary': True, 'min': -np.inf, 'max': np.inf},
                    'EC50': {'value': 1, 'vary': True, 'min': 1e-15, 'max': np.inf},
                    'n': {'value': 1, 'vary': True, 'min': 1e-2, 'max': 10},
                },
            },
        }
        if self._namedExpressions:
            self._fitTypeComboBox.insertSeparator(self._fitTypeComboBox.count())
            self._fitTypeComboBox.addItems(list(self._namedExpressions.keys()))

        # polynomial
        self._polynomialDegreeSpinBox = QSpinBox()
        self._polynomialDegreeSpinBox.setMinimum(0)
        self._polynomialDegreeSpinBox.setMaximum(100)
        self._polynomialDegreeSpinBox.setValue(2)
        self._polynomialDegreeSpinBox.valueChanged.connect(lambda value: self._on_curve_fit_changed())

        self._polynomialGroupBox = QGroupBox()
        form = QFormLayout(self._polynomialGroupBox)
        form.setContentsMargins(3, 3, 3, 3)
        form.setSpacing(3)
        form.setHorizontalSpacing(5)
        form.addRow('Degree', self._polynomialDegreeSpinBox)

        # spline
        self._splineNumberOfSegmentsSpinbox = QSpinBox()
        self._splineNumberOfSegmentsSpinbox.setValue(10)
        self._splineNumberOfSegmentsSpinbox.setMinimum(1)
        self._splineNumberOfSegmentsSpinbox.valueChanged.connect(lambda value: self._on_curve_fit_changed())

        self._splineGroupBox = QGroupBox()
        form = QFormLayout(self._splineGroupBox)
        form.setContentsMargins(3, 3, 3, 3)
        form.setSpacing(3)
        form.setHorizontalSpacing(5)
        form.addRow('# Segments', self._splineNumberOfSegmentsSpinbox)

        # y = f(x)
        self._expressionEdit = QLineEdit()
        self._expressionEdit.setPlaceholderText('a * x + b')
        self._expressionEdit.editingFinished.connect(self._on_curve_fit_expression_changed)

        self._expressionParamsTable = QTableWidget(0, 5)
        self._expressionParamsTable.setHorizontalHeaderLabels(['Param', 'Start', 'Vary', 'Min', 'Max'])
        self._expressionParamsTable.verticalHeader().setVisible(False)
        self._expressionParamsTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._expressionParamsTable.model().dataChanged.connect(lambda model_index: self._on_curve_fit_changed())

        self._expressionGroupBox = QGroupBox()
        vbox = QVBoxLayout(self._expressionGroupBox)
        vbox.setContentsMargins(3, 3, 3, 3)
        vbox.setSpacing(3)
        vbox.addWidget(self._expressionEdit)
        vbox.addWidget(self._expressionParamsTable)

        # options and buttons
        self._limitFitInputToROIsCheckbox = QCheckBox('Optimize within ROIs only', checked=True)
        self._limitFitInputToROIsCheckbox.stateChanged.connect(lambda state: self._on_curve_fit_ROI_dependence_changed())

        self._limitFitOutputToROIsCheckbox = QCheckBox('Fit within ROIs only', checked=False)
        self._limitFitOutputToROIsCheckbox.stateChanged.connect(lambda state: self._on_curve_fit_ROI_dependence_changed())

        self._fitLivePreviewCheckbox = QCheckBox('Live Preview', checked=False)
        self._fitLivePreviewCheckbox.stateChanged.connect(lambda state: self._update_curve_fit_preview())

        self._fitPreviewResidualsCheckbox = QCheckBox('Preview Residuals', checked=False)
        self._fitPreviewResidualsCheckbox.stateChanged.connect(lambda state: self._update_curve_fit_preview(update_data=True))
        self._fitPreviewResidualsCheckbox.setEnabled(self._fitLivePreviewCheckbox.isChecked())
        self._fitLivePreviewCheckbox.stateChanged.connect(lambda state: self._fitPreviewResidualsCheckbox.setEnabled(self._fitLivePreviewCheckbox.isChecked()))

        self._fitButton = QPushButton('Fit')
        self._fitButton.pressed.connect(lambda: self._update_curve_fit_preview(force_preview=True))

        self._saveFitButton = QPushButton('Save Fit')
        self._saveFitButton.pressed.connect(self.saveCurveFit)

        # layout
        vbox = QVBoxLayout()
        vbox.setContentsMargins(5, 5, 5, 5)
        vbox.setSpacing(5)
        vbox.addWidget(self._fitTypeComboBox)
        vbox.addWidget(self._polynomialGroupBox)
        vbox.addWidget(self._splineGroupBox)
        vbox.addWidget(self._expressionGroupBox)
        vbox.addSpacing(10)
        vbox.addWidget(self._limitFitInputToROIsCheckbox)
        vbox.addWidget(self._limitFitOutputToROIsCheckbox)
        vbox.addSpacing(10)
        vbox.addWidget(self._fitLivePreviewCheckbox)
        vbox.addWidget(self._fitPreviewResidualsCheckbox)
        vbox.addSpacing(10)
        vbox.addWidget(self._fitButton)
        vbox.addWidget(self._saveFitButton)
        self._fitControlsSpacer = QSpacerItem(0, 0, QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
        vbox.addSpacerItem(self._fitControlsSpacer)

        # scroll area
        self._curve_fit_panel = QScrollArea()
        self._curve_fit_panel.setFrameShape(QFrame.Shape.NoFrame)
        self._curve_fit_panel.setLayout(vbox)
        self._curve_fit_panel.setWidgetResizable(True)

        self._update_curve_fit_control_panel()
    
    def _init_measurement_panel(self) -> None:
        """ Initialize measurement control panel. """

        self._measure_type_combobox = QComboBox()
        self._measure_type_combobox.addItems(['Mean', 'Median'])
        self._measure_type_combobox.insertSeparator(self._measure_type_combobox.count())
        self._measure_type_combobox.addItems(['Min', 'Max', 'AbsMax'])
        self._measure_type_combobox.insertSeparator(self._measure_type_combobox.count())
        self._measure_type_combobox.addItems(['Peaks'])
        # self._measure_type_combobox.insertSeparator(self._measure_type_combobox.count())
        # self._measure_type_combobox.addItems(['Standard Deviation', 'Variance'])
        self._measure_type_combobox.currentIndexChanged.connect(self._on_measure_type_changed)

        self._measure_peak_type_combobox = QComboBox()
        self._measure_peak_type_combobox.addItems(['Positive', 'Negative'])
        self._measure_peak_type_combobox.setCurrentText('Positive')
        self._measure_peak_type_combobox.currentIndexChanged.connect(lambda index: self._update_measurement_preview())

        self._max_num_peaks_per_region_spinbox = QSpinBox()
        self._max_num_peaks_per_region_spinbox.setMinimum(0)
        self._max_num_peaks_per_region_spinbox.setMaximum(1000000)
        self._max_num_peaks_per_region_spinbox.setSpecialValueText('Any')
        self._max_num_peaks_per_region_spinbox.setValue(0)
        self._max_num_peaks_per_region_spinbox.valueChanged.connect(lambda value: self._update_measurement_preview())

        self._measure_peak_avg_half_width_spinbox = QSpinBox()
        self._measure_peak_avg_half_width_spinbox.setMinimum(0)
        self._measure_peak_avg_half_width_spinbox.setSpecialValueText('None')
        self._measure_peak_avg_half_width_spinbox.setValue(0)
        self._measure_peak_avg_half_width_spinbox.valueChanged.connect(lambda value: self._update_measurement_preview())

        self._measure_peak_threshold_edit = QLineEdit('0')
        self._measure_peak_threshold_edit.editingFinished.connect(self._update_measurement_preview)

        self._measure_peak_group = QGroupBox()
        form = QFormLayout(self._measure_peak_group)
        form.setContentsMargins(3, 3, 3, 3)
        form.setSpacing(3)
        form.setHorizontalSpacing(5)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.addRow('Peak type', self._measure_peak_type_combobox)
        form.addRow('Max # peaks', self._max_num_peaks_per_region_spinbox)
        Delta_symbol = u'\u00b1'
        form.addRow(f'{Delta_symbol} sample mean', self._measure_peak_avg_half_width_spinbox)
        form.addRow('Peak threshold', self._measure_peak_threshold_edit)

        # options and buttons
        self._measure_in_ROIs_only_checkbox = QCheckBox('Measure within ROIs only')
        self._measure_in_ROIs_only_checkbox.setChecked(True)
        self._measure_in_ROIs_only_checkbox.stateChanged.connect(lambda state: self._update_measurement_preview())

        self._measure_per_ROI_checkbox = QCheckBox('Measure for each ROI')
        self._measure_per_ROI_checkbox.setChecked(True)
        self._measure_in_ROIs_only_checkbox.setEnabled(not self._measure_per_ROI_checkbox.isChecked)
        self._measure_per_ROI_checkbox.stateChanged.connect(lambda state: self._measure_in_ROIs_only_checkbox.setEnabled(Qt.CheckState(state) == Qt.CheckState.Unchecked))
        self._measure_per_ROI_checkbox.stateChanged.connect(lambda state: self._update_measurement_preview())

        self._measureLivePreviewCheckbox = QCheckBox('Live Preview', checked=False)
        self._measureLivePreviewCheckbox.stateChanged.connect(lambda state: self._update_measurement_preview())

        self._measureButton = QPushButton('Measure')
        self._measureButton.pressed.connect(lambda: self._update_measurement_preview(force_preview=True))

        self._saveMeasurementButton = QPushButton('Save Measurement')
        self._saveMeasurementButton.pressed.connect(self.saveMeasurement)

        # layout
        vbox = QVBoxLayout()
        vbox.setContentsMargins(5, 5, 5, 5)
        vbox.setSpacing(5)
        vbox.addWidget(self._measure_type_combobox)
        vbox.addWidget(self._measure_peak_group)
        vbox.addSpacing(10)
        vbox.addWidget(self._measure_in_ROIs_only_checkbox)
        vbox.addWidget(self._measure_per_ROI_checkbox)
        vbox.addSpacing(10)
        vbox.addWidget(self._measureLivePreviewCheckbox)
        vbox.addSpacing(10)
        vbox.addWidget(self._measureButton)
        vbox.addWidget(self._saveMeasurementButton)
        vbox.addStretch()

        # scroll area
        self._measurement_panel = QScrollArea()
        self._measurement_panel.setFrameShape(QFrame.Shape.NoFrame)
        self._measurement_panel.setLayout(vbox)
        self._measurement_panel.setWidgetResizable(True)

        self._update_measurement_control_panel()
    
    def _init_notes_edit(self) -> None:
        """ Initialize notes editor. """

        self._notes_edit = QTextEdit()
        self._notes_edit.setToolTip('Notes')
        self._notes_edit.textChanged.connect(lambda: self._on_notes_changed())
    
    @staticmethod
    def _to_valid_datatree(data: xr.DataTree | xr.Dataset | xr.DataArray | np.ndarray | list[np.ndarray] | tuple[np.ndarray] | None) -> xr.DataTree:
        """ convert data -> datatree ensuring the root node does not have any data """
        datatree = xr.DataTree()
        if data is None:
            pass
        elif isinstance(data, xr.DataTree):
            if data.has_data:
                name = data.name or 'Data'
                datatree[name] = data
            else:
                datatree = data
        elif isinstance(data, xr.Dataset):
            name = data.name or 'Data'
            datatree[name] = data
        elif isinstance(data, xr.DataArray):
            name = data.name or 'data'
            datatree['Data'] = xr.Dataset(data_vars={name: data})
        elif isinstance(data, np.ndarray):
            datatree['Data'] = xr.Dataset(data_vars={'data': data})
        else:
            # assume list or tuple of two np.ndarrays (x, y)
            try:
                x, y = data
                datatree['Data'] = xr.Dataset(data_vars={'y': ('x', y)}, coords={'x': ('x', x)})
            except Exception:
                raise ValueError('XarrayGraph.datatree.setter: Invalid input.')
        return datatree


class DimIterWidget(QWidget):

    xdimChanged = Signal(str)
    tileChanged = Signal(str, object)

    def __init__(self, *args, **kwargs):
        QWidget.__init__(self, *args, **kwargs)

        # self._xgraph = None

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


def get_icon(name: str, opacity: float = None, size: int | QSize = None) -> QIcon:
    """ get QtAwesome icon by name. Default opacity from settings. """
    if opacity is None:
        opacity = settings['icon opacity']
    icon = qta.icon(name, options=[{'opacity': opacity}])
    if size is not None:
        if isinstance(size, QSize):
            icon.setIconSize(size)
        elif isinstance(size, int):
            icon.setIconSize(QSize(size, size))
    return icon


def get_unique_name(name: str, names: list[str]) -> str:
    if name not in names:
        return name
    base_name = name
    i = 0
    name = f'{base_name}_{i}'
    while name in names:
        i += 1
        name = f'{base_name}_{i}'
    return name


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


def remove_inherited_data_vars(dt: xr.DataTree) -> xr.DataTree:
    dt = dt.copy(deep=False)  # copy tree but not underlying data
    for node in reversed(list(dt.subtree)):
        if not node.parent:
            continue
        for key in list(node.parent.data_vars):
            if key in node.data_vars:
                if node.data_vars[key].values is node.parent.data_vars[key].values:
                    node.dataset = node.to_dataset().drop_vars(key)
    return dt


def inherit_missing_data_vars(dt: xr.DataTree) -> xr.DataTree:
    dt = dt.copy(deep=False)  # copy tree but not underlying data
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
    

def get_ordered_dims(objects: list[xr.DataTree | xr.Dataset | xr.DataArray]) -> list[str]:
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


def find_aligned_root(dt: xr.DataTree) -> xr.DataTree:
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


def find_subtree_alignment_roots(dt: xr.DataTree) -> list[xr.DataTree]:
    if dt.has_data:
        return [dt]
    roots: list[xr.DataTree] = []
    for node in dt.subtree:
        if not node.has_data:
            continue
        root: xr.DataTree = node
        while root.parent is not None and root.parent.has_data:
            root = root.parent
        ok = True
        for found_root in roots:
            if root is found_root:
                ok = False
                break
        if ok:
            roots.append(root)
    return roots


def to_base_units(data: xr.DataArray | xr.Dataset) -> xr.DataArray | xr.Dataset:
    if isinstance(data, xr.DataArray):
        if 'units' not in data.attrs:
            return data
        quantity = data.values * UREG(data.attrs['units'])
        quantity = quantity.to_base_units()
        base_data = data.copy(data=quantity.magnitude)
        base_data.attrs['units'] = str(quantity.units)
        return base_data
    elif isinstance(data, xr.Dataset):
        return xr.Dataset(
            data_vars={name: to_base_units(var) for name, var in data.data_vars.items()},
            coords={name: to_base_units(coord) for name, coord in data.coords.items()},
            attrs=data.attrs,
        )


def test_live():
    app = QApplication()

    xg = XarrayGraph()
    xg.show()
    xg.datatree = xr.open_datatree('examples/ERPdata.nc', engine='h5netcdf')
    app.exec()


# def test_stuff():
#     t1 = np.load('time_0.npy')
#     t2 = np.load('time_1.npy')
#     ds1 = xr.Dataset(
#         coords={
#             'time': xr.DataArray(data=t1, dims=['time'], attrs={'units': 'second'})
#         }
#     )
#     ds2 = xr.Dataset(
#         coords={
#             'time': xr.DataArray(data=t2, dims=['time'], attrs={'units': 'second'})
#         }
#     )
#     ds = xr.merge([ds1, ds2], compat='no_conflicts', join='outer')
#     print(ds)


if __name__ == '__main__':
    test_live()