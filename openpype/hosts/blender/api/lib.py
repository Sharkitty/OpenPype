import os
import shutil
import traceback
import importlib
import contextlib
from pathlib import Path
from typing import Dict, List, Union

import bpy
import addon_utils
from openpype.lib import Logger
from openpype.modules import ModulesManager
from openpype.pipeline import (
    Anatomy,
    get_current_project_name,
    get_current_asset_name,
    get_current_task_name,
)
from openpype.pipeline.template_data import (
    get_template_data,
)
from openpype.pipeline.workfile.path_resolving import (
    get_workfile_template_key,
    get_last_workfile_with_version,
)
from openpype.client.entities import (
    get_subsets,
    get_representations,
    get_last_version_by_subset_id,
    get_asset_by_name,
    get_project,
)

from . import pipeline

log = Logger.get_logger(__name__)


def load_scripts(paths):
    """Copy of `load_scripts` from Blender's implementation.

    It is possible that this function will be changed in future and usage will
    be based on Blender version.
    """
    import bpy_types

    loaded_modules = set()

    previous_classes = [
        cls
        for cls in bpy.types.bpy_struct.__subclasses__()
    ]

    def register_module_call(mod):
        register = getattr(mod, "register", None)
        if register:
            try:
                register()
            except:
                traceback.print_exc()
        else:
            print("\nWarning! '%s' has no register function, "
                  "this is now a requirement for registerable scripts" %
                  mod.__file__)

    def unregister_module_call(mod):
        unregister = getattr(mod, "unregister", None)
        if unregister:
            try:
                unregister()
            except:
                traceback.print_exc()

    def test_reload(mod):
        # reloading this causes internal errors
        # because the classes from this module are stored internally
        # possibly to refresh internal references too but for now, best not to.
        if mod == bpy_types:
            return mod

        try:
            return importlib.reload(mod)
        except:
            traceback.print_exc()

    def test_register(mod):
        if mod:
            register_module_call(mod)
            bpy.utils._global_loaded_modules.append(mod.__name__)

    from bpy_restrict_state import RestrictBlend

    with RestrictBlend():
        for base_path in paths:
            for path_subdir in bpy.utils._script_module_dirs:
                path = os.path.join(base_path, path_subdir)
                if not os.path.isdir(path):
                    continue

                bpy.utils._sys_path_ensure_prepend(path)

                # Only add to 'sys.modules' unless this is 'startup'.
                if path_subdir != "startup":
                    continue
                for mod in bpy.utils.modules_from_path(path, loaded_modules):
                    test_register(mod)

    addons_paths = []
    for base_path in paths:
        addons_path = os.path.join(base_path, "addons")
        if not os.path.exists(addons_path):
            continue
        addons_paths.append(addons_path)
        addons_module_path = os.path.join(addons_path, "modules")
        if os.path.exists(addons_module_path):
            bpy.utils._sys_path_ensure_prepend(addons_module_path)

    if addons_paths:
        # Fake addons
        origin_paths = addon_utils.paths

        def new_paths():
            paths = origin_paths() + addons_paths
            return paths

        addon_utils.paths = new_paths
        addon_utils.modules_refresh()

    # load template (if set)
    if any(bpy.utils.app_template_paths()):
        import bl_app_template_utils
        bl_app_template_utils.reset(reload_scripts=False)
        del bl_app_template_utils

    for cls in bpy.types.bpy_struct.__subclasses__():
        if cls in previous_classes:
            continue
        if not getattr(cls, "is_registered", False):
            continue
        for subcls in cls.__subclasses__():
            if not subcls.is_registered:
                print(
                    "Warning, unregistered class: %s(%s)" %
                    (subcls.__name__, cls.__name__)
                )


def append_user_scripts():
    user_scripts = os.environ.get("OPENPYPE_BLENDER_USER_SCRIPTS")
    if not user_scripts:
        return

    try:
        load_scripts(user_scripts.split(os.pathsep))
    except Exception:
        print("Couldn't load user scripts \"{}\"".format(user_scripts))
        traceback.print_exc()


def set_app_templates_path():
    # Blender requires the app templates to be in `BLENDER_USER_SCRIPTS`.
    # After running Blender, we set that variable to our custom path, so
    # that the user can use their custom app templates.

    # We look among the scripts paths for one of the paths that contains
    # the app templates. The path must contain the subfolder
    # `startup/bl_app_templates_user`.
    paths = os.environ.get("OPENPYPE_BLENDER_USER_SCRIPTS").split(os.pathsep)

    app_templates_path = None
    for path in paths:
        if os.path.isdir(
                os.path.join(path, "startup", "bl_app_templates_user")):
            app_templates_path = path
            break

    if app_templates_path and os.path.isdir(app_templates_path):
        os.environ["BLENDER_USER_SCRIPTS"] = app_templates_path


def imprint(node: bpy.types.bpy_struct_meta_idprop, data: Dict):
    r"""Write `data` to `node` as userDefined attributes

    Arguments:
        node: Long name of node
        data: Dictionary of key/value pairs

    Example:
        >>> import bpy
        >>> def compute():
        ...   return 6
        ...
        >>> bpy.ops.mesh.primitive_cube_add()
        >>> cube = bpy.context.view_layer.objects.active
        >>> imprint(cube, {
        ...   "regularString": "myFamily",
        ...   "computedValue": lambda: compute()
        ... })
        ...
        >>> cube['avalon']['computedValue']
        6
    """

    imprint_data = dict()

    for key, value in data.items():
        if value is None:
            continue

        if callable(value):
            # Support values evaluated at imprint
            value = value()

        if not isinstance(value, (int, float, bool, str, list)):
            raise TypeError(f"Unsupported type: {type(value)}")

        imprint_data[key] = value

    pipeline.metadata_update(node, imprint_data)


def lsattr(attr: str,
           value: Union[str, int, bool, List, Dict, None] = None) -> List:
    r"""Return nodes matching `attr` and `value`

    Arguments:
        attr: Name of Blender property
        value: Value of attribute. If none
            is provided, return all nodes with this attribute.

    Example:
        >>> lsattr("id", "myId")
        ...   [bpy.data.objects["myNode"]
        >>> lsattr("id")
        ...   [bpy.data.objects["myNode"], bpy.data.objects["myOtherNode"]]

    Returns:
        list
    """

    return lsattrs({attr: value})


def lsattrs(attrs: Dict) -> List:
    r"""Return nodes with the given attribute(s).

    Arguments:
        attrs: Name and value pairs of expected matches

    Example:
        >>> lsattrs({"age": 5})  # Return nodes with an `age` of 5
        # Return nodes with both `age` and `color` of 5 and blue
        >>> lsattrs({"age": 5, "color": "blue"})

    Returns a list.

    """

    # For now return all objects, not filtered by scene/collection/view_layer.
    matches = set()
    for coll in dir(bpy.data):
        if not isinstance(
                getattr(bpy.data, coll),
                bpy.types.bpy_prop_collection,
        ):
            continue
        for node in getattr(bpy.data, coll):
            for attr, value in attrs.items():
                avalon_prop = node.get(pipeline.AVALON_PROPERTY)
                if not avalon_prop:
                    continue
                if (avalon_prop.get(attr)
                        and (value is None or avalon_prop.get(attr) == value)):
                    matches.add(node)
    return list(matches)


def read(node: bpy.types.bpy_struct_meta_idprop):
    """Return user-defined attributes from `node`"""

    data = dict(node.get(pipeline.AVALON_PROPERTY, {}))

    # Ignore hidden/internal data
    data = {
        key: value
        for key, value in data.items() if not key.startswith("_")
    }

    return data


def get_selection() -> List[bpy.types.Object]:
    """Return the selected objects from the current scene."""
    return [obj for obj in bpy.context.scene.objects if obj.select_get()]


@contextlib.contextmanager
def maintained_selection():
    r"""Maintain selection during context

    Example:
        >>> with maintained_selection():
        ...     # Modify selection
        ...     bpy.ops.object.select_all(action='DESELECT')
        >>> # Selection restored
    """

    previous_selection = get_selection()
    previous_active = bpy.context.view_layer.objects.active
    try:
        yield
    finally:
        # Clear the selection
        for node in get_selection():
            node.select_set(state=False)
        if previous_selection:
            for node in previous_selection:
                try:
                    node.select_set(state=True)
                except ReferenceError:
                    # This could happen if a selected node was deleted during
                    # the context.
                    log.exception("Failed to reselect")
                    continue
        try:
            bpy.context.view_layer.objects.active = previous_active
        except ReferenceError:
            # This could happen if the active node was deleted during the
            # context.
            log.exception("Failed to set active object.")


@contextlib.contextmanager
def maintained_time():
    """Maintain current frame during context."""
    current_time = bpy.context.scene.frame_current
    try:
        yield
    finally:
        bpy.context.scene.frame_current = current_time


def download_last_workfile(
    project_name: str, asset_name: str, task_name: str
) -> str:
    """Download last workfile and return its path.

    Args:
        project_name (str): Name of project.
        asset_name (str): Name of asset.
        task_name (str): Name of task.

    Returns:
        str: Path to last workfile.
    """
    from openpype.modules.sync_server.sync_server import (
        download_last_published_workfile,
    )

    sync_server = ModulesManager().get("sync_server")
    if not sync_server or not sync_server.enabled:
        raise RuntimeError("Sync server module is not enabled or available")

    anatomy = Anatomy(project_name)
    asset_doc = get_asset_by_name(
        project_name,
        asset_name,
    )
    family = "workfile"

    filtered_subsets = [
        subset
        for subset in get_subsets(
            project_name,
            asset_ids=[asset_doc["_id"]],
            fields=["_id", "name", "data.family", "data.families"],
        )
        if (
            subset["data"].get("family") == family
            # Legacy compatibility
            or family in subset["data"].get("families", {})
        )
    ]
    if not filtered_subsets:
        raise RuntimeError(
            "Not any subset for asset '{}' with id '{}'".format(
                asset_doc["name"], asset_doc["_id"]
            )
        )

    # Match subset wich has `task_name` in its name
    low_task_name = task_name.lower()
    if len(filtered_subsets) > 1:
        for subset in filtered_subsets:
            if low_task_name in subset["name"].lower():
                subset_id = subset["_id"]  # What if none is found?
    else:
        subset_id = filtered_subsets[0]["_id"]

    if subset_id is None:
        print(
            f"Not any matched subset for task '{task_name}'"
            f" of '{asset_name}'"
        )
        return

    # Get workfile representation
    last_version_doc = get_last_version_by_subset_id(
        project_name, subset_id, fields=["_id", "name", "data"]
    )
    if not last_version_doc:
        print("Subset does not have any version")
        return

    workfile_representations = list(
        get_representations(
            project_name,
            context_filters={
                "asset": asset_name,
                "family": "workfile",
                "task": {"name": task_name},
            },
        )
    )

    if not workfile_representations:
        raise RuntimeError(
            f"No published workfile for task {task_name} and host blender."
        )

    workfile_representation = max(
        filter(
            lambda r: r["context"].get("version"),
            workfile_representations,
        ),
        key=lambda r: r["context"]["version"],
    )
    if not workfile_representation:
        raise RuntimeError(
            "No published workfile for task " f"'{task_name}' and host blender"
        )

    # Download and get last workfile
    last_published_workfile_path = download_last_published_workfile(
        "blender",
        project_name,
        task_name,
        workfile_representation,
        int(
            (
                sync_server.sync_project_settings[project_name]["config"][
                    "retry_cnt"
                ]
            )
        ),
        anatomy=anatomy,
    )

    if (
        not last_published_workfile_path
        or not Path(last_published_workfile_path).exists()
    ):
        raise OSError("Failed to download last published workfile")

    return last_published_workfile_path, last_version_doc["data"]["time"]


def save_as_local_workfile(
    project_name: str, asset_name: str, task_name: str, filepath: Path
) -> str:
    """Save given filepath as local workfile.

    Args:
        project_name (str): Name of project.
        asset_name (str): Name of asset.
        task_name (str): Name of task.
        filepath (Path): Path to save file as workfile.

    Returns:
        str: Path to saved local workfile.
    """
    anatomy = Anatomy(project_name)
    asset_doc = get_asset_by_name(
        project_name,
        asset_name,
    )

    # Get workfile template data
    workfile_data = get_template_data(
        get_project(project_name, inactive=False),
        asset_doc,
        task_name,
        "blender",
    )

    # Get workfile version
    workfile_data["version"] = (
        get_last_workfile_with_version(
            Path(bpy.data.filepath).parent.as_posix(),
            anatomy.templates[
                get_workfile_template_key(task_name, "blender", project_name)
            ]["file"],
            workfile_data,
            ["blend"],
        )[1]
        + 1
    )
    workfile_data["ext"] = "blend"

    # Get local workfile path
    local_workfile_path = anatomy.format(workfile_data)[
        get_workfile_template_key(task_name, "blender", project_name)
    ]["path"]

    # Download and copy last published workfile to local workfile path
    shutil.copy(
        filepath,
        local_workfile_path,
    )

    return local_workfile_path
