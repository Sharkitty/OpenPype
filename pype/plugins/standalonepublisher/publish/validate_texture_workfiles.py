import pyblish.api
import pype.api


class ValidateTextureBatchWorkfiles(pyblish.api.InstancePlugin):
    """Validates that textures workfile has collected resources (optional).

        Collected recourses means secondary workfiles (in most cases).
    """

    label = "Validate Texture Workfile Has Resources"
    hosts = ["standalonepublisher"]
    order = pype.api.ValidateContentsOrder
    families = ["texture_batch_workfile"]
    optional = True

    def process(self, instance):
        if instance.data["family"] == "workfile":
            msg = "No resources for workfile {}".\
                format(instance.data["name"])
            assert instance.data.get("resources"), msg
