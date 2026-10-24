"""FreeCAD-hosted service registry, independent of MCP and Qt.

Trusted installed add-ons publish small, versioned JSON operations in-process.
Transports discover these operations; they never import a module supplied by a
remote caller. The transport remains responsible for document authority and
owner-thread dispatch. Workers receive immutable snapshots, not document handles.
"""
from __future__ import annotations

import json
import math
import re
import threading
from dataclasses import dataclass
from typing import Any, Callable, cast

PROTOCOL_VERSION = 1
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,95}$")
_MAX_BYTES = 2 * 1024 * 1024
_SCHEMA_KEYS = {"type", "properties", "required", "additionalProperties", "items", "enum",
                "minimum", "maximum", "minItems", "maxItems", "minLength", "maxLength", "description"}


class ServiceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _json_copy(value: Any) -> Any:
    def check(item: Any, depth: int = 0) -> None:
        if depth > 32:
            raise ServiceError("INVALID_JSON", "JSON nesting exceeds 32 levels.")
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ServiceError("INVALID_JSON", "JSON object keys must be strings.")
            for child in item.values():
                check(child, depth + 1)
        elif type(item) is list:
            for child in item:
                check(child, depth + 1)
        elif item is not None and type(item) not in {str, int, float, bool}:
            raise ServiceError("INVALID_JSON", "Only JSON values may cross the service boundary.")

    check(value)
    try:
        data = json.dumps(value, allow_nan=False, separators=(",", ":"))
        size = len(data.encode("utf-8"))
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ServiceError("INVALID_JSON", str(exc)) from exc
    if size > _MAX_BYTES:
        raise ServiceError("PAYLOAD_TOO_LARGE", "Request a smaller page (maximum 2 MiB).")
    return json.loads(data)


def _check_schema(schema: Any, depth: int = 0) -> None:
    if depth > 12 or not isinstance(schema, dict) or set(schema) - _SCHEMA_KEYS:
        raise ServiceError("INVALID_SCHEMA", "Use the documented bounded JSON-schema subset.")
    if not isinstance(schema.get("type"), str) or schema["type"] not in {"object", "array", "string", "number", "integer", "boolean", "null"}:
        raise ServiceError("INVALID_SCHEMA", "Every schema requires an explicit supported type.")
    if schema["type"] == "object":
        if schema.get("additionalProperties", False) is not False:
            raise ServiceError("INVALID_SCHEMA", "Object schemas must reject undeclared properties.")
        props = schema.get("properties", {})
        if not isinstance(props, dict) or not isinstance(schema.get("required", []), list):
            raise ServiceError("INVALID_SCHEMA", "Invalid object properties/required.")
        required = schema.get("required", [])
        if any(not isinstance(key, str) or key not in props for key in required):
            raise ServiceError("INVALID_SCHEMA", "Required properties must be declared.")
        for child in props.values():
            _check_schema(child, depth + 1)
    if schema["type"] == "array":
        _check_schema(schema.get("items"), depth + 1)
    for name in ("minimum", "maximum", "minItems", "maxItems", "minLength", "maxLength"):
        if name in schema and (isinstance(schema[name], bool) or not isinstance(schema[name], (int, float))
                               or (isinstance(schema[name], float) and not math.isfinite(schema[name]))):
            raise ServiceError("INVALID_SCHEMA", "Schema bounds must be finite numbers.")
        if name in schema and name not in {"minimum", "maximum"} and (schema[name] < 0 or not isinstance(schema[name], int)):
            raise ServiceError("INVALID_SCHEMA", "Length bounds must be nonnegative integers.")
    for lower, upper in (("minimum", "maximum"), ("minItems", "maxItems"), ("minLength", "maxLength")):
        if lower in schema and upper in schema and schema[lower] > schema[upper]:
            raise ServiceError("INVALID_SCHEMA", "Schema minimum exceeds maximum.")
    if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
        raise ServiceError("INVALID_SCHEMA", "enum must be a nonempty array.")
    _json_copy(schema)
    if "enum" in schema:
        without_enum = {key: value for key, value in schema.items() if key != "enum"}
        for choice in schema["enum"]:
            try:
                validate_arguments(choice, without_enum)
            except ServiceError as exc:
                raise ServiceError("INVALID_SCHEMA", "enum values must satisfy their schema.") from exc


def validate_arguments(value: Any, schema: dict[str, Any], path: str = "arguments") -> None:
    kind = schema["type"]
    types: dict[str, Any] = {"object": dict, "array": list, "string": str, "integer": int,
             "number": (int, float), "boolean": bool, "null": type(None)}
    if not isinstance(value, types[kind]) or (kind in {"integer", "number"} and isinstance(value, bool)):
        raise ServiceError("INVALID_ARGUMENT", f"{path} must be {kind}.")
    if "enum" in schema and value not in schema["enum"]:
        raise ServiceError("INVALID_ARGUMENT", f"{path} is outside the declared choices.")
    if kind == "object":
        props = schema.get("properties", {})
        if set(value) - set(props) or any(key not in value for key in schema.get("required", [])):
            raise ServiceError("INVALID_ARGUMENT", f"{path} has missing or undeclared properties.")
        for key, item in value.items():
            validate_arguments(item, props[key], f"{path}.{key}")
    elif kind == "array":
        for item in value:
            validate_arguments(item, schema["items"], path + "[]")
    if kind in {"number", "integer"}:
        if (isinstance(value, float) and not math.isfinite(value)) or value < schema.get("minimum", -math.inf) or value > schema.get("maximum", math.inf):
            raise ServiceError("INVALID_ARGUMENT", f"{path} is outside its finite bounds.")
    if kind in {"array", "string"}:
        low, high = ("minItems", "maxItems") if kind == "array" else ("minLength", "maxLength")
        if len(value) < schema.get(low, 0) or len(value) > schema.get(high, 100000):
            raise ServiceError("INVALID_ARGUMENT", f"{path} is outside its length bounds.")


@dataclass(frozen=True)
class ServiceContext:
    """Supplied by the host after checking authority, never from JSON arguments."""
    document: Any
    access: str
    actor_id: str = "local"
    on_rejected: Callable[[Callable[[], None]], None] | None = None
    after_commit: Callable[[Callable[[], Any]], None] | None = None


class Registry:
    protocol_version = PROTOCOL_VERSION

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._providers: dict[str, tuple[dict[str, Any], dict[str, Callable[[ServiceContext, dict[str, Any]], Any]]]] = {}

    def register(self, addon_id: str, version: str, operations: list[dict[str, Any]], handlers: dict[str, Callable[[ServiceContext, dict[str, Any]], Any]]) -> None:
        """Register trusted local callbacks. Replacement requires unregister first."""
        if not isinstance(addon_id, str) or not _NAME.fullmatch(addon_id) or not isinstance(version, str) or not version:
            raise ServiceError("INVALID_PROVIDER", "A named, versioned provider is required.")
        if not isinstance(operations, list) or not isinstance(handlers, dict):
            raise ServiceError("INVALID_PROVIDER", "Supply an operations array and callback mapping.")
        entries = {}
        for operation in operations:
            op = _json_copy(operation)
            if not isinstance(op, dict):
                raise ServiceError("INVALID_OPERATION", "Each operation must be an object.")
            name = op.get("name")
            if not isinstance(name, str) or not _NAME.fullmatch(name) or name in entries:
                raise ServiceError("INVALID_OPERATION", "Operation names must be unique identifiers.")
            if not isinstance(op.get("access"), str) or op["access"] not in {"query", "mutation"}:
                raise ServiceError("INVALID_OPERATION", "Declare query or mutation access.")
            if op.get("execution", "document") != "document":
                raise ServiceError("UNSUPPORTED_EXECUTION", "Version 1 dispatches document-owner callbacks only; queue UI/background work explicitly.")
            _check_schema(op.get("input_schema"))
            if op["input_schema"]["type"] != "object":
                raise ServiceError("INVALID_SCHEMA", "Operation arguments must be an object.")
            if not callable(handlers.get(name)):
                raise ServiceError("INVALID_OPERATION", "Every declared operation needs a local callback.")
            entries[name] = op
        if not entries or set(entries) != set(handlers):
            raise ServiceError("INVALID_OPERATION", "Declare exactly the callable public operations.")
        descriptor = {"addon_id": addon_id, "version": version, "protocol_version": PROTOCOL_VERSION,
                      "operations": list(entries.values())}
        _json_copy(descriptor)
        with self._lock:
            if addon_id in self._providers:
                raise ServiceError("ALREADY_REGISTERED", "Unregister the existing provider before replacing it.")
            self._providers[addon_id] = (descriptor, dict(handlers))

    def unregister(self, addon_id: str) -> None:
        with self._lock:
            self._providers.pop(addon_id, None)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return cast(list[dict[str, Any]], _json_copy([{"addon_id": key, "version": item[0]["version"], "protocol_version": PROTOCOL_VERSION}
                               for key, item in sorted(self._providers.items())]))

    def describe(self, addon_id: str) -> dict[str, Any]:
        if not isinstance(addon_id, str):
            raise ServiceError("INVALID_ARGUMENT", "addon_id must be a string.")
        with self._lock:
            if addon_id not in self._providers:
                raise ServiceError("ADDON_NOT_FOUND", "The requested add-on has not registered services.")
            return cast(dict[str, Any], _json_copy(self._providers[addon_id][0]))

    def invoke(self, addon_id: str, operation: str, arguments: dict[str, Any], *, context: ServiceContext) -> Any:
        """Execute on the caller's already-authorized document owner thread."""
        if not isinstance(operation, str) or not isinstance(arguments, dict):
            raise ServiceError("INVALID_ARGUMENT", "Supply an operation name and object arguments.")
        with self._lock:
            self.describe(addon_id)
            descriptor, handlers = self._providers[addon_id]
            matches = [op for op in descriptor["operations"] if op["name"] == operation]
            if not matches:
                raise ServiceError("OPERATION_NOT_FOUND", "Only explicitly registered operations can be called.")
            entry, callback = matches[0], handlers[operation]
        if not isinstance(context, ServiceContext) or context.document is None:
            raise ServiceError("DOCUMENT_REQUIRED", "Supply a host-resolved document context.")
        if context.access not in {"query", "mutation"} or (entry["access"] == "mutation" and context.access != "mutation"):
            raise ServiceError("MUTATION_REQUIRED", "This operation requires document mutation authority.")
        args = _json_copy(arguments)
        validate_arguments(args, entry["input_schema"])
        return _json_copy(callback(context, args))


def install(app: Any) -> Registry:
    """Install one registry on FreeCAD; add-on load order does not matter."""
    existing = getattr(app, "AddonServices", None)
    if existing is None:
        app.AddonServices = Registry()
    elif getattr(existing, "protocol_version", None) != PROTOCOL_VERSION:
        raise ServiceError("PROTOCOL_MISMATCH", "Unsupported FreeCAD add-on service registry version.")
    discover(app)
    return cast(Registry, app.AddonServices)


def discover(app: Any) -> None:
    """Consume in-process providers declared by installed add-on Init.py files."""
    registry = app.AddonServices
    registered = {item["addon_id"] for item in registry.list()}
    for addon_id, factory in tuple(getattr(app, "AddonServiceProviders", {}).items()):
        if addon_id not in registered:
            factory(registry)


__all__ = ["Registry", "ServiceContext", "ServiceError", "install", "discover", "validate_arguments"]
