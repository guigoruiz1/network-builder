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


def filename(name):
    """
    Converts a passed name into a filename path.
    Must be consistent with the naming scheme used in `download()`.
    Returns None if no file exists.

    Args:
        name (str): Node name.
    Returns:
        str: Path to the filename.
    """
    return ""