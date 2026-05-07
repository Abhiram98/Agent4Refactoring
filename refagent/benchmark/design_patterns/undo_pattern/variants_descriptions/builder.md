# Undo: Builder

## Pattern Structure Being Removed

A `Builder` (inner or separate) class exposes fluent `setX()` methods returning `this`,
accumulates parameters, and produces an immutable product via a terminal `build()` call.
The product's constructor is private, accepting only the builder.

### Canonical "With Pattern" Code

```java
// --- Product (immutable) ---
class Table {
    private final String name;
    private final int operationTimeoutMs;
    private final int readRpcTimeoutMs;
    private final int writeRpcTimeoutMs;

    private Table(Builder b) {      // private — only the builder can call this
        this.name                = b.name;
        this.operationTimeoutMs  = b.operationTimeoutMs;
        this.readRpcTimeoutMs    = b.readRpcTimeoutMs;
        this.writeRpcTimeoutMs   = b.writeRpcTimeoutMs;
    }

    // --- Builder ---
    public static class Builder {
        private final String name;          // required
        private int operationTimeoutMs = 30_000;   // defaults
        private int readRpcTimeoutMs   = 5_000;
        private int writeRpcTimeoutMs  = 5_000;

        public Builder(String name) { this.name = name; }

        public Builder setOperationTimeout(int ms) { this.operationTimeoutMs = ms; return this; }
        public Builder setReadRpcTimeout(int ms)   { this.readRpcTimeoutMs   = ms; return this; }
        public Builder setWriteRpcTimeout(int ms)  { this.writeRpcTimeoutMs  = ms; return this; }
        public Table build()                       { return new Table(this); }
    }
}

// --- Client ---
Table t = new Table.Builder("orders")
    .setOperationTimeout(10_000)
    .setReadRpcTimeout(2_000)
    .build();
```

---

## Undo Variants (sorted by realism ★ high → low)

---

### B-1 · Telescoping Constructors ★★★
**Realism:** ★★★ | **Compile Risk:** 🔴 High | **Scope:** ⚫ Wide
**Smell:** Long Parameter List, Combinatorial Explosion

<!--variant
id: B-1
realism: 3
smell: "Long Parameter List"
task: |
  Remove the Builder pattern from class {class_name} in file {pattern_file}.
  Replace the builder with telescoping constructors on the product class.

  Steps:
  1. Identify the product class that the builder constructs (the class with the private
     constructor accepting the builder). Make its constructor(s) public.
  2. Add multiple overloaded public constructors for the most common combinations of
     parameters. Each constructor should delegate to a fully-parameterised one using
     `this(...)`.
  3. Delete the {class_name} builder class (and any inner Builder class) entirely.
  4. Find every call site that used the builder (search for `new {class_name}.Builder`
     or `{class_name}.builder()` or similar) and replace each with a direct constructor
     call using the appropriate overload.
  5. Ensure the product class fields are no longer final if they were set only via the
     builder — or keep them final and ensure all constructors initialise them.

  The resulting code should have constructors with 3 or more parameters on the product
  class, exhibiting the Long Parameter List code smell.
-->

Restore multiple overloaded constructors on the product, one per common combination of
parameters. Every call site must be updated to use the right overload.

```java
class Table {
    // ...
    public Table(String name) { this(name, 30_000, 5_000, 5_000); }
    public Table(String name, int operationTimeoutMs) { this(name, operationTimeoutMs, 5_000, 5_000); }
    public Table(String name, int operationTimeoutMs, int readRpcTimeoutMs) { ... }
    public Table(String name, int operationTimeoutMs, int readRpcTimeoutMs, int writeRpcTimeoutMs) { ... }
}

// Client: positional confusion — which arg is which?
Table t = new Table("orders", 10_000, 2_000);
```

**What's smelly:** Callers must remember the argument order. Adding a new optional field
requires a new family of constructors.

---

### B-2 · All-Args Constructor ★★★
**Realism:** ★★★ | **Compile Risk:** 🔴 High | **Scope:** ⚫ Wide
**Smell:** Long Parameter List

<!--variant
id: B-2
realism: 3
smell: "Long Parameter List"
task: |
  Remove the Builder pattern from class {class_name} in file {pattern_file}.
  Replace the builder with a single all-arguments constructor on the product class.

  Steps:
  1. Identify the product class and make it have one public constructor accepting
     ALL configuration fields as parameters (including optional ones).
  2. For optional parameters that previously had defaults in the builder, use sentinel
     values (e.g. -1 for ints, null for objects) to indicate "use default".
  3. Delete the {class_name} builder class entirely.
  4. Update all call sites to invoke the new all-args constructor, passing null or -1
     for parameters they do not wish to configure.

  The resulting code should have a single constructor with many parameters exhibiting
  the Long Parameter List code smell, with callers forced to pass sentinel/null values.
-->

```java
class Table {
    public Table(String name, int operationTimeoutMs, int readRpcTimeoutMs, int writeRpcTimeoutMs) {
        this.operationTimeoutMs = operationTimeoutMs < 0 ? 30_000 : operationTimeoutMs;
        // ...
    }
}
// Client
Table t = new Table("orders", 10_000, 2_000, -1);  // -1 = use default
```

**What's smelly:** The `-1` sentinel is a magic number. Every caller must provide every argument.

---

### B-3 · Plain Mutable Config Object ★★★
**Realism:** ★★★ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** Missing Encapsulation, Mutable DTO

<!--variant
id: B-3
realism: 3
smell: "Missing Encapsulation"
task: |
  Remove the Builder pattern from class {class_name} in file {pattern_file}.
  Replace the builder with a plain mutable configuration POJO.

  Steps:
  1. Create a new class (e.g. `<ProductName>Config`) with public fields (or simple
     getters/setters) for each configurable parameter, with field initialisers for
     defaults.
  2. Change the product class to accept a `<ProductName>Config` object in its
     constructor instead of a builder.
  3. Delete the {class_name} builder class entirely.
  4. At all call sites, replace the builder chain with: create a config object, set
     the desired fields, then call the product constructor.

  The config object must be mutable (public fields or setters with no build() step),
  exhibiting the Missing Encapsulation smell.
-->

---

### B-4 · Non-Fluent Setter Object ★★★
**Realism:** ★★★ | **Compile Risk:** 🟢 Low | **Scope:** 🔵 Local
**Smell:** Boilerplate proliferation, Missing Fluency

<!--variant
id: B-4
realism: 3
smell: "Missing Fluency / Boilerplate"
task: |
  Degrade the Builder pattern in class {class_name} in file {pattern_file} by removing
  method chaining (fluency) from all setter methods.

  Steps:
  1. Change every setter method in {class_name} from `return this` (returning the
     builder) to `return void`.
  2. Update all call sites: replace each fluent chain
     (`builder.setA(x).setB(y).build()`) with separate statements
     (`builder.setA(x); builder.setB(y); builder.build();`).
  3. Keep the builder class itself; only the return types of setters change.

  The resulting code retains a builder class but loses its defining characteristic —
  fluent chaining — exhibiting the Boilerplate Proliferation smell.
-->

---

### B-5 · Static Factory Methods with Named Variants ★★☆
**Realism:** ★★☆ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** Divergent Change, Primitive Obsession

<!--variant
id: B-5
realism: 2
smell: "Divergent Change"
task: |
  Remove the Builder pattern from class {class_name} in file {pattern_file}.
  Replace the builder with static factory methods encoding common presets.

  Steps:
  1. Create a utility class (e.g. `<ProductName>Factory`) with static methods for
     each common combination of parameters (e.g. `withDefaults(name)`,
     `withCustomTimeout(name, timeoutMs)`).
  2. Delete the {class_name} builder class.
  3. Update call sites to use the appropriate static factory method.
-->

---

### B-6 · Property Map / Stringly-Typed Config ★★☆
**Realism:** ★★☆ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** Magic Strings, Missing Type Safety

<!--variant
id: B-6
realism: 2
smell: "Magic Strings"
task: |
  Replace the typed setters in class {class_name} (file {pattern_file}) with a single
  `setProperty(String key, Object value)` method backed by a HashMap.

  Steps:
  1. Replace all typed setter methods with one method:
     `public {class_name} setProperty(String key, Object value)`.
  2. Store all values in an internal `Map<String, Object>`.
  3. In the `build()` method, read each parameter by key string (with defaults for
     missing keys) and use them to construct the product.
  4. Update all call sites to use `setProperty("keyName", value)` string-keyed calls.

  The result should have no compile-time safety for property names, exhibiting the
  Magic Strings smell.
-->
