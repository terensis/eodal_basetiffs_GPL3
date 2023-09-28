"""
Basic script to query, load and save out S2 images of a specified AOI using EOdal 
The images are saved as TIFFs in WGS84 format for processing in a web-framework

TODO: make this into a jupyter NB or an executable script later

GPL 3 license
25.09.2023
"""

import geopandas as gpd
import matplotlib.pyplot as plt
from datetime import datetime
from eodal.config import get_settings
from eodal.core.sensors.sentinel2 import Sentinel2  # native support for Sentinel2
from eodal.mapper.feature import Feature
from eodal.mapper.filter import Filter
from eodal.mapper.mapper import Mapper, MapperConfigs
from typing import List
from pathlib import Path


# -------------------------- User input ---------------------------
base_dir: Path = Path()
data_dir: Path = Path(base_dir.joinpath("data"))

# define time range
time_start: datetime = datetime(2023, 9, 1)  # year, month, day (incl.)
time_end: datetime = datetime(2023, 9, 28)  # year, month, day (incl.)

# Spatial Feature
data_dir = Path("data")
data_dir.mkdir(exist_ok=True)
# geom: Path = gpd.read_file(data_dir.joinpath("canton_sh.gpkg")).dissolve()
geom: Path = gpd.read_file(data_dir.joinpath("farm_maranhao.gpkg")).dissolve()

# define project name
# aoi_name = "SH"
aoi_name = 'FM'

# -----------------------------------------------------------------

# make out folder
out_dir = base_dir.joinpath(aoi_name)
out_dir.mkdir(exist_ok=True)

# Define settings, s.t. we can access the data from MS planetary computer
Settings = get_settings()
Settings.USE_STAC = True


# -------------------------- Collection -------------------------------
collection: str = "sentinel2-msi"

# ------------------------- Metadata Filters ---------------------------
metadata_filters: List[Filter] = [
    Filter("cloudy_pixel_percentage", "<", 25),
    Filter("processing_level", "==", "Level-2A"),
]

# -------- Define kwargs for the scene constructor ---------------------
scene_kwargs = {
    "scene_constructor": Sentinel2.from_safe,
    "scene_constructor_kwargs": {
        "band_selection": ["B02", "B03", "B04", "B08"],
        'read_scl': False},
}

# query the scenes available (no I/O of scenes, this only fetches metadata)
feature = Feature.from_geoseries(geom.geometry)
mapper_configs = MapperConfigs(
    collection=collection,
    time_start=time_start,
    time_end=time_end,
    feature=feature,
    metadata_filters=metadata_filters,
)

# create a Mapper instance
mapper = Mapper(mapper_configs)

# fetch metadata
mapper.query_scenes()

# write metadata df (for easier querying?)
metadata_df = mapper.metadata

# get actual data, this is the I/O step
mapper.load_scenes(scene_kwargs=scene_kwargs)

# store the data (type = SceneCollection) separately
scene_coll = mapper.data

# get timestamps
scene_ts = scene_coll.timestamps

# iterate over timestamps and write out TIFFs
for idx, timestamp in enumerate(scene_ts):
    print(f"processing {idx+1}/{len(scene_ts)}")

    # select scene
    scene = scene_coll[timestamp]

    # write out
    out_fname = f"{timestamp.split(' ')[0]}_{aoi_name}_WGS84.tiff"

    # plot RGB
    f, ax = plt.subplots(dpi=300)
    scene.plot_multiple_bands(['B04', 'B03', 'B02'], ax=ax)
    ax.set_title(f'{timestamp}')
    ax.axis('off')
    geom.to_crs(epsg=scene[scene.band_names[0]].geo_info.epsg).boundary.plot(ax=ax)
    f.savefig(out_dir.joinpath(out_fname.replace('.tiff', '.png')))
    plt.close(f)

    # NDVI
    if 'NDVI' not in scene.band_names:
        scene.calc_si('ndvi', inplace=True)

    # reproject to wgs84 for web mercator plotting
    # here could be a problem ...
    scene_wgs84 = scene.reproject(
        target_crs=4326)

    scene_wgs84.to_rasterio(
        band_selection=["red", "green", "blue", "ndvi"],
        fpath_raster=out_dir.joinpath(out_fname),
    )
