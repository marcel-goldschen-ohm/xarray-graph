
import numpy as np
from qtpy.QtCore import Qt, QAbstractTableModel, QModelIndex

class ArrayTableModel(QAbstractTableModel):

    def __init__(self, array: np.ndarray):
        super().__init__()
        self._array = np.array([])
        self._read_only = False

        if array.ndim not in (1, 2):
            raise ValueError("Array must be 1D or 2D.")
        self._array = array
    
    def array(self) -> np.ndarray:
        return self._array
    
    def setArray(self, array: np.ndarray):
        if array.ndim not in (1, 2):
            raise ValueError("Array must be 1D or 2D.")
        self.beginResetModel()
        self._array = array
        self.endResetModel()
    
    def isReadOnly(self):
        return self._read_only
    
    def setReadOnly(self, read_only: bool):
        self._read_only = read_only
        # Notify the view that the data has changed to update the editability
        top_left = self.index(0, 0)
        bottom_right = self.index(self.rowCount() - 1, self.columnCount() - 1)
        self.dataChanged.emit(top_left, bottom_right, [Qt.ItemDataRole.EditRole])

    def rowCount(self, parent: QModelIndex = None):
        return self._array.shape[0]

    def columnCount(self, parent: QModelIndex = None):
        return self._array.shape[1] if self._array.ndim > 1 else 1

    def data(self, index: QModelIndex, role = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            row = index.row()
            col = index.column()
            if self._array.ndim == 1:
                return str(self._array[row])
            elif self._array.ndim == 2:
                return str(self._array[row, col])
        return None

    def setData(self, index: QModelIndex, value, role = Qt.ItemDataRole.EditRole):
        if not index.isValid():
            return False
        if role == Qt.ItemDataRole.EditRole:
            try:
                # Convert the input string back to the original array type
                typed_value = self._array.dtype.type(value)
                row = index.row()
                col = index.column()
                if self._array.ndim == 1:
                    self._array[row] = typed_value
                elif self._array.ndim == 2:
                    self._array[row, col] = typed_value
                
                # Notify the view that the cell has changed
                self.dataChanged.emit(index, index, [role])
                return True
            except ValueError:
                # Discard input if it cannot be converted to the array's data type
                return False
        return False

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = super().flags(index)
        if not self._read_only:
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags


if __name__ == "__main__":
    import sys
    from qtpy.QtWidgets import QApplication, QTableView

    app = QApplication(sys.argv)
    
    # Initialize an integer matrix (dtype determines how input is converted)
    matrix = np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]], dtype=np.int32)
    
    view = QTableView()
    model = ArrayTableModel(matrix)
    view.setModel(model)
    view.show()
    
    sys.exit(app.exec())
