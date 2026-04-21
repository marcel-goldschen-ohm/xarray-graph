""" PyQt widget for viewing/analyzing (x,y) slices of a Xarray DataTree.
"""

from __future__ import annotations
from copy import deepcopy
import textwrap
import numpy as np
from functools import reduce
import cftime
# to be able to read unit attributes following the CF conventions
import cf_xarray.units  # noqa: F401  # must be imported before pint_xarray
import xarray as xr
import pint_xarray
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
from xarray_graph.utils import xarray_utils
from xarray_graph.apps import XarrayDataTreeViewer
from xarray_graph.tree import XarrayDataTreeItem
from xarray_graph.graph import *
from xarray_graph.widgets import CollapsibleSectionsSplitter


class XarrayGraph(XarrayDataTreeViewer):
    """ PyQt widget for viewing/analyzing (x,y) slices of a Xarray DataTree.
    """

    ureg = pint_xarray.unit_registry

    _default_settings = {
        'icon size': 24,
    }
    _settings = deepcopy(_default_settings)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def xdim(self) -> str | None:
        try:
            return self._xdim
        except AttributeError:
            return None
    
    def setXDim(self, xdim: str | None) -> None:
        # try:
        #     self._prev_xdim = self._xdim
        # except AttributeError:
        #     pass
        self._xdim = xdim
        self.refresh()
    
    def onSelectionChanged(self) -> None:
        print('\n'*2, '>'*50)

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
            self._onInvalidSelection(
                '''
                Empty Selection

                No data variables selected.
                
                Please select at least one data variable to plot.
                '''
            )
            return
        self._selected_data_vars: list[xr.DataArray] = [item.data() for item in self._selected_data_var_items]
        # print(f'_selected_data_vars:')
        # for item in self._selected_data_var_items:
        #     print(f'  {item.abspath()}')
        
        # shared dimensions across selection
        dims_per_data_var = [np.array(list(data_var.dims)) for data_var in self._selected_data_vars]
        self._selection_shared_dims = reduce(np.intersect1d, dims_per_data_var).tolist() if dims_per_data_var else []
        if not self._selection_shared_dims:
            self._onInvalidSelection(
                '''
                Alignment Conflict

                There is no single dimension that is shared by all selected data variables. Variables must share at least one common dimension in order to be plotted together.
                
                Please select data variables that share a common dimension.
                '''
            )
            return
        # print(f'_selection_shared_dims: {self._selection_shared_dims}')
        
        # ordered dimensions
        self._selection_ordered_dims = list(xarray_utils.ordered_dims_iter(self._selected_data_vars)) if self._selected_data_vars else []
        # print(f'_selection_ordered_dims: {self._selection_ordered_dims}')

        # ensure xdim is one of the shared dimensions
        xdim = self.xdim()
        if self._selection_shared_dims:
            if xdim not in self._selection_shared_dims:
                # try to preserve previous xdim
                prev_xdim = getattr(self, '_prev_xdim', None)
                if prev_xdim in self._selection_shared_dims:
                    xdim = self._xdim = prev_xdim
                else:
                    self._prev_xdim = xdim
                    xdim = self._xdim = self._selection_shared_dims[0]
        else:
            xdim = None
        print(f'xdim: {xdim}')
        
        # common units across selection
        # if units conflict, attempt to convert to base units using pint
        self._selection_units: dict[str, str] = {}
        names_with_units_conflict = set()
        datetime_dtypes = set()
        for data_var in self._selected_data_vars:
            units = data_var.attrs.get('units', None)
            if units is not None:
                existing_units = self._selection_units.get(data_var.name, None)
                if existing_units is None:
                    self._selection_units[data_var.name] = units
                elif units != existing_units:
                    names_with_units_conflict.add(data_var.name)
            coord: xr.DataArray
            for name, coord in data_var.coords.items():
                # check for datetime dtypes
                if np.issubdtype(coord.dtype, np.datetime64):
                    datetime_dtypes.add(coord.dtype)
                elif isinstance(coord.data[0], cftime.datetime):
                    datetime_dtypes.add(type(coord.data[0]))
                units = coord.attrs.get('units', None)
                if units is not None:
                    existing_units = self._selection_units.get(name, None)
                    if existing_units is None:
                        self._selection_units[name] = units
                    elif units != existing_units:
                        names_with_units_conflict.add(name)
        if names_with_units_conflict:
            for i, data_var in enumerate(self._selected_data_vars):
                if data_var.name in names_with_units_conflict and 'units' in data_var.attrs:
                    try:
                        qvar = data_var.pint.quantify()
                        qdata = qvar.data.to_base_units()
                        units = str(qdata.units)
                        data_var = data_var.copy(deep=False, data=qdata.magnitude)
                        data_var.attrs['units'] = units
                        self._selected_data_vars[i] = data_var
                        self._selection_units[data_var.name] = units
                    except:
                        item = self._selected_data_var_items[i]
                        self._onInvalidSelection(
                            f'''
                            Units Conflict

                            All variables and their coordinates of the same name across the selection must have the same units in order to be plotted together. If units differ, pint will attempt to convert to base units, but if conversion fails then the selection is considered invalid.

                            Failed to convert data variable "{item.abspath()}" to base units.
                            '''
                        )
                        return
                coord: xr.DataArray
                for coord in data_var.coords.values():
                    if coord.name in names_with_units_conflict and 'units' in coord.attrs:
                        try:
                            qvar = coord.pint.quantify()
                            qdata = qvar.data.to_base_units()
                            units = str(qdata.units)
                            coord = coord.copy(deep=False, data=qdata.magnitude)
                            coord.attrs['units'] = units
                            data_var = data_var.assign_coords({coord.name: coord})
                            self._selected_data_vars[i] = data_var
                            self._selection_units[coord.name] = units
                        except:
                            item = self._selected_data_var_items[i]
                            self._onInvalidSelection(
                                f'''
                                Units Conflict

                                All variables and their coordinates of the same name across the selection must have the same units in order to be plotted together. If units differ, pint will attempt to convert to base units, but if conversion fails then the selection is considered invalid.

                                Failed to convert coordinate "{coord.name}" in data variable "{item.abspath()}" to base units.
                                '''
                            )
                            return
        if len(datetime_dtypes) > 1:
            self._onInvalidSelection(
                f'''
                Datetime Type Conflict

                All datetime coordinates across the selection must have the same dtype in order to be plotted together. If there are different datetime dtypes across the selection, then the selection is considered invalid.

                Found conflicting datetime dtypes across selection: {', '.join(str(dt) for dt in datetime_dtypes)}
                '''
            )
            return
        print(f'_selection_units: {self._selection_units}')

        # selection combined coords
        selected_coords = []
        for data_var in self._selected_data_vars:
            coords_ds = xr.Dataset(
                coords=data_var.coords
            )
            selected_coords.append(coords_ds)
        if selected_coords:
            try:
                self._selection_combined_coords: xr.Dataset = xr.merge(selected_coords, compat='no_conflicts', join='outer')
            except Exception as e:
                self._onInvalidSelection(
                    f'''
                    Alignment Conflict

                    All selected data variables must align in order to be plotted together. If there are any alignment conflicts between coordinates of the same name across the selection, then the selection is considered invalid.

                    Failed to merge combined coordinates for entire selection: {e}
                    '''
                )
                return
        else:
            self._selection_combined_coords = None
        print(f'_selection_combined_coords: {self._selection_combined_coords}')
        
        # unique data_var names
        self._selected_data_var_unique_names = np.unique([var.name for var in self._selected_data_vars]).tolist()
        print(f'_selected_data_var_unique_names: {self._selected_data_var_unique_names}')

        self._plot_grid.setVisible(True)
        self._message_label.setVisible(False)
   
    def _onInvalidSelection(self, msg: str) -> None:
        self._selected_data_var_items = []
        self._selected_data_vars = []
        self._selection_ordered_dims = []
        self._selection_units = {}
        self._plot_grid.setVisible(False)
        msg = textwrap.dedent(msg).strip()
        self._message_label.setText(msg)
        self._message_label.setVisible(True)
    
    def onROISelectionChanged(self) -> None:
        pass # TODO
   
    def onROITypeChanged(self) -> None:
        if self._ROI_event_action.isChecked():
            self._ROI_selection_button.setIcon(self._ROI_event_icon)
        elif self._ROI_xrange_action.isChecked():
            self._ROI_selection_button.setIcon(self._ROI_xrange_icon)
        self._ROI_selection_button.setChecked(True)
    
    def autoscale(self) -> None:
        pass # TODO
    
    def notes(self) -> None:
        pass # TODO
    
    def filter(self) -> None:
        pass # TODO

    def curveFit(self) -> None:
        pass # TODO

    def measure(self) -> None:
        pass # TODO
    
    def isDataPanelVisible(self) -> bool:
        return self._datatree_ROIs_splitter.isVisible()
    
    def setDataPanelVisible(self, visible: bool) -> None:
        self._datatree_ROIs_splitter.setVisible(visible)
        self._data_action.setChecked(visible)
    
    def settings(self) -> None:
        pass # TODO
    
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
        
        self._ROI_event_action = QAction(
            icon=qta.icon('fa6s.arrow-down-long'),
            iconVisibleInMenu=True,
            text='Event',
            toolTip='Create event ROI with mouse click',
            checkable=True,
            checked=False,
            shortcut=QKeySequence('E'),
            shortcutVisibleInContextMenu=True,
            triggered=lambda checked: self.onROITypeChanged()
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
            triggered=lambda checked: self.onROITypeChanged()
        )
        self._ROI_xrange_icon = qta.icon('mdi.arrow-expand-horizontal', color=faded_text_color, color_on=text_color)

        self._notes_action = QAction(
            icon=qta.icon('mdi6.text-box-edit-outline'),
            iconVisibleInMenu=True,
            text='Notes',
            toolTip='Notes',
            checkable=False,
            triggered=lambda checked: self.notes()
        )

        self._filter_action = QAction(
            icon=qta.icon('mdi.sine-wave'),
            iconVisibleInMenu=True,
            text='Filter',
            toolTip='Filter',
            checkable=True,
            checked=False,
            triggered=lambda checked: self.filter()
        )

        self._curve_fit_action = QAction(
            icon=qta.icon('mdi.chart-bell-curve-cumulative'),
            iconVisibleInMenu=True,
            text='Curve Fit',
            toolTip='Curve Fit',
            checkable=True,
            checked=False,
            triggered=lambda checked: self.curveFit()
        )

        self._measure_action = QAction(
            parent=self, 
            icon=qta.icon('mdi.chart-scatter-plot'),
            iconVisibleInMenu=True,
            text='Measure',
            toolTip='Measure',
            checkable=True,
            checked=False,
            triggered=lambda checked: self.measure()
        )

        self._opertions_action_group = QActionGroup(self)
        self._opertions_action_group.addAction(self._filter_action)
        self._opertions_action_group.addAction(self._curve_fit_action)
        self._opertions_action_group.addAction(self._measure_action)
        self._opertions_action_group.setExclusionPolicy(QActionGroup.ExclusionPolicy.ExclusiveOptional)
    
    def _initMenubar(self) -> None:
        super()._initMenubar()

        sep = self._view_menu.insertSeparator(self.console._console_action)
        self._view_menu.insertAction(sep, self._notes_action)

        self._operations_menu = QMenu('Operations')
        self._operations_menu.addAction(self._filter_action)
        self._operations_menu.addAction(self._curve_fit_action)
        self._operations_menu.addSeparator()
        self._operations_menu.addAction(self._measure_action)
        self.menuBar().insertMenu(self._view_menu.menuAction(), self._operations_menu)
    
    def _initUI(self) -> None:
        """ Initialize UI elements and layout.
        """
        # ROIs view
        self._ROIs_view = QTreeView()
        # self._ROIs_view.selectionWasChanged.connect(self.onROISelectionChanged)

        # datatree and ROI views splitter
        self._datatree_ROIs_splitter = QSplitter(Qt.Orientation.Vertical)
        self._datatree_ROIs_splitter.addWidget(self._datatree_view)
        self._datatree_ROIs_splitter.addWidget(self._ROIs_view)

        # graphs view
        self._plot_grid = PlotGrid()
        # self._plot_grid.setGrid(1, 1)

        # invalid selection label
        self._message_label = QLabel()
        self._message_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._message_label.setWordWrap(True)

        # right side vbox
        panel = QWidget()
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)
        vbox.addWidget(self._plot_grid)
        vbox.addWidget(self._message_label)

        # toolbars
        self._initTopToolbar()

        # main layout
        hsplitter = QSplitter(Qt.Orientation.Horizontal)
        hsplitter.addWidget(self._datatree_ROIs_splitter)
        hsplitter.addWidget(panel)
        self.setCentralWidget(hsplitter)
    
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
        self.onROITypeChanged() # set initial icon
        self._ROI_selection_button.setChecked(False)

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
        self._top_toolbar_spacer_action = self._top_toolbar.addWidget(self._dim_iters_spacer)
        self._after_dim_iters_separator_action = self._top_toolbar.addSeparator()
        self._top_toolbar.addAction(self._notes_action)
        self._top_toolbar.addWidget(self._ROI_selection_button)
        self._top_toolbar.addAction(self._home_action)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._top_toolbar)
    

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

    
    window = XarrayGraph()
    window.setDatatree(dt)
    window._datatree_view.showAll()
    window.show()

    app.exec()


if __name__ == '__main__':
    test_live()