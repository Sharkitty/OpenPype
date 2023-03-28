# -*- coding: utf-8 -*-
import gazu
import pyblish.api


class IntegrateKitsuReview(pyblish.api.InstancePlugin):
    """Integrate Kitsu Review"""

    order = pyblish.api.IntegratorOrder + 0.01
    label = "Kitsu Review"
    families = ["render", "review"]
    optional = True

    def process(self, instance):
        task = instance.data["kitsu_task"]["id"]
        comment = instance.data.get("kitsu_comment")

        # Check comment has been created
        if not comment:
            self.log.debug(
                "Comment not created, review not pushed to preview."
            )
            return

        # Add review representations as preview of comment
        for representation in instance.data.get("representations", []):
            review_path = representation.get("published_path")
            self.log.debug("Found review at: {}".format(review_path))

            gazu.task.add_preview(
                task, comment["id"], review_path, normalize_movie=True
            )
            self.log.info("Review upload on comment")
