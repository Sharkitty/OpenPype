import bpy

from openpype.lib.log import Logger
from openpype.lib.dateutils import get_timestamp

if __name__ == "__main__":
    log = Logger().get_logger()
    log.debug("Setting workfile last publish time")

    # Set last publish time to current time
    # This script assumes it is only executed in a known up to date workfile
    # TODO Use UTC time instead of local time
    bpy.context.scene["op_published_time"] = get_timestamp()
