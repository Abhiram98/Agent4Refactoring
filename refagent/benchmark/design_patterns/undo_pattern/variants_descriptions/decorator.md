# Undo: Decorator

## Pattern Structure Being Removed

A `Decorator` implements the same `Component` interface as the objects it wraps, holds a
`Component` reference, and adds behaviour before/after delegating to it. Multiple
decorators can be stacked at runtime.

### Canonical "With Pattern" Code

```java
interface TextRenderer { String render(String text); }

class PlainTextRenderer implements TextRenderer {
    public String render(String text) { return text; }
}

class BoldDecorator implements TextRenderer {
    private final TextRenderer wrapped;
    BoldDecorator(TextRenderer r) { this.wrapped = r; }
    public String render(String text) { return "<b>" + wrapped.render(text) + "</b>"; }
}

class ItalicDecorator implements TextRenderer {
    private final TextRenderer wrapped;
    ItalicDecorator(TextRenderer r) { this.wrapped = r; }
    public String render(String text) { return "<i>" + wrapped.render(text) + "</i>"; }
}

// Client — combinable at runtime
TextRenderer r = new ItalicDecorator(new BoldDecorator(new PlainTextRenderer()));
r.render("Hello");   // → <i><b>Hello</b></i>
```

---

## Undo Variants (sorted by realism ★ high → low)

---

### D-1 · Boolean Configuration Flags ★★★
**Realism:** ★★★ | **Compile Risk:** 🔴 High | **Scope:** ⚫ Wide
**Smell:** Primitive Obsession, Combinatorial Explosion

<!--variant
id: D-1
realism: 3
smell: "Primitive Obsession / Boolean Flags"
task: |
  Remove the Decorator pattern from class {class_name} in file {pattern_file}.
  Replace the stacked decorator objects with boolean/enum flags on the base component.

  Steps:
  1. Delete all concrete Decorator classes ({class_name} and any siblings).
  2. Add boolean fields to the base component class for each former decorator
     (e.g. `private boolean bold; private boolean italic;`).
  3. Add setters or constructor parameters for each flag.
  4. In the base component's `render()` (or equivalent) method, apply all active
     decorations inline using if/else on the flags.
  5. Update all call sites: replace decorator stacking with flag-setting.

  The result has no Decorator classes; all decoration is controlled by booleans,
  exhibiting the Primitive Obsession smell. Adding a new decoration requires modifying
  the base class.
-->

```java
// BoldDecorator, ItalicDecorator deleted.
class PlainTextRenderer {
    private boolean bold;
    private boolean italic;

    public PlainTextRenderer bold(boolean b)   { this.bold   = b; return this; }
    public PlainTextRenderer italic(boolean i) { this.italic = i; return this; }

    public String render(String text) {
        if (bold)   text = "<b>" + text + "</b>";
        if (italic) text = "<i>" + text + "</i>";
        return text;
    }
}
// Client
new PlainTextRenderer().bold(true).italic(true).render("Hello");
```

---

### D-2 · Subclass per Combination ★★★
**Realism:** ★★★ | **Compile Risk:** 🔴 High | **Scope:** ⚫ Wide
**Smell:** Subclass Explosion

<!--variant
id: D-2
realism: 3
smell: "Subclass Explosion"
task: |
  Remove the Decorator pattern from class {class_name} in file {pattern_file}.
  Replace decorator composition with one subclass per feature combination.

  Steps:
  1. Delete all concrete Decorator classes.
  2. Create a concrete subclass of the base component for each combination that is
     actually used in the codebase (e.g. `BoldTextRenderer`, `ItalicTextRenderer`,
     `BoldItalicTextRenderer`).
  3. Each subclass overrides the component method to apply its fixed set of decorations.
  4. Update all call sites to instantiate the appropriate subclass instead of composing
     decorators.

  The result cannot support new combinations without adding new subclasses, exhibiting
  Subclass Explosion.
-->

---

### D-3 · Template Method Decorator ★★★
**Realism:** ★★★ | **Compile Risk:** 🔴 High | **Scope:** ⚫ Wide
**Smell:** Fragile Base Class

<!--variant
id: D-3
realism: 3
smell: "Fragile Base Class"
task: |
  Remove the Decorator pattern from class {class_name} in file {pattern_file}.
  Replace it with a Template Method in an abstract base class that has hook methods
  for each decoration step.

  Steps:
  1. Delete all Decorator classes.
  2. Convert the Component interface to an abstract class with a final `render()` (or
     equivalent) method that calls `preProcess()` + `doRender()` + `postProcess()` in
     sequence (Template Method).
  3. Each concrete component subclass overrides the hook methods to apply its specific
     decoration.
  4. Decoration combinations require creating new subclasses.
-->

---

### D-4 · Utility / Helper Methods ★★☆
**Realism:** ★★☆ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** Feature Envy, Procedural Style

<!--variant
id: D-4
realism: 2
smell: "Feature Envy / Procedural Style"
task: |
  Remove the Decorator pattern from class {class_name} in file {pattern_file}.
  Replace decorator composition with static utility methods that apply transformations
  to a result string.

  Steps:
  1. Delete all Decorator classes and the Component interface (if only used for decoration).
  2. Create a `TextUtils` (or equivalent) utility class with static methods:
     `bold(String text)`, `italic(String text)`, etc.
  3. At call sites, replace decorator chains with nested static calls:
     `TextUtils.italic(TextUtils.bold(renderer.render("Hello")))`.
  4. The decorations are no longer composable objects; they are procedural function calls.
-->
