# Undo: Visitor

## Pattern Structure Being Removed

A `Visitor` interface declares a `visit()` method for each `ConcreteElement`. Each
`ConcreteElement` has an `accept(Visitor v)` method that calls back `v.visit(this)`.
New operations are added as new Visitor implementations without changing the element
hierarchy.

### Canonical "With Pattern" Code

```java
interface ShapeVisitor {
    void visit(Circle c);
    void visit(Rectangle r);
}

interface Shape { void accept(ShapeVisitor v); }

class Circle implements Shape {
    double radius;
    public void accept(ShapeVisitor v) { v.visit(this); }
}

class Rectangle implements Shape {
    double width, height;
    public void accept(ShapeVisitor v) { v.visit(this); }
}

class AreaCalculator implements ShapeVisitor {
    private double total = 0;
    public void visit(Circle c)    { total += Math.PI * c.radius * c.radius; }
    public void visit(Rectangle r) { total += r.width * r.height; }
    public double getTotal()       { return total; }
}
```

---

## Undo Variants (sorted by realism ★ high → low)

---

### V-1 · instanceof Chain ★★★
**Realism:** ★★★ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** Switch Statement smell

<!--variant
id: V-1
realism: 3
smell: "Switch Statement / instanceof chain"
task: |
  Remove the Visitor pattern from class {class_name} in file {pattern_file}.
  Replace the double-dispatch accept/visit mechanism with instanceof type checks.

  Steps:
  1. Delete the Visitor interface ({class_name} may be this).
  2. Delete the `accept(Visitor)` method from all Element classes.
  3. For each operation that was implemented as a Visitor, create an equivalent
     method (or utility class) that iterates over elements and uses instanceof to
     dispatch to the correct logic branch for each element type.
  4. Delete all ConcreteVisitor classes; embed their logic in the instanceof branches.

  The result has instanceof chains that must be updated whenever a new element type
  is added, exhibiting the Switch Statement smell.
-->

---

### V-2 · Iterator + Per-Element Type Filter ★★★
**Realism:** ★★★ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** Feature Envy, Code Duplication

<!--variant
id: V-2
realism: 3
smell: "Feature Envy / Code Duplication"
task: |
  Remove the Visitor pattern from class {class_name} (file {pattern_file}).
  Replace the visitor traversal with an iterator that filters elements by type and
  processes each type separately.

  Steps:
  1. Delete the Visitor interface and all ConcreteVisitor classes.
  2. Delete the `accept()` methods from Element classes.
  3. For each operation, write an external traversal that:
     (a) iterates over all elements,
     (b) filters for a specific type (using instanceof or `stream().filter()`),
     (c) casts and processes that type.
  4. Each type is processed in a separate loop/stream, so the same collection is
     iterated multiple times.
-->

---

### V-3 · Add Operation Methods to Each Element ★★★
**Realism:** ★★★ | **Compile Risk:** 🔴 High | **Scope:** ⚫ Wide
**Smell:** Divergent Change, Low Cohesion

<!--variant
id: V-3
realism: 3
smell: "Divergent Change / Low Cohesion"
task: |
  Remove the Visitor pattern from class {class_name} (file {pattern_file}).
  Move each operation directly into the Element classes as a new method.

  Steps:
  1. Delete the Visitor interface and all ConcreteVisitor implementations.
  2. Delete the `accept()` methods from each Element class.
  3. For each former Visitor operation (e.g. `AreaCalculator`), add an equivalent
     method directly on each concrete Element class (e.g. `Circle.computeArea()`,
     `Rectangle.computeArea()`).
  4. Update the caller to call the method on each element directly.

  The result adds a new method to every element class for every operation, violating
  Open-Closed Principle and exhibiting Divergent Change.
-->

---

### V-4 · God Processor Class ★★★
**Realism:** ★★★ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** God Class

<!--variant
id: V-4
realism: 3
smell: "God Class"
task: |
  Remove the Visitor pattern from class {class_name} (file {pattern_file}).
  Merge all visitor implementations into one large "processor" class with methods
  for every combination of operation × element type.

  Steps:
  1. Delete the Visitor interface.
  2. Delete `accept()` from all element classes.
  3. Create a single `ShapeProcessor` (or similar) class that has one method per
     (operation, element-type) pair, plus one dispatcher method per operation that
     uses instanceof to call the right type-specific method.
  4. Delete all individual ConcreteVisitor classes.
-->

---

### V-5 · Reflection-Based Dispatch ★★☆
**Realism:** ★★☆ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** Magic Strings, Brittle Runtime Dispatch

<!--variant
id: V-5
realism: 2
smell: "Magic Strings / Brittle Reflection"
task: |
  Remove the Visitor pattern from class {class_name} (file {pattern_file}).
  Replace double-dispatch with a reflection-based runtime dispatchinstead:
  look up a method by name using reflection on the element's concrete class.

  Steps:
  1. Delete the Visitor interface and `accept()` methods.
  2. In each operation class (formerly a Visitor), use reflection to dynamically find
     and invoke a method named `process` + element class simple name
     (e.g. `processCircle(Circle c)`).
  3. Delete the ConcreteVisitor `visit()` methods; rename them to match the reflection
     naming convention.
-->
