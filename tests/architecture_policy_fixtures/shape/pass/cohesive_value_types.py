"""Several immutable values for one request/result subject are cohesive."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ObjectId:
    value: str


@dataclass(frozen=True)
class ObjectRevision:
    value: int


@dataclass(frozen=True)
class ObjectSnapshot:
    object_id: ObjectId
    revision: ObjectRevision
    label: str


@dataclass(frozen=True)
class ObjectMutation:
    object_id: ObjectId
    expected_revision: ObjectRevision
    label: str


__all__ = ("ObjectId", "ObjectMutation", "ObjectRevision", "ObjectSnapshot")
