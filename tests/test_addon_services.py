"""Service boundary tests: real registry, no live document or transport."""
from types import SimpleNamespace

import pytest

from freecad_mcp.addon_services import Registry, ServiceContext, ServiceError, install


def provider(registry):
    registry.register("Example", "1.0", [{
        "name": "set_width", "access": "mutation", "description": "Set the permitted width",
        "input_schema": {"type": "object", "properties": {
            "width": {"type": "number", "minimum": 1, "maximum": 20}}, "required": ["width"]},
    }], {"set_width": lambda ctx, args: {"document": ctx.document.Name, "width": args["width"]}})


def test_load_order_and_repeated_discovery_do_not_replace_providers():
    app = SimpleNamespace(AddonServiceProviders={"Example": provider})
    registry = install(app)
    assert install(app) is registry
    assert registry.list()[0]["addon_id"] == "Example"
    descriptor = registry.describe("Example")
    descriptor["operations"].clear()
    assert len(registry.describe("Example")["operations"]) == 1


@pytest.mark.parametrize("args", [{"width": 0}, {"width": True}, {"width": float("nan")},
                                   {"width": 2, "module": "os"}, {}])
def test_invalid_remote_arguments_never_reach_provider(args):
    registry = Registry()
    provider(registry)
    with pytest.raises(ServiceError):
        registry.invoke("Example", "set_width", args,
                        context=ServiceContext(SimpleNamespace(Name="Fixture"), "mutation"))


def test_query_cannot_invoke_mutation_and_undeclared_call_is_rejected():
    registry = Registry()
    provider(registry)
    with pytest.raises(ServiceError, match="mutation authority"):
        registry.invoke("Example", "set_width", {"width": 3},
                        context=ServiceContext(SimpleNamespace(Name="Fixture"), "query"))
    with pytest.raises(ServiceError, match="explicitly registered"):
        registry.invoke("Example", "__import__", {}, context=ServiceContext(object(), "mutation"))
    result = registry.invoke("Example", "set_width", {"width": 3},
                             context=ServiceContext(SimpleNamespace(Name="Fixture"), "mutation"))
    assert result == {"document": "Fixture", "width": 3}


def test_schema_features_cannot_silently_escape_validation():
    registry = Registry()
    with pytest.raises(ServiceError, match="subset"):
        registry.register("Broken", "1", [{"name": "run", "access": "query",
                          "input_schema": {"type": "object", "$ref": "https://example.com"}}],
                          {"run": lambda *_: None})


@pytest.mark.parametrize("schema", [
    {"type": []}, {"type": "object", "required": [{}]},
    {"type": "object", "enum": {}}, {"type": "object", "enum": []},
    {"type": "object", "maxLength": -1}, {"type": "object", "maxItems": 1.5},
    {"type": "object", "minimum": 10, "maximum": 2},
    {"type": "object", "additionalProperties": True},
])
def test_malformed_schema_fails_registration_explicitly(schema):
    with pytest.raises(ServiceError) as error:
        Registry().register("Broken", "1", [{"name": "run", "access": "query", "input_schema": schema}],
                            {"run": lambda *_: None})
    assert error.value.code == "INVALID_SCHEMA"


@pytest.mark.parametrize("operation", [None, [], "run"])
def test_non_object_operation_descriptors_are_rejected(operation):
    with pytest.raises(ServiceError) as error:
        Registry().register("Broken", "1", [operation], {"run": lambda *_: None})
    assert error.value.code == "INVALID_OPERATION"


def test_json_depth_and_non_string_keys_are_rejected_before_callback():
    calls = []
    registry = Registry()
    registry.register("Example", "1", [{"name": "run", "access": "query",
                      "input_schema": {"type": "object"}}],
                      {"run": lambda *_: calls.append(True)})
    deep = {}
    for _ in range(40):
        deep = {"nested": deep}
    for arguments in ({1: "not a JSON key"}, deep):
        with pytest.raises(ServiceError) as error:
            registry.invoke("Example", "run", arguments,
                            context=ServiceContext(object(), "mutation"))
        assert error.value.code == "INVALID_JSON"
    assert not calls
