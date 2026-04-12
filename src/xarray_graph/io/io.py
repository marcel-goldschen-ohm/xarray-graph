

from __future__ import annotations
import os
from pathlib import Path
import xarray as xr
import zarr
from xarray_graph.utils import xarray_utils


supported_filetypes = [
    'Zarr Zip',
    'Zarr Directory',
    'NetCDF',
    'HDF5',
    'WinWCP',
    'HEKA',
    # 'Axon ABF'
]


def open_datatree(filepath: str | os.PathLike, filetype: str = None, engine: str = None, chunks = None) -> xr.DataTree:
    filepath = Path(filepath)
        
    # read datatree from filesystem
    if filepath.is_dir():
        # Zaar directory
        with zarr.storage.LocalStore(filepath, mode='r') as store:
            datatree = xr.open_datatree(store, engine='zarr', chunks=chunks)
    elif (filetype == 'Zarr Zip') or (filepath.suffix in ['.zip', '.ZIP']):
        # Zaar zip file
        with zarr.storage.ZipStore(filepath, mode='r') as store:
            datatree = xr.open_datatree(store, engine='zarr', chunks=chunks)
    elif (filetype == 'WinWCP') or (filepath.suffix in ['.wcp', '.WCP']):
        pass
    elif (filetype == 'HEKA'):
        pass
    elif (filetype == 'Axon ABF') or (filepath.suffix in ['.abf', '.ABF']):
        pass
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
        # Zaar directory
        with zarr.storage.LocalStore(filepath, mode='w') as store:
            datatree.to_zarr(store)
    elif (filetype == 'Zarr Zip') or ((filetype is None) and (filepath.suffix in ['.zip', '.ZIP'])):
        # Zaar zip file
        with zarr.storage.ZipStore(filepath, mode='w') as store:
            datatree.to_zarr(store)
    elif engine:
        # netCDF/HDF5
        datatree.to_netcdf(filepath, mode='w', engine=engine)
    else:
        # netCDF/HDF5
        datatree.to_netcdf(filepath, mode='w')