""" Tree view for a `KeyValueTreeModel` with drag-and-drop, context menu, and mouse wheel expand/collapse.

TODO:
- copy/paste
- edit numpy 1d/2d arrays in a table?
- bug fix: resize column to contents not working with custom delegates
    - !!! move logic out of delegate and into model? This might be the simplest approach.
"""

from __future__ import annotations
import numpy as np
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
from xarray_graph.tree import KeyValueTreeItem, KeyValueTreeModel, TreeView


class KeyValueTreeView(TreeView):

    def __init__(self, *args, **kwargs) -> None:
        TreeView.__init__(self, *args, **kwargs)

        self._cut_icon = qta.icon('mdi.content-cut')
        self._copy_icon = qta.icon('mdi.content-copy')
        self._paste_icon = qta.icon('mdi.content-paste')

        self.setItemDelegate(KeyValueTreeViewDelegate(self))
    
    def customContextMenu(self, index: QModelIndex = QModelIndex()) -> QMenu:
        model: KeyValueTreeModel = self.model()
        menu = QMenu(self)

        # item that was clicked on
        item: KeyValueTreeItem = model.itemFromIndex(index)
        
        # selection
        has_selection: bool = self.selectionModel().hasSelection()
        if self.selectionMode() in [QAbstractItemView.SelectionMode.ContiguousSelection, QAbstractItemView.SelectionMode.ExtendedSelection, QAbstractItemView.SelectionMode.MultiSelection]:
            menu.addSeparator()
            menu.addAction(self._selectAllAction)
            menu.addAction(self._clearSelectionAction)
        
        # cut/copy/paste
        has_copy: bool = hasattr(self, '_clipboardItems')
        menu.addSeparator()
        menu.addAction(QAction('Cut', parent=menu, icon=self._cut_icon, iconVisibleInMenu=True, shortcut=QKeySequence.StandardKey.Cut, triggered=lambda checked: self.cutSelection(), enabled=has_selection))
        menu.addAction(QAction('Copy', parent=menu, icon=self._copy_icon, iconVisibleInMenu=True, shortcut=QKeySequence.StandardKey.Copy, triggered=lambda checked: self.copySelection(), enabled=has_selection))
        menu.addAction(QAction('Paste', parent=menu, icon=self._paste_icon, iconVisibleInMenu=True, shortcut=QKeySequence.StandardKey.Paste, triggered=lambda checked, parent_item=item: self.pasteCopy(parent_item), enabled=has_copy))
        
        # remove item(s)
        menu.addSeparator()
        menu.addAction(QAction('Remove', parent=menu, triggered=lambda checked: self.removeSelectedItems(), enabled=has_selection))
        
        # insert new item
        menu.addSeparator()
        if item is model.rootItem():
            menu.addAction(QAction('Add New', parent=menu, triggered=lambda checked, parent_item=item, row=len(item.children): self.insertNew(parent_item, row)))
        else:
            menu.addAction(QAction('Insert New', parent=menu, triggered=lambda checked, parent_item=item.parent, row=item.row: self.insertNew(parent_item, row)))
        
        # expand/collapse
        menu.addSeparator()
        menu.addAction(self._expandAllAction)
        menu.addAction(self._collapseAllAction)
        if model.columnCount() > 1:
            menu.addAction(self._resizeAllColumnsToContentsAction)
            menu.addAction(self._showAllAction)

        # refresh
        menu.addSeparator()
        menu.addAction(self._refreshAction)
        
        return menu
    
    def cutSelection(self) -> None:
        self.copySelection()
        self.removeSelectedItems(ask=False)
    
    def copySelection(self) -> None:
        items: list[KeyValueTreeItem] = self.selectedItems()
        if not items:
            return
        self._clipboardItems: list[KeyValueTreeItem] = items
    
    def pasteCopy(self, parent_item: KeyValueTreeItem) -> None:
        items: list[KeyValueTreeItem] = getattr(self, '_clipboardItems', None)
        if not items:
            return
        # TODO: paste items
        delattr(self, '_clipboardItems')
    
    def insertNew(self, parent_item: KeyValueTreeItem, row: int) -> None:
        model: KeyValueTreeModel = self.model()
        names = [item.name for item in parent_item.children]
        name = model.unique_name('New', names)
        new_item = KeyValueTreeItem('')
        model.insertItems({name: new_item}, row, parent_item)


class KeyValueTreeViewDelegate(QStyledItemDelegate):
    """ Delegate for editing values.
    """
    def __init__(self, parent: QObject = None):
        QStyledItemDelegate.__init__(self, parent)
    
    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex):
        data = index.model().data(index, Qt.ItemDataRole.EditRole)
        editor = QLineEdit(parent)
        text = value_to_str(data)
        editor.setText(text)
        return editor
        # if isinstance(data, bool):
        #     # will handle with paint(), editorEvent(), and setModelData()
        #     return None
        # return QStyledItemDelegate.createEditor(self, parent, option, index)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        if index.column() == 1:
            data = index.model().data(index, Qt.ItemDataRole.DisplayRole)
            if data is not None and type(data) not in [bool, int, float, str]:
                text = value_to_str(data)
                if option.state & QStyle.StateFlag.State_Selected:
                    painter.fillRect(option.rect, option.palette.highlight())
                    painter.setPen(option.palette.highlightedText().color())
                else:
                    painter.setPen(option.palette.text().color())
                painter.drawText(option.rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
                return
        # elif isinstance(data, bool):
        #     # paint checkbox without label
        #     checked = data
        #     opts = QStyleOptionButton()
        #     opts.state |= QStyle.State_Active
        #     if index.flags() & Qt.ItemFlag.ItemIsEditable:
        #         opts.state |= QStyle.State_Enabled
        #     else:
        #         opts.state |= QStyle.State_ReadOnly
        #     if checked:
        #         opts.state |= QStyle.State_On
        #     else:
        #         opts.state |= QStyle.State_Off
        #     opts.rect = self.getCheckBoxRect(option)
        #     QApplication.style().drawControl(QStyle.CE_CheckBox, opts, painter)
        #     return
        return QStyledItemDelegate.paint(self, painter, option, index)

    def editorEvent(self, event: QEvent, model: KeyValueTreeModel, option: QStyleOptionViewItem, index: QModelIndex):
        # data = index.model().data(index, Qt.ItemDataRole.EditRole)
        # if isinstance(data, bool):
        #     # handle checkbox events
        #     if not (index.flags() & Qt.ItemFlag.ItemIsEditable):
        #         return False
        #     if event.button() == Qt.MouseButton.LeftButton:
        #         if event.type() == QEvent.MouseButtonRelease:
        #             if self.getCheckBoxRect(option).contains(event.pos()):
        #                 self.setModelData(None, model, index)
        #                 return True
        #         elif event.type() == QEvent.MouseButtonDblClick:
        #             if self.getCheckBoxRect(option).contains(event.pos()):
        #                 return True
        #     return False
        return QStyledItemDelegate.editorEvent(self, event, model, option, index)

    def setModelData(self, editor: QWidget, model: KeyValueTreeModel, index: QModelIndex):
        if isinstance(editor, QLineEdit):
            text = editor.text()
            if index.column() == 0:
                value = str_to_value(text)
                model.setData(index, value, Qt.ItemDataRole.EditRole)
                return
            elif index.column() == 1:
                item: KeyValueTreeItem = model.itemFromIndex(index)
                old_value = item.value
                if type(old_value) in [dict, list] and len(old_value) > 0:
                    answer = QMessageBox.question(self.parent(), 'Overwrite?', 'Overwrite non-empty key:value map?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                    if answer == QMessageBox.StandardButton.No:
                        return
                value = str_to_value(text, default_type=type(old_value))
                mapping_changed = (type(old_value) in [dict, list]) or (type(value) in [dict, list])
                if mapping_changed:
                    view: KeyValueTreeView = self.parent()
                    view.storeViewState()
                model.setData(index, value, Qt.ItemDataRole.EditRole)
                if mapping_changed:
                    view.restoreViewState()
                return
        
        return QStyledItemDelegate.setModelData(self, editor, model, index)

    def getCheckBoxRect(self, option: QStyleOptionViewItem):
        """ Get rect for checkbox positioned in option.rect.
        """
        # Get size of a standard checkbox
        opts = QStyleOptionButton()
        checkBoxRect = QApplication.style().subElementRect(QStyle.SE_CheckBoxIndicator, opts, None)
        # Position checkbox in option.rect
        x = option.rect.x()
        y = option.rect.y()
        w = option.rect.width()
        h = option.rect.height()
        # checkBoxTopLeftCorner = QPoint(x + w / 2 - checkBoxRect.width() / 2, y + h / 2 - checkBoxRect.height() / 2)  # horizontal center, vertical center
        checkBoxTopLeftCorner = QPoint(x, y + h / 2 - checkBoxRect.height() / 2)  # horizontal left, vertical center
        return QRect(checkBoxTopLeftCorner, checkBoxRect.size())


def str_to_value(text: str, default_type = None) -> bool | int | float | str | tuple | list | dict | set | np.ndarray:
    if text.lower().strip() == 'true':
        return True
    if text.lower().strip() == 'false':
        return False
    if text.lstrip().startswith('numpy.array(') and text.rstrip().endswith(')'):
        # numpy array
        inner_text = text.strip()[len('numpy.array(['):-2]
        values = [str_to_value(item.strip()) for item in split_text(inner_text)]
        return np.array(values)
    if text.lstrip().startswith('np.array(') and text.rstrip().endswith(')'):
        # numpy array
        inner_text = text.strip()[len('np.array(['):-2]
        values = [str_to_value(item.strip()) for item in split_text(inner_text)]
        return np.array(values)
    if text.lstrip().startswith('array(') and text.rstrip().endswith(')'):
        # numpy array
        inner_text = text.strip()[len('array(['):-2]
        values = [str_to_value(item.strip()) for item in split_text(inner_text)]
        return np.array(values)
    if text.lstrip().startswith('(') and text.rstrip().endswith(')'):
        # tuple
        inner_text = text.strip()[1:-1]
        values = [str_to_value(item.strip()) for item in split_text(inner_text)]
        return tuple(values)
    if text.lstrip().startswith('[') and text.rstrip().endswith(']'):
        # list or numpy array
        inner_text = text.strip()[1:-1]
        values = [str_to_value(item.strip()) for item in split_text(inner_text)]
        if default_type is np.ndarray:
            return np.array(values)
        return values
    if text.lstrip().startswith('{') and text.rstrip().endswith('}'):
        # dict or set
        inner_text = text.strip()[1:-1]
        items = split_text(inner_text)
        if not items:
            # empty dict
            return {}
        if ':' in items[0]:
            # dict
            values = {}
            for item in items:
                key, value = item.split(':')
                values[key.strip()] = str_to_value(value.strip())
            return values
        else:
            # set
            values = set()
            for item in items:
                values.add(str_to_value(item))
            return values
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text


def value_to_str(value: bool | int | float | str | tuple | list | dict | np.ndarray, in_recursion: bool = False) -> str:
    if isinstance(value, str):
        return value
    if type(value) in [bool, int, float]:
        return str(value)
    if isinstance(value, tuple):
        return '(' + ', '.join([value_to_str(val) for val in value]) + ')'
    if isinstance(value, list):
        return '[' + ', '.join([value_to_str(val) for val in value]) + ']'
    if isinstance(value, set):
        return '{' + ', '.join([value_to_str(val) for val in value]) + '}'
    if isinstance(value, dict):
        return '{' + ', '.join([f'{key}: ' + value_to_str(val) for key, val in value.items()]) + '}'
    if isinstance(value, np.ndarray):
        return '[' + ', '.join([value_to_str(val, in_recursion=True) for val in value]) + ']'
    return str(value)


def split_text(text: str) -> list[str]:
    parts: list[str] = ['']
    grouping: str = ''
    for char in text:
        if char == '(' or char == '[' or char == '{':
            grouping += char
        elif grouping:
            if grouping[-1] == '(' and char == ')':
                grouping = grouping[:-1]
            elif grouping[-1] == '[' and char == ']':
                grouping = grouping[:-1]
            elif grouping[-1] == '{' and char == '}':
                grouping = grouping[:-1]
        if char == ',' and not grouping:
            parts.append('')
        else:
            parts[-1] += char
    parts = [part.strip() for part in parts if part.strip()]
    return parts


def test_live():

    data = {
        'a': 1,
        'b': [4, 8, (1, 5.5234985270827504823702, True, 'good'), 5, 7, 99, True, False, 'hi', 'bye'],
        'c': {
            'me': 'hi',
            3: 67,
            'd': {
                'e': np.float32(3.14),
                'f': 'ya!',
                'g': np.int16(5),
            },
        },
        '1d': np.array([1, 2, 3]),
        'nd': np.array([[1, 2, 3], [4, 5, 6]]),
    }

    app = QApplication()

    root = KeyValueTreeItem(data)

    model = KeyValueTreeModel()
    model.setTypesColumnVisible(True)
    model.setRootItem(root)

    view = KeyValueTreeView()
    view.setModel(model)
    view.show()
    view.resize(QSize(800, 600))
    view.showAll()

    app.exec()

    # print(model.rootItem())
    print(data)

if __name__ == '__main__':
    test_live()
