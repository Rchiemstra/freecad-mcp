# Prompts shown in the replay

Scripted replay using real MCP tools on the companion FreeCAD fork. No language model during replay.

## 1. Build from a spreadsheet

You: Build a small head that picks strawberries by the stem. Use a spreadsheet for its dimensions.

What this proves: Spreadsheet values drive the head and its reference cluster.

## 2. Enough force?

You: Can it grip with 10 N and cut with 15 N? Show the force budget.

What this proves: The calculated force stays above both targets through the stroke.

## 3. One pick, slowly

You: Show approach, clamp, cut, withdraw, then move the fruit to the tray.

What this proves: The scripted parts move in order; tray transfer is a preview.

## 4. Check the space

You: Measure the gaps and check whether any parts overlap the neighbouring fruit.

What this proves: Measured gaps are positive and sampled common volume is zero.

## 5. Tighter berries

You: The berries are only 10 mm apart. Show the clash, reshape the nose and check again.

What this proves: The original nose clashes; the retained nose fix clears the checked samples.

## 6. Check the jaw

You: Run a strength check on the jaw with a 10 N load at the pad.

What this proves: The coarse FEM checks the changed jaw under the stated load.

## 7. Ready for a bench test

You: What does it weigh? List the parts and export files I can inspect and print.

What this proves: The model supplies a mass estimate, parts list and separate print files.

