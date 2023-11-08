# EOdal basetiffs

A tool to download satellite data, pre-process it and store it as [cloud-optimized GeoTIFFs](https://www.cogeo.org/) based on [EOdal](https://github.com/EOA-team/eodal).


## Installation

```bash
pip install git+https://github.com/terensis/eodal_basetiffs_GPL3
```

## Usage

```bash
eodal_basetiffs
```

```bash
usage: eodal_basetiffs [-h] [-a AREA_OF_INTEREST] [-o OUTPUT_DIR] [-t TEMPORAL_INCREMENT_DAYS] [-c TARGET_CRS]
                       [-p {sentinel-2,landsat-c2-l1,landsat-c2-l2}] [-r {True,False}]

A tool to download satellite data, pre-process it and store it as cloud-optimized GeoTIFFs based on EOdal.

options:
  -h, --help            show this help message and exit
  -a AREA_OF_INTEREST, --area-of-interest AREA_OF_INTEREST
                        path to the GeoPackage or Shapefile with the area of interest
  -o OUTPUT_DIR, --output-dir OUTPUT_DIR
                        path to the output directory where to store the data
  -t TEMPORAL_INCREMENT_DAYS, --temporal-increment-days TEMPORAL_INCREMENT_DAYS
                        temporal increment in days
  -c TARGET_CRS, --target-crs TARGET_CRS
                        target CRS for reprojection as EPSG code
  -p {sentinel-2,landsat-c2-l1,landsat-c2-l2}, --platform {sentinel-2,landsat-c2-l1,landsat-c2-l2}
                        platform to use for data acquisition
  -r {True,False}, --run-till-complete {True,False}
                        run until all scenes are processed
```