import bpy
from datetime import datetime

from openpype.lib.log import Logger
from openpype.lib.dateutils import get_timestamp

if __name__ == "__main__":
    current_time = get_timestamp()

    log = Logger().get_logger()
    log.debug(f"Setting workfile last publish time to {current_time}")

    # Set last publish time to current time
    # This script assumes it is only executed in a known up to date workfile
    bpy.context.scene["op_published_time"] = current_time
