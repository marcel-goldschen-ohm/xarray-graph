
import struct
from pathlib import Path
import numpy as np
import xarray as xr

def read_winwcp(filepath: Path | str) -> xr.DataTree:
    """Read data from a WinWCP file into an xarray.DataTree.
    
    Return a xarray.DataTree with a single dataset if all sweeps have the same sample interval.
    Otherwise return a tree with multiple leaf datasets (one per sweep).
    """

    if isinstance(filepath, str):
        filepath = Path(filepath)

    # read file contents as binary byte array
    with filepath.open(mode='rb') as file:
        file_bytes = file.read()

    # search for the number of channels in the header
    start = file_bytes.find(b'NC=') + 3
    stop = start + file_bytes[start:].find(b'\r\n')
    n_channels = int(file_bytes[start:stop])

    # read header
    n_header_bytes = (int((n_channels - 1) / 8) + 1) * 1024
    header_bytes = file_bytes[:n_header_bytes]
    header_lines = header_bytes.decode('utf-8').split('\r\n')
    header = {}
    for line in header_lines:
        try:
            k, v = line.split('=')
            header[k] = v
        except:
            pass
    
    # datetime
    date = header['CTIME'].split(' ')[0].strip()
    month, day, year = date.split('-')
    if len(year) == 2:
        year = f'20{year}'
    if len(month) == 1:
        month = f'0{month}'
    if len(day) == 1:
        day = f'0{day}'
    date = f'{year}-{month}-{day}'
    timestamp = header['RTIME'].split(' ')[-1].strip()
    datetime = f'{date} {timestamp}'

    # read records (i.e., sweeps)
    # Each record consists of an analysis block followed by a data block.
    n_sweeps = int(header['NR'])
    try:
        n_analysis_bytes = int(header['NBA']) * 512
    except:
        n_analysis_bytes = (int((n_channels - 1) / 8) + 1) * 1024
    n_data_bytes = int(header['NBD']) * 512
    try:
        n_samples = int(header['NP'])
    except:
        n_samples = int(n_data_bytes / 2 / n_channels)
    
    # store everything in a xarray.Dataset
    channel_names = [header[f'YN{i}'] for i in range(n_channels)]
    channel_units = [header[f'YU{i}'] for i in range(n_channels)]
    data = xr.Dataset(
        data_vars={
            channel_names[i]: xr.DataArray(
                data=np.zeros((n_sweeps, n_samples)),
                dims=['sweep', 'time'], 
                attrs={'units': channel_units[i]})
            for i in range(n_channels)
        },
        coords={
            'sweep': np.arange(1, n_sweeps + 1), # 1-based sweep index
            'time': xr.DataArray(
                data=np.arange(n_samples) * float(header['DT']), 
                dims=['time'], 
                attrs={'units': 's'}),
            'sweep_status': xr.DataArray(
                data=np.array(['ACCEPTED'] * n_sweeps, dtype=object), 
                dims=['sweep']),
            'sweep_type': xr.DataArray(
                data=np.array(['TEST'] * n_sweeps, dtype=object), 
                dims=['sweep']),
            'sweep_group': xr.DataArray(
                data=np.zeros(n_sweeps), 
                dims=['sweep']),
            'sweep_start_time': xr.DataArray(
                data=np.zeros(n_sweeps), 
                dims=['sweep'], 
                attrs={'units': 's'}),
            'sweep_sample_interval': xr.DataArray(
                data=np.zeros(n_sweeps), 
                dims=['sweep'], 
                attrs={'units': 's'}),
        },
        attrs={
            'date': date,
            'datetime': datetime,
            'winwcp_header': header,
        }
    )

    # for converting digitized signal to signal in physical units
    ADCmax = int(header['ADCMAX'])
    gain_per_channel = np.array([float(header[f'YG{i}']) for i in range(n_channels)]).reshape(n_channels, 1) * ADCmax

    for i in range(n_sweeps):
        n_offset_bytes = n_header_bytes + i * (n_analysis_bytes + n_data_bytes)
        analysis_bytes = file_bytes[n_offset_bytes:n_offset_bytes+n_analysis_bytes]
        data_bytes = file_bytes[n_offset_bytes+n_analysis_bytes:n_offset_bytes+n_analysis_bytes+n_data_bytes]

        data['sweep_status'][i] = analysis_bytes[:8].decode('utf-8')
        data['sweep_type'][i] = analysis_bytes[8:12].decode('utf-8')
        data['sweep_group'][i] = struct.unpack('f', analysis_bytes[12:16])[0]
        data['sweep_start_time'][i] = struct.unpack('f', analysis_bytes[16:20])[0]
        data['sweep_sample_interval'][i] = struct.unpack('f', analysis_bytes[20:24])[0]
        Vmax_per_channel = np.array(struct.unpack('f'*n_channels, analysis_bytes[24:24+4*n_channels])).reshape(n_channels, 1)

        # digitized sweep as 16-bit signed integers -> (channel, sample)
        n_pts = int(n_samples * n_channels)
        digitized_sweep = np.array(struct.unpack('h'*n_pts, data_bytes[:2*n_pts])).reshape(n_samples, n_channels).T
        
        # calibrated signal in physical units (channel, sample)
        conversion_factor = Vmax_per_channel / gain_per_channel
        calibrated_sweep = conversion_factor * digitized_sweep

        for j in range(n_channels):
            data[channel_names[j]][i] = calibrated_sweep[j]
    
    if np.unique(data['sweep_sample_interval']).size == 1:
        # all sweeps have the same sample interval (most likely case)
        return xr.DataTree(dataset=data)

    # Differing sweep sample intervals (least likely case).
    # Separate sweeps into individual xarray.DataArrays each with their own time coordinates.
    dt = xr.DataTree()
    for sweep in data['sweep'].values:
        ds: xr.Dataset = data.sel(sweep=[sweep])
        ds = ds.assign_coords(
            time=xr.DataArray(
                data=np.arange(n_samples) * ds['sweep_sample_interval'].values, 
                dims=['time'], 
                attrs=data['time'].attrs),
        )
        dt[f'Sweep{sweep}'] = ds
    return dt


if __name__ == '__main__':
    # for testing only

    filepath = 'your/path/to/file.wcp'  # change this
    dt = read_winwcp(filepath)
    print(dt)

    import matplotlib.pyplot as plt
    for i, name in enumerate(dt.data_vars):
        plt.subplot(len(dt.data_vars), 1, i + 1)
        dt[name].mean(dim='sweep').plot()
    plt.tight_layout()
    plt.show()
