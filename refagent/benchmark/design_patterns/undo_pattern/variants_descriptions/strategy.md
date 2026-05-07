# Undo: Strategy

## Pattern Structure Being Removed

A `Strategy` interface declares the algorithm contract. Multiple `ConcreteStrategy`
classes implement it. A `Context` holds a `Strategy` reference set at construction or
via a setter, and delegates algorithm execution to `strategy.execute(...)`. The key
property: the algorithm is **swappable at runtime**.

### Canonical "With Pattern" Code

```java
interface SortStrategy {
    void sort(int[] data);
}

class BubbleSort implements SortStrategy {
    public void sort(int[] data) { /* bubble sort */ }
}

class QuickSort implements SortStrategy {
    public void sort(int[] data) { /* quicksort */ }
}

class Sorter {
    private SortStrategy strategy;   // injected — swappable at runtime

    Sorter(SortStrategy strategy) { this.strategy = strategy; }

    public void setStrategy(SortStrategy s) { this.strategy = s; }

    public void doSort(int[] data) { strategy.sort(data); }
}

// Client
Sorter sorter = new Sorter(new BubbleSort());
sorter.doSort(data);
sorter.setStrategy(new QuickSort());    // swap at runtime
sorter.doSort(data);
```

---

## Undo Variants (sorted by realism ★ high → low)

---

### S-1 · Inline switch/if-else ★★★
**Realism:** ★★★ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** Switch Statement smell, Open-Closed violation

<!--variant
id: S-1
realism: 3
smell: "Switch Statement"
task: |
  Remove the Strategy pattern from class {class_name} in file {pattern_file}.
  Replace the strategy dispatch with an inline switch or if-else inside the context.

  Steps:
  1. Delete the Strategy interface and all ConcreteStrategy classes.
  2. In the Context class ({class_name}), replace the `strategy` field with a type
     discriminator (e.g. an enum or String field like `private String algorithmType`).
  3. In the method that previously called `strategy.execute(...)`, replace the
     delegation with a switch or if-else block that contains the algorithm logic
     for each case inline.
  4. Update all call sites that previously passed a ConcreteStrategy to instead pass
     a type string/enum to the context constructor or setter.

  The resulting code must have an explicit switch or if-else on algorithm type,
  making it impossible to add a new algorithm without modifying the context class.
-->

```java
// BubbleSort, QuickSort classes deleted.

class Sorter {
    private String algorithm;  // "bubble" or "quick"

    Sorter(String algorithm) { this.algorithm = algorithm; }

    public void doSort(int[] data) {
        switch (algorithm) {           // ← Switch Statement smell
            case "bubble": /* inline bubble sort */ break;
            case "quick":  /* inline quicksort */   break;
            default: throw new IllegalArgumentException("Unknown: " + algorithm);
        }
    }
}
```

---

### S-2 · Replace with Lambda / Functional Interface ★★★
**Realism:** ★★★ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** Loss of Encapsulation, Inline Logic

<!--variant
id: S-2
realism: 3
smell: "Loss of Encapsulation"
task: |
  Remove the Strategy pattern from class {class_name} in file {pattern_file}.
  Replace the Strategy interface and ConcreteStrategy classes with lambdas passed
  directly at call sites.

  Steps:
  1. Delete all ConcreteStrategy classes.
  2. Replace the Strategy interface with Java's built-in `Consumer<int[]>` (or a
     similar functional interface), OR keep a simple `@FunctionalInterface` version
     of the strategy type but remove all named implementing classes.
  3. Update the context class to hold a `Consumer<int[]>` (or the functional type).
  4. At every call site that previously passed a `new ConcreteStrategy()`, replace
     with an inline lambda: `new Sorter(data -> { /* algorithm inline */ })`.

  The resulting code should have algorithm logic inlined as lambdas with no named
  strategy classes, reducing reusability and discoverability.
-->

---

### S-3 · Hardcode a Single Algorithm ★★★
**Realism:** ★★★ | **Compile Risk:** 🔴 High | **Scope:** ⚫ Wide
**Smell:** Hardcoded Behaviour, No Extensibility

<!--variant
id: S-3
realism: 3
smell: "Hardcoded Behaviour"
task: |
  Remove the Strategy pattern from class {class_name} in file {pattern_file}.
  Hardcode a single algorithm directly in the context; remove all strategy extensibility.

  Steps:
  1. Delete the Strategy interface and all ConcreteStrategy classes.
  2. Remove the `strategy` field from the Context.
  3. Inline the most common algorithm's logic directly inside the context's dispatch
     method, with no ability to swap it.
  4. Update all call sites that previously configured a strategy — remove that
     configuration.
-->

---

### S-4 · Subclass per Algorithm ★★★
**Realism:** ★★★ | **Compile Risk:** 🔴 High | **Scope:** ⚫ Wide
**Smell:** Parallel Inheritance Hierarchy, Fragile Base Class

<!--variant
id: S-4
realism: 3
smell: "Parallel Inheritance Hierarchy"
task: |
  Remove the Strategy pattern from class {class_name} in file {pattern_file}.
  Replace composition with inheritance: create one subclass of the Context per algorithm.

  Steps:
  1. Delete the Strategy interface and ConcreteStrategy classes.
  2. For each former ConcreteStrategy, create a subclass of the Context class that
     overrides the algorithm method and bakes in that specific algorithm.
  3. Remove the `strategy` field and the setter from the Context.
  4. Update call sites: instead of `new Context(new ConcreteStrategy())`, use
     `new ConcreteAlgorithmContext()` directly.

  The resulting code can no longer swap algorithms at runtime, exhibiting the
  Parallel Inheritance Hierarchy smell.
-->

---

### S-5 · Enum-Dispatched Strategy ★★★
**Realism:** ★★★ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** Switch Statement (via enum ordinal)

<!--variant
id: S-5
realism: 3
smell: "Switch Statement via Enum"
task: |
  Remove the Strategy pattern from class {class_name} in file {pattern_file}.
  Replace it with an enum whose constants implement the algorithm directly.

  Steps:
  1. Delete the Strategy interface and ConcreteStrategy classes.
  2. Create an enum (e.g. `SortAlgorithm`) with one constant per algorithm.
  3. Either (a) add an abstract method to the enum that each constant implements, or
     (b) use a switch in the context on the enum value.
  4. Replace the `strategy` field in the Context with the enum type.
  5. Update call sites to pass the enum constant instead of a strategy object.
-->

---

### S-6 · Context Conditionals via Boolean Flags ★★☆
**Realism:** ★★☆ | **Compile Risk:** 🟢 Low | **Scope:** 🔵 Local
**Smell:** Speculative Generality, Primitive Obsession

<!--variant
id: S-6
realism: 2
smell: "Primitive Obsession / Boolean Flags"
task: |
  Remove the Strategy pattern from class {class_name} in file {pattern_file}.
  Replace the strategy object with multiple boolean/int flags on the context, one
  per algorithm option.

  Steps:
  1. Delete the Strategy interface and ConcreteStrategy classes.
  2. Replace the `strategy` field with boolean/int configuration flags
     (e.g. `private boolean useQuickSort;`, `private boolean useMergeSort;`).
  3. In the dispatch method, use if/else on the flags to choose the algorithm.
  4. Update call sites to set the appropriate flags instead of passing a strategy.
-->
