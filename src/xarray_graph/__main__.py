from xarray_graph.XarrayGraph import XarrayGraph
from qtpy.QtWidgets import QApplication, QMessageBox


def main():
    app = QApplication()
    ui = XarrayGraph()
    ui.setWindowTitle('xarray-graph')
    ui.show()

    # MacOS Magnet warning
    import platform
    if platform.system() == 'Darwin':
        QMessageBox.warning(ui, 'Magnet Warning', 'If you are using the window management software Magnet, please disable it for this app to work properly.')

    # load example data?
    answer = QMessageBox.question(ui, 'Example?', 'Load example data?')
    if answer == QMessageBox.StandardButton.Yes:
        load_example(ui)
    
    app.exec()


def load_example(ui: XarrayGraph):
    import numpy as np
    import xarray as xr
    from datatree import DataTree

    n = 100
    raw_ds = xr.Dataset(
        data_vars={
            'current': (['series', 'sweep', 'time'], np.random.rand(3, 10, n) * 1e-9, {'units': 'A'}),
            'voltage': (['series', 'sweep', 'time'], np.random.rand(3, 10, n) * 10000, {'units': 'V'}),
        },
        coords={
            'series': ('series', np.arange(3)),
            'sweep': ('sweep', np.arange(10)),
            'time': ('time', np.arange(n) * 0.01, {'units': 's'}),
        },
    )

    baselined_ds = xr.Dataset(
        data_vars={
            'current': (['series', 'sweep', 'time'], np.random.rand(3, 10, n) * 1e-9, {'units': 'A'}),
        },
        coords={
            'series': ('series', np.arange(3)),
            'sweep': ('sweep', np.arange(10)),
            'time': ('time', np.arange(n) * 0.01, {'units': 's'}),
        },
    )

    scaled_ds = xr.Dataset(
        data_vars={
            'current': (['series', 'sweep', 'time'], np.random.rand(1, 2, n) * 1e-9, {'units': 'A'}),
        },
        coords={
            'series': ('series', [1]),
            'sweep': ('sweep', [5,8]),
            'time': ('time', np.arange(n) * 0.01, {'units': 's'}),
        },
    )
    
    root_node = DataTree()
    raw_node = DataTree(name='raw', data=raw_ds, parent=root_node)
    baselined_node = DataTree(name='baselined', data=baselined_ds, parent=raw_node)
    scaled_node = DataTree(name='scaled', data=scaled_ds, parent=baselined_node)

    ui.data = root_node

    ui._show_control_panel_at(0)
    ui._data_treeview.expandAll()


if __name__ == '__main__':
    main()
