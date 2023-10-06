"""
Main script of the EODAL Viewer application.
"""

import eodal
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import warnings

from datetime import datetime, timedelta
from eodal.core.band import Band
from eodal.core.scene import SceneCollection
from eodal.core.sensors import Sentinel2
from eodal.mapper.filter import Filter
from eodal.mapper.feature import Feature
from eodal.mapper.mapper import Mapper, MapperConfigs
from eodal.config import get_settings
from pathlib import Path
from shapely.geometry import box

from eodal_viewer.utils import preprocess_sentinel2_scenes

# setup logging and usage of STAC API for data access
settings = get_settings()
settings.USE_STAC = True
logger = settings.logger

# global variables
COLLECTION = 'sentinel2-msi'
METADATA_FILTERS = [
    Filter('cloudy_pixel_percentage', '<', 80),
    Filter('processing_level', '==', 'Level-2A')
]
SCENE_KWARGS = {
    'scene_constructor': Sentinel2.from_safe,
    'scene_constructor_kwargs': {
        'band_selection': ['B02', 'B03', 'B04', 'B08'],
        'read_scl': True,
        'apply_scaling': False},
    'scene_modifier': preprocess_sentinel2_scenes
}

# ignore warnings
warnings.filterwarnings('ignore')


def fetch_data(
    time_start: datetime,
    time_end: datetime,
    output_dir: Path,
    mapper_configs: MapperConfigs
):
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
        logger.info('No scenes found')
        return

    # load the data. This is the actual download step
    mapper.load_scenes(scene_kwargs=SCENE_KWARGS)

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
        output_dir_scene = output_dir.joinpath(f'{timestamp.date()}')
        output_dir_scene.mkdir(parents=True, exist_ok=True)

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
        # To do so, scale the NDVI by 10000 and add 10000 to avoid
        # negative values so that the NDVI can be stored
        # as uint16 to save disk space
        ndvi_as_uint16 = (s2_scene['ndvi'] * 10000 + 10000).values.astype(np.uint16)
        # set scale and offset for the NDVI
        scale = 1 / 10000
        offset = -10000
        # create a new band object
        ndvi_band = Band(
            band_name='ndvi',
            band_alias='ndvi',
            values=ndvi_as_uint16,
            geo_info=s2_scene['ndvi'].geo_info,
            scale=scale,
            offset=offset,
            nodata=0
        )
        # write the NDVI to disk
        fpath_ndvi = output_dir_scene.joinpath(
            f'{timestamp.date()}_ndvi.tif'
        )
        ndvi_band.to_rasterio(fpath_raster=fpath_ndvi)

        # write the cloudy pixel percentage to disk
        fpath_cloudy_pixel_percentage = output_dir_scene.joinpath(
            f'{timestamp.date()}_cloudy_pixel_percentage.txt'
        )
        with open(fpath_cloudy_pixel_percentage, 'w') as f:
            f.write(f'{s2_scene.get_cloudy_pixel_percentage():.1f}')

        # write the scene metadata to disk
        fpath_metadata = output_dir_scene.joinpath(
            f'{timestamp.date()}_metadata.txt'
        )
        product_uri = s2_scene.scene_properties.product_uri
        sensing_time = s2_scene.scene_properties.sensing_time
        processing_level = s2_scene.scene_properties.processing_level
        creation_time = datetime.now()
        eodal_version = eodal.__version__
        with open(fpath_metadata, 'w') as f:
            f.write(f'product_uri: {product_uri}\n')
            f.write(f'sensing_time: {sensing_time}\n')
            f.write(f'processing_level: {processing_level}\n')
            f.write(f'creation_time: {creation_time}\n')
            f.write(f'eodal_version: {eodal_version}\n')

        # write a file termed "complete" to disk to indicate
        # that the scene has been processed successfully
        fpath_complete = output_dir_scene.joinpath(
            f'complete.txt'
        )
        with open(fpath_complete, 'w') as f:
            f.write('complete')

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
    # list all sub-directories (i.e., scenes) in the folder
    sub_dirs = sorted(folder_to_monitor.glob('*'))
    # exclude the sub-directories that do not contain a file
    # termed "complete.txt" and exclude the "log" sub-directory
    sub_dirs = [
        sub_dir.name for sub_dir in sub_dirs
        if sub_dir.joinpath('complete.txt').exists()
        and sub_dir.name != 'log'
    ]
    # get the last processed scene. The start time for the next query
    # will be the time stamp of the last processed scene plus 1 day
    last_processed_scene = datetime.strptime(sub_dirs[-1], '%Y-%m-%d')
    time_start = last_processed_scene + timedelta(days=1)
    # the end time for the next query will be the time stamp of the
    # last processed scene plus the temporal increment
    time_end = time_start + timedelta(days=temporal_increment_days)

    # setup the Mapper
    mapper_configs = MapperConfigs(
        collection=COLLECTION,
        time_start=time_start,
        time_end=time_end,
        metadata_filters=METADATA_FILTERS,
        feature=feature
    )

    # fetch data
    try:
        fetch_data(
            time_start,
            time_end,
            folder_to_monitor,
            mapper_configs
        )
    except Exception as e:
        logger.error(f'Error while fetching data: {e}')
        return


if __name__ == '__main__':

    # ---------- test setup ----------

    # define directory to monitor
    directory_to_monitor = Path('data')
    directory_to_monitor.mkdir(parents=True, exist_ok=True)

    # define area of interest
    # test region: canton of Schaffhausen
    fpath_aoi = Path('data/canton_sh.gpkg')

    # read the data and buffer it by 10km in LV95 (EPSG:2056)
    # projection
    aoi = gpd.read_file(fpath_aoi).dissolve().to_crs(epsg=2056).buffer(10000)
    feature = Feature.from_geoseries(canton_sh)

    monitor_folder(
        folder_to_monitor=directory_to_monitor,
        feature=feature
    )
