
from pathlib import Path
import numpy as np
import scipy as sp
import xarray as xr

def read_adicht_mat(filepath: Path | str) -> xr.DataTree:
    """Read data from a LabChart .adicht file that has been converted to a MATLAB .mat file into an xarray.Dataset.
    """
    
    matdict = sp.io.loadmat(str(filepath), simplify_cells=True)
    # print(matdict)

    current = matdict['current']
    # if current.ndim == 1:
    #     current = current.reshape((1, -1))  # (sweep, time)
    current_units = matdict['current_units']

    voltage = matdict['voltage']
    # if voltage.ndim == 1:
    #     voltage = voltage.reshape((1, -1))  # (sweep, time)
    voltage_units = matdict['voltage_units']
    
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
        ds.attrs['ROIs'] = []
        for event in matdict['events']:
            time = event['time_sec']
            text = event['text']
            ds.attrs['ROIs'].append({
                'type': 'vregion',
                'position': {'time': [time, time]},
                'movable': False,
                'text': text,
            })
    
    if 'notes' in matdict:
        ds.attrs['notes'] = matdict['notes']
    
    return xr.DataTree(dataset=ds)


if __name__ == '__main__':
    filepath = 'your/path/to/file.mat'  # change this
    filepath = 'examples/GOLabChart.mat'
    dt = read_adicht_mat(filepath)
    print(dt)

    import matplotlib.pyplot as plt
    for i, name in enumerate(dt.data_vars):
        plt.subplot(len(dt.data_vars), 1, i + 1)
        dt[name].plot()
    plt.tight_layout()
    plt.show()