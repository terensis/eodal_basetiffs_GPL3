"""
Main script of the EODAL Viewer application.

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
    
from eodal_viewer.utils import (
    get_latest_scene,
    indicate_complete,
    make_output_dir_scene,
    preprocess_sentinel2_scenes,
    post_process_scene,
    set_latest_scene,
    SceneProcessedException,
    write_cloudy_pixel_percentage,
    write_scene_metadata
)


# define constants
class Constants:
    # name of the collection to query (Sentinel-2)
    COLLECTION: str = 'sentinel2-msi'

    # filters to apply to the metadata
    # - only scenes with less than 80% cloudy pixels
    # - only scenes with processing level 'Level-2A'
    METADATA_FILTERS: list[Filter] = [
        Filter('cloudy_pixel_percentage', '<', 80),
        Filter('processing_level', '==', 'Level-2A')
    ]

    # kwargs for the scene constructor
    # - scene_constructor: constructor of the scene class
    # - scene_constructor_kwargs: kwargs for the scene constructor
    # - scene_modifier: function to modify the scene after loading
    SCENE_KWARGS: dict = {
        'scene_constructor': Sentinel2.from_safe,
        'scene_constructor_kwargs': {
            'band_selection': ['B02', 'B03', 'B04', 'B08'],
            'read_scl': True,
            'apply_scaling': False},
        'scene_modifier': preprocess_sentinel2_scenes
    }

    # start date of the time period to query if no time period
    # is specified
    START_DATE: datetime = datetime(2017, 1, 1)


# setup logging and usage of STAC API for data access
settings = get_settings()
settings.USE_STAC = True
logger = settings.logger

# ignore warnings
warnings.filterwarnings('ignore')


def fetch_data(
    output_dir: Path,
    mapper_configs: MapperConfigs
) -> None:
    """
    Fetch Sentinel-2 data for a given time period and geographic extent
    and apply post-processing steps to obtain RGB, FCIR, and NDVI images
    as well as a cloud mask. The data is stored as GeoTIFFs organized
    in sub-directories named by the time stamp of the scene.

    :param time_start: start of the time period
    :param time_end: end of the time period
    :param output_dir: output directory
    :param mapper_configs: MapperConfigs object
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
    mapper.load_scenes(scene_kwargs=Constants.SCENE_KWARGS)

    # Loop over the scenes in the collection.
    # Each scene is stored in a separate sub-directory named by
    # the time stamp of the scene. For each scene, four files
    # are created and stored as GeoTIFFs:
    # - RGB image (red, green, blue)
    # - cloud mask (binary)
    # - FCIR image (false color infrared, i.e., nir, red, green)
    # - NDVI image (normalized difference vegetation index)
    for timestamp, s2_scene in mapper.data:
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
        # - reprojection to EPSG:2056 (LV95)
        # - calculation of the NDVI
        # - generation of a binary cloud mask from the Scene
        try:
            s2_scene = post_process_scene(s2_scene)
        except Exception as e:
            logger.error(f'Error while post-processing scene: {e}')
            continue

        # save the RGB bands as GeoTIFF
        fpath_rgb = output_dir_scene.joinpath(f'{timestamp.date()}_rgb.tif')
        s2_scene.to_rasterio(
            band_selection=['red', 'green', 'blue'],
            fpath_raster=fpath_rgb
        )

        # save the cloud mask as GeoTIFF
        fpath_cloud_mask = output_dir_scene.joinpath(
            f'{timestamp.date()}_cloud_mask.tif'
        )
        s2_scene.to_rasterio(
            band_selection=['cloud_mask'],
            fpath_raster=fpath_cloud_mask
        )

        # save the FCIR bands as GeoTIFF
        fpath_fcir = output_dir_scene.joinpath(
            f'{timestamp.date()}_fcir.tif'
        )
        s2_scene.to_rasterio(
            band_selection=['nir_1', 'red', 'green'],
            fpath_raster=fpath_fcir
        )

        # save the NDVI as GeoTIFF
        fpath_ndvi = output_dir_scene.joinpath(
            f'{timestamp.date()}_ndvi.tif'
        )
        s2_scene.to_rasterio(
            band_selection=['ndvi'],
            fpath_raster=fpath_ndvi
        )

        # write the cloudy pixel percentage to disk
        fpath_cloudy_pixel_percentage = output_dir_scene.joinpath(
            f'{timestamp.date()}_cloudy_pixel_percentage.txt'
        )
        write_cloudy_pixel_percentage(
            s2_scene,
            fpath_cloudy_pixel_percentage
        )

        # write the scene metadata to disk
        fpath_metadata = output_dir_scene.joinpath(
            f'{timestamp.date()}_metadata.yaml'
        )
        write_scene_metadata(s2_scene, fpath_metadata)

        # write a file termed "complete" to disk to indicate
        # that the scene has been processed successfully
        set_latest_scene(output_dir, timestamp=timestamp)
        indicate_complete(output_dir_scene)

        logger.info(f'Processed scene {timestamp.date()}')


def monitor_folder(
    folder_to_monitor: Path,
    feature: Feature,
    temporal_increment_days: int = 7
) -> None:
    """
    Monitor a folder with Sentinel-2 scenes and fetch new data
    automatically. This function is intended to be run as a
    cron job or similar on a regular basis. The function looks
    for the last processed scene and fetches all scenes that
    are newer than the last processed scene with a given temporal
    increment.

    :param folder_to_monitor: folder to monitor with Sentinel-2 scenes
    :param feature: Feature object of the area of interest
    :param temporal_increment_days: temporal increment in days
    """
    # get the latest scene to determine the start date
    last_processed_scene = get_latest_scene(folder_to_monitor)
    time_start = last_processed_scene + timedelta(days=1)
    # the end time for the next query will be the time stamp of the
    # last processed scene plus the temporal increment
    time_end = time_start + timedelta(days=temporal_increment_days)

    # setup the Mapper
    mapper_configs = MapperConfigs(
        collection=Constants.COLLECTION,
        time_start=time_start,
        time_end=time_end,
        metadata_filters=Constants.METADATA_FILTERS,
        feature=feature
    )

    # fetch data
    try:
        fetch_data(
            folder_to_monitor,
            mapper_configs
        )
    except Exception as e:
        logger.error(f'Error while fetching data: {e}')
        return


if __name__ == '__main__':

    # ---------- test setup ----------
    import os
    cwd = Path(__file__).parents[1].absolute()
    os.chdir(cwd)

    # define directory to monitor
    directory_to_monitor = Path('data')
    directory_to_monitor.mkdir(parents=True, exist_ok=True)

    # define area of interest
    # test region: canton of Schaffhausen
    fpath_aoi = cwd.joinpath('data/canton_sh.gpkg')

    # read the data and buffer it by 10km in LV95 (EPSG:2056)
    # projection
    aoi = gpd.read_file(fpath_aoi).dissolve().to_crs(epsg=2056).buffer(10000)
    feature = Feature.from_geoseries(aoi)

    monitor_folder(
        folder_to_monitor=directory_to_monitor,
        feature=feature
    )
