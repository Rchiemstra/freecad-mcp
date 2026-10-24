# One FreeCAD-hosted add-on service bridge

Installed add-ons register local callbacks with `FreeCAD.AddonServices`. The shared
FreeCAD MCP server exposes exactly three generic tools; an add-on does not need
its own MCP server, transport, installer, or arbitrary Python execution wrapper.
Registration trusts installed in-process code. Remote callers can only select
registered add-on/operation names and supply JSON arguments; names are never
interpreted as import, module, function, or filesystem paths.

## MCP and RPC surface

The tools and positional RPC methods have the same names and parameter order:

```python
list_addons()
describe_addon(addon_id: str)
invoke_addon_operation(doc_name: str, addon_id: str, operation: str, arguments: dict)
```

Named authenticated v2 params use those exact parameter names. In particular,
`arguments` is one nested JSON object, not expanded into RPC keyword arguments.
The client binds the explicit `doc_name` into the existing mutation context.

`list_addons` returns `{"success": true, "addons": [{"addon_id": "Example",
"version": "1.0", "protocol_version": 1}]}`. `describe_addon` returns
`{"success": true, "addon": <descriptor>}`. The descriptor contains `addon_id`,
`version`, `protocol_version`, and `operations` (the registered operation metadata).
Both methods read cached registration metadata only. They do not discover or
import providers, call factories/callbacks, read documents, or dispatch to Qt.
They work without an active document or GUI once the registry is installed.

Every invocation is a **DOCUMENT_MUTATION**, including operations declared
`access="query"` and job polls/cancels. This preserves native document authority
and conservatively covers opaque plugin effects. The existing transport auth and
pause admission gates run first. The RPC facade dispatches through the existing
GUI dispatcher; `collaboration_api.commit_native_mutation` resolves the named
document, and the native coordinator admits the lease/CAS state and runs
`apply(document)` on the document owner thread. Provider code is called only
inside that native apply. There is no parallel security gateway.

Native recompute and a same-document invariant check precede commit. The response
is successful only after native terminal `status="Committed"` with
`committed=true` and the successful postcondition. A callback return alone is
provisional. GUI async commits are awaited off the GUI thread through
`native_commit_wait`; a timeout, unknown status, or failed rollback reports an
uncertain outcome. The successful invocation response is:

```json
{
  "success": true,
  "committed": true,
  "outcome": "committed",
  "retry_safe": false,
  "document_name": "Model",
  "addon_id": "Example",
  "operation": "set_width",
  "result": {"width": 12.0}
}
```

The MCP adapter preserves the RPC payload in the standard tool result envelope.
It also rejects successful invocation responses without terminal commit evidence.

## Exact host registration API

The registry API lives in `freecad_mcp.addon_services`:

```python
registry.register(addon_id: str, version: str,
                  operations: list[dict], handlers: dict[str, callable]) -> None
registry.unregister(addon_id: str) -> None
registry.list() -> list[dict]
registry.describe(addon_id: str) -> dict
registry.invoke(addon_id: str, operation: str, arguments: dict,
                *, context: ServiceContext) -> JSON_value
install(app) -> Registry
discover(app) -> None
```

`install(FreeCAD)` installs the version 1 registry and consumes trusted pending
factories in `FreeCAD.AddonServiceProviders`. FreeCADMCP's `Init.py` calls it.
`discover` is a trusted local startup action, never a remote operation.
Duplicate registration raises `ALREADY_REGISTERED`; replacement requires an
explicit unregister. `list` and `describe` return independent JSON copies.

An installed add-on can use this in its `Init.py` (including headless startup):

```python
import FreeCAD as App


def register_services(registry):
    # Importing the registry types here also supports loading before FreeCADMCP.
    from freecad_mcp.addon_services import ServiceError

    def set_width(context, arguments):
        doc = context.document  # Exact host-resolved document, on its native owner.
        box = doc.getObject("Box")
        if box is None:
            raise ServiceError("BOX_NOT_FOUND", "Create Box before setting its width.")
        box.Width = arguments["width"]
        # Do not open/commit transactions or recompute here; native owns them.
        return {"width": float(box.Width)}

    registry.register("Example", "1.0", [{
        "name": "set_width",
        "description": "Set Box.Width in the named document.",
        "access": "mutation",       # Or "query"; MCP still requires mutation authority.
        "execution": "document",    # The only supported execution venue in version 1.
        "input_schema": {
            "type": "object",
            "properties": {"width": {"type": "number", "minimum": 1, "maximum": 100}},
            "required": ["width"],
            "additionalProperties": False,
        },
    }], {"set_width": set_width})


if not hasattr(App, "AddonServiceProviders"):
    App.AddonServiceProviders = {}
App.AddonServiceProviders["Example"] = register_services
if hasattr(App, "AddonServices"):
    if not any(item["addon_id"] == "Example" for item in App.AddonServices.list()):
        register_services(App.AddonServices)
```

Callbacks have the exact signature `callback(context, arguments)`. The frozen
`ServiceContext` contains `document`, `access`, and informational `actor_id`.
The MCP host supplies `access="mutation"`, `actor_id="mcp"`; authority and actor
attribution come from the native request context, not from these strings or JSON
arguments. Local hosts may use `registry.invoke` only after establishing their
own document authority and owner-thread venue. It is not a remote bypass API.

Remote example:

```json
{"doc_name": "Model", "addon_id": "Example", "operation": "set_width", "arguments": {"width": 12}}
```

## Schemas, JSON, and errors

Every schema requires an explicit `type`: `object`, `array`, `string`, `number`,
`integer`, `boolean`, or `null`. Supported keys are `type`, `properties`,
`required`, `additionalProperties`, `items`, `enum`, `minimum`, `maximum`,
`minItems`, `maxItems`, `minLength`, `maxLength`, and `description`. Objects reject
undeclared properties (`additionalProperties` is false or omitted); arrays
require `items`. Unsupported schema features, including `$ref`, are rejected at
registration. Schema nesting is limited to 12 levels; JSON nesting to 32 levels.
Length defaults to at most 100,000 items/characters unless explicitly bounded.
Arguments must be an object and are copied and schema-validated before callbacks.

Arguments, results, and metadata must contain JSON values only: string-keyed
objects, arrays, finite numbers, strings, booleans, and null. Tuples, document
objects, shapes, byte strings, arbitrary instances, non-string keys, and NaN or
Infinity are rejected. Each JSON payload is limited to 2 MiB; providers should
page large results. Result validation happens inside native apply, so an invalid
or oversized result aborts the document mutation.

Failures expose `success=false`, `error_code`, `error`, `committed`, `outcome`,
and `retry_safe`. Registry errors include `INVALID_SCHEMA`, `INVALID_ARGUMENT`,
`INVALID_JSON`, `PAYLOAD_TOO_LARGE`, `ADDON_NOT_FOUND`, and `OPERATION_NOT_FOUND`.
Unexpected callback exceptions become `ADDON_OPERATION_FAILED`. Raise
`ServiceError(code, message)` for a provider-specific public error; returning an
error-shaped JSON object is still a normal operation result. Missing documents,
native refusals, postcondition failures, and uncertain commits are explicit.
A confirmed document rollback includes `rollback_succeeded=true`. Opaque plugin
side effects outside the document cannot be undone by that transaction, so
failures after apply are conservatively not safe for automatic retry.

## Long-running jobs

Register short document-owner operations named, for example, `start`, `poll`, and
`cancel`. They use the same `invoke_addon_operation` RPC with these argument and
result shapes (declare each input schema during registration):

| Operation | Arguments | Example result |
| --- | --- | --- |
| `start` | `{"object_name":"Box"}` | `{"job_id":"opaque-token","state":"queued"}` |
| `poll` | `{"job_id":"opaque-token"}` | `{"job_id":"opaque-token","state":"running"}` |
| `cancel` | `{"job_id":"opaque-token"}` | `{"job_id":"opaque-token","state":"cancel_requested"}` |

`start` snapshots immutable data on the owner thread and enqueues only that data
for computation. Workers must never receive or capture `context`, a document,
document objects, live shapes, or GUI handles. Use detached serialized geometry,
scalar values, bytes, or immutable snapshots as appropriate. Keep document and
GUI access in owner callbacks; apply completed work in a later invocation, with
fresh native authority and stale-input checks. Poll/cancel must remain short.
Use provider-owned opaque handles scoped to the originating document/request,
bounded job retention, explicit failed/cancelled/completed states, and cooperative
cancellation. A bridge commit means the start/poll/cancel callback committed; it
does not mean the background job completed. Starting a worker is an external
side effect: providers own its cancellation/cleanup if the document commit fails.
The host supplies optional `context.on_rejected(cleanup_callback)` registration.
Register a short, background-safe cleanup that closes over only an opaque task
handle, for example a cooperative cancellation request. It runs if native commit
is rejected, rolled back, or uncertain. It must not access a document or GUI.
Cleanup failure cannot convert a rejected commit into success.
The bridge does not install add-ons, start per-add-on servers, or provide a worker
that accepts arbitrary remote Python.
