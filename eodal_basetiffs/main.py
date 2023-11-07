"""
Main module of the eodal_basetiffs application.

Author: Lukas Valentin Graf (lukas.graf@terensis.io)
Date: 2023-10-06
License: GPLv3
"""

import geopandas as gpd
import warnings

from datetime import datetime, timedelta
from eodal.core.sensors import Sentinel2
from eodal.mapper.filter import Filter
from eodal.mapper.feature import Feature
from eodal.mapper.mapper import Mapper, MapperConfigs
from eodal.config import get_settings
from pathlib import Path

from eodal_basetiffs.constants import (
    Constants,
    Sentinel2Constants,
    LandsatC2L1Constants,
    LandsatC2L2Constants
)
from eodal_basetiffs.utils import (
    get_latest_scene,
    indicate_complete,
    make_output_dir_scene,
    post_process_scene,
    scale_ndvi,
    set_latest_scene,
    SceneProcessedException,
    write_cloudy_pixel_percentage,
    write_scene_metadata
)


# setup logging and usage of STAC API for data access
settings = get_settings()
settings.USE_STAC = True
logger = settings.logger

# ignore warnings
warnings.filterwarnings('ignore')


def fetch_data(
    output_dir: Path,
    mapper_configs: MapperConfigs,
    constants: Constants,
    target_crs: int
) -> None:
    """
    Fetch satellite data for a given time period and geographic extent
    and apply post-processing steps to obtain RGB, FCIR, and NDVI images
    as well as a cloud mask. The data is stored as GeoTIFFs organized
    in sub-directories named by the time stamp of the scene.

    :param output_dir: output directory where to store the data
    :param mapper_configs: MapperConfigs object
    :param constants: Constants object containing the scene kwargs
    :param target_crs: target CRS for reprojection as EPSG code
    """
    # create the Mapper object
    mapper = Mapper(mapper_configs)
    # query metadata to identify available scenes
    mapper.query_scenes()
    # check if scenes are available
    if mapper.metadata.empty:
        # if there are no scenes we must fake the folder
        # structure to let the extraction script continue
        first_timestamp = mapper.mapper_configs.time_start
        last_timestamp = mapper.mapper_configs.time_end
        set_latest_scene(output_dir, timestamp=last_timestamp)
        logger.info(
            f'No data found {first_timestamp.date()} ' +
            f'and {last_timestamp.date()}')
        return

    # load the data. This is the actual download step
    mapper.load_scenes(scene_kwargs=constants.SCENE_KWARGS)

    # Loop over the scenes in the collection.
    # Each scene is stored in a separate sub-directory named by
    # the time stamp of the scene. For each scene, four files
    # are created and stored as GeoTIFFs:
    # - RGB image (red, green, blue; not for Landsat 1-4)
    # - cloud mask (binary)
    # - FCIR image (false color infrared, i.e., nir, red, green)
    # - NDVI image (normalized difference vegetation index)
    for timestamp, scene in mapper.data:
        # create the output directory
        try:
            output_dir_scene = make_output_dir_scene(
                output_dir=output_dir,
                timestamp=timestamp
            )
        except SceneProcessedException as e:
            logger.info(e)
            # increase the time stamp to the last processed scene
            # and continue
            set_latest_scene(output_dir, timestamp=timestamp)
            continue

        # post-process the scene
        # This means:
        # - reprojection to target CRS
        # - calculation of the NDVI
        # - generation of a binary cloud mask from the Scene
        try:
            scene = post_process_scene(scene, target_crs=target_crs)
        except Exception as e:
            logger.error(f'Error while post-processing scene: {e}')
            continue

        # save the RGB bands as GeoTIFF. This is not possible
        # for Landsat 1-4 as they do not have a blue band.
        if 'blue' in scene.band_names or 'blue' in scene.band_aliases:
            fpath_rgb = output_dir_scene.joinpath(f'{timestamp.date()}_rgb.tif')
            scene.to_rasterio(
                band_selection=['red', 'green', 'blue'],
                fpath_raster=fpath_rgb,
                as_cog=True
            )

        # save the cloud mask as GeoTIFF
        fpath_cloud_mask = output_dir_scene.joinpath(
            f'{timestamp.date()}_cloud_mask.tif'
        )
        scene.to_rasterio(
            band_selection=['cloud_mask'],
            fpath_raster=fpath_cloud_mask,
            as_cog=True
        )

        # save the FCIR bands as GeoTIFF
        fpath_fcir = output_dir_scene.joinpath(
            f'{timestamp.date()}_fcir.tif'
        )
        # the naming of the nir band is different for Landsat
        # and Sentinel-2
        if isinstance(scene, Sentinel2):
            band_selection = ['nir_1', 'red', 'green']
        elif isinstance(scene, Landsat):
            band_selection = ['nir08', 'red', 'green']
        scene.to_rasterio(
            band_selection=band_selection,
            fpath_raster=fpath_fcir,
            as_cog=True
        )

        # save the NDVI as GeoTIFF
        fpath_ndvi = output_dir_scene.joinpath(
            f'{timestamp.date()}_ndvi.tif'
        )
        # calculate the scaled NDVI
        scale_ndvi(scene)

        scene.to_rasterio(
            band_selection=['ndvi_scaled'],
            fpath_raster=fpath_ndvi,
            as_cog=True
        )

        # write the cloudy pixel percentage to disk
        fpath_cloudy_pixel_percentage = output_dir_scene.joinpath(
            f'{timestamp.date()}_cloudy_pixel_percentage.txt'
        )
        write_cloudy_pixel_percentage(
            scene,
            fpath_cloudy_pixel_percentage
        )

        # write the scene metadata to disk
        fpath_metadata = output_dir_scene.joinpath(
            f'{timestamp.date()}_metadata.yaml'
        )
        write_scene_metadata(scene, fpath_metadata)

        # write a file termed "complete" to disk to indicate
        # that the scene has been processed successfully
        set_latest_scene(output_dir, timestamp=timestamp)
        indicate_complete(output_dir_scene)

        logger.info(f'Processed scene {timestamp.date()}')


def monitor_folder(
    folder_to_monitor: Path,
    feature: Feature,
    constants: Constants = Sentinel2Constants,
    temporal_increment_days: int = 7,
    target_crs: int = 2056
) -> None:
    """
    Monitor a folder with satellite scenes and fetch new data
    automatically. This function is intended to be run as a
    cron job or similar on a regular basis. The function looks
    for the last processed scene and fetches all scenes that
    are newer than the last processed scene with a given temporal
    increment.

    The function also takes care of reprojection and post-processing
    of the satellite scenes. It can handle Sentinel-2 and Landsat.

    :param folder_to_monitor: folder to monitor with satellite scenes
    :param feature: Feature object of the area of interest
    :param constants: Constants object define how to fetch the data
    :param temporal_increment_days: temporal increment in days
    :param target_crs: target CRS for reprojection as EPSG code
    """
    # get the latest scene to determine the start date
    last_processed_scene = get_latest_scene(folder_to_monitor)
    time_start = last_processed_scene + timedelta(days=1)
    # the end time for the next query will be the time stamp of the
    # last processed scene plus the temporal increment
    time_end = time_start + timedelta(days=temporal_increment_days)

    # setup the Mapper
    mapper_configs = MapperConfigs(
        collection=constants.COLLECTION,
        time_start=time_start,
        time_end=time_end,
        metadata_filters=constants.METADATA_FILTERS,
        feature=feature
    )

    # fetch data
    try:
        fetch_data(
            folder_to_monitor,
            mapper_configs,
            target_crs=target_crs,
            constants=constants
        )
    except Exception as e:
        logger.error(f'Error while fetching data: {e}')
        return


def cli() -> None:
    """
    Command line interface for the eodal_basetiffs application.
    """
    # define the CLI arguments
    import argparse
    parser = argparse.ArgumentParser(
        description='Fetch satellite data and post-process it. Requires ' +
                    'a GeoPackage or Shapefile with the area of interest ' +
                    'as input. It fetches data from Sentinel-2 or Landsat ' +
                    'and stores the outputs (true-color RGB, false-color ' +
                    'FCIR, NDVI, and a cloud mask) as cloud optimized GeoTiffs.'
    )
    parser.add_argument(
        '-a', '--area-of-interest',
        type=str,
        help='path to the GeoPackage or Shapefile with the area of interest'
    )
    parser.add_argument(
        '-o', '--output-dir',
        type=str,
        help='path to the output directory where to store the data'
    )
    parser.add_argument(
        '-t', '--temporal-increment-days',
        type=int,
        default=7,
        help='temporal increment in days'
    )
    parser.add_argument(
        '-c', '--target-crs',
        type=int,
        default=2056,
        help='target CRS for reprojection as EPSG code'
    )
    parser.add_argument(
        '-p', '--platform',
        type=str,
        default='sentinel-2',
        choices=['sentinel-2', 'landsat-c2-l1', 'landsat-c2-l2'],
        help='platform to use for data acquisition'
    )

    # parse the CLI arguments
    args = parser.parse_args()

    # unpack the arguments and call the monitor_folder function
    # with the appropriate constants
    folder_to_monitor = Path(args.output_dir)
    folder_to_monitor.mkdir(exist_ok=True, parents=True)

    if args.platform == 'sentinel-2':
        constants = Sentinel2Constants
    elif args.platform == 'landsat-c2-l1':
        constants = LandsatC2L1Constants
    elif args.platform == 'landsat-c2-l2':
        constants = LandsatC2L2Constants
    else:
        raise ValueError(f'Platform {args.platform} not supported')

    # load the area of interest
    fpath_feature = Path(args.area_of_interest)
    if not fpath_feature.exists():
        raise FileNotFoundError(f'{fpath_feature} does not exist')
    feature = Feature.from_geoseries(gpd.read_file(fpath_feature).geometry.disolve())

    # call the monitor_folder function
    monitor_folder(
        folder_to_monitor=folder_to_monitor,
        feature=feature,
        constants=constants,
        temporal_increment_days=args.temporal_increment_days,
        target_crs=args.target_crs
    )


if __name__ == '__main__':
    cli()
