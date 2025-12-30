""" PySide/PyQt table widget with copy/paste.
"""

from qtpy.QtCore import Qt
from qtpy.QtGui import QKeyEvent
from qtpy.QtWidgets import QTableWidget, QApplication, QTableWidgetItem


class TableWidgetWithCopyPaste(QTableWidget):
    """ QTableWidget with copy/paste to/from clipboard in CSV format.
    """
    
    def __init__(self, *args, **kwargs):
        QTableWidget.__init__(self, *args, **kwargs)
    
    def keyPressEvent(self, event: QKeyEvent):
        QTableWidget.keyPressEvent(self, event)

        if event.key() == Qt.Key.Key_C and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self.copy_selected_cells()
        elif event.key() == Qt.Key.Key_V and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self.paste_to_cells()
    
    def copy_selected_cells(self):
        copied_cells = sorted(self.selectedIndexes())
        copy_text = ''
        max_column = copied_cells[-1].column()
        max_row = copied_cells[-1].row()
        for c in copied_cells:
            copy_text += self.item(c.row(), c.column()).text()
            if c.column() == max_column:
                if c.row() != max_row:
                    copy_text += '\n'
            else:
                copy_text += '\t'
        QApplication.clipboard().setText(copy_text)
    
    def paste_to_cells(self):
        selection = self.selectedIndexes()
        if selection:
            row_anchor = selection[0].row()
            column_anchor = selection[0].column()
            clipboard = QApplication.clipboard()
            rows = clipboard.text().split('\n')
            for indx_row, row in enumerate(rows):
                values = row.split('\t')
                for indx_col, value in enumerate(values):
                    if row_anchor + indx_row < self.rowCount() and column_anchor + indx_col < self.columnCount():
                        item = QTableWidgetItem(value)
                        self.setItem(row_anchor + indx_row, column_anchor + indx_col, item)


def test_live():
    app = QApplication()

    table = TableWidgetWithCopyPaste(3, 3)
    for i in range(3):
        for j in range(3):
            table.setItem(i, j, QTableWidgetItem(f'{i},{j}'))
    table.show()

    app.exec()


if __name__ == '__main__':
    test_live()
