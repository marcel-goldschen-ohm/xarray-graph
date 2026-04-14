

from __future__ import annotations
import os
from pathlib import Path
import xarray as xr
import zarr
from xarray_graph.utils import xarray_utils
from xarray_graph.io.labchart import read_adicht_mat
from xarray_graph.io.heka import read_heka
from xarray_graph.io.winwcp import read_winwcp


# supported_filetypes = [
#     'Zarr Zip',
#     'Zarr Directory',
#     'NetCDF',
#     'HDF5',
#     'WinWCP',
#     'HEKA',
#     # 'Axon ABF'
#     'LabChart MATLAB TEVC'
# ]


def open_datatree(filepath: str | os.PathLike, filetype: str = None, engine: str = None, chunks = None) -> xr.DataTree:
    filepath = Path(filepath)
        
    # read datatree from filesystem
    if filepath.is_dir():
        # Zarr Directory
        with zarr.storage.LocalStore(filepath, mode='r') as store:
            datatree = xr.open_datatree(store, engine='zarr', chunks=chunks)
    elif (filetype == 'Zarr Zip') or (filepath.suffix in ['.zip', '.ZIP']):
        with zarr.storage.ZipStore(filepath, mode='r') as store:
            datatree = xr.open_datatree(store, engine='zarr', chunks=chunks)
    elif (filetype == 'WinWCP') or (filepath.suffix in ['.wcp', '.WCP']):
        return read_winwcp(filepath)
    elif (filetype == 'HEKA'):
        return read_heka(filepath)
    elif (filetype == 'Axon ABF') or (filepath.suffix in ['.abf', '.ABF']):
        pass # TODO
    elif (filetype == 'LabChart MATLAB TEVC'):
        return read_adicht_mat(filepath)
    elif engine:
        # netCDF/HDF5
        datatree: xr.DataTree = xr.open_datatree(filepath, engine=engine, chunks=chunks)
    else:
        # netCDF/HDF5
        datatree: xr.DataTree = xr.open_datatree(filepath, chunks=chunks)
        
    datatree = xarray_utils.recover_post_deserialization(datatree)
    
    return datatree


def save_datatree(datatree: xr.DataTree, filepath: str | os.PathLike, filetype: str = None, engine: str = None) -> None:
    filepath = Path(filepath)

    datatree = xarray_utils.prepare_for_serialization(datatree)

    # write datatree to filesystem
    if (filetype == 'Zarr Directory') or ((filetype is None) and (filepath.is_dir() or filepath.suffix in ['', '.zarr'])):
        with zarr.storage.LocalStore(filepath, mode='w') as store:
            datatree.to_zarr(store)
    elif (filetype == 'Zarr Zip') or ((filetype is None) and (filepath.suffix in ['.zip', '.ZIP'])):
        with zarr.storage.ZipStore(filepath, mode='w') as store:
            datatree.to_zarr(store)
    elif engine:
        # NetCDF/HDF5
        datatree.to_netcdf(filepath, mode='w', engine=engine)
    else:
        # NetCDF/HDF5
        datatree.to_netcdf(filepath, mode='w')


if __name__ == '__main__':
    dt = open_datatree('examples/HEKA.dat', filetype='HEKA')
    print(dt)