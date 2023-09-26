"""
Utility functions

not used atm
"""

import os


def get_files(in_dir: str, file_ending: str, full_path: bool) -> list:
    """
    Get the file paths of a specified in_dir

    Parameters
    ----------
    in_dir :
        directory to look for files
    file_ending :
        ending of the files to look for
    full_path :
        should the full filepath or the filename be reported?

    Returns
    -------
    a list of either filenames or filepaths, depending on the full_path keyword
    """

    filelist = []
    for filepath in os.scandir(in_dir):
        if filepath.name.endswith(f".{file_ending}") and filepath.is_file():
            if full_path:
                filelist.append(filepath.path)
            else:
                filelist.append(filepath.name)

    return filelist
