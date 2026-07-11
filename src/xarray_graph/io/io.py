

from __future__ import annotations
import os
from pathlib import Path
import shutil
import xarray as xr
import zarr
from xarray_graph.utils import xarray_utils
from xarray_graph.io.labchart import read_adicht_mat
from xarray_graph.io.heka import read_heka
from xarray_graph.io.winwcp import read_winwcp
from xarray_graph.tree import KeyValueTreeModel


supported_filetypes = [
    'Zarr Directory',
    # 'Zarr Zip', <-- Currently unsupported due to zarr issues with zip files which are a huge headache that has yet to be stably resolved.
    'NetCDF/HDF5',
    'WinWCP',
    'HEKA',
    # 'Axon ABF'
    'LabChart MATLAB (GOlab TEVC)'
]


def open_datatree(filepath: str | os.PathLike, filetype: str = None, engine: str = None, chunks = None, consolidated: bool = False) -> xr.DataTree:
    filepath = Path(filepath)

    if (filetype == 'Zarr Directory') and not filepath.is_dir():
        raise ValueError(f"Filepath {filepath} is not a directory, but filetype is 'Zarr Directory'.")

    # read datatree from filesystem
    if filepath.is_dir():
        # Zarr Directory
        with zarr.storage.LocalStore(filepath) as store:
            datatree = xr.open_datatree(store, engine='zarr', chunks=chunks, consolidated=consolidated)
    # elif (filetype == 'Zarr Zip') or (filepath.suffix in ['.zip', '.ZIP']):
    #     # Zarr Zip
    #     # !! This should work, but zarr v3 has issues with zip files, so a workaround is to zip/unzip Zarr directories using OS commands)
    #     # with zarr.storage.ZipStore(filepath, mode='r') as store:
    #     #     datatree = xr.open_datatree(store, engine='zarr', chunks=chunks, consolidated=consolidated)
        
    #     # !! zarr v3 has issues with zip files, so a workaround is to zip/unzip Zarr directories using OS commands)
    #     # Assume .zip file is a zipped Zarr directory. Unzip it to a temporary directory, read it, then delete the temporary directory.
    #     tmp_dir = filepath.with_name('~' + filepath.stem + '_unzipped')
    #     shutil.unpack_archive(filepath, tmp_dir)
    #     with zarr.storage.LocalStore(tmp_dir) as store:
    #         datatree = xr.open_datatree(store, engine='zarr', chunks=chunks, consolidated=consolidated)
    #     shutil.rmtree(tmp_dir)
    elif (filetype == 'WinWCP') or (filepath.suffix in ['.wcp', '.WCP']):
        # WinWCP
        return read_winwcp(filepath)
    elif (filetype == 'HEKA'):
        # HEKA
        return read_heka(filepath)
    elif (filetype == 'Axon ABF') or (filepath.suffix in ['.abf', '.ABF']):
        # Axon ABF
        pass # TODO
    elif (filetype == 'LabChart MATLAB (GOlab TEVC)'):
        # LabChart MATLAB (GOlab TEVC)
        return read_adicht_mat(filepath)
    else:
        # netCDF/HDF5 [.nc, .h5, .hdf5]
        datatree: xr.DataTree = xr.open_datatree(filepath, engine=engine, chunks=chunks)
        # nested attrs not allowed in netCDF/HDF5, so we need to recover them after deserialization
        for key, value in datatree.attrs.items():
            if isinstance(value, str):
                datatree.attrs[key] = KeyValueTreeModel.str_to_value(value)
        
    datatree = xarray_utils.recover_post_deserialization(datatree)
    
    return datatree


def save_datatree(datatree: xr.DataTree, filepath: str | os.PathLike, filetype: str = None, engine: str = None, consolidated: bool = False) -> None:
    filepath = Path(filepath)

    datatree = xarray_utils.prepare_for_serialization(datatree)

    # write datatree to filesystem
    if (filetype == 'Zarr Directory') or ((filetype is None) and (filepath.is_dir() or filepath.suffix in ['', '.zarr'])):
        # Zarr Directory
        with zarr.storage.LocalStore(filepath) as store:
            datatree.to_zarr(store, mode='w', consolidated=consolidated)
    # elif (filetype == 'Zarr Zip') or ((filetype is None) and (filepath.suffix in ['.zip', '.ZIP'])):
    #     # Zarr Zip
    #     # !! This should work, but zarr v3 has issues with zip files, so a workaround is to zip/unzip Zarr directories using OS commands)
    #     # with zarr.storage.ZipStore(filepath, mode='w') as store:
    #     #     datatree.to_zarr(store, mode='w', consolidated=consolidated)
        
    #     # !! zarr v3 has issues with zip files, so a workaround is to zip/unzip Zarr directories using OS commands)
    #     # Write it to a temporary Zarr directory, zip it, then delete the temporary directory.
    #     tmp_dir = filepath.with_name('~' + filepath.stem + '_unzipped')
    #     with zarr.storage.LocalStore(tmp_dir) as store:
    #         datatree.to_zarr(store, mode='w', consolidated=consolidated)
    #     shutil.make_archive(filepath.with_suffix(''), "zip", tmp_dir)
    #     shutil.rmtree(tmp_dir)
    else:
        # NetCDF/HDF5
        if filepath.suffix not in ['.nc', '.h5', '.hdf5']:
            filepath = filepath.with_suffix('.h5')
        # nested attrs not allowed in netCDF/HDF5, so we need to convert them to strings before serialization
        for key, value in datatree.attrs.items():
            if isinstance(value, (list, tuple, dict)):
                datatree.attrs[key] = KeyValueTreeModel.value_to_str(value)
                # raise ValueError(f"Attribute '{key}' has value of type {type(value)}, which is not supported by NetCDF/HDF5. For non-flat attributes, consider using Zarr.")
        datatree.to_netcdf(filepath, mode='w', engine=engine)


def test():
    dt = open_datatree('examples/LabChartTEVC.mat', filetype='LabChart MATLAB (GOlab TEVC)')
    print(dt)

    # save_datatree(dt, 'examples/LabChartTEVC.zarr', filetype='Zarr Directory')
    # dt2 = open_datatree('examples/LabChartTEVC.zarr', filetype='Zarr Directory')
    # print(dt2)

    # save_datatree(dt, 'examples/LabChartTEVC.zarr.zip', filetype='Zarr Zip')
    # dt2 = open_datatree('examples/LabChartTEVC.zarr.zip', filetype='Zarr Zip')
    # print(dt2)

    # dt.attrs['_XG_ROI'] = 'ROIs'
    save_datatree(dt, 'examples/LabChartTEVC.h5', filetype='HDF5')
    dt2 = open_datatree('examples/LabChartTEVC.h5', filetype='HDF5')
    print(dt2)


if __name__ == '__main__':
    test()