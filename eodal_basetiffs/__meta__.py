# name as for `pip install package`
name = "eodal-basetiffs"
# `path` is the name of the package for `import package`
path = name.lower().replace("-", "_").replace(" ", "_")

author = (
    "Lukas Valentin Graf, Terensis, Zurich, Switzerland"
)
author_email = "lukas.graf@terensis.io"
description = "A tool to download satellite data, pre-process it and store it as cloud-optimized GeoTIFFs based on EOdal."
url = "https://github.com/terensis/eodal_basetiffs_GPL3"
license = "GNU General Public License version 3"
version = "1.1"
