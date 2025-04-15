from pathlib import Path
import numpy as np
import xarray as xr
import warnings
try:
    from xarray_graph.io import heka_reader
except ImportError:
    warnings.warn("HEKA file i/o requires heka_reader")


def read_heka(filepath: Path | str) -> xr.DataTree:
    """ Read data from a HEKA file into an xarray.DataTree.

    HEKA format:
    ------------
    Group
        Series
            Sweep
                Trace (Data Series for Channel_A)
                Trace (Data Series for Channel_B)
    """

    if isinstance(filepath, str):
        filepath = Path(filepath)
    
    bundle = heka_reader.Bundle(str(filepath))

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
                sweep_ds = xr.Dataset()
                for trace_index in range(n_traces):
                    trace = bundle.pul[group_index][series_index][sweep_index][trace_index]
                    # print(trace)
                    y = bundle.data[(group_index, series_index, sweep_index, trace_index)]
                    # print(group_name, f'Series.{series_index}', f'Sweep.{sweep_index}', trace.Label, y.shape)
                    sweep_ds[trace.Label] = xr.DataArray(
                        y,
                        dims=['time'],
                        attrs={
                            'units': trace.YUnit,
                            # 'conversion_to_units': trace.DataScaler,
                            # 'offset_in_units': trace.YOffset,
                        },
                    )
                time = np.arange(len(y)) * trace.XInterval + trace.XStart
                sweep_ds.coords['time'] = xr.DataArray(
                    time,
                    dims=['time'],
                    attrs={
                        'units': trace.XUnit,
                    },
                )
                sweeps.append(sweep_ds)
            
            # merge sweep datasets if they all share the same channels and times
            if len(sweeps) == 1:
                sweeps = sweeps[0]
            else:
                try:
                    sweeps = xr.concat(sweeps, 'sweep')
                    sweeps = sweeps.assign_coords(sweep=xr.DataArray(
                        data=np.arange(1, sweeps.sizes['sweep'] + 1),
                        dims=['sweep'],
                    ))
                except:
                    pass
            
            series.append(sweeps)
        
        # merge series datasets if they all share the same sweeps, channels and times
        if len(series) == 1:
            series = series[0]
        else:
            try:
                series = xr.concat(series, 'series')
                series = series.assign_coords(series=xr.DataArray(
                    data=np.arange(1, series.sizes['series'] + 1),
                    dims=['series'],
                ))
            except:
                pass
        
        groups[group_name] = series
    
    # put everything into a DataTree
    dt = xr.DataTree()
    for group_name, group in groups.items():
        if isinstance(group, xr.Dataset):
            dt[group_name] = group
        elif isinstance(group, list):
            group_node = xr.DataTree()
            dt[group_name] = group_node
            for series_index, series in enumerate(group):
                series_name = f'Series.{series_index + 1}'
                if isinstance(series, xr.Dataset):
                    group_node[series_name] = series
                elif isinstance(series, list):
                    series_node = xr.DataTree()
                    group_node[series_name] = series_node
                    for sweep_index, sweep in enumerate(series):
                        sweep_name = f'Sweep.{sweep_index + 1}'
                        if isinstance(sweep, xr.Dataset):
                            series_node[sweep_name] = sweep
                        elif isinstance(sweep, list):
                            raise NotImplementedError
    return dt


if __name__ == '__main__':
    dt = read_heka('./examples/heka.dat')

    print(dt)
