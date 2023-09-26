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
time_start: datetime = datetime(2023, 6, 1)  # year, month, day (incl.)
time_end: datetime = datetime(2023, 9, 26)  # year, month, day (incl.)

# Spatial Feature
geom: Path = Path(data_dir.joinpath("Witzwil_BoundingBox_WGS84.geojson"))

# define project name
aoi_name = "WITZ"

# -----------------------------------------------------------------

# make out folder
out_dir = base_dir.joinpath(aoi_name)
out_dir.mkdir(exist_ok=True)

# Define settings, s.t. we can access the data from MS planetary computer
Settings = get_settings()
Settings.USE_STAC = True


# TODO: move all inputs not directly needed to a separate file
# -------------------------- Preprocessing ---------------------------
def preprocess_sentinel2_scenes(
    ds: Sentinel2,
    target_resolution: int,
) -> Sentinel2:
    """
    Resample Sentinel-2 scenes and mask clouds, shadows, and snow
    based on the Scene Classification Layer (SCL).

    NOTE:
        Depending on your needs, the pre-processing function can be
        fully customized using the full power of EOdal and its
        interfacing libraries!

    :param target_resolution:
        spatial target resolution to resample all bands to.
    :returns:
        resampled, cloud-masked Sentinel-2 scene.
    """
    # resample scene
    ds.resample(inplace=True, target_resolution=target_resolution)
    # Do not mask clouds
    # ds.mask_clouds_and_shadows(inplace=True)
    return ds


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
    "scene_constructor_kwargs": {"band_selection": ["B02", "B03", "B04", "B08"]},
    "scene_modifier": preprocess_sentinel2_scenes,  # our function from above
    "scene_modifier_kwargs": {"target_resolution": 10},
}

# query the scenes available (no I/O of scenes, this only fetches metadata)
feature = Feature.from_geoseries(gpd.read_file(geom).geometry)
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

    # reproject to wgs84 for web mercator plotting
    scene_wgs84 = scene.reproject(target_crs=4326)

    scene_wgs84.to_rasterio(
        band_selection=["red", "green", "blue"],
        fpath_raster=out_dir.joinpath(out_fname),
    )

    """# create naked png and write out
    fig_naked = scene_wgs84.plot_multiple_bands(
        ["red", "green", "blue"], figsize=(10, 10)
    )
    fig_naked.axes
    # axs = fig_naked.get_axes
    plt.axis("off")
    plt.title(None)
    plt.tight_layout()
    fig_naked.savefig(data_dir.joinpath(out_fname + ".png"))

    # save out naked tiff?
    fig_naked.savefig(data_dir.joinpath("test.tiff"))"""
