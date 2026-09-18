""" A table model for displaying and editing numpy arrays in a table view.
"""


import numpy as np
from numpy.typing import NDArray
from qtpy.QtCore import Signal  # type: ignore
from qtpy.QtCore import Qt, QAbstractTableModel, QModelIndex


class ArrayTableModel(QAbstractTableModel):

    dataTypeChanged = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._array = np.array([])
        self._read_only = False

        # headers
        self._row_labels: list[str] = []
        self._column_labels: list[str] = []
    
    def array(self) -> NDArray:
        return self._array
    
    def setArray(self, array: NDArray) -> None:
        ndim = len(array.shape)
        if ndim < 1 or ndim > 2:
            raise ValueError(f"Array must be 1D or 2D, but got {ndim}D array with shape {array.shape}.")
        self.beginResetModel()
        self._array = array
        self.endResetModel()

    def _allDataChanged(self, roles: list[Qt.ItemDataRole] = [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole]):
        # Notify the view that the data has changed to update the displayed values
        top_left = self.index(0, 0)
        bottom_right = self.index(self.rowCount() - 1, self.columnCount() - 1)
        self.dataChanged.emit(top_left, bottom_right, roles)

    def isReadOnly(self):
        return self._read_only
    
    def setReadOnly(self, read_only: bool):
        self._read_only = read_only
        self._allDataChanged([Qt.ItemDataRole.EditRole])

    def rowCount(self, parent: QModelIndex = None):
        return self._array.shape[0]

    def columnCount(self, parent: QModelIndex = None):
        return self._array.shape[1] if len(self._array.shape) > 1 else 1

    def data(self, index: QModelIndex, role = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            row = index.row()
            col = index.column()
            ndim = len(self._array.shape)
            if ndim == 1:
                value = self._array[row]
            elif ndim == 2:
                value = self._array[row, col]
            else:
                # should never happen because we validate the array shape in setArray, but just in case
                raise ValueError(f"Array must be 1D or 2D, but got {ndim}D array with shape {self._array.shape}.")
            # return value as string so that the dtype can be changed when editing the value in the table view
            return str(value)
        return None

    def setData(self, index: QModelIndex, value, role = Qt.ItemDataRole.EditRole):
        if not index.isValid():
            return False
        if role == Qt.ItemDataRole.EditRole:
            dataTypeWasChanged = False
            try:
                # Convert the input string back to the original array type
                typed_value = self._array.dtype.type(value)
            except ValueError:
                try:
                    typed_value = float(value)
                    new_array = self._array.astype(float)
                    from qtpy.QtWidgets import QMessageBox
                    reply = QMessageBox.question(None, "Array Data Type Changed", "The data type of the entire array will be changed to `<float>` due to the input value. Continue?", QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
                    if reply != QMessageBox.StandardButton.Ok:
                        return False
                    self._array = new_array
                    dataTypeWasChanged = True
                except ValueError:
                    try:
                        typed_value = str(value)
                        new_array = self._array.astype(str)
                        from qtpy.QtWidgets import QMessageBox
                        reply = QMessageBox.question(None, "Array Data Type Changed", "The data type of the entire array will be changed to `<str>` due to the input value. Continue?", QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
                        if reply != QMessageBox.StandardButton.Ok:
                            return False
                        self._array = new_array
                        dataTypeWasChanged = True
                    except ValueError:
                        return False

            row = index.row()
            col = index.column()
            ndim = len(self._array.shape)
            if ndim == 1:
                self._array[row] = typed_value
            elif ndim == 2:
                self._array[row, col] = typed_value
            else:
                # should never happen because we validate the array shape in setArray, but just in case
                raise ValueError(f"Array must be 1D or 2D, but got {ndim}D array with shape {self._array.shape}.")

            if dataTypeWasChanged:
                # Notify the view that all data has changed to update the displayed values and data type
                self._allDataChanged()
                # Emit a signal if the data type was changed as self._array is now a new array with a different dtype
                self.dataTypeChanged.emit()
            else:
                # Notify the view that the cell has changed
                self.dataChanged.emit(index, index, [role])
            return True
        return False

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = super().flags(index)
        if not self._read_only:
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def headerData(self, section: int, orientation: Qt.Orientation, role: int):
        """ Get row or column label.
        """
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                labels = self.columnLabels()
            else: #elif orientation == Qt.Orientation.Vertical:
                labels = self.rowLabels()
            if section < len(labels):
                label = labels[section]
                if label is not None:
                    return label
            return section

    def setHeaderData(self, section: int, orientation: Qt.Orientation, value, role: int) -> bool:
        """ Set row or column label.
        """
        if role == Qt.ItemDataRole.EditRole:
            if orientation == Qt.Orientation.Horizontal:
                labels = self.columnLabels()
            else: #elif orientation == Qt.Orientation.Vertical:
                labels = self.rowLabels()
            if section < len(labels):
                labels[section] = value
            else:
                labels += [None] * (section - len(labels)) + [value]
            if orientation == Qt.Orientation.Horizontal:
                self.setColumnLabels(labels)
            elif orientation == Qt.Orientation.Vertical:
                self.setRowLabels(labels)
            self.headerDataChanged.emit(orientation, section, section)
            return True
        return False
    
    def rowLabels(self) -> list:
        return self._row_labels
    
    def setRowLabels(self, labels: list) -> None:
        old_labels = self._row_labels
        n_overlap = min(len(labels), len(old_labels))
        first_change = 0
        while (first_change < n_overlap) and (labels[first_change] == old_labels[first_change]):
            first_change += 1
        last_change = max(len(labels), len(old_labels)) - 1
        while (last_change >= 0) and (last_change < n_overlap) and (labels[last_change] == old_labels[last_change]):
            last_change -= 1
        self._row_labels = labels
        if first_change <= last_change: 
            self.headerDataChanged.emit(Qt.Orientation.Vertical, first_change, last_change)
    
    def columnLabels(self) -> list:
        return self._column_labels
    
    def setColumnLabels(self, labels: list) -> None:
        old_labels = self._column_labels
        n_overlap = min(len(labels), len(old_labels))
        first_change = 0
        while (first_change < n_overlap) and (labels[first_change] == old_labels[first_change]):
            first_change += 1
        last_change = max(len(labels), len(old_labels)) - 1
        while (last_change >= 0) and (last_change < n_overlap) and (labels[last_change] == old_labels[last_change]):
            last_change -= 1
        self._column_labels = labels
        if first_change <= last_change: 
            self.headerDataChanged.emit(Qt.Orientation.Horizontal, first_change, last_change)


if __name__ == "__main__":
    import sys
    from qtpy.QtWidgets import QApplication, QTableView

    app = QApplication(sys.argv)
    
    # Initialize an integer matrix (dtype determines how input is converted)
    matrix = np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
    
    view = QTableView()
    model = ArrayTableModel()
    model.setArray(matrix)
    view.setModel(model)
    view.show()
    
    sys.exit(app.exec())
