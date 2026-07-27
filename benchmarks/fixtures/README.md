# Benchmark fixtures

The benchmark creates bounded `.FCStd` fixtures in its temporary workspace so
the installed FreeCAD build writes the archive format it will reopen. This
avoids checking in version-specific binary documents while still exercising
save/reopen, rollback, broken links, PartDesign, spreadsheet, and
multi-document scenarios.
