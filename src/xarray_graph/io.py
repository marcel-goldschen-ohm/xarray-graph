""" I/O functions for xarray datasets
"""


import numpy as np
import xarray as xr
from datatree import DataTree
# import zarr


def abf2xarray(filepath: str) -> DataTree:
    """ load Axon ABF file into xarray datatree
    """
    raise NotImplementedError


def heka2xarray(filepath: str) -> DataTree:
    """ load HEKA data file into xarray datatree

    HEKA format:
    ------------
    Group
        Series
            Sweep
                Trace (Data Series for Channel_A)
                Trace (Data Series for Channel_B)
    
    xarray datatree:
    ----------------
    /
        Group.i/
            Series.j/
                Sweep.k = xr.Dataset(
                    datavars = {
                        'Channel_A': xr.DataArray(data=bundle.data[...], dims=['time'], attrs={'units': trace.YUnit}),
                        'Channel_B': xr.DataArray(data=bundle.data[...], dims=['time'], attrs={'units': trace.YUnit}),
                    },
                    coords = {
                        'time': xr.DataArray(data=np.arange(# pts) * trace.XInterval + trace.XStart, dims=['time'], attrs={'units': trace.XUnit}),
                    },
                )
    
    If sweeps can be concatenated:
    /
        Group.i/
            Series.j = xr.Dataset(
                datavars = {
                    'Channel_A': xr.DataArray(data=bundle.data[...], dims=['sweep', 'time'], attrs={'units': trace.YUnit}),
                    'Channel_B': xr.DataArray(data=bundle.data[...], dims=['sweep', 'time'], attrs={'units': trace.YUnit}),
                },
                coords = {
                    'time': xr.DataArray(data=np.arange(# pts) * trace.XInterval + trace.XStart, dims=['time'], attrs={'units': trace.XUnit}),
                },
            )
    
    If series can be concatenated:
    /
        Group.i = xr.Dataset(
                datavars = {
                    'Channel_A': xr.DataArray(data=bundle.data[...], dims=['series', 'sweep', 'time'], attrs={'units': trace.YUnit}),
                    'Channel_B': xr.DataArray(data=bundle.data[...], dims=['series', 'sweep', 'time'], attrs={'units': trace.YUnit}),
                },
                coords = {
                    'time': xr.DataArray(data=np.arange(# pts) * trace.XInterval + trace.XStart, dims=['time'], attrs={'units': trace.XUnit}),
                },
            )
    """
    from xarray_graph import heka_reader
    bundle = heka_reader.Bundle(filepath)
    n_groups = len(bundle.pul)
    if n_groups == 0:
        return
    groups = {}
    group_names = [bundle.pul[i].Label for i in range(n_groups)]
    for group_index, group_name in enumerate(group_names):
        series = []
        n_series = len(bundle.pul[group_index])
        for series_index in range(n_series):
            sweeps = []
            n_sweeps = len(bundle.pul[group_index][series_index])
            for sweep_index in range(n_sweeps):
                n_traces = len(bundle.pul[group_index][series_index][sweep_index])
                ds = xr.Dataset()
                for trace_index in range(n_traces):
                    trace = bundle.pul[group_index][series_index][sweep_index][trace_index]
                    # print(trace)
                    y = bundle.data[(group_index, series_index, sweep_index, trace_index)]
                    # print(group_name, f'Series.{series_index}', f'Sweep.{sweep_index}', trace.Label, y.shape)
                    ds[trace.Label] = xr.DataArray(
                        y,
                        dims=['time'],
                        attrs={
                            'units': trace.YUnit,
                            # 'conversion_to_units': trace.DataScaler,
                            # 'offset_in_units': trace.YOffset,
                        },
                    )
                time = np.arange(len(y)) * trace.XInterval + trace.XStart
                ds.coords['time'] = xr.DataArray(
                    time,
                    dims=['time'],
                    attrs={
                        'units': trace.XUnit,
                    },
                )
                sweeps.append(ds)
            # merge sweep datasets if they all share the same channels and times
            if len(sweeps) == 1:
                sweeps = sweeps[0]
            else:
                try:
                    sweeps = xr.concat(sweeps, 'sweep')
                except:
                    pass
            series.append(sweeps)
        # merge series datasets if they all share the same sweeps, channels and times
        if len(series) == 1:
            series = series[0]
        else:
            try:
                series = xr.concat(series, 'series')
            except:
                pass
        groups[group_name] = series
    
    root_node = DataTree()
    for group_name, group in groups.items():
        if isinstance(group, xr.Dataset):
            group_node = DataTree(data=group, name=group_name, parent=root_node)
        elif isinstance(group, list):
            group_node = DataTree(name=group_name, parent=root_node)
            for series_index, series in enumerate(group):
                series_name = f'Series.{series_index}'
                if isinstance(series, xr.Dataset):
                    series_node = DataTree(data=series, name=series_name, parent=group_node)
                elif isinstance(group, list):
                    series_node = DataTree(name=series_name, parent=group_node)
                    for sweep_index, sweep in enumerate(series):
                        sweep_name = f'Sweep.{sweep_index}'
                        if isinstance(sweep, xr.Dataset):
                            sweep_node = DataTree(data=sweep, name=sweep_name, parent=series_node)
                        elif isinstance(group, list):
                            raise NotImplementedError
    return root_node


# def heka2zarr(path:str) -> zarr.hierarchy.Group:
#     """ load HEKA data file into zarr hierarchy in memory

#     HEKA format:
#     ------------
#     Group
#         Series
#             Sweep
#                 Trace (Data Series for Channel A)
#                 Trace (Data Series for Channel B)
    
#     zarr hierarchy:
#     ---------------
#     groupname
#         series.i
#             sweep.j
#                 channel.k
#                     trace.0
#                         ydata
#                             attrs['label']
#                             attrs['units']
#                             attrs['conversion_to_units']
#                             attrs['offset_in_units']
#                             attrs['sample_interval']
#                             attrs['sample_interval_units']
#     """
#     from xarray_graph import heka_reader
#     bundle = heka_reader.Bundle(path)
#     numHekaGroups = len(bundle.pul)
#     if numHekaGroups == 0:
#         return
#     root = zarr.group()
#     hekaGroupNames = [bundle.pul[i].Label for i in range(numHekaGroups)]
#     for hekaGroupIndex, hekaGroupName in enumerate(hekaGroupNames):
#         group = root.create_group(hekaGroupName)
#         numHekaSeries = len(bundle.pul[hekaGroupIndex])
#         for hekaSeriesIndex in range(numHekaSeries):
#             series = group.create_group(f'series.{hekaSeriesIndex}')
#             numHekaSweeps = len(bundle.pul[hekaGroupIndex][hekaSeriesIndex])
#             for hekaSweepIndex in range(numHekaSweeps):
#                 sweep = series.create_group(f'sweep.{hekaSweepIndex}')
#                 numHekaTraces = len(bundle.pul[hekaGroupIndex][hekaSeriesIndex][hekaSweepIndex])
#                 for hekaTraceIndex in range(numHekaTraces):
#                     channel = sweep.create_group(f'channel.{hekaTraceIndex}')
#                     trace = channel.create_group(f'trace.0')
#                     hekaTrace = bundle.pul[hekaGroupIndex][hekaSeriesIndex][hekaSweepIndex][hekaTraceIndex]
#                     # print(hekaTrace)
#                     y = bundle.data[(hekaGroupIndex, hekaSeriesIndex, hekaSweepIndex, hekaTraceIndex)]
#                     ydata = trace.create_dataset('ydata', data=y)
#                     ydata.attrs['label'] = hekaTrace.Label
#                     ydata.attrs['units'] = hekaTrace.YUnit
#                     ydata.attrs['sample_interval'] = hekaTrace.XInterval
#                     ydata.attrs['sample_interval_units'] = hekaTrace.XUnit
#     return root


if __name__ == '__main__':
    data = heka2xarray('/Users/marcel/GitHub/tmp/heka.dat')

    print(data[0][0])
