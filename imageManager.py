# Module stub for image management.
# To be populated by the user for specific use cases.

import os
import re

# --- Mandatory functions for network script ---


def download(names, config):
    """
    Function to download images. The user is free to implement this as they see fit.
    The saved images should be named consistently with the return value of `filename(name)`.

    Args:
        names (Iterable[str]): Node names for which to download images.
        config (Any): Optional configuration object with user-defined parameters from the calling context.

    returns:
        None
    """
    return


DEFAULT_IMAGE = "images/default.jpg"


def filename(name):
    """
    Converts a passed name into a filename path.
    Must be consistent with the naming scheme used in `download()`.
    Returns the image path if the file exists, otherwise returns DEFAULT_IMAGE.

    Args:
        name (str): Node name.
    Returns:
        str: Path to the filename, or DEFAULT_IMAGE if no matching file is found.
    """
    if name and name.strip():
        file_name = "images/" + re.sub(r"[^\w]", "", name) + ".jpg"
        if os.path.exists(file_name):
            return file_name

    return DEFAULT_IMAGE
