from pathlib import Path

from openpype.lib import PreLaunchHook
from openpype.hosts.blender import utility_scripts


class PreSetWorkfilePublishTime(PreLaunchHook):
    app_groups = [
        "blender",
    ]

    def execute(self):
        if self.data.get("source_filepath"):
            # Add `set_workfile_publish_time` script to launch arguments
            self.launch_context.launch_args.insert(
                self.launch_context.launch_args.index("-P"),
                [
                    "-P",
                    Path(utility_scripts.__file__).parent.joinpath(
                        "set_workfile_publish_time.py"
                    ).as_posix(),
                ],
            )
