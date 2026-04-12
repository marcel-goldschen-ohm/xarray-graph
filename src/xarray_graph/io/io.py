

from __future__ import annotations
import os
from pathlib import Path
import xarray as xr
import zarr
from xarray_graph.utils import xarray_utils


def open_datatree(filepath: str | os.PathLike, engine: str = None, chunks = None) -> xr.DataTree:
    filepath = Path(filepath)
        
    # read datatree from filesystem
    if filepath.is_dir():
        # zaar directory
        with zarr.storage.LocalStore(filepath, mode='r') as store:
            datatree = xr.open_datatree(store, engine='zarr', chunks=chunks)
    elif filepath.suffix == '.zip':
        # zaar zip file
        with zarr.storage.ZipStore(filepath, mode='r') as store:
            datatree = xr.open_datatree(store, engine='zarr', chunks=chunks)
    elif engine:
        datatree: xr.DataTree = xr.open_datatree(filepath, engine=engine, chunks=chunks)
    else:
        datatree: xr.DataTree = xr.open_datatree(filepath, chunks=chunks)
        
    datatree = xarray_utils.recover_post_deserialization(datatree)
    
    return datatree


def save_datatree(datatree: xr.DataTree, filepath: str | os.PathLike, engine: str = None) -> None:
    filepath = Path(filepath)

    datatree = xarray_utils.prepare_for_serialization(datatree)

    # write datatree to filesystem
    if filepath.is_dir() or filepath.suffix in ['', '.zarr']:
        # zaar directory
        with zarr.storage.LocalStore(filepath, mode='w') as store:
            datatree.to_zarr(store)
    elif filepath.suffix == '.zip':
        # zaar zip file
        with zarr.storage.ZipStore(filepath, mode='w') as store:
            datatree.to_zarr(store)
    elif engine:
        datatree.to_netcdf(filepath, mode='w', engine=engine)
    else:
        datatree.to_netcdf(filepath, mode='w')