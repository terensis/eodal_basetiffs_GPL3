# name as for `pip install package`
name = "eodal-viewer"
# `path` is the name of the package for `import package`
path = name.lower().replace("-", "_").replace(" ", "_")

author = (
    "Lukas Valentin Graf, Terensis, Zurich, Switzerland"
)
author_email = "lukas.graf@terensis.io"
description = "Downloading and pre-processing of Sentinel-2 data products using EOdal"
url = ""
license = "GNU General Public License version 3"
version = "0.1"
