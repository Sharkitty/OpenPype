import os
import glob

import pyblish.api
import openpype.api
from openpype.hosts.blender.api import capture
from openpype.hosts.blender.api.lib import maintained_time

import bpy


class ExtractThumbnail(openpype.api.Extractor):
    """Extract viewport thumbnail.

    Takes review camera and creates a thumbnail based on viewport
    capture.

    """

    label = "Extract Thumbnail"
    hosts = ["blender"]
    families = ["review", "model", "rig"]
    order = pyblish.api.ExtractorOrder + 0.01

    def process(self, instance):
        self.log.info("Extracting capture..")

        stagingdir = self.staging_dir(instance)
        filename = instance.name
        path = os.path.join(stagingdir, filename)

        self.log.info(f"Outputting images to {path}")

        camera = instance.data.get("review_camera", "AUTO")
        start = instance.data.get("frameStart", bpy.context.scene.frame_start)
        family = instance.data.get("family")
        isolate = instance.data("isolate", None)

        instance_collection = instance[-1]
        instance_collection.hide_viewport = False
        bpy.context.view_layer.layer_collection.children.get(
            instance_collection.name
        ).hide_viewport = False

        if not isolate:
            isolate = [
                obj for obj in bpy.context.scene.objects
                if obj.type == "MESH" and obj.visible_get()
            ]
            for sibling_instance in instance.context:
                if sibling_instance is not instance:
                    for obj in sibling_instance:
                        if obj in isolate:
                            isolate.remove(obj)

        focus = [
            obj for obj in instance
            if isinstance(obj, bpy.types.Object)
            and obj.type == "MESH"
            and obj.visible_get()
        ]

        project_settings = instance.context.data["project_settings"]["blender"]
        extractor_settings = project_settings["publish"]["ExtractThumbnail"]
        presets = extractor_settings.get("presets")

        preset = presets.get(family, {})

        preset.update(
            {
                "camera": camera,
                "start_frame": start,
                "end_frame": start,
                "filename": path,
                "overwrite": True,
                "isolate": isolate,
                "focus": focus,
            }
        )
        preset.setdefault("height", preset.setdefault("width", 512))
        preset.setdefault(
            "image_settings",
            {
                "file_format": "JPEG",
                "color_mode": "RGB",
                "quality": 100,
            },
        )

        # Keep current display shading
        # Catch source window because Win changes focus
        screen = bpy.context.window_manager.windows[0].screen
        current_area = next(
            (a for a in screen.areas if a.type == "VIEW_3D"), None
        )
        shading_type = (
            current_area.spaces[0].shading.type if current_area else "SOLID"
        )
        preset.setdefault(
            "display_options",
            {"shading": {"type": shading_type}},
        )

        with maintained_time():
            path = capture(**preset)

        thumbnail = os.path.basename(self._fix_output_path(path))

        self.log.info(f"thumbnail: {thumbnail}")

        instance.data.setdefault("representations", [])

        representation = {
            "name": "thumbnail",
            "ext": "jpg",
            "files": thumbnail,
            "stagingDir": stagingdir,
            "thumbnail": True,
            "tags": ["review", "thumbnail"],
        }
        instance.data["representations"].append(representation)

    def _fix_output_path(self, filepath):
        """Workaround to return correct filepath.

        To workaround this we just glob.glob() for any file extensions and
        assume the latest modified file is the correct file and return it.

        """
        # Catch cancelled playblast
        if filepath is None:
            self.log.warning(
                "Playblast did not result in output path. "
                "Playblast is probably interrupted."
            )
            return None

        if not os.path.exists(filepath):
            files = glob.glob(f"{filepath}.*.jpg")

            if not files:
                raise RuntimeError(f"Couldn't find playblast from: {filepath}")
            filepath = max(files, key=os.path.getmtime)

        return filepath