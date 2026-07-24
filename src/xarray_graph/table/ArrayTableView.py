
import numpy as np
from qtpy.QtCore import Qt
from qtpy.QtGui import QKeyEvent
from qtpy.QtWidgets import QTableView
from xarray_graph.table.ArrayTableModel import ArrayTableModel


class ArrayTableView(QTableView):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableView.SelectionBehavior.SelectItems)
        self.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        # self.setSortingEnabled(False)
    
    def selectedRowsAndColumns(self):
        """ Returns a tuple of (rows, cols) arrays for the selected cells in the table.
        """
        selected_indices = sorted(self.selectionModel().selectedIndexes())
        N = len(selected_indices)
        if N == 0:
            return (np.array([], dtype=int), np.array([], dtype=int))
        rows = np.empty((N,), dtype=int)
        cols = np.empty((N,), dtype=int)
        for i, index in enumerate(selected_indices):
            rows[i] = index.row()
            cols[i] = index.column()
        return (rows, cols)
    
    @staticmethod
    def _text_from_matrix(array: np.ndarray) -> str:
        """ Converts a 1D or 2D numpy array into a tab-delimited string.
        """
        array = np.atleast_2d(array)
        return '\n'.join(['\t'.join(map(str, row)) for row in array])
    
    @staticmethod
    def _matrix_from_text(text: str, dtype: np.dtype = None) -> np.ndarray:
        """ Converts a tab-delimited string into a 2D numpy array.
        """
        rows = text.strip().split('\n')
        data = [row.split('\t') for row in rows]
        if dtype:
            return np.array(data, dtype=dtype)
        return np.array(data)
    
    def keyPressEvent(self, event: QKeyEvent):
        super().keyPressEvent(event)

        is_control_pressed = event.modifiers() & Qt.KeyboardModifier.ControlModifier
        if is_control_pressed:
            if event.key() == Qt.Key.Key_C:
                self.copyToClipboard()
            elif event.key() == Qt.Key.Key_V:
                self.pasteFromClipboard()
    
    def copyToClipboard(self):
        rows, cols = self.selectedRowsAndColumns()
        urows, ucols = np.unique(rows), np.unique(cols)
        nrows, ncols = len(urows), len(ucols)
        if nrows == 0 or ncols == 0:
            return
        model: ArrayTableModel = self.model()
        array = model.array()
        if array.ndim == 1:
            array_selection = array[rows]
        else:
            try:
                array_selection = array[(rows, cols)].reshape(nrows, ncols)
            except:
                raise ValueError("Selected cells must form a rectangular block for copying.")

        # store copy as tab-delimited text in clipboard
        text = self._text_from_matrix(array_selection)
        from qtpy.QtWidgets import QApplication
        QApplication.clipboard().setText(text)

        # print(f"Copied array:\n{array_selection}")
        # print(f"Copied text:\n{text}")
    
    def pasteFromClipboard(self):
        rows, cols = self.selectedRowsAndColumns()
        selsize = len(rows)
        if selsize == 0:
            return
        
        model: ArrayTableModel = self.model()
        array = model.array()
        
        # get copy as tab-delimited text in clipboard
        from qtpy.QtWidgets import QApplication
        text = QApplication.clipboard().text()
        array_to_paste = self._matrix_from_text(text, array.dtype)

        urows, ucols = np.unique(rows), np.unique(cols)
        nrows, ncols = len(urows), len(ucols)
        prows, pcols = array_to_paste.shape

        if array.ndim == 1:
            array_to_paste = array_to_paste.flatten()
            prows = array_to_paste.size
            if prows == nrows:
                # paste over selection
                for i, row in enumerate(rows):
                    array[row] = array_to_paste[i]
                top_left = model.index(rows[0], 0)
                bottom_right = model.index(rows[-1], 0)
            else:
                # paste block starting from the first selected row
                row0 = rows[0]
                array[row0:row0 + prows] = array_to_paste
                top_left = model.index(row0, 0)
                bottom_right = model.index(row0 + prows - 1, 0)
        else:
            if (prows, pcols) == (nrows, ncols):
                # paste over selection
                for i, row in enumerate(urows):
                    for j, col in enumerate(ucols):
                        array[row, col] = array_to_paste[i, j]
                top_left = model.index(urows[0], ucols[0])
                bottom_right = model.index(urows[-1], ucols[-1])
            else:
                # paste block starting from the first selected cell
                row0 = rows[0]
                col0 = cols[0]
                array[row0:row0 + prows, col0:col0 + pcols] = array_to_paste
                top_left = model.index(row0, col0)
                bottom_right = model.index(row0 + prows - 1, col0 + pcols - 1)
        
        # Notify the model that the data has changed
        model.dataChanged.emit(top_left, bottom_right, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole])


def test_array_text_conversion():
    # Test the conversion functions
    array = np.array([[1, 2], [3, 4]])
    text = ArrayTableView._text_from_matrix(array)
    print("Text from array:")
    print(text)
    
    new_array = ArrayTableView._matrix_from_text(text, dtype=array.dtype)
    print("Array from text:")
    print(new_array)
    print(new_array.dtype)


def test_live():
    from qtpy.QtWidgets import QApplication
    app = QApplication()

    # Create a sample 2D array
    sample_array = np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]])

    # Create the model and view
    model = ArrayTableModel(sample_array)
    view = ArrayTableView()
    view.setModel(model)
    view.show()

    app.exec()
    print(sample_array)  # Print the modified array after closing the application


if __name__ == "__main__":
    # test_array_text_conversion()
    test_live()