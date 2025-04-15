from xarray_graph.XarrayGraph import XarrayGraph
from qtpy.QtWidgets import QApplication, QMessageBox


def main():
    app = QApplication()
    xg = XarrayGraph()
    xg.setWindowTitle('xarray-graph')
    xg.show()

    # MacOS Magnet warning
    import platform
    if platform.system() == 'Darwin':
        QMessageBox.warning(xg, 'Magnet Warning', 'If you are using the window management software Magnet, please disable it for this app to work properly.')

    # load example data?
    answer = QMessageBox.question(xg, 'Example?', 'Load example data?')
    if answer == QMessageBox.StandardButton.Yes:
        try:
            load_example(xg)
        except Exception as err:
            QMessageBox.critical(xg, 'Failed to load example', str(err))
    
    app.exec()


def load_example(xg: XarrayGraph):
    import xarray as xr
    import requests
    import io

    url = 'https://raw.githubusercontent.com/marcel-goldschen-ohm/xarray-graph/main/examples/ERPdata.nc'
    req = requests.get(url, stream=True)
    if req.status_code != 200:
        raise ValueError(f'Failed to download example data: request status code = {req.status_code}')
    
    dt: xr.DataTree = xr.open_datatree(io.BytesIO(req.content), 'h5netcdf')
    xg.datatree = dt
    xg._datatree_view.expandAll()


if __name__ == '__main__':
    main()
