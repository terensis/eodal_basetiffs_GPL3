"""
Utility functions called in the eodal_viewer.main module.

Author: Lukas Valentin Graf (lukas.graf@terensis.io)
Date: 2023-10-06
License: GPLv3
"""

import numpy as np

from eodal.core.sensors import Sentinel2


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
