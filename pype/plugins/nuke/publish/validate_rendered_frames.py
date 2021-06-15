import os
import pyblish.api
from pype.api import ValidationException
import clique


@pyblish.api.log
class RepairCollectionActionToLocal(pyblish.api.Action):
    label = "Repair > rerender with `Local` machine"
    on = "failed"
    icon = "wrench"

    def process(self, context, plugin):
        self.log.info(context[0][0])
        files_remove = [os.path.join(context[0].data["outputDir"], f)
                        for r in context[0].data.get("representations", [])
                        for f in r.get("files", [])
                        ]
        self.log.info("Files to be removed: {}".format(files_remove))
        for f in files_remove:
            os.remove(f)
            self.log.debug("removing file: {}".format(f))
        context[0][0]["render"].setValue("Local")
        self.log.info("Rendering toggled to `Local`")


@pyblish.api.log
class RepairCollectionActionToFarm(pyblish.api.Action):
    label = "Repair > rerender `On farm` with remote machines"
    on = "failed"
    icon = "wrench"

    def process(self, context, plugin):
        self.log.info(context[0][0])
        files_remove = [os.path.join(context[0].data["outputDir"], f)
                        for r in context[0].data.get("representations", [])
                        for f in r.get("files", [])
                        ]
        self.log.info("Files to be removed: {}".format(files_remove))
        for f in files_remove:
            os.remove(f)
            self.log.debug("removing file: {}".format(f))
        context[0][0]["render"].setValue("On farm")
        self.log.info("Rendering toggled to `On farm`")


class ValidateRenderedFrames(pyblish.api.InstancePlugin):
    """ Validates file output. """

    order = pyblish.api.ValidatorOrder + 0.1
    families = ["render", "prerender"]

    label = "Validate rendered frame"
    hosts = ["nuke", "nukestudio"]
    actions = [RepairCollectionActionToLocal, RepairCollectionActionToFarm]


    def process(self, instance):

        for repre in instance.data["representations"]:

            if not repre.get("files"):
                msg = ("no frames were collected, "
                       "you need to render them")
                self.log.error(msg)
                raise ValidationException(msg)

            collections, remainder = clique.assemble(repre["files"])
            self.log.info("collections: {}".format(str(collections)))
            self.log.info("remainder: {}".format(str(remainder)))

            collection = collections[0]

            fstartH = instance.data["frameStartHandle"]
            fendH = instance.data["frameEndHandle"]

            frame_length = int(fendH - fstartH + 1)

            if frame_length != 1:
                if len(collections) != 1:
                    msg = "There are multiple collections in the folder"
                    self.log.error(msg)
                    raise ValidationException(msg)

                if not collection.is_contiguous():
                    msg = "Some frames appear to be missing"
                    self.log.error(msg)
                    raise ValidationException(msg)

            collected_frames_len = int(len(collection.indexes))
            coll_start = min(collection.indexes)
            coll_end = max(collection.indexes)

            self.log.info("frame_length: {}".format(frame_length))
            self.log.info("collected_frames_len: {}".format(
                collected_frames_len))
            self.log.info("fstartH-fendH: {}-{}".format(fstartH, fendH))
            self.log.info(
                "coll_start-coll_end: {}-{}".format(coll_start, coll_end))

            self.log.info(
                "len(collection.indexes): {}".format(collected_frames_len)
            )

            if ("slate" in instance.data["families"]) \
                    and (frame_length != collected_frames_len):
                collected_frames_len -= 1
                fstartH += 1

            assert ((collected_frames_len >= frame_length)
                    and (coll_start <= fstartH)
                    and (coll_end >= fendH)), (
                "{} missing frames. Use repair to render all frames"
            ).format(__name__)

            instance.data["collection"] = collection

            return
