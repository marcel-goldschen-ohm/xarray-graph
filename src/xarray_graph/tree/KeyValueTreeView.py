""" Tree view for a `KeyValueTreeModel` with drag-and-drop, context menu, and mouse wheel expand/collapse.

TODO:
- edit numpy 1d/2d arrays in a table?
"""
from __future__ import annotations

from typing import cast
from qtpy.QtCore import QPoint, QSize, QModelIndex
from qtpy.QtWidgets import QAbstractItemView, QMenu
from xarray_graph.tree.KeyValueTreeItem import KeyValueTreeItem
from xarray_graph.tree.KeyValueTreeModel import KeyValueTreeModel
from xarray_graph.tree.TreeView import TreeView

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from qtpy.QtGui import QIcon


class KeyValueTreeView(TreeView[KeyValueTreeItem, KeyValueTreeModel]):
    """ Tree view for a `KeyValueTreeModel` with drag-and-drop, context menu, and mouse wheel expand/collapse.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.setAlternatingRowColors(True)

        # icons
        import qtawesome as qta
        self._dict_icon: QIcon = qta.icon('ph.folder-thin')
        self._list_icon: QIcon = qta.icon('ph.list-numbers-thin')

        # actions
        from qtpy.QtGui import QAction  # type: ignore
        self._showTypeColumnAction = QAction(
            text='Show Type Column',
            icon=qta.icon('fa6s.info'),
            iconVisibleInMenu=True,
            checkable=True,
            checked=False,
            toolTip='Show data type column in the tree view. Uncheck to hide column.'
        )
        self._showTypeColumnAction.triggered.connect(lambda checked: self._updateModelFromViewOptions())
    
    def treeData(self) -> dict | list:
        """ Get the root key:value map.
        """
        model = self.model()
        return model.treeData()
    
    def setTreeData(self, data: dict | list) -> None:
        """ Set the root key:value map.
        """
        model = self.model()
        if not model:
            root_item = KeyValueTreeItem(None, data)
            root_item.rebuildSubtree()
            model = KeyValueTreeModel(root_item)
            self.setModel(model)
            return
        self.storeViewState()
        model.setTreeData(data)
        self.restoreViewState()
    
    def setModel(self, model: KeyValueTreeModel, updateViewOptionsFromModel: bool = True) -> None:
        super().setModel(model)
        if updateViewOptionsFromModel:
            self._updateViewOptionsFromModel()
        else:
            self._updateModelFromViewOptions()

    def _updateViewOptionsFromModel(self):
        model = self.model()
        self._showTypeColumnAction.blockSignals(True)
        self._showTypeColumnAction.setChecked(model.isTypesColumnVisible())
        self._showTypeColumnAction.blockSignals(False)

    def _updateModelFromViewOptions(self):
        model = self.model()
        self.storeViewState()
        model.setTypesColumnVisible(self._showTypeColumnAction.isChecked())
        self.restoreViewState()
    
    def customContextMenu(self, index: QModelIndex = QModelIndex()) -> QMenu:
        model = self.model()

        from qtpy.QtGui import QAction  # type: ignore
        
        menu = QMenu(self)

        # item that was clicked on
        item = model.itemFromIndex(index)
        assert isinstance(item, KeyValueTreeItem)
        if item.isDict():
            icon: QIcon | None = self._dict_icon
        elif item.isList():
            icon: QIcon | None = self._list_icon
        else:
            icon: QIcon | None = None
        
        # disabled action acts as a label for the item that was right-clicked on
        if icon:
            menu.addAction(QAction(
                text=f'{item.path()}:',
                parent=menu,
                icon=icon,
                iconVisibleInMenu=True,
                enabled=False
            ))
        else:
            menu.addAction(QAction(
                text=f'{item.path()}:',
                parent=menu,
                enabled=False
            ))

        # item-specific actions
        if item is not model.rootItem():
            action = QAction(
                text='Insert New',
                parent=menu
            )
            action.triggered.connect(lambda checked, parent_item=item.parent, row=item.siblingIndex(): self.insertNew(parent_item, row))
            menu.addAction(action)

        if item.isContainer():
            action = QAction(
                text='Append New Child',
                parent=menu
            )
            action.triggered.connect(lambda checked, parent_item=item, row=len(item.children): self.insertNew(parent_item, row))
            menu.addAction(action)
        
        # selection
        has_selection: bool = self.selectionModel().hasSelection()
        self._clearSelectionAction.setEnabled(has_selection)
        if self.selectionMode() in [QAbstractItemView.SelectionMode.ContiguousSelection, QAbstractItemView.SelectionMode.ExtendedSelection, QAbstractItemView.SelectionMode.MultiSelection]:
            menu.addSeparator()
            menu.addAction(self._selectAllAction)
            menu.addAction(self._clearSelectionAction)
        
        # cut/copy/paste
        has_copy: bool = self.hasCopy()
        self._cutSelectionAction.setEnabled(has_selection)
        self._copySelectionAction.setEnabled(has_selection)
        self._pasteAction.setEnabled(has_copy)
        menu.addSeparator()
        menu.addAction(self._cutSelectionAction)
        menu.addAction(self._copySelectionAction)
        menu.addAction(self._pasteAction)

        # remove item(s)
        self._removeSelectedAction.setEnabled(has_selection)
        menu.addSeparator()
        menu.addAction(self._removeSelectedAction)
        
        # expand/collapse
        menu.addSeparator()
        menu.addAction(self._expandAllAction)
        menu.addAction(self._collapseAllAction)
        if model.columnCount() > 1:
            menu.addAction(self._resizeAllColumnsToContentsAction)
            menu.addAction(self._viewAllAction)
        
        # options
        menu.addSeparator()
        menu.addAction(self._showTypeColumnAction)

        # refresh
        menu.addSeparator()
        menu.addAction(self._refreshAction)
        
        return menu
    
    def _defaultPlacement(self, parent_item: KeyValueTreeItem = None, row: int = None) -> tuple[KeyValueTreeItem, int]:
        parent_item, row = super()._defaultPlacement(parent_item, row)
        if not parent_item.isContainer() and not parent_item.isRoot():
            row = parent_item.siblingIndex()
            parent_item = parent_item.parent
        parent_item = cast(KeyValueTreeItem, parent_item)
        return parent_item, row
    
    def insertNew(self, parent_item: KeyValueTreeItem | None = None, row: int = None) -> None:
        try:
            model = self.model()
            parent_item, row = self._defaultPlacement(parent_item, row)
            names = [item.name() for item in parent_item.children]
            from xarray_graph.tree.AbstractTreeUtils import uniqueName
            name = uniqueName('New', names)
            new_item = KeyValueTreeItem(name, None)
            model.insertItems([new_item], row, parent_item)
        except Exception as err:
            from qtpy.QtWidgets import QApplication, QMessageBox
            focus_widget = QApplication.focusWidget()
            QMessageBox.warning(focus_widget, 'Error', f'Error pasting items: {err}')


def test_live():
    import numpy as np
    from qtpy.QtWidgets import QApplication

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

    view = KeyValueTreeView()
    view.setTreeData(data)
    view.show()
    view.resize(QSize(800, 800))
    view.move(QPoint(50, 50))
    view.viewAll()
    view.raise_()

    from copy import deepcopy
    data2 = deepcopy(data)

    view2 = KeyValueTreeView()
    view2.setTreeData(data2)
    view2.show()
    view2.resize(QSize(800, 800))
    view2.move(QPoint(900, 50))
    view2.viewAll()
    view2.raise_()

    app.exec()

    # print(model.rootItem())
    print(data)

if __name__ == '__main__':
    test_live()
