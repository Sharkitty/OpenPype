import os
import re
import logging

log = logging.getLogger(__name__)


def get_paths_from_environ(env_key, return_first=False):
    """Return existing paths from specific envirnment variable.

    :param env_key: Environment key where should look for paths.
    :type env_key: str
    :param return_first: Return first path on `True`, list of all on `False`.
    :type return_first: boolean

    Difference when none of paths exists:
    - when `return_first` is set to `False` then function returns empty list.
    - when `return_first` is set to `True` then function returns `None`.
    """
    existing_paths = []
    paths = os.environ.get(env_key) or ""
    path_items = paths.split(os.pathsep)
    for path in path_items:
        # Skip empty string
        if not path:
            continue
        # Normalize path
        path = os.path.normpath(path)
        # Check if path exists
        if os.path.exists(path):
            # Return path if `return_first` is set to True
            if return_first:
                return path
            # Store path
            existing_paths.append(path)

    # Return None if none of paths exists
    if return_first:
        return None
    # Return all existing paths from environment variable
    return existing_paths


def get_ffmpeg_tool_path(tool="ffmpeg"):
    """Find path to ffmpeg tool in FFMPEG_PATH paths.

    Function looks for tool in paths set in FFMPEG_PATH environment. If tool
    exists then returns it's full path.

    Returns tool name itself when tool path was not found. (FFmpeg path may be
    set in PATH environment variable)
    """
    dir_paths = get_paths_from_environ("FFMPEG_PATH")
    for dir_path in dir_paths:
        for file_name in os.listdir(dir_path):
            base, _ext = os.path.splitext(file_name)
            if base.lower() == tool.lower():
                return os.path.join(dir_path, tool)
    return tool


def _rreplace(s, a, b, n=1):
    """Replace a with b in string s from right side n times."""
    return b.join(s.rsplit(a, n))


def version_up(filepath):
    """Version up filepath to a new non-existing version.

    Parses for a version identifier like `_v001` or `.v001`
    When no version present _v001 is appended as suffix.

    Returns:
        str: filepath with increased version number

    """
    dirname = os.path.dirname(filepath)
    basename, ext = os.path.splitext(os.path.basename(filepath))

    regex = r"[._]v\d+"
    matches = re.findall(regex, str(basename), re.IGNORECASE)
    if not matches:
        log.info("Creating version...")
        new_label = "_v{version:03d}".format(version=1)
        new_basename = "{}{}".format(basename, new_label)
    else:
        label = matches[-1]
        version = re.search(r"\d+", label).group()
        padding = len(version)

        new_version = int(version) + 1
        new_version = '{version:0{padding}d}'.format(version=new_version,
                                                     padding=padding)
        new_label = label.replace(version, new_version, 1)
        new_basename = _rreplace(basename, label, new_label)

    if not new_basename.endswith(new_label):
        index = (new_basename.find(new_label))
        index += len(new_label)
        new_basename = new_basename[:index]

    new_filename = "{}{}".format(new_basename, ext)
    new_filename = os.path.join(dirname, new_filename)
    new_filename = os.path.normpath(new_filename)

    if new_filename == filepath:
        raise RuntimeError("Created path is the same as current file,"
                           "this is a bug")

    for file in os.listdir(dirname):
        if file.endswith(ext) and file.startswith(new_basename):
            log.info("Skipping existing version %s" % new_label)
            return version_up(new_filename)

    log.info("New version %s" % new_label)
    return new_filename


def get_version_from_path(file):
    """Find version number in file path string.s

    Args:
        file (string): file path

    Returns:
        v: version number in string ('001')

    """
    pattern = re.compile(r"[\._]v([0-9]+)", re.IGNORECASE)
    try:
        return pattern.findall(file)[0]
    except IndexError:
        log.error(
            "templates:get_version_from_workfile:"
            "`{}` missing version string."
            "Example `v004`".format(file)
        )


def get_last_version_from_path(path_dir, filter):
    """Find last version of given directory content.

    Args:
        path_dir (string): directory path
        filter (list): list of strings used as file name filter

    Returns:
        string: file name with last version

    Example:
        last_version_file = get_last_version_from_path(
            "/project/shots/shot01/work", ["shot01", "compositing", "nk"])
    """
    assert os.path.isdir(path_dir), "`path_dir` argument needs to be directory"
    assert isinstance(filter, list) and (
        len(filter) != 0), "`filter` argument needs to be list and not empty"

    filtred_files = list()

    # form regex for filtering
    patern = r".*".join(filter)

    for file in os.listdir(path_dir):
        if not re.findall(patern, file):
            continue
        filtred_files.append(file)

    if filtred_files:
        sorted(filtred_files)
        return filtred_files[-1]

    return None
