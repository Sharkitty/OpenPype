import os
import shutil
from time import sleep
from openpype.client.entities import (
    get_last_version_by_subset_id,
    get_representations,
    get_subsets,
)
from openpype.client.entity_links import get_linked_representation_id
from openpype.lib import PreLaunchHook
from openpype.lib.local_settings import get_local_site_id
from openpype.lib.profiles_filtering import filter_profiles
from openpype.pipeline.load.utils import get_representation_path
from openpype.pipeline.template_data import get_template_data_with_names
from openpype.pipeline.workfile.path_resolving import get_workfile_template_key
from openpype.settings.lib import get_project_settings
from openpype.modules.sync_server.sync_server import (
    download_last_published_workfile,
    get_subset_id,
)


class CopyLastPublishedWorkfile(PreLaunchHook):
    """Copy last published workfile as first workfile.

    Prelaunch hook works only if last workfile leads to not existing file.
        - That is possible only if it's first version.
    """

    # Before `AddLastWorkfileToLaunchArgs`
    order = -1
    app_groups = ["blender", "photoshop", "tvpaint", "aftereffects"]

    def execute(self):
        """Check if local workfile doesn't exist, else copy it.

        1- Check if setting for this feature is enabled
        2- Check if workfile in work area doesn't exist
        3- Check if published workfile exists and is copied locally in publish
        4- Substitute copied published workfile as first workfile
           with incremented version by +1

        Returns:
            None: This is a void method.
        """

        # Check there is no workfile available
        last_workfile = self.data.get("last_workfile_path")
        if os.path.exists(last_workfile):
            self.log.debug(
                "Last workfile exists. Skipping {} process.".format(
                    self.__class__.__name__
                )
            )
            return

        # Get data
        project_name = self.data["project_name"]
        asset_name = self.data["asset_name"]
        task_name = self.data["task_name"]
        task_type = self.data["task_type"]
        host_name = self.application.host_name

        # Check settings has enabled it
        project_settings = get_project_settings(project_name)
        profiles = project_settings["global"]["tools"]["Workfiles"][
            "last_workfile_on_startup"
        ]
        filter_data = {
            "tasks": task_name,
            "task_types": task_type,
            "hosts": host_name,
        }
        last_workfile_settings = filter_profiles(profiles, filter_data)
        use_last_published_workfile = last_workfile_settings.get(
            "use_last_published_workfile"
        )
        if use_last_published_workfile is None:
            self.log.info(
                (
                    "Seems like old version of settings is used."
                    ' Can\'t access custom templates in host "{}".'.format(
                        host_name
                    )
                )
            )
            return
        elif use_last_published_workfile is False:
            self.log.info(
                (
                    'Project "{}" has turned off to use last published'
                    ' workfile as first workfile for host "{}"'.format(
                        project_name, host_name
                    )
                )
            )
            return

        self.log.info("Trying to fetch last published workfile...")

        project_doc = self.data.get("project_doc")
        asset_doc = self.data.get("asset_doc")
        anatomy = self.data.get("anatomy")

        # Getting subset ID
        filtered_subsets = [
            subset
            for subset in get_subsets(
                project_name,
                asset_ids=[asset_doc["_id"]],
                fields=["_id", "name", "data.family", "data.families"],
            )
            if (
                subset["data"].get("family") == "workfile"
                # Legacy compatibility
                or "workfile" in subset["data"].get("families", {})
            )
        ]
        if not filtered_subsets:
            self.log.debug(
                "No any subset for asset '{}' with id '{}'.".format(
                    asset_name, asset_doc["_id"]
                )
            )
            return

        # Matching subset which has task name in its name
        subset_id = None
        low_task_name = task_name.lower()
        if len(filtered_subsets) > 1:
            for subset in filtered_subsets:
                if low_task_name in subset["name"].lower():
                    subset_id = subset["_id"]
                    break
        if subset_id is None:
            self.log.debug(
                "No any matched subset for task '{}' of '{}'.".format(
                    low_task_name, asset_name
                )
            )
            return

        # Getting workfile representation
        last_version_doc = get_last_version_by_subset_id(
            project_name, subset_id, fields=["_id", "name"]
        )
        if not last_version_doc:
            self.log.debug("Subset does not have any versions")
            return

        workfile_representation = next(
            (
                representation
                for representation in get_representations(
                    project_name, version_ids=[last_version_doc["_id"]]
                )
                if representation["context"]["task"]["name"] == task_name
            ),
            None,
        )
        if not workfile_representation:
            self.log.debug(
                'No published workfile for task "{}" and host "{}".'.format(
                    task_name, host_name
                )
            )
            return

        published_workfile_path = get_last_published_workfile_path(
            host_name,
            project_name,
            task_name,
            workfile_representation,
            anatomy=anatomy,
        )

        # Copy file and substitute path
        self.data["last_workfile_path"] = download_last_published_workfile(
            host_name,
            project_name,
            self.data["asset_name"],
            task_name,
            published_workfile_path,
            workfile_representation,
            subset_id,
            last_version_doc,
            anatomy=anatomy,
            asset_doc=asset_doc,
        )
        # Keep source filepath for further path conformation
        self.data["source_filepath"] = published_workfile_path
        return

        # Check it can proceed
        if not project_doc and not asset_doc:
            return

        # Get subset id
        filtered_subsets = [
            subset
            for subset in get_subsets(
                project_name,
                asset_ids=[asset_doc["_id"]],
                fields=["_id", "name", "data.family", "data.families"],
            )
            if (
                subset["data"].get("family") == "workfile"
                # Legacy compatibility
                or "workfile" in subset["data"].get("families", {})
            )
        ]
        if not filtered_subsets:
            self.log.debug(
                "No any subset for asset '{}' with id '{}'.".format(
                    asset_name, asset_doc["_id"]
                )
            )
            return

        # Matching subset which has task name in its name
        subset_id = None
        low_task_name = task_name.lower()
        if len(filtered_subsets) > 1:
            for subset in filtered_subsets:
                if low_task_name in subset["name"].lower():
                    subset_id = subset["_id"]
                    break

        # Set default matched subset
        if subset_id is None:
            self.log.debug(
                "No any matched subset for task '{}' of '{}'.".format(
                    low_task_name, asset_name
                )
            )
            return

        # Get workfile representation
        last_version_doc = get_last_version_by_subset_id(
            project_name, subset_id, fields=["_id", "name"]
        )
        if not last_version_doc:
            self.log.debug("Subset does not have any versions")
            return

        workfile_representation = next(
            (
                representation
                for representation in get_representations(
                    project_name, version_ids=[last_version_doc["_id"]]
                )
                if representation["context"]["task"]["name"] == task_name
            ),
            None,
        )

        if not workfile_representation:
            self.log.debug(
                'No published workfile for task "{}" and host "{}".'.format(
                    task_name, host_name
                )
            )
            return

        local_site_id = get_local_site_id()

        # Tag worfile and linked representations to be downloaded
        representation_ids = {workfile_representation["_id"]}
        representation_ids.update(
            get_linked_representation_id(
                project_name, repre_id=workfile_representation["_id"]
            )
        )
        for repre_id in representation_ids:
            sync_server.add_site(
                project_name,
                repre_id,
                local_site_id,
                force=True,
                priority=99,
                reset_timer=True,
            )

        while not sync_server.is_representation_on_site(
            project_name, workfile_representation["_id"], local_site_id
        ):
            sleep(5)

        # Get paths
        published_workfile_path = get_representation_path(
            workfile_representation, root=anatomy.roots
        )

        # Build workfile to copy and open's name from anatomy template settings
        workfile_data = get_template_data_with_names(
            project_name, asset_name, task_name, host_name
        )
        workfile_data["version"] = last_version_doc["name"] + 1
        workfile_data["ext"] = os.path.splitext(published_workfile_path)[-1]
        template_key = get_workfile_template_key(
            task_type, host_name, project_name, project_settings
        )
        anatomy_result = anatomy.format(workfile_data)
        local_workfile_path = anatomy_result[template_key]["path"]

        # Copy file and substitute path
        self.data["last_workfile_path"] = shutil.copy(
            published_workfile_path,
            local_workfile_path,
        )

        # Keep source filepath for further path conformation
        self.data["source_filepath"] = published_workfile_path
