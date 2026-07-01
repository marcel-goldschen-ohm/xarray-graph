import xarray as xr
from qtpy.QtWidgets import QApplication, QMessageBox
from xarray_graph.apps import XarrayDataTreeViewer, XarrayGraph


def xtree():
    app = QApplication()
    app.setQuitOnLastWindowClosed(False)
    ui = XarrayDataTreeViewer.new()
    ui.setWindowTitle('xarray-tree')
    ui.show()
    # ui.raise_()
    show_warnings()
    load_datatree(ui, 'https://raw.githubusercontent.com/marcel-goldschen-ohm/xarray-graph/main/examples/ERPdata.nc', ask=True)
    app.exec()


def xgraph():
    app = QApplication()
    app.setQuitOnLastWindowClosed(False)
    ui = XarrayGraph.new()
    ui.setWindowTitle('xarray-graph')
    ui.show()
    # ui.raise_()
    show_warnings()
    load_datatree(ui, 'https://raw.githubusercontent.com/marcel-goldschen-ohm/xarray-graph/main/examples/ERPdata.nc', ask=True)
    app.exec()


def show_warnings() -> None:
    import platform
    if platform.system() == 'Darwin':
        QMessageBox.warning(None, 'Magnet Warning', 'If you are using the window management software Magnet, please disable it for this app to work properly.')


def load_datatree(ui: XarrayDataTreeViewer, url: str = 'https://raw.githubusercontent.com/marcel-goldschen-ohm/xarray-graph/main/examples/ERPdata.nc', ask: bool = True) -> None:
    import requests, io

    if ask:
        answer = QMessageBox.question(ui, 'Example?', 'Load example data?')
    if (ask == False) or (answer == QMessageBox.StandardButton.Yes):
        try:
            req = requests.get(url, stream=True)
            if req.status_code != 200:
                raise ValueError(f'Failed to download example data: request status code = {req.status_code}')
            dt: xr.DataTree = xr.open_datatree(io.BytesIO(req.content), engine='h5netcdf')
            ui.setDatatree(dt)
            ui._datatree_view.showAll()
        except Exception as err:
            QMessageBox.critical(ui, 'Failed to load example', str(err))


if __name__ == '__main__':
    # xtree()
    xgraph()
