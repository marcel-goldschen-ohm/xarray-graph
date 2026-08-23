""" Tree view for a `AnnotationTreeModel` with drag-and-drop, context menu, and mouse wheel expand/collapse.
"""
from __future__ import annotations

from qtpy.QtCore import QPoint, QSize, QModelIndex
from qtpy.QtWidgets import QAbstractItemView, QMenu
from xarray_graph.tree.AbstractTreeModel import AbstractTreeModel
from xarray_graph.tree.TreeView import TreeView
from xarray_graph.tree.AnnotationTreeItem import AnnotationTreeItem
from xarray_graph.tree.AnnotationTreeModel import AnnotationTreeModel


class AnnotationTreeView(TreeView):

    _copied_annotations: list[dict] = []

    def __init__(self, *args, **kwargs) -> None:
        TreeView.__init__(self, *args, **kwargs)

        from qtpy.QtGui import QKeySequence
        from qtpy.QtWidgets import QShortcut  # type: ignore
        import qtawesome as qta

        self._cut_icon = qta.icon('mdi.content-cut')
        self._copy_icon = qta.icon('mdi.content-copy')
        self._paste_icon = qta.icon('mdi.content-paste')

        self._cut_shortcut = QShortcut(QKeySequence.StandardKey.Cut, self)
        self._cut_shortcut.activated.connect(self.cutSelection)

        self._copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self)
        self._copy_shortcut.activated.connect(self.copySelection)

        self._paste_shortcut = QShortcut(QKeySequence.StandardKey.Paste, self)
        self._paste_shortcut.activated.connect(lambda: self.pasteCopy())

        # self.setAlternatingRowColors(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragAndDropEnabled(True)
    
    def annotations(self) -> list[dict]:
        model = self.model()
        assert isinstance(model, AnnotationTreeModel)
        return model.annotations()
    
    def setAnnotations(self, annotations: list[dict]) -> None:
        model = self.model()
        if model is None:
            model = AnnotationTreeModel()
            model.setAnnotations(annotations)
            self.setModel(model)
        elif isinstance(model, AnnotationTreeModel):
            self.storeViewState()
            model.setAnnotations(annotations)
            self.restoreViewState()
    
    def selectedAnnotations(self) -> list[dict]:
        model = self.model()
        if not isinstance(model, AnnotationTreeModel):
            return []
        annotations = []
        for item in self.selectedItems():
            for leaf in item.subtree_leaves():
                assert isinstance(leaf, AnnotationTreeItem)
                if leaf.isAnnotation():
                    annotation = leaf._data
                    if annotation not in annotations:
                        annotations.append(annotation)
        return annotations

    def setSelectedAnnotations(self, annotations: list[dict]) -> None:
        model = self.model()
        if not isinstance(model, AnnotationTreeModel):
            return
        root = model.rootItem()
        self.selectionModel().clearSelection()
        from qtpy.QtCore import QItemSelection
        toSelect = QItemSelection()
        for item in root.subtree_leaves():
            if item is root:
                continue
            assert isinstance(item, AnnotationTreeItem)
            if item.isAnnotation():
                annotation = item._data
                if annotation in annotations:
                    index: QModelIndex = model.indexFromItem(item)
                    toSelect.select(index, index)
        if toSelect.indexes():
            from qtpy.QtCore import QItemSelectionModel
            flags = (
                QItemSelectionModel.SelectionFlag.Select |
                QItemSelectionModel.SelectionFlag.Rows
            )
            self.selectionModel().select(toSelect, flags)
    
    def customContextMenu(self, index: QModelIndex = QModelIndex()) -> QMenu:
        from qtpy.QtGui import QAction  # type: ignore

        model = self.model()
        if not isinstance(model, AnnotationTreeModel):
            raise RuntimeError('AnnotationTreeView must have an AnnotationTreeModel to show a context menu.')

        menu = QMenu(self)

        # item that was clicked on
        item = model.itemFromIndex(index)
        assert isinstance(item, AnnotationTreeItem)

        if item.isAnnotation():
            action = QAction('Edit', parent=menu)
            action.triggered.connect(lambda checked, item=item: self.editAnnotation(item))
            menu.addAction(action)
            menu.addSeparator()
        
        # selection
        has_selection: bool = self.selectionModel().hasSelection()
        if self.selectionMode() in [QAbstractItemView.SelectionMode.ContiguousSelection, QAbstractItemView.SelectionMode.ExtendedSelection, QAbstractItemView.SelectionMode.MultiSelection]:
            menu.addSeparator()
            menu.addAction(self._selectAllAction)
            menu.addAction(self._clearSelectionAction)
        
        # cut/copy/paste (annotations only)
        has_copy: bool = self.hasCopy()
        menu.addSeparator()

        action = QAction('Cut', parent=menu, icon=self._cut_icon, iconVisibleInMenu=True, enabled=has_selection)
        action.triggered.connect(lambda checked: self.cutSelection())
        menu.addAction(action)

        action = QAction('Copy', parent=menu, icon=self._copy_icon, iconVisibleInMenu=True, enabled=has_selection)
        action.triggered.connect(lambda checked: self.copySelection())
        menu.addAction(action)

        action = QAction('Paste', parent=menu, icon=self._paste_icon, iconVisibleInMenu=True, enabled=has_copy)
        action.triggered.connect(lambda checked, parent_item=item: self.pasteCopy(parent_item))
        menu.addAction(action)

        # remove item(s)
        menu.addSeparator()
        action = QAction('Remove', parent=menu, enabled=has_selection)
        action.triggered.connect(lambda checked: self.removeSelectedItems())
        menu.addAction(action)
        
        # insert new item
        if item.isRoot() or (item.parent and item.parent.isRoot()):
            parent_item = item if item.isRoot() else item.parent
            assert isinstance(parent_item, AnnotationTreeItem)
            menu.addSeparator()

            action = QAction('New Group', parent=menu)
            action.triggered.connect(lambda checked, parent_item=parent_item, row=len(parent_item.children): self.insertNewGroup(parent_item, row))
            menu.addAction(action)
        
        # group selected
        if has_selection:
            menu.addSeparator()

            action = QAction('Group Selected', parent=menu)
            action.triggered.connect(lambda checked: self.groupSelected())
            menu.addAction(action)

            action = QAction('Ungroup Selected', parent=menu)
            action.triggered.connect(lambda checked: self.ungroupSelected())
            menu.addAction(action)
        
        # expand/collapse
        menu.addSeparator()
        menu.addAction(self._expandAllAction)
        menu.addAction(self._collapseAllAction)
        if model.columnCount() > 1:
            menu.addAction(self._resizeAllColumnsToContentsAction)
            menu.addAction(self._viewAllAction)

        # refresh
        menu.addSeparator()
        menu.addAction(self._refreshAction)
        
        return menu
    
    def cutSelection(self) -> None:
        self.copySelection()
        self.removeSelectedItems(ask=False)
    
    def copySelection(self) -> None:
        items = []
        for item in self.selectedItems():
            for leaf_item in item.subtree_leaves():
                if leaf_item not in items:
                    items.append(leaf_item)
        if not items:
            return
        # copy the annotation dicts
        from copy import deepcopy
        AnnotationTreeView._copied_annotations = [deepcopy(item._data) for item in items if isinstance(item, AnnotationTreeItem) and item.isAnnotation() and isinstance(item._data, dict)]
    
    def pasteCopy(self, parent_item: AnnotationTreeItem = None) -> None:
        model = self.model()
        if not isinstance(model, AnnotationTreeModel):
            return
        from copy import deepcopy
        annotations = [deepcopy(ann) for ann in AnnotationTreeView._copied_annotations]
        if not annotations:
            return
        if parent_item is None:
            items = self.selectedItems()
            if not items:
                return
            first_item = items[0]
            assert isinstance(first_item, AnnotationTreeItem)
            parent_item = first_item
            if parent_item.isAnnotation():
                assert isinstance(parent_item.parent, AnnotationTreeItem)
                parent_item = parent_item.parent
        # assign group to pasted annotations if pasting into a group or remove group if pasting into root
        group = parent_item.group()
        for annotation in annotations:
            if group:
                annotation['group'] = group
            else:
                annotation['group'] = ''
        # paste items
        annotations = model.annotations() + annotations
        model.setAnnotations(annotations)
    
    def hasCopy(self) -> bool:
        if AnnotationTreeView._copied_annotations:
            return True
        return False
    
    def editAnnotation(self, item: AnnotationTreeItem) -> None:
        if not item.isAnnotation():
            return
        
        from qtpy.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox
        from xarray_graph.tree.KeyValueTreeModel import KeyValueTreeModel
        from xarray_graph.tree.KeyValueTreeView import KeyValueTreeView

        annotation = item._data
        model = KeyValueTreeModel()
        model.setTreeData(annotation)
        view = KeyValueTreeView()
        view.setAlternatingRowColors(True)
        view.setModel(model)
        view.viewAll()
        
        dialog = QDialog(parent=self)
        dialog.setWindowTitle('Edit Annotation')
        vbox = QVBoxLayout(dialog)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(10)
        vbox.addWidget(view)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=dialog)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        vbox.addWidget(button_box)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
    
    def insertNewGroup(self, parent_item: AnnotationTreeItem, row: int) -> None:
        if not parent_item.isRoot():
            return
        model = self.model()
        if not isinstance(model, AnnotationTreeModel):
            return
        annotations = parent_item._data
        if not isinstance(annotations, list):
            return
        group_names = list(set([ann['group'] for ann in annotations if ann.get('group', None)]))
        # in case we have any empty group nodes
        for child_item in parent_item.children:
            assert isinstance(child_item, AnnotationTreeItem)
            if child_item.isGroup():
                group_name = child_item.group()
                if group_name not in group_names:
                    group_names.append(group_name)
        # insert new empty group node with unique name
        from xarray_graph.tree.AbstractTreeModel import AbstractTreeModel
        group_name = AbstractTreeModel.uniqueName('Group', group_names)
        new_item = AnnotationTreeItem([], group_name)
        model.insertItems([new_item], row, parent_item)
    
    def groupSelected(self) -> None:
        items = self.selectedItems()
        if not items:
            return
        from qtpy.QtWidgets import QInputDialog
        title = 'Group'
        label = 'Group name:'
        group, ok = QInputDialog.getText(self, title, label)
        group = group.strip()
        if not ok or not group:
            return
        for item in items:
            assert isinstance(item, AnnotationTreeItem)
            if item.isAnnotation():
                annotation = item._data
                assert isinstance(annotation, dict)
                annotation['group'] = group
        self.refresh()
    
    def ungroupSelected(self) -> None:
        items = self.selectedItems()
        if not items:
            return
        for item in items:
            assert isinstance(item, AnnotationTreeItem)
            if item.isAnnotation():
                annotation = item._data
                assert isinstance(annotation, dict)
                annotation['group'] = ''
        self.refresh()


def test_live():
    from qtpy.QtWidgets import QApplication

    annotations = [
        {'type': 'region', 'position': {'lat': [0, 1]}},
        {'type': 'region', 'position': {'lon': [2, 3]}},
        {'type': 'region', 'position': {'lat': [4, 5], 'lon': [6, 7]}, 'group': 'Group A'},
        {'type': 'region', 'position': {'lon': [6, 7]}, 'group': 'Group A', 'text': 'some text\nsecond line'},
        {'type': 'region', 'position': {'lat': [8, 9]}, 'group': 'Group B'},
    ]

    app = QApplication()

    model = AnnotationTreeModel()
    model.setAnnotations(annotations)

    view = AnnotationTreeView()
    view.setModel(model)
    view.show()
    view.resize(QSize(800, 800))
    view.move(QPoint(100, 100))
    view.viewAll()
    view.raise_()

    app.exec()

    print(model.rootItem())
    print(annotations)

if __name__ == '__main__':
    test_live()
