"""Shared functionalities for Blender files data manipulation."""
from typing import Optional, Union, Iterator
from collections.abc import Iterable

import bpy

# Match Blender type to a datapath to look into. Needed for native UI creator.
BL_TYPE_DATAPATH = (
    {  # NOTE Order is important for some hierarchy based processes!
        bpy.types.Collection: "collections",  # NOTE Must be always first
        bpy.types.Object: "objects",
        bpy.types.Camera: "cameras",
        bpy.types.Action: "actions",
        bpy.types.Armature: "armatures",
    }
)
# Match Blender type to an ICON for display
BL_TYPE_ICON = {
    bpy.types.Collection: "OUTLINER_COLLECTION",
    bpy.types.Object: "OBJECT_DATA",
    bpy.types.Camera: "CAMERA_DATA",
    bpy.types.Action: "ACTION",
    bpy.types.Armature: "ARMATURE_DATA",
}
# Types which can be handled through the outliner
BL_OUTLINER_TYPES = frozenset((bpy.types.Collection, bpy.types.Object))


def get_children_recursive(
    entity: Union[bpy.types.Collection, bpy.types.Object]
) -> Iterator[Union[bpy.types.Collection, bpy.types.Object]]:
    """Get childrens recursively from a object or a collection.

    Arguments:
        entity: The parent entity.

    Yields:
        The next childrens from parent entity.
    """
    # Since Blender 3.1.0 we can use "children_recursive" attribute.
    if hasattr(entity, "children_recursive"):
        for child in entity.children_recursive:
            yield child
    else:
        for child in entity.children:
            yield child
            yield from get_children_recursive(child)


def get_parent_collection(
    entity: Union[bpy.types.Collection, bpy.types.Object],
) -> Optional[bpy.types.Collection]:
    """Get the parent of the input outliner entity (collection or object).

    Args:
        entity (Union[bpy.types.Collection, bpy.types.Object]):
            Collection to get parent of.

    Returns:
        Optional[bpy.types.Collection]: Parent of entity
    """
    scene_collection = bpy.context.scene.collection
    if entity.name in scene_collection.children:
        return scene_collection
    # Entity is a Collection.
    elif isinstance(entity, bpy.types.Collection):
        for col in scene_collection.children_recursive:
            if entity.name in col.children:
                return col
    # Entity is an Object.
    elif isinstance(entity, bpy.types.Object):
        for col in scene_collection.children_recursive:
            if entity.name in col.objects:
                return col


def link_to_collection(
    entity: Union[bpy.types.Collection, bpy.types.Object, Iterator],
    collection: bpy.types.Collection,
):
    """link an entity to a collection.

    Note:
        Recursive function if entity is iterable.

    Arguments:
        entity: The collection, object or list of valid entities who need to be
            parenting with the given collection.
        collection: The collection used for parenting.
    """
    # Entity is Iterable, execute function recursively.
    if isinstance(entity, Iterable):
        for i in entity:
            link_to_collection(i, collection)
    # Entity is a Collection.
    elif (
        isinstance(entity, bpy.types.Collection)
        and entity not in collection.children.values()
        and collection not in entity.children.values()
        and entity is not collection
    ):
        collection.children.link(entity)
    # Entity is an Object.
    elif (
        isinstance(entity, bpy.types.Object)
        and entity not in collection.objects.values()
        and entity.instance_collection is not collection
        and entity.instance_collection
        not in set(get_children_recursive(collection))
    ):
        collection.objects.link(entity)


def unlink_from_collection(
    entity: Union[bpy.types.Collection, bpy.types.Object, Iterator],
    collection: bpy.types.Collection,
):
    """Unlink an entity from a collection.

    Note:
        Recursive function if entity is iterable.

    Args:
        entity (Union[bpy.types.Collection, bpy.types.Object, Iterator]): The collection, object or list of valid entities who need to be
            parenting with the given collection.
        collection (bpy.types.Collection): The collection to remove parenting.
    """
    # Entity is Iterable, execute function recursively.
    if isinstance(entity, Iterable):
        for i in entity:
            unlink_from_collection(i, collection)
    # Entity is a Collection.
    elif isinstance(entity, bpy.types.Collection) and entity is not collection:
        collection.children.unlink(entity)
    # Entity is an Object.
    elif isinstance(entity, bpy.types.Object):
        collection.objects.unlink(entity)