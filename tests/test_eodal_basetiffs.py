"""
Tests for `eodal_basetiffs`.

Copyright (C) 2023 Terensis

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

from __future__ import annotations

import pytest
import geopandas as gpd
import shutil
import yaml

from eodal.core.raster import RasterCollection
from eodal.mapper.feature import Feature
from pathlib import Path

from eodal_basetiffs.constants import (
    LandsatC2L1Constants,
    LandsatC2L2Constants,
    Sentinel2Constants)
from eodal_basetiffs.main import monitor_folder


@pytest.fixture
def get_data_dir() -> Path:
    return Path(__file__).parents[1].joinpath('data')


@pytest.fixture
def get_feature(get_data_dir) -> Feature:
    data_dir = get_data_dir
    fpath_feature = data_dir.joinpath('test_region.gpkg')
    feature = Feature.from_geoseries(
        gpd.read_file(fpath_feature).dissolve().geometry)
    return feature


def validate_rgb(fpath: Path) -> None:
    rc = RasterCollection.from_multi_band_raster(fpath)
    assert len(rc) == 3
    assert rc.band_names == ['red', 'green', 'blue']

    for band_name in rc.band_names:
        assert rc[band_name].scale == 0.0001
        assert rc[band_name].values.dtype == 'uint16'
        assert rc[band_name].nodata == 0
        assert rc[band_name].geo_info.epsg == 3857
        scaled = rc[band_name].scale_data()
        assert scaled.values.min() >= -0.1
        assert scaled.values.max() <= 1.6


def validate_rgb_landsat(fpath: Path) -> None:
    rc = RasterCollection.from_multi_band_raster(fpath)
    assert len(rc) == 3
    assert rc.band_names == ['red', 'green', 'blue']

    for band_name in rc.band_names:
        assert rc[band_name].scale == 1e-5
        assert rc[band_name].values.dtype == 'uint16'
        assert rc[band_name].nodata == 0
        assert rc[band_name].geo_info.epsg == 3857
        scaled = rc[band_name].scale_data()
        assert scaled.values.min() >= 0
        assert scaled.values.max() <= 1


def validate_fcir(fpath: Path) -> None:
    rc = RasterCollection.from_multi_band_raster(fpath)
    assert len(rc) == 3
    assert rc.band_names == ['nir_1', 'red', 'green']

    for band_name in rc.band_names:
        assert rc[band_name].scale == 0.0001
        assert rc[band_name].values.dtype == 'uint16'
        assert rc[band_name].nodata == 0
        assert rc[band_name].geo_info.epsg == 3857
        scaled = rc[band_name].scale_data()
        assert scaled.values.min() >= -0.1
        assert scaled.values.max() <= 1.6


def validate_fcir_landsat_l2(fpath: Path) -> None:
    rc = RasterCollection.from_multi_band_raster(fpath)
    assert len(rc) == 3
    assert rc.band_names  == ['nir08', 'red', 'green']

    for band_name in rc.band_names:
        assert rc[band_name].scale == 1e-5
        assert rc[band_name].offset == 0
        assert rc[band_name].values.dtype == 'uint16'
        assert rc[band_name].nodata == 0
        assert rc[band_name].geo_info.epsg == 3857
        scaled = rc[band_name].scale_data()
        assert scaled.values.min() >= 0.
        assert scaled.values.max() <= 1.


def validate_fcir_landsat_l1(fpath: Path) -> None:
    rc = RasterCollection.from_multi_band_raster(fpath)
    assert len(rc) == 3
    assert rc.band_names == rc.band_names == ['nir08', 'red', 'green']

    # the level 1 is in 8bit!
    for band_name in rc.band_names:
        assert rc[band_name].scale == 1.0
        assert rc[band_name].values.dtype == 'uint8'
        assert rc[band_name].nodata == 0
        assert rc[band_name].geo_info.epsg == 3857
        scaled = rc[band_name].scale_data()
        assert scaled.values.min() >= 0
        assert scaled.values.max() <= 255


def validate_ndvi(fpath: Path) -> None:
    rc = RasterCollection.from_multi_band_raster(fpath)
    assert len(rc) == 1
    assert rc.band_names == ['ndvi']
    assert rc['ndvi'].values.dtype == 'uint16'
    assert rc['ndvi'].nodata == 21000
    assert rc['ndvi'].scale == 0.0001
    assert rc['ndvi'].offset == -1


def validate_yaml(fpath: Path) -> None:
    # check if the yaml file is valid and contains the
    # required fields
    with open(fpath, 'r') as f:
        yaml_dict = yaml.load(f, Loader=yaml.FullLoader)
        assert 'product_uri' in yaml_dict
        assert 'sensing_time' in yaml_dict
        assert 'eodal_version' in yaml_dict
        assert 'processing_level' in yaml_dict


def test_sentinel2(get_data_dir, get_feature):

    constants = Sentinel2Constants
    feature = get_feature
    output_dir = get_data_dir.joinpath('sentinel2')
    # ensure a "clean" start
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir()

    monitor_folder(
        constants=constants,
        feature=feature,
        folder_to_monitor=output_dir,
        temporal_increment_days=14
    )

    scene_dir = output_dir.joinpath('2017-01-07')
    # ensure all outputs exist
    assert scene_dir.exists()
    assert scene_dir.joinpath('2017-01-07_cloud_mask.tif').exists()
    assert scene_dir.joinpath('2017-01-07_ndvi.tif').exists()
    assert scene_dir.joinpath('2017-01-07_rgb.tif').exists()
    assert scene_dir.joinpath('2017-01-07_fcir.tif').exists()
    assert scene_dir.joinpath('complete.txt').exists()
    assert scene_dir.joinpath('2017-01-07_cloudy_pixel_percentage.txt').exists()
    assert scene_dir.joinpath('2017-01-07_metadata.yaml').exists()

    # validate output
    validate_fcir(scene_dir.joinpath('2017-01-07_fcir.tif'))
    validate_rgb(scene_dir.joinpath('2017-01-07_rgb.tif'))
    validate_ndvi(scene_dir.joinpath('2017-01-07_ndvi.tif'))
    validate_yaml(scene_dir.joinpath('2017-01-07_metadata.yaml'))
    # read the cloudy pixel percentage file and assure it is correct
    with open(
        scene_dir.joinpath('2017-01-07_cloudy_pixel_percentage.txt'),'r') as f:
        cloud_cover = float(f.read())
    assert cloud_cover == 26.5


def test_landsat_c2l1(get_data_dir, get_feature):

    constants = LandsatC2L1Constants
    feature = get_feature
    output_dir = get_data_dir.joinpath('landsat-l1')
    # ensure a "clean" start
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir()

    monitor_folder(
        constants=constants,
        feature=feature,
        folder_to_monitor=output_dir,
        temporal_increment_days=30
    )

    scene_dir = output_dir.joinpath('1972-09-20')
    # ensure all outputs exist
    assert scene_dir.exists()

    assert scene_dir.joinpath('1972-09-20_cloud_mask.tif').exists()
    assert scene_dir.joinpath('1972-09-20_ndvi.tif').exists()
    assert not scene_dir.joinpath('1972-09-20_rgb.tif').exists()
    assert scene_dir.joinpath('1972-09-20_fcir.tif').exists()
    assert scene_dir.joinpath('complete.txt').exists()
    assert scene_dir.joinpath('1972-09-20_cloudy_pixel_percentage.txt').exists()
    assert scene_dir.joinpath('1972-09-20_metadata.yaml').exists()

    # validate output
    validate_fcir_landsat_l1(scene_dir.joinpath('1972-09-20_fcir.tif'))
    validate_ndvi(scene_dir.joinpath('1972-09-20_ndvi.tif'))
    validate_yaml(scene_dir.joinpath('1972-09-20_metadata.yaml'))


def test_landsat_c2l2(get_data_dir, get_feature):

    constants = LandsatC2L2Constants
    feature = get_feature
    output_dir = get_data_dir.joinpath('landsat-l2')
    # ensure a "clean" start
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir()

    monitor_folder(
        constants=constants,
        feature=feature,
        folder_to_monitor=output_dir,
        temporal_increment_days=60)

    scenes = [
        '2016-01-05',
        '2016-01-06',
        '2016-01-14',
        '2016-01-21',
        '2016-01-22',
        '2016-01-29',
        '2016-01-30',
        '2016-02-06',
        '2016-02-15',
        '2016-02-22',
        '2016-03-01'
    ]
    for scene in scenes:
        scene_dir = output_dir.joinpath(scene)
        # ensure all outputs exist
        assert scene_dir.exists()
        assert scene_dir.joinpath(f'{scene}_cloud_mask.tif').exists()
        assert scene_dir.joinpath(f'{scene}_ndvi.tif').exists()
        assert scene_dir.joinpath(f'{scene}_rgb.tif').exists()
        assert scene_dir.joinpath(f'{scene}_fcir.tif').exists()
        assert scene_dir.joinpath('complete.txt').exists()
        assert scene_dir.joinpath(f'{scene}_cloudy_pixel_percentage.txt').exists()
        assert scene_dir.joinpath(f'{scene}_metadata.yaml').exists()
    
        # validate output
        validate_fcir_landsat_l2(scene_dir.joinpath(f'{scene}_fcir.tif'))
        validate_rgb_landsat(scene_dir.joinpath(f'{scene}_rgb.tif'))
        validate_ndvi(scene_dir.joinpath(f'{scene}_ndvi.tif'))
        validate_yaml(scene_dir.joinpath(f'{scene}_metadata.yaml'))


# TODO: Add test for cli function to test the full argparser (especially the store_true option)