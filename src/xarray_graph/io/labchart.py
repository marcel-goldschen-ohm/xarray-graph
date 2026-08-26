
from pathlib import Path
import numpy as np
import xarray as xr


def read_adicht_mat(filepath: Path | str) -> xr.DataTree:
    """Read data from a LabChart .adicht file that has been converted to a MATLAB .mat file into an xarray.Dataset.

    !! This loader is specific for TEVC recordings.
    """
    # Import within function to avoid error due to circular dependency
    # as XarrayGraph also imports this function.
    # Putting the import within the function delays this import until use,
    # which means XarrayGraph will already have been imported.
    from xarray_graph.apps.XarrayGraph import ROI_KEY, NOTES_KEY
    
    from scipy.io import loadmat
    matdict = loadmat(str(filepath), simplify_cells=True)
    # print(matdict)

    current: np.ndarray = matdict['current']
    current_units: str = matdict['current_units']

    voltage: np.ndarray = matdict['voltage']
    voltage_units: str = matdict['voltage_units']
    
    time = np.arange(current.shape[-1]) * matdict['time_interval_sec']
    time_units = 's'

    ds = xr.Dataset(
        data_vars={
            'Im': xr.DataArray(data=current, dims=['time'], attrs={'units': current_units}),
            'Vm': xr.DataArray(data=voltage, dims=['time'], attrs={'units': voltage_units}),
        },
        coords={
            'time': xr.DataArray(data=time, dims=['time'], attrs={'units': time_units}),
        },
    )

    if 'events' in matdict and matdict['events']:
        rois: list[dict] = []
        for event in matdict['events']:
            time = event['time_sec']
            text = event['text']
            rois.append({
                'type': 'region',
                'position': {'time': time},
                'movable': False,
                'text': text,
            })
        ds.attrs[ROI_KEY] = rois
    
    if 'notes' in matdict:
        ds.attrs[NOTES_KEY] = matdict['notes']
    
    return xr.DataTree(dataset=ds)


if __name__ == '__main__':
    filepath = 'examples/LabChartTEVC.mat'
    dt = read_adicht_mat(filepath)
    print(dt)

    # import matplotlib.pyplot as plt
    # for i, name in enumerate(dt.data_vars):
    #     plt.subplot(len(dt.data_vars), 1, i + 1)
    #     dt[name].plot()
    # plt.tight_layout()
    # plt.show()