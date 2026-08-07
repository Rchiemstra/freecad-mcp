"""Resolve FEM objects without publishing their GUI presentation early."""

from __future__ import annotations

from contextlib import AbstractContextManager as _AbstractContextManager
from importlib import reload as _reload
from inspect import getmodule as _getmodule
from inspect import isclass as _isclass

import FreeCAD
import ObjectsFem


def _import_module(name: str):
    return __import__(name, fromlist=["ViewProxy"])


def _fem_objects(doc) -> list[object]:
    return list(getattr(doc, "Objects", ()) or ())


def _module_providers(module, module_name: str) -> dict[str, object]:
    if module is None:
        return {}
    return {
        name: candidate
        for name, candidate in vars(module).items()
        if (name == "ViewProxy" or name.startswith("VP") or name.endswith("ViewProxy"))
        and _isclass(candidate)
        and getattr(candidate, "__module__", None) == module_name
    }


def _select_provider(candidates, proxy_class, *, source: str):
    for exact_name in ("ViewProxy", f"VP{proxy_class.__name__}"):
        if exact_name in candidates:
            return candidates[exact_name]
    if len(candidates) == 1:
        return next(iter(candidates.values()))
    if candidates:
        detail = ", ".join(sorted(candidates))
        raise RuntimeError(
            f"FEM presentation for proxy '{proxy_class.__name__}' "
            f"is ambiguous in {source}: {detail}."
        )
    return None


def _presentation_provider_for_proxy(proxy):
    proxy_class = proxy.__class__
    model_module = str(getattr(proxy_class, "__module__", "") or "")
    module_tail = model_module.rsplit(".", 1)[-1]
    if not module_tail or model_module == "builtins":
        raise RuntimeError(
            f"FEM Python proxy '{proxy_class.__name__}' has no model module."
        )
    model_module_obj = _getmodule(proxy_class)
    if _module_providers(model_module_obj, model_module):
        # The factory may have first imported a combined model/GUI module while
        # GuiUp was suppressed. Refresh it after restoration so conditional GUI
        # dependencies are present before retaining its presentation provider.
        refreshed_module = _reload(model_module_obj)
        same_module_provider = _select_provider(
            _module_providers(refreshed_module, model_module),
            proxy_class,
            source=model_module,
        )
        if same_module_provider is not None:
            return same_module_provider

    provider_module_name = f"femviewprovider.view_{module_tail}"
    try:
        provider_module = _import_module(provider_module_name)
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError(
            f"FEM presentation module '{provider_module_name}' is unavailable."
        ) from exc

    provider = _select_provider(
        _module_providers(provider_module, provider_module_name),
        proxy_class,
        source=provider_module_name,
    )
    if provider is not None:
        return provider
    raise RuntimeError(
        f"FEM presentation for proxy '{proxy_class.__name__}' has no provider "
        f"in {provider_module_name}."
    )


class _DeferredFemPresentation(_AbstractContextManager):
    """Keep FEM model construction atomic and replay GUI setup after commit.

    ObjectsFem combines App proxy construction and ViewProvider construction in
    one factory.  Structural compatibility callbacks deliberately have no
    presentation object until native publication, so only the factory's GUI
    branch is suppressed here. The exact GUI-provider constructors are then
    invoked by the RPC orchestrator after the native commit has returned.
    """

    def __init__(self, doc) -> None:
        self._doc = doc
        self._before = {id(obj) for obj in _fem_objects(doc)}
        self._objects: list[object] = []
        self._presentations: list[tuple[object, object]] = []
        self._gui_up_value = getattr(FreeCAD, "GuiUp", False)
        self._gui_up = bool(self._gui_up_value)

    def __enter__(self):
        if self._gui_up:
            # GUI RPC work is serialized on the GUI thread.  Restore this in
            # __exit__ before the native coordinator publishes NewObject.
            FreeCAD.GuiUp = False
        return self

    def capture(self, obj) -> None:
        if obj is not None and all(existing is not obj for existing in self._objects):
            self._objects.append(obj)

    def __exit__(self, exc_type, exc_value, traceback):
        if self._gui_up:
            FreeCAD.GuiUp = self._gui_up_value
        for obj in _fem_objects(self._doc):
            if id(obj) not in self._before:
                self.capture(obj)
        if exc_type is None and self._gui_up:
            for obj in self._objects:
                proxy = getattr(obj, "Proxy", None)
                if proxy is not None:
                    self._presentations.append(
                        (obj, _presentation_provider_for_proxy(proxy))
                    )
        return False

    @property
    def requires_replay(self) -> bool:
        return bool(self._presentations)

    def apply_after_commit(self) -> None:
        """Attach suppressed FEM presentation providers after publication."""

        if not self._gui_up:
            return
        for obj, factory in self._presentations:
            presentation_obj = getattr(obj, "ViewObject", None)
            if presentation_obj is None:
                name = getattr(obj, "Name", "<unknown>")
                raise RuntimeError(
                    f"FEM presentation for '{name}' was unavailable after native commit."
                )
            factory(presentation_obj)


def defer_fem_presentation(doc) -> _DeferredFemPresentation:
    return _DeferredFemPresentation(doc)


def resolve_analysis(doc, analysis_name: str) -> tuple[object | None, dict | None]:
    analysis = doc.getObject(analysis_name)
    if analysis is None:
        return None, {"success": False, "error": f"Analysis '{analysis_name}' not found."}
    if analysis.TypeId not in ("Fem::FemAnalysis", "Fem::FemAnalysisPython"):
        return None, {
            "success": False,
            "error": (
                f"'{analysis_name}' is not a FEM analysis "
                f"(TypeId={analysis.TypeId})."
            ),
        }
    return analysis, None


def resolve_solver(doc, analysis) -> object:
    for member in analysis.Group:
        tid = getattr(member, "TypeId", "")
        if "SolverCcx" in tid or "SolverCalculix" in tid:
            return member
    solver_factory = (
        getattr(ObjectsFem, "makeSolverCalculiXCcxTools", None)
        or getattr(ObjectsFem, "makeSolverCalculixCcxTools", None)
    )
    if solver_factory is None:
        raise RuntimeError("ObjectsFem has no Calculix solver factory.")
    solver = solver_factory(doc, "CalculiX")
    analysis.addObject(solver)
    return solver
