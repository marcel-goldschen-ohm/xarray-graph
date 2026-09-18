
from typing import Any
import numpy as np
from xarray import DataArray, Dataset, DataTree
from qtpy.QtCore import Qt, QSize
from qtpy.QtWidgets import QWidget, QLabel, QFrame
from xarray_graph.table.ArrayTableModel import ArrayTableModel
from xarray_graph.table.ArrayTableView import ArrayTableView


class XarrayTableViewer(QWidget):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._model = ArrayTableModel()
        self._model.dataTypeChanged.connect(self._onDataTypeChanged)

        self._view = ArrayTableView()
        self._view.setModel(self._model)

        self._data: DataArray | Dataset | DataTree = DataArray(np.empty((0, 0)), dims=["dim_0", "dim_1"])
        self._array_name = ''  # array selector if _data is a Dataset or DataTree
        self._isel: dict[str, int] = {}  # selection of indices for non-table dimensions

        self._model.setArray(self.arrayTable().data)

        from qtpy.QtWidgets import QLabel, QGridLayout, QHBoxLayout

        self._dims_hbox = QHBoxLayout()
        self._dim_widgets: dict[str, DimIterWidget] = {}

        self._array_title = QLabel("name (units)", alignment=Qt.AlignmentFlag.AlignCenter)
        self._rows_title = VerticalLabel("dim_0", alignment=Qt.AlignmentFlag.AlignCenter)
        self._columns_title = QLabel("dim_1", alignment=Qt.AlignmentFlag.AlignCenter)

        grid = QGridLayout(self)
        grid.addWidget(self._array_title, 0, 0, 1, 2)
        grid.addLayout(self._dims_hbox, 1, 0, 1, 2)
        grid.addWidget(self._columns_title, 2, 1)
        grid.addWidget(self._rows_title, 3, 0)
        grid.addWidget(self._view, 3, 1)

        self._view.setFocus()
    
    def dims(self) -> list[str]:
        return list(str(dim) for dim in self.array().sizes.keys())

    def array(self) -> DataArray:
        if isinstance(self._data, DataArray):
            return self._data
        elif isinstance(self._data, (Dataset, DataTree)):
            # if self._array_name in self._data.dims and self._array_name not in self._data.coords:
            #     return DataArray(data=np.arange(self._data.sizes[self._array_name]), dims=[self._array_name])
            return self._data[self._array_name]  # type: ignore
        else:
            raise ValueError("No valid DataArray is set in the viewer.")
    
    def setArray(self, data: DataArray | Dataset | DataTree, array_name = '', sel: dict[str, Any] = {}, isel: dict[str, int] = {}) -> None:
        self._data = data
        self._array_name = array_name
        self._isel = self._validatedSelection(self.array(), sel, isel)
        self._model.setArray(self.arrayTable().data)

        self._updateArrayTitle()
        self._updateRowAndColumnLabels()
        self._updateDimWidgets()

    def arrayTable(self) -> DataArray:
        array = self.array()
        if self._isel:
            return array.isel(self._isel, drop=True)
        else:
            return array

    def parentDatasetOrDataTree(self) -> DataTree | Dataset | None:
        if isinstance(self._data, (Dataset, DataTree)):
            return self._data
        return None

    def selectionCoords(self) -> dict[str, Any]:
        array = self.array()
        sel: dict[str, Any] = {}
        for dim, index in self._isel.items():
            sel[dim] = array[dim].values[index]
        return sel

    def isArrayAnIndexCoordinate(self) -> bool:
        container = self.parentDatasetOrDataTree()
        if not container:
            return False
        array = self.array()
        if array.name in container.xindexes:
            return True
        if (array.name in container.dims) and (array.ndim ==1) and (array.name in array.dims):
            return True
        return False

    def _validatedSelection(self, array: DataArray, sel: dict[str, Any] = {}, isel: dict[str, int] = {}) -> dict[str, int]:
        dims = list(str(dim) for dim in array.sizes.keys())
        for dim, value in sel.items():
            if dim in dims and dim in array.coords:
                index = array.indexes[dim].get_loc(value)
                isel[dim] = index
        visible_dims = [dim for dim in dims if dim not in isel]
        if len(visible_dims) not in (1, 2):
            raise ValueError(f"Selection is not a valid 1D or 2D array. Selected full dimensions: {visible_dims}")
        return isel

    def updateSelection(self, sel: dict[str, Any] = {}, isel: dict[str, int] = {}, update_dim_widgets: bool = True) -> None:
        self._isel = self._validatedSelection(self.array(), sel, isel)
        self._model.setArray(self.arrayTable().data)
        self._updateRowAndColumnLabels()
        if update_dim_widgets:
            self._updateDimWidgets()

    def _updateArrayTitle(self):
        array = self.array()
        title = f"{array.name}"
        if 'units' in array.attrs:
            title += f" ({array.attrs['units']})"
        self._array_title.setText(title)

    def _updateRowAndColumnLabels(self):
        if self.isArrayAnIndexCoordinate():
            self._rows_title.setVisible(False)
            self._columns_title.setVisible(False)
            self._view.verticalHeader().setVisible(False)
            self._view.horizontalHeader().setVisible(False)
            self._view.horizontalHeader().setStretchLastSection(True)
            return

        # table with rows and columns labeled by their associated coordinate dimensions
        array_table = self.arrayTable()
        table_dims = list(str(dim) for dim in array_table.sizes.keys())
        if len(table_dims) == 1:
            row_dim = table_dims[0]
            col_dim = ''
        else:
            row_dim, col_dim = table_dims

        # titles are the dimension names, optionally with units if available in the coordinate attributes
        row_title, col_title = row_dim, col_dim
        if row_dim in array_table.coords and 'units' in array_table[row_dim].attrs:
            row_title += f" ({array_table[row_dim].attrs['units']})"
        if col_dim in array_table.coords and 'units' in array_table[col_dim].attrs:
            col_title += f" ({array_table[col_dim].attrs['units']})"
        
        self._rows_title.setText(row_title)
        self._columns_title.setText(col_title)

        if row_dim:
            self._model.setRowLabels([str(v) for v in array_table[row_dim].values])
            self._view.verticalHeader().setVisible(True)
            self._rows_title.setVisible(True)
        else:
            self._view.verticalHeader().setVisible(False)
            self._rows_title.setVisible(False)

        if col_dim:
            self._model.setColumnLabels([str(v) for v in array_table[col_dim].values])
            self._view.horizontalHeader().setVisible(True)
            self._view.horizontalHeader().setStretchLastSection(False)
            self._columns_title.setVisible(True)
        else:
            self._view.horizontalHeader().setVisible(False)
            self._view.horizontalHeader().setStretchLastSection(True)
            self._columns_title.setVisible(False)

    def _updateDimWidgets(self):
        array = self.array()
        array_table = self.arrayTable()
        # clear hbox layout of any existing dim widgets
        for item in self._dims_hbox.children():
            if isinstance(item, DimIterWidget):
                item.setParent(None)
        dim_widgets: dict[str, DimIterWidget] = {}
        dims = self.dims()
        if len(dims) > 1:
            for dim in dims:
                is_table_dim = dim in array_table.dims
                if dim in self._dim_widgets:
                    dim_widget = self._dim_widgets[dim]
                else:
                    dim_widget = DimIterWidget()
                    dim_widget._dim_checkbox.clicked.connect(lambda checked, dim=dim: self._updateSelectionFromDimWidgets(dim))
                    dim_widget._spinbox.indicesChanged.connect(lambda dim=dim: self._updateSelectionFromDimWidgets(dim))
                from qtpy.QtCore import QSignalBlocker
                with QSignalBlocker(dim_widget._dim_checkbox), QSignalBlocker(dim_widget._spinbox):
                    dim_widget.setDim(dim)
                    dim_widget.setCoords(array[dim].values)
                    dim_widget._dim_checkbox.setChecked(is_table_dim)
                    dim_widget._spinbox.setVisible(not is_table_dim)
                    dim_widget._drop_select_button.setVisible(not is_table_dim)
                dim_widget._updateDimCheckboxState()
                dim_widgets[dim] = dim_widget
                self._dims_hbox.addWidget(dim_widget)
        self._dim_widgets = dim_widgets

    def _updateSelectionFromDimWidgets(self, last_changed_dim = ''):
        dims = [dim for dim in self._dim_widgets.keys()]
        selected_dims = [dim for dim, widget in self._dim_widgets.items() if widget._dim_checkbox.isChecked()]
        if len(selected_dims) == 0:
            # reselect either the first or the last changed dim, preferring the later
            dim = last_changed_dim if last_changed_dim in dims else dims[0]
            cbox = self._dim_widgets[dim]._dim_checkbox
            spinbox = self._dim_widgets[dim]._spinbox
            listbox = self._dim_widgets[dim]._list_selector
            cbox.setChecked(True)
            spinbox.setVisible(False)
            listbox.setVisible(False)
            self._dim_widgets[dim]._updateDimCheckboxState()
            selected_dims.append(dim)
            from qtpy.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Selection Warning", "At least one dimension must be selected for the table view.")
        elif len(selected_dims) > 2:
            while len(selected_dims) > 2:
                # unselect either the last selected or the last changed dim, preferring the later
                dim = last_changed_dim if last_changed_dim in selected_dims else selected_dims[-1]
                cbox = self._dim_widgets[dim]._dim_checkbox
                spinbox = self._dim_widgets[dim]._spinbox
                listbox = self._dim_widgets[dim]._list_selector
                cbox.setChecked(False)
                spinbox.setVisible(True)
                listbox.setVisible(True)
                self._dim_widgets[dim]._updateDimCheckboxState()
                selected_dims.remove(dim)
            from qtpy.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Selection Warning", "Only one or two dimensions can be selected for the table view.")

        isel = {}
        for dim, widget in self._dim_widgets.items():
            if widget._dim_checkbox.isChecked():
                continue
            isel[dim] = widget._spinbox.indices().item()
        self.updateSelection(isel=isel, update_dim_widgets=False)

    def setReadOnly(self, read_only: bool):
        self._model.setReadOnly(read_only)

    def _onDataTypeChanged(self):
        # the model's array is no longer a view into the data array, so we need to update the data array with the new values from the model
        table_array = self._model.array()
        array = self.array()
        sel = self.selectionCoords()
        if not sel:
            array = array.copy(data=table_array)
        else:
            array = array.copy(data=array.values.astype(table_array.dtype))
            array.loc[sel] = table_array

        container = self.parentDatasetOrDataTree()
        if container is not None:
            container[array.name] = array  # type: ignore
        else:
            self._data = array


class VerticalLabel(QLabel):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    def paintEvent(self, event):
        from qtpy.QtCore import QRect
        from qtpy.QtGui import QPainter

        painter = QPainter(self)
        
        # Translate and rotate coordinate system
        painter.translate(0, self.height())
        painter.rotate(-90)
        
        # Draw the text matching the swapped geometry bounds
        painter.drawText(QRect(0, 0, self.height(), self.width()), self.alignment(), self.text())
        painter.end()

    def sizeHint(self) -> QSize:
        s = super().sizeHint()
        return QSize(s.height(), s.width())

    def minimumSizeHint(self) -> QSize:
        s = super().minimumSizeHint()
        return QSize(s.height(), s.width())


class DimIterWidget(QFrame):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        from qtpy.QtGui import QColor, QPalette
        from qtpy.QtWidgets import QApplication, QGridLayout, QLabel, QSizePolicy, QGraphicsOpacityEffect, QCheckBox, QListWidget, QWidgetAction, QMenu, QToolButton, QVBoxLayout, QHBoxLayout
        from qtawesome import icon
        from xarray_graph.widgets.MultiValueSpinBox import MultiValueSpinBox

        color_on: QColor = QApplication.palette().color(QPalette.ColorRole.Text)
        color_off = QColor(color_on)
        color_off.setAlphaF(0.5)

        self._dim_checkbox = QCheckBox('dim')
        self._dim_checkbox.setTristate(False)
        self._dim_checkbox.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred))
        self._dim_checkbox.clicked.connect(self._onDimCheckboxClicked)

        self._size_label = QLabel(': n')
        self._size_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._size_label.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred))
        self._size_label_opacity_effect = QGraphicsOpacityEffect(self._size_label)
        self._size_label_opacity_effect.setOpacity(0.5)
        self._size_label.setGraphicsEffect(self._size_label_opacity_effect)

        self._spinbox = MultiValueSpinBox()
        self._spinbox.setSingleSelectionMode(True)
        self._spinbox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._spinbox.editingFinished.connect(lambda: self._spinbox.clearFocus())
        self._spinbox.indicesChanged.connect(self._onSpinboxSelectionChanged)

        self._list_selector = QListWidget()
        self._list_selector.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._list_selector.itemSelectionChanged.connect(self._onListSelectorSelectionChanged)

        self._select_menu = QMenu()
        action = QWidgetAction(self._select_menu)
        action.setDefaultWidget(self._list_selector)
        self._select_menu.addAction(action)

        self._drop_select_button = QToolButton()
        self._drop_select_button.setIcon(icon('ph.list', color=color_off, color_on=color_on))
        self._drop_select_button.setToolTip('Select coordinates')
        self._drop_select_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._drop_select_button.setMaximumSize(QSize(20, 20))
        self._drop_select_button.setMenu(self._select_menu)
        self._drop_select_button.setStyleSheet('QToolButton { border: none; background: transparent; } QToolButton::menu-indicator { image: none; }')

        toprow = QHBoxLayout()
        toprow.setContentsMargins(0, 0, 0, 0)
        toprow.setSpacing(5)
        toprow.addWidget(self._dim_checkbox)
        toprow.addWidget(self._size_label)

        bottomrow = QHBoxLayout()
        bottomrow.setContentsMargins(0, 0, 0, 0)
        bottomrow.setSpacing(5)
        bottomrow.addWidget(self._spinbox)
        bottomrow.addWidget(self._drop_select_button)

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(5, 2, 5, 2)
        vbox.setSpacing(2)
        vbox.addLayout(toprow)
        vbox.addLayout(bottomrow)

        # grid = QGridLayout(self)
        # grid.setContentsMargins(5, 2, 5, 2)
        # grid.setSpacing(3)
        # grid.addWidget(self._dim_checkbox, 0, 0)
        # grid.addWidget(self._size_label, 0, 1, 1, 2)
        # grid.addWidget(self._spinbox, 1, 0, 1, 2)
        # grid.addWidget(self._drop_select_button, 1, 2)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.setFrameShape(QFrame.Shape.Box)
        self.setLineWidth(1)
        self.setStyleSheet(".DimIterWidget { border-width: 1px; border-style: solid; border-radius: 5px; }")
    
    def dim(self) -> str:
        return self._dim_checkbox.text()
    
    def setDim(self, dim: str) -> None:
        self._dim_checkbox.setText(dim)
    
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

        self._list_selector.blockSignals(True)
        self._list_selector.clear()
        self._list_selector.addItems([str(c) for c in coords])
        selected_indices = self._spinbox.indices()
        for i in range(self._list_selector.count()):
            item = self._list_selector.item(i)
            item.setSelected(i in selected_indices)
        self._list_selector.blockSignals(False)
    
    def selectedCoords(self) -> np.ndarray:
        return self._spinbox.selectedValues()
    
    def setSelectedCoords(self, coords: np.ndarray) -> None:
        self._spinbox.blockSignals(True)
        self._spinbox.setSelectedValues(coords)
        self._spinbox.blockSignals(False)
        self._onSpinboxSelectionChanged()
    
    def _onSpinboxSelectionChanged(self) -> None:
        self._list_selector.blockSignals(True)
        selected_indices = self._spinbox.indices()
        for i in range(self._list_selector.count()):
            item = self._list_selector.item(i)
            item.setSelected(i in selected_indices)
        self._list_selector.blockSignals(False)

    def _onListSelectorSelectionChanged(self) -> None:
        selected_indices = [i for i in range(self._list_selector.count()) if self._list_selector.item(i).isSelected()]
        self._spinbox.setIndices(selected_indices)

    def _updateDimCheckboxState(self) -> None:
        from qtpy.QtWidgets import QSizePolicy

        is_checked = self._dim_checkbox.isChecked()
        self._spinbox.setVisible(not is_checked)
        self._drop_select_button.setVisible(not is_checked)

        if is_checked:
            self._size_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
            self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        else:
            self._size_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.adjustSize()
        self.updateGeometry()

    def _onDimCheckboxClicked(self) -> None:
        self._updateDimCheckboxState()


def test_live():
    from qtpy.QtWidgets import QApplication
    app = QApplication()

    ds = Dataset(
        {
            "var1": DataArray(dims=('x', 'y', 'z', 'w'), data=np.random.random((5, 5, 3, 4)), attrs={"units": "m/s"}),
        },
        coords={
            "x": DataArray(dims=['x'], data=["a", "b", "c", "d", "e"], attrs={"units": "cat"}),
            "y": DataArray(dims=['y'], data=[1, 2, 3, 4, 5], attrs={"units": "#"}),
            "z": (['z'], ["p", "q", "r"]),
            "w": (['w'], [10, 20, 30, 40]),
        },
    )
    dt = DataTree(ds, name="root")
    print('before', '-'*82)
    print(dt)

    viewer = XarrayTableViewer()
    viewer.setArray(dt, "var1", isel={'z': 1, 'w': 2})
    # viewer.setArray(dt, "var1", isel={'y': 3, 'z': 1, 'w': 2})
    # viewer.setArray(dt, "x")
    # viewer.setArray(dt, "y")
    viewer.show()

    app.exec()
    print('after', '-'*82)
    print(dt)


if __name__ == "__main__":
    # test_array_text_conversion()
    test_live()