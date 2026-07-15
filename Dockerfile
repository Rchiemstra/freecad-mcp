# Headless FreeCAD test image for the freecad-mcp e2e / core-repro test suite.
#
# Strategy: install FreeCAD from conda-forge, which ships the `FreeCADCmd`
# headless console and exposes the FreeCAD/Part/Sketcher Python modules on the
# interpreter path. The container's Python *is* FreeCAD's Python, so `pytest`
# can `import FreeCAD` directly and `exec` generated MCP code in-process (the
# same pattern used by tests/integration/test_assembly_path_live.py).
#
# Build:  docker build -t freecad-mcp-tests .
# Run:    docker run --rm freecad-mcp-tests pytest -m e2e

FROM condaforge/mambaforge:latest AS base

# Avoid interactive prompts and reduce noise.
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FREECAD_TEST=1

# Create the conda env with FreeCAD + the test runner. Pinning the channel is
# important: conda-forge is the only reliable source of up-to-date FreeCADCmd.
RUN mamba create -y -n freecad -c freecad/label/dev -c conda-forge \
        python=3.12 \
        freecad \
        pytest \
        pytest-asyncio \
        pytest-xdist \
        pytest-cov \
    && mamba clean -afy

# Make the conda env the default for subsequent RUN/ENTRYPOINT.
ENV PATH=/opt/conda/envs/freecad/bin:$PATH \
    FREECAD_HOME=/opt/conda/envs/freecad \
    PYTHONPATH=/opt/conda/envs/freecad/lib

# Working directory for the package source.
WORKDIR /workspace

# Copy the package and install it in editable mode so test edits are picked up
# without rebuilding the image.
COPY pyproject.toml README.md ./
COPY src ./src
COPY addon ./addon
COPY tests ./tests

RUN pip install --no-cache-dir -e ".[dev]"

# Sanity gate: fail the build early if FreeCADCmd or the Python modules are
# unavailable. This catches a broken conda-forge FreeCAD build immediately.
RUN (command -v FreeCADCmd >/dev/null && FreeCADCmd --version) \
    || (command -v freecadcmd >/dev/null && freecadcmd --version) \
    || FreeCAD --version
RUN python -c "import FreeCAD, Part, Sketcher; print('FreeCAD', FreeCAD.Version())"

# Default: run the full suite. Override with `pytest -m unit` for the fast
# mock-based layer that does not need FreeCAD.
ENTRYPOINT ["pytest"]
CMD ["-m", "e2e", "-ra", "--tb=short"]
