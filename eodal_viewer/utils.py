"""
Utility functions called in the eodal_viewer.main module.

Author: Lukas Valentin Graf (lukas.graf@terensis.io)
Date: 2023-10-06
License: GPLv3
"""

import eodal
import numpy as np
import yaml

from datetime import datetime
from eodal.core.band import Band
from eodal.core.sensors import Sentinel2
from pathlib import Path


class SceneProcessedException(Exception):
    pass


def get_latest_scene(output_dir) -> datetime:
    """
    Get the timestamp of the latest scene from a
    file called `latest_scene`. If this file does
    not exist use the default date

    :param output_dir:
        directory where scenes are stored (in sub-directories)
    """
    fpath_latest_scene = output_dir.joinpath('latest_scene')
    if fpath_latest_scene.exists():
        with open(output_dir.joinpath('latest_scene'), 'r') as f:
            timestamp_raw = f.read()
        timestamp_raw = timestamp_raw.replace('\n', '')
        timestamp = datetime.strptime(timestamp_raw, '%Y-%m-%d')
    else:
        timestamp = datetime(2016, 12, 31)
    return timestamp


def indicate_complete(output_dir_scene: Path) -> None:
    """
    Indicate that a scene was extracted and post-
    processed complete by writing a file named
    "complete" to the scene sub-directory.

    :param output_dir_scene:
        output directory of the scene.
    """
    fpath_complete = output_dir_scene.joinpath(
        f'complete.txt'
    )
    with open(fpath_complete, 'w') as f:
        f.write('complete')


def make_output_dir_scene(
    output_dir: Path,
    timestamp: datetime
) -> Path:
    """
    Make an output directory for a scene. The output directory
    is name by the sensing date of the scene.

    :param output_dir:
        directory where to create the scene output sub-directory
    :param timestamp:
        sensing time of the scene. Used for the naming of the
        output directory.
    """
    output_dir_scene = output_dir.joinpath(f'{timestamp.date()}')
    # make sure not to process an existing dataset again
    if output_dir_scene.exists() and output_dir_scene.joinpath('complete'):
        raise SceneProcessedException(
            f'{output_dir_scene} already processed -> skipping')
    output_dir_scene.mkdir()
    return output_dir_scene


def preprocess_sentinel2_scenes(
    ds: Sentinel2,
    target_resolution: int = 10,
) -> Sentinel2:
    """
    Resample Sentinel-2 scenes and mask clouds, shadows, and snow
    based on the Scene Classification Layer (SCL).

    :param ds:
        Sentinel-2 scene.
    :param target_resolution:
        spatial target resolution to resample all bands to.
        Default: 10 m.
    :returns:
        resampled, cloud-masked Sentinel-2 scene.
    """
    # resample scene
    ds.resample(inplace=True, target_resolution=target_resolution)
    return ds


def post_process_scene(
    s2_scene: Sentinel2
) -> Sentinel2:
    """
    Post-process a Sentinel-2 scene.

    This means:
    - reprojection to EPSG:2056 (LV95)
    - calculation of the NDVI
    - generation of a binary cloud mask from the Scene
      Classification Layer (SCL)

    :param s2_scene:
        Sentinel-2 scene
    :returns:
        post-processed Sentinel-2 scene
    """
    # reprojection to EPSG:2056 (LV95)
    s2_scene.reproject(target_crs=2056, inplace=True)

    # calculate the NDVI
    s2_scene.calc_si('ndvi', inplace=True)

    # generate a binary cloud mask from the Scene Classification
    # Layer (SCL) that is part of the standard ESA product.
    # SCL classes that will be treated as clouds are:
    # - 3: cloud shadows
    # - 8: cloud medium probability
    # - 9: cloud high probability
    # Cirrus clouds (SCL class 10) are not treated as clouds
    # as cirrus clouds can be corrected by the Sen2Cor processor
    cloud_mask = np.isin(s2_scene['scl'].values, [3, 8, 9])
    # update cloud mask with the mask of the area of interest,
    # i.e., s2_scene['scl'].values.mask
    if s2_scene['scl'].is_masked_array:
        cloud_mask = np.logical_and(cloud_mask, ~s2_scene['scl'].values.mask)

    # cast to uint8.
    # 0 = no cloud or outside of the area of interest
    # 1 = cloud or cloud shadow
    cloud_mask = cloud_mask.astype(np.uint8)
    # add cloud mask to the scene
    s2_scene.add_band(
        band_constructor=Band,
        band_name='cloud_mask',
        band_alias='cloud_mask',
        values=cloud_mask,
        geo_info=s2_scene['B02'].geo_info
    )
    return s2_scene


def set_latest_scene(
        output_dir: Path,
        timestamp: datetime
) -> None:
    """
    Set the timestamp of the latest scene
    to a file called `latest_scene`.

    :param output_dir:
        directory where scenes are stored (in sub-directories)
    :param timestamp:
        time stamp of the latest scene
    """
    with open(output_dir.joinpath('latest_scene'), 'w+') as f:
        f.write(f'{timestamp.date()}')


def write_cloudy_pixel_percentage(
    s2_scene: Sentinel2,
    fpath_cloudy_pixel_percentage: Path
) -> None:
    """
    Write the percentage of cloudy pixels in a Sentinel-2 scene
    to disk.

    :param s2_scene:
        Sentinel-2 scene
    :param fpath_cloudy_pixel_percentage:
        path to the file where the cloudy pixel percentage
        should be written to
    """
    # calculate the percentage of cloudy pixels
    cloudy_pixel_percentage = s2_scene.get_cloudy_pixel_percentage(
            cloud_classes=[3, 8, 9]
        )

    # write the percentage of cloudy pixels to disk
    with open(fpath_cloudy_pixel_percentage, 'w') as f:
        f.write(f'{cloudy_pixel_percentage:.1f}')


def write_scene_metadata(
    s2_scene: Sentinel2,
    fpath_metadata: Path
) -> None:
    """
    Write scene metadata to disk in YAML format.

    :param s2_scene:
        Sentinel-2 scene
    :param fpath_metadata:
        path to the metadata file
    """
    metadata = {
        'product_uri': s2_scene.scene_properties.product_uri,
        'sensing_time': str(s2_scene.scene_properties.sensing_time),
        'processing_level': s2_scene.scene_properties.processing_level.value,
        'eodal_version': eodal.__version__
    }

    # save as YAML
    with open(fpath_metadata, 'w+') as f:
        yaml.dump(metadata, f, default_flow_style=False)
