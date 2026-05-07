# Undo: Pattern Index

This directory contains one file per design pattern documenting all known undo variants —
that is, ways to transform code that uses the pattern back into code that doesn't
(or into a smellier alternative). These are used to generate synthetic "before refactoring"
snapshots for the design pattern benchmark dataset.

## Files

| File | Pattern | # Variants |
|------|---------|-----------|
| [factory_method.md](factory_method.md) | Factory Method | 5 |
| [builder.md](builder.md) | Builder | 6 |
| [observer.md](observer.md) | Observer | 7 |
| [adapter.md](adapter.md) | Adapter | 6 |
| [composite.md](composite.md) | Composite | 5 |
| [decorator.md](decorator.md) | Decorator | 4 |
| [strategy.md](strategy.md) | Strategy | 6 |
| [iterator.md](iterator.md) | Iterator | 5 |
| [visitor.md](visitor.md) | Visitor | 5 |
| [command.md](command.md) | Command | 7 |

## File Structure

Each file follows this format:

```
# Undo: <Pattern Name>

## Pattern Structure Being Removed
  [description of what structural elements define the pattern]

### Canonical "With Pattern" Code
  [self-contained Java example showing the pattern in use]

## Undo Variants (sorted by realism ★ high → low)

### <ID> · <Name> ★★★/★★☆/★☆☆
  Realism / Compile Risk / Scope ratings
  Resulting Smell
  [smelly code example]
  [explanation of what's wrong]
```

## Ratings Key

### Realism ★
How closely the undone code resembles what a developer would actually write *before*
the refactoring:
- ★★★ High — seen regularly in real codebases; a plausible "first attempt"
- ★★☆ Medium — technically valid but less common; possible in legacy or rushed code  
- ★☆☆ Low — artificial; unlikely to appear in real projects

### Compilation Risk 🔴🟡🟢
Risk that the undo transformation produces code that doesn't compile or requires
extensive cascading fixes:
- 🟢 Low — changes are local; the surrounding code still compiles easily
- 🟡 Medium — interface/type changes propagate to 2–5 files
- 🔴 High — cascades across many call sites; significant rework required

### Scope 🔵🟣⚫
How many files are touched by the transformation:
- 🔵 Local — 1–2 files
- 🟣 Medium — 3–5 files  
- ⚫ Wide — 6+ files

## Cross-Pattern Summary

### Resulting Smells by Frequency

| Smell | Patterns |
|-------|---------|
| Switch Statement / if-else chains | Factory Method, Strategy, Visitor, Command, Composite, Iterator |
| Long Parameter List | Builder, Factory Method |
| God Class | Decorator, Observer, Strategy, Visitor, Command, Composite |
| Tight Coupling / Feature Envy | Observer, Command, Adapter, Iterator |
| Code Duplication / Shotgun Surgery | Strategy, Command, Adapter, Factory Method, Visitor |
| Parallel Inheritance Hierarchy | Composite, Decorator, Strategy |
| Missing Encapsulation | Iterator, Builder, Adapter |
| Boilerplate proliferation | Builder (non-fluent), Adapter (event) |

### Best Variants for Automated Synthetic Generation

High realism + well-defined transformation scope = easiest to automate:

| Variant | Pattern | Why Automate This |
|---------|---------|-------------------|
| B-1: Telescoping Constructors | Builder | Very common; transformation is mechanical (inline fields) |
| B-4: Non-Fluent Setters | Builder | Trivial: remove `return this` — lowest risk undo |
| S-1: Inline switch | Strategy | Switch is the canonical precursor to Strategy |
| S-2: Lambda replacement | Strategy | Mechanical: interface → Consumer<T> |
| O-1: Polling | Observer | Removes notification; leaves a getState() getter |
| O-3: Lambda callbacks | Observer | Minimal change: interface → Consumer |
| FM-1: switch dispatcher | Factory Method | Add switch, delete interface hierarchy |
| V-1: instanceof chain | Visitor | Add instanceof checks, remove accept() |
| V-2: Iterator + filter | Visitor | Remove accept(), expose iterator |
| D-1: Boolean flags | Decorator | Add booleans, collapse decorators |
| Cmd-6: Remove undo() | Command | Remove one method — narrowest change |
| Cmd-1: Direct call | Command | Delete command objects, call receiver directly |
| I-1: getAll() exposure | Iterator | Add getter, delete iterator class |
| A-1: instanceof dispatch | Adapter | Add instanceof, delete adapter |
| C-1: instanceof traversal | Composite | Add instanceof in traversal, remove interface |
