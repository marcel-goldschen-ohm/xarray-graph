import requests
import io
import xarray as xr
from qtpy.QtWidgets import QApplication, QMessageBox
from xarray_graph.XarrayGraph import XarrayGraph


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
            xg.datatree = load_example()
            xg._datatree_view.expandAll()
        except Exception as err:
            QMessageBox.critical(xg, 'Failed to load example', str(err))
    
    app.exec()


def load_example() -> xr.DataTree:
    url = 'https://raw.githubusercontent.com/marcel-goldschen-ohm/xarray-graph/main/examples/ERPdata.nc'
    req = requests.get(url, stream=True)
    if req.status_code != 200:
        raise ValueError(f'Failed to download example data: request status code = {req.status_code}')
    
    dt: xr.DataTree = xr.open_datatree(io.BytesIO(req.content), engine='h5netcdf')
    return dt


if __name__ == '__main__':
    main()
