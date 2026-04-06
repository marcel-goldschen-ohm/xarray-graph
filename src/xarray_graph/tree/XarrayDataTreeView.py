""" Tree view for a Xarray.DataTree with context menu and mouse wheel expand/collapse.

Uses XarrayDataTreeModel for the model interface.

TODO:
- open 1d or 2d array in table? editable? slice selection for 3d or higher dim?
- merge items?
"""

from __future__ import annotations
from copy import deepcopy
import xarray as xr
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import qtawesome as qta
from xarray_graph.utils import xarray_utils
from xarray_graph.tree import AbstractTreeItem, TreeView, XarrayDataTreeItem, XarrayDataTreeModel, KeyValueTreeModel, KeyValueTreeView


class XarrayDataTreeView(TreeView):

    finishedEditingAttrs = Signal(XarrayDataTreeItem)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        # icons
        self._node_icon: QIcon = qta.icon('ph.folder-thin')
        self._data_var_icon: QIcon = qta.icon('ph.cube-thin')
        self._coord_icon: QIcon = qta.icon('ph.list-numbers-thin')
        self._index_coord_icon: QIcon = qta.icon('ph.asterisk-thin')
        self._unknown_icon: QIcon = qta.icon('fa6s.question')

        # self._info_shortcut = QShortcut(QKeySequence.StandardKey.Italic, self)
        # self._info_shortcut.activated.connect(lambda: self.infoDialog())

        # actions
        self._showDataVarsAction = QAction(
            text = 'Show Variables',
            icon = self._data_var_icon,
            iconVisibleInMenu=True,
            checkable = True,
            checked = True,
            toolTip = 'Show/hide data_vars in the tree view.',
            triggered = lambda checked: self._updateModelFromViewOptions()
        )

        self._showCoordsAction = QAction(
            text = 'Show Coordinates',
            icon = self._coord_icon,
            iconVisibleInMenu=True,
            checkable = True,
            checked = False,
            toolTip = 'Show/hide coords in the tree view.',
            triggered = lambda checked: self._updateModelFromViewOptions()
        )

        self._showInheritedCoordsAction = QAction(
            text = 'Show Inherited Coordinates',
            icon = self._coord_icon,
            iconVisibleInMenu=True,
            checkable = True,
            checked = False,
            toolTip = 'Show/hide inherited coords in the tree view.',
            triggered = lambda checked: self._updateModelFromViewOptions()
        )

        self._showDetailsColumnAction = QAction(
            text = 'Show Details Column',
            icon = qta.icon('fa6s.info'),
            iconVisibleInMenu=True,
            checkable = True,
            checked = False,
            toolTip = 'Show details column in the tree view. Uncheck to hide column.',
            triggered = lambda checked: self._updateModelFromViewOptions()
        )
    
    def setModel(self, model: XarrayDataTreeModel, updateViewOptionsFromModel: bool = True) -> None:
        super().setModel(model)
        if updateViewOptionsFromModel:
            self._updateViewOptionsFromModel()
        else:
            self._updateModelFromViewOptions()

    def _updateViewOptionsFromModel(self):
        model: XarrayDataTreeModel = self.model()
        
        self._showDataVarsAction.blockSignals(True)
        self._showDataVarsAction.setChecked(model.isDataVarsVisible())
        self._showDataVarsAction.blockSignals(False)
        
        self._showCoordsAction.blockSignals(True)
        self._showCoordsAction.setChecked(model.isCoordsVisible())
        self._showCoordsAction.blockSignals(False)
        
        self._showInheritedCoordsAction.blockSignals(True)
        self._showInheritedCoordsAction.setChecked(model.isInheritedCoordsVisible())
        self._showInheritedCoordsAction.blockSignals(False)
        
        self._showDetailsColumnAction.blockSignals(True)
        self._showDetailsColumnAction.setChecked(model.isDetailsColumnVisible())
        self._showDetailsColumnAction.blockSignals(False)

    def _updateModelFromViewOptions(self):
        model: XarrayDataTreeModel = self.model()
        self.storeViewState()
        model.setDataVarsVisible(self._showDataVarsAction.isChecked())
        model.setCoordsVisible(self._showCoordsAction.isChecked())
        model.setInheritedCoordsVisible(self._showInheritedCoordsAction.isChecked())
        model.setDetailsColumnVisible(self._showDetailsColumnAction.isChecked())
        self.restoreViewState()
    
    def treeData(self) -> xr.DataTree:
        model: XarrayDataTreeModel = self.model()
        return model.treeData()
    
    def setTreeData(self, data: xr.DataTree) -> None:
        model: XarrayDataTreeModel = self.model()
        if model is None:
            model = XarrayDataTreeModel()
            model.setTreeData(data)
            self.setModel(model)
        else:
            self.storeViewState()
            model.setTreeData(data)
            self.restoreViewState()
    
    def customContextMenu(self, index: QModelIndex = QModelIndex()) -> QMenu:
        model: XarrayDataTreeModel = self.model()
        menu = QMenu(self)

        # item that was clicked on
        item: XarrayDataTreeItem = model.itemFromIndex(index)
        if item.isNode():
            icon: QIcon = self._node_icon
        elif item.isDataVar():
            icon: QIcon = self._data_var_icon
        elif item.isCoord():
            icon: QIcon = self._coord_icon
        else:
            # should never happen
            icon: QIcon = self._unknown_icon
        
        # disabled action acts as a label for the item that was right-clicked on
        menu.addAction(QAction(
            text=f'{item.path()}:',
            parent=menu,
            icon=icon,
            iconVisibleInMenu=True,
            enabled=False
        ))
        # item-specific actions
        menu.addAction(QAction(
            text='Info',
            parent=menu,
            shortcut=QKeySequence('Ctrl+I'),
            shortcutVisibleInContextMenu=True,
            triggered=lambda checked, item=item: self.infoDialog(item)
        ))
        if not item.isInheritedCoord():
            menu.addAction(QAction(
                text='Attrs',
                parent=menu,
                triggered=lambda checked, item=item: self.attrsDialog(item)
            ))
            if item.isVariable():
                menu.addAction(QAction(
                    text='Data',
                    parent=menu,
                    enabled=False # TODO
                ))
            menu.addAction(QAction(
                text='Rename Dimensions',
                parent=menu,
                # triggered=lambda checked, item=item: self.renameDimensions(item),
                enabled=False # TODO
            ))
            if item.isNode():
                menu.addAction(QAction(
                    text='New Child Node',
                    parent=menu,
                    triggered=lambda checked, parent_item=item: self.insertNewChildNode(parent_item),
                ))
        
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
        
        # combine items
        if has_selection and len(self.selectedIndexes()) > 1:
            menu.addSeparator()
            menu.addAction(QAction(
                text='Merge Selection',
                parent=menu,
                # triggered=lambda checked: self.mergeSelection(),
                enabled=False # TODO
            ))
            menu.addAction(QAction(
                text='Concatenate Selection',
                parent=menu,
                # triggered=lambda checked: self.concatenateSelectedGroups(),
                enabled=False # TODO
            ))
        
        # expand/collapse
        menu.addSeparator()
        menu.addAction(self._expandAllAction)
        menu.addAction(self._collapseAllAction)
        if model.columnCount() > 1:
            menu.addAction(self._resizeAllColumnsToContentsAction)
            menu.addAction(self._showAllAction)

        # options
        menu.addSeparator()
        menu.addAction(self._showDataVarsAction)
        menu.addAction(self._showCoordsAction)
        menu.addAction(self._showInheritedCoordsAction)
        menu.addAction(self._showDetailsColumnAction)

        # refresh
        menu.addSeparator()
        menu.addAction(self._refreshAction)
        
        return menu
    
    def infoDialog(self, items: XarrayDataTreeItem | list[XarrayDataTreeItem] = None, font_size: int = None) -> None:
        if isinstance(items, XarrayDataTreeItem):
            item = items
            data = item.data
            title = item.path()
        elif items is None:
            items: list[XarrayDataTreeItem] = self.selectedItems()
            if not items:
                return
            # ensure items are in tree order
            items = AbstractTreeItem.orderedItems(items)
            data = [item.data for item in items]
            title = 'Selected'
        elif len(items) == 1:
            item = items[0]
            data = item.data
            title = item.path()
        else:
            data = [item.data for item in items]
            title = None
        infoDialog(data, parent=self, size=self.size(), pos=QPoint(0, 0), title=title, font_size=font_size)
        
    def attrsDialog(self, item: XarrayDataTreeItem) -> None:
        data = item.data
        title = item.path()
        status = attrsDialog(data, parent=self, size=self.size(), pos=QPoint(0, 0), title=title)
        if status == QDialog.DialogCode.Accepted:
            self.finishedEditingAttrs.emit(item)
        
    def insertNewChildNode(self, parent_item: XarrayDataTreeItem, row: int = None) -> None:
        if not parent_item.isNode():
            return
        model: XarrayDataTreeModel = self.model()
        if not self.model:
            return
        if row is None or row == -1:
            row = len(parent_item.children)
        new_node = xr.DataTree()
        new_node_item = XarrayDataTreeItem(new_node)
        model.insertItems([new_node_item], row, parent_item)
    
    # def renameDimensions(self, root_item: XarrayDataTreeItem) -> None:
    #     model: XarrayDataTreeModel = self.model()
    #     if not model:
    #         return
    #     if not root_item.is_group:
    #         root_item = root_item.parent
    #     root_group: xr.DataTree = root_item.data
    #     root_group: xr.DataTree = xarray_utils._branch_root(root_group)
    #     while root_item.parent and root_item.data is not root_group:
    #         root_item = root_item.parent
        
    #     dims: list[str] = []
    #     for group in root_group.subtree:
    #         for dim in list(group.dims):
    #             if dim not in dims:
    #                 dims.append(dim)
        
    #     dim_lineedits: dict[str, QLineEdit] = {}
    #     for dim in dims:
    #         dim_lineedits[dim] = QLineEdit()
    #         dim_lineedits[dim].setPlaceholderText(dim)
        
    #     dlg = QDialog(self)
    #     dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
    #     dlg.setWindowTitle('Rename Dimensions')
    #     vbox = QVBoxLayout(dlg)
    #     for dim in dims:
    #         vbox.addWidget(dim_lineedits[dim])
        
    #     buttons = QDialogButtonBox(standardButtons=QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    #     buttons.accepted.connect(dlg.accept)
    #     buttons.rejected.connect(dlg.reject)
    #     vbox.addWidget(buttons)

    #     if dlg.exec() != QDialog.DialogCode.Accepted:
    #         return
        
    #     renamed_dims = {}
    #     for dim in dims:
    #         new_dim = dim_lineedits[dim].text().strip()
    #         if new_dim and new_dim != dim:
    #             renamed_dims[dim] = new_dim
    #     if not renamed_dims:
    #         return
        
    #     xarray_utils.rename_dims(root_group, renamed_dims)
    #     self.refresh()
    
    # def renameVariables(self, root_item: XarrayDataTreeItem) -> None:
    #     model: XarrayDataTreeModel = self.model()
    #     if not model:
    #         return
    #     if not root_item.is_group:
    #         root_item = root_item.parent
    #     root_group: xr.DataTree = root_item.data
        
    #     var_names: list[str] = []
    #     for group in root_group.subtree:
    #         for name in group.variables:
    #             if name not in var_names:
    #                 var_names.append(name)
        
    #     lineedits: dict[str, QLineEdit] = {}
    #     for name in var_names:
    #         lineedits[name] = QLineEdit()
    #         lineedits[name].setPlaceholderText(name)
        
    #     dlg = QDialog(self)
    #     dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
    #     dlg.setWindowTitle('Rename Variables')
    #     vbox = QVBoxLayout(dlg)
    #     for name in var_names:
    #         vbox.addWidget(lineedits[name])
        
    #     buttons = QDialogButtonBox(standardButtons=QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    #     buttons.accepted.connect(dlg.accept)
    #     buttons.rejected.connect(dlg.reject)
    #     vbox.addWidget(buttons)

    #     if dlg.exec() != QDialog.DialogCode.Accepted:
    #         return
        
    #     var_renames = {}
    #     for name in var_names:
    #         new_name = lineedits[name].text().strip()
    #         if new_name and new_name != name:
    #             var_renames[name] = new_name
    #     if not var_renames:
    #         return
        
    #     xarray_utils.rename_vars(root_group, var_renames)
    #     self.refresh()
    
    # def mergeSelection(self) -> None:
    #     pass # TODO
    
    # def concatenateSelectedGroups(self, dim: str = None) -> None:
    #     model: XarrayDataTreeModel = self.model()
    #     if not model:
    #         return
    #     items: list[XarrayDataTreeItem] = [item for item in self.selectedItems() if item.is_group]
    #     if not items or len(items) < 2:
    #         return
    #     if dim is None:
    #         title = 'Concatenate'
    #         label = 'Concatenate along dim:'
    #         dim, ok = QInputDialog.getText(self, title, label)
    #         if not ok:
    #             return
    #         dim = dim.strip()
    #         if not dim:
    #             return
    #     try:
    #         datasets: list[xr.Dataset] = [item.data.to_dataset() for item in items]
    #         concatenated_dataset: xr.Dataset = xr.concat(datasets, dim)
    #         parent_item: XarrayDataTreeItem = items[0].parent
    #         parent_group: xr.DataTree = parent_item.data
    #         name = xarray_utils.unique_name('Concat', list(parent_group.keys()))
    #         parent_group[name] = concatenated_dataset
    #         self.refresh()
    #     except Exception as err:
    #         model.popupWarningDialog(str(err))
    
    def keyPressEvent(self, event: QKeyEvent):
        if (event.key() == Qt.Key.Key_I) and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            items: list[XarrayDataTreeItem] = self.selectedItems()
            if items:
                # ensure items are in tree order
                items = AbstractTreeItem.orderedItems(items)
                if len(items) == 1:
                    data = items[0].data
                    title = items[0].path()
                else:
                    data = [item.data for item in items]
                    title = 'Selected'
                xarray_utils.infoDialog(data, parent=self, size=self.size(), pos=QPoint(0, 0), title=title)
            return
        return super().keyPressEvent(event)


def makeDialog(parent: QWidget = None, size: QSize = None, pos: QPoint = None, title: str = None) -> QDialog:
    dlg = QDialog(parent)
    if size is not None:
        dlg.resize(size)
    if pos is not None:
        if parent:
            dlg.move(parent.mapToGlobal(pos))
        else:
            dlg.move(pos)
    if title is not None:
        dlg.setWindowTitle(title)
    return dlg


def infoDialog(data: xr.DataTree | xr.Dataset | xr.DataArray | list[xr.DataTree | xr.Dataset | xr.DataArray], parent: QWidget = None, size: QSize = None, pos: QPoint = None, title: str = None, font_size: int = None) -> int:
    text_edit = infoTextEdit(data, font_size=font_size)
    dlg = makeDialog(parent, size, pos, title)
    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(text_edit)
    return dlg.exec()


def infoTextEdit(data: xr.DataTree | xr.Dataset | xr.DataArray | list[xr.DataTree | xr.Dataset | xr.DataArray], text_edit_to_update: QTextEdit = None, font_size: int = None) -> QTextEdit:
    text_edit = text_edit_to_update
    if not isinstance(text_edit, QTextEdit):
        text_edit = QTextEdit()
        font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        if font_size is None:
            # font_size = QFont().pointSize()
            font_size = QFontDatabase.systemFont(QFontDatabase.SmallestReadableFont).pointSize() + 2
        font.setPointSize(font_size)
        text_edit.setFont(font)
    else:
        text_edit.clear()
        if font_size is not None:
            font = text_edit.font()
            font.setPointSize(font_size)
            text_edit.setFont(font)

    if isinstance(data, (xr.DataTree, xr.Dataset, xr.DataArray)):
        text_edit.setPlainText(str(data))
    elif isinstance(data, (list, tuple)):
        sep = False
        for obj in data:
            if sep:
                # TODO: check if this works on Windows (see https://stackoverflow.com/questions/76710833/how-do-i-add-a-full-width-horizontal-line-in-qtextedit)
                text_edit.insertHtml('<br><hr><br>')
            else:
                sep = True
            text_edit.insertPlainText(str(obj))

            # tc = self.result_text_box.textCursor()
            # # move the cursor to the end of the document
            # tc.movePosition(tc.End)
            # # insert an arbitrary QTextBlock that will inherit the previous format
            # tc.insertBlock()
            # # get the block format
            # fmt = tc.blockFormat()
            # # remove the horizontal ruler property from the block
            # fmt.clearProperty(fmt.BlockTrailingHorizontalRulerWidth)
            # # set (not merge!) the block format
            # tc.setBlockFormat(fmt)
            # # eventually, apply the cursor so that editing actually starts at the end
            # self.result_text_box.setTextCursor(tc)
    
    text_edit.setReadOnly(True)
    return text_edit


def attrsDialog(data: xr.DataTree | xr.Dataset | xr.DataArray, parent: QWidget = None, size: QSize = None, pos: QPoint = None, title: str = None) -> int:
    attrs_copy: dict = deepcopy(data.attrs)

    view = KeyValueTreeView()
    view.setAlternatingRowColors(True)
    view.setTreeData(attrs_copy)
    view.showAll()

    dlg = makeDialog(parent, size, pos, title)
    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(view)

    btns = QDialogButtonBox()
    btns.setStandardButtons(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)
    layout.addWidget(btns)
    
    status = dlg.exec()
    if status == QDialog.DialogCode.Accepted:
        data.attrs = attrs_copy
    return status


def test_live():
    app = QApplication()

    dt = xr.DataTree()
    dt['air_temperature'] = xr.tutorial.load_dataset('air_temperature')
    dt['air_temperature/twice air'] = dt['air_temperature/air'] * 2
    dt['air_temperature/inherits'] = xr.tutorial.load_dataset('air_temperature')
    dt['air_temperature/inherits/again'] = xr.tutorial.load_dataset('air_temperature')
    dt['child/grandchild/greatgrandchild'] = xr.DataTree()
    dt['child/grandchild/tiny'] = xr.tutorial.load_dataset('tiny')
    dt['child/grandchild/rasm'] = xr.tutorial.load_dataset('rasm')
    dt['rasm'] = xr.tutorial.load_dataset('rasm')
    dt['air_temperature_gradient'] = xr.tutorial.load_dataset('air_temperature_gradient')
    # print(dt)

    model = XarrayDataTreeModel()
    model.setDataVarsVisible(True)
    model.setCoordsVisible(True)
    model.setInheritedCoordsVisible(True)
    model.setDetailsColumnVisible(True)
    model.setTreeData(dt)

    view = XarrayDataTreeView()
    view.setModel(model)
    view.show()
    view.resize(800, 1000)
    view.showAll()
    view.move(50, 50)
    view.raise_()

    dt2 = dt.copy(deep=True)

    model2 = XarrayDataTreeModel()
    model2.setDataVarsVisible(True)
    model2.setCoordsVisible(True)
    model2.setInheritedCoordsVisible(True)
    model2.setDetailsColumnVisible(True)
    model2.setTreeData(dt2)

    view2 = XarrayDataTreeView()
    view2.setModel(model2)
    view2.show()
    view2.resize(800, 1000)
    view2.showAll()
    view2.move(900, 50)
    view2.raise_()

    app.exec()

    # print(dt)
    # print(dt2)


if __name__ == '__main__':
    test_live()
