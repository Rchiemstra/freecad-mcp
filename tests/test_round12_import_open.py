from types import SimpleNamespace as NS, ModuleType
import sys
import pytest
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.open_document import run_open_document

pytestmark = pytest.mark.unit


def app():
    docs = {}
    def project(path):
        doc = NS(Name='Project')
        docs[doc.Name] = doc
        return doc
    return NS(openDocument=project, getDocument=docs.get, listDocuments=lambda: docs,
              getImportType=lambda ext: ['R12Importer']), docs


def test_project_open_uses_existing_path(tmp_path):
    runtime, docs = app()
    p = tmp_path / 'x.FCStd'; p.write_text('project')
    assert run_open_document(NS(freecad=runtime), str(p))['document_name'] == 'Project'


def test_registered_importer_opens_file(tmp_path, monkeypatch):
    runtime, docs = app()
    module = ModuleType('R12Importer')
    def open(path):
        docs['Imported'] = NS(Name='Imported')
        # Most FreeCAD importers return None and set ActiveDocument.
    module.open = open
    monkeypatch.setitem(sys.modules, module.__name__, module)
    p = tmp_path / 'x.r12'; p.write_text('import')
    assert run_open_document(NS(freecad=runtime), str(p))['document_name'] == 'Imported'


def test_import_candidates_are_deduplicated_and_ambiguity_is_clear(tmp_path, monkeypatch):
    runtime, docs = app()
    runtime.getImportType = lambda ext: ['R12Importer', 'R12Importer', 'OtherImporter']
    p = tmp_path / 'x.r12'; p.write_text('import')
    result = run_open_document(NS(freecad=runtime), str(p))
    assert result['error_code'] == 'AMBIGUOUS_IMPORT_MODULE'
    assert 'OtherImporter' in result['error'] and 'module' in result['error']
    module = ModuleType('R12Importer')
    module.open = lambda path: docs.setdefault('Imported', NS(Name='Imported'))
    monkeypatch.setitem(sys.modules, module.__name__, module)
    assert run_open_document(NS(freecad=runtime), str(p), 'R12Importer')['document_name'] == 'Imported'


def test_unregistered_extension_is_clear(tmp_path):
    runtime, _ = app()
    runtime.getImportType = lambda ext: []
    p = tmp_path / 'x.r12'; p.write_text('import')
    assert run_open_document(NS(freecad=runtime), str(p))['error'] == 'no import module handles .r12'


def test_importer_creates_document_then_raises_reports_uncertain(tmp_path, monkeypatch):
    runtime, docs = app()
    module = ModuleType('R12Importer')

    def partial_open(path):
        docs['PartialImport'] = NS(Name='PartialImport')
        raise RuntimeError('unsupported entity after document creation')

    module.open = partial_open
    monkeypatch.setitem(sys.modules, module.__name__, module)
    path = tmp_path / 'partial.r12'
    path.write_text('import')
    result = run_open_document(NS(freecad=runtime), str(path))

    assert 'PartialImport' in docs
    assert result['error_code'] == 'IMPORT_OPEN_FAILED'
    assert 'unsupported entity' in result['error']
    assert result['outcome'] == 'uncertain', result
    assert result['committed'] is None
    assert result['retry_safe'] is False


def test_importer_creates_multiple_unresolved_documents_reports_uncertain(tmp_path, monkeypatch):
    runtime, docs = app()
    module = ModuleType('R12Importer')

    def multiple_open(path):
        docs['ImportedOne'] = NS(Name='ImportedOne')
        docs['ImportedTwo'] = NS(Name='ImportedTwo')

    module.open = multiple_open
    monkeypatch.setitem(sys.modules, module.__name__, module)
    path = tmp_path / 'multiple.r12'
    path.write_text('import')
    result = run_open_document(NS(freecad=runtime), str(path))

    assert set(docs) == {'ImportedOne', 'ImportedTwo'}
    assert result['error_code'] == 'IMPORT_DOCUMENT_UNRESOLVED'
    assert result['outcome'] == 'uncertain', result
    assert result['committed'] is None
    assert result['retry_safe'] is False
