# Undo: Composite

## Pattern Structure Being Removed

A `Component` interface unifies `Leaf` and `Composite` nodes. `Composite` holds a
`List<Component>` and delegates `operation()` to each child recursively.

### Canonical "With Pattern" Code

```java
interface FileSystemNode {
    long size();
    void print(String indent);
}

class File implements FileSystemNode {
    private final String name; private final long bytes;
    public long size()               { return bytes; }
    public void print(String indent) { System.out.println(indent + name); }
}

class Directory implements FileSystemNode {
    private final String name;
    private final List<FileSystemNode> children = new ArrayList<>();
    public void add(FileSystemNode n) { children.add(n); }
    public long size()               { return children.stream().mapToLong(FileSystemNode::size).sum(); }
    public void print(String indent) {
        System.out.println(indent + name + "/");
        children.forEach(c -> c.print(indent + "  "));
    }
}
```

---

## Undo Variants (sorted by realism ★ high → low)

---

### C-1 · instanceof-Based Traversal ★★★
**Realism:** ★★★ | **Compile Risk:** 🟢 Low | **Scope:** 🟣 Medium
**Smell:** Switch Statement smell, Fragile Hierarchy

<!--variant
id: C-1
realism: 3
smell: "Switch Statement / instanceof chain"
task: |
  Remove the Composite pattern from class {class_name} in file {pattern_file}.
  Delete the uniform Component interface and replace recursive delegation with
  explicit instanceof dispatch.

  Steps:
  1. Delete the Component interface ({class_name} may be this interface or a class
     that uses it).
  2. Change any method that traverses the component tree to check each node's type
     with instanceof and call type-specific APIs directly.
  3. Remove uniform delegation: Leaf nodes and Composite nodes now have separate
     code paths in every traversal.

  The result has instanceof chains instead of polymorphic dispatch, exhibiting the
  Switch Statement smell.
-->

---

### C-2 · Flat List Representation ★★★
**Realism:** ★★★ | **Compile Risk:** 🔴 High | **Scope:** ⚫ Wide
**Smell:** Feature Envy, Primitive Obsession

<!--variant
id: C-2
realism: 3
smell: "Primitive Obsession / Flat Structure"
task: |
  Remove the Composite pattern from class {class_name} in file {pattern_file}.
  Replace the recursive object tree with a flat list of nodes using an adjacency-list
  (parent-ID) representation.

  Steps:
  1. Delete the Composite class and the Component interface.
  2. Introduce a single flat node class with fields: `id`, `parentId` (null for root),
     `name`, `isLeaf`, and any leaf-specific data.
  3. Replace the tree with a `List<FlatNode>`.
  4. Rewrite traversal methods (size, print, etc.) as external utility functions that
     walk the flat list using parent-ID lookups.
  5. Update all call sites to build the flat list and call the utility functions.
-->

---

### C-3 · Separate APIs for Leaf and Composite ★★★
**Realism:** ★★★ | **Compile Risk:** 🔴 High | **Scope:** ⚫ Wide
**Smell:** Parallel API explosion, Missing Abstraction

<!--variant
id: C-3
realism: 3
smell: "Missing Abstraction / API Divergence"
task: |
  Remove the Component interface ({class_name}) from file {pattern_file}.
  Leaf and Composite classes should now have entirely separate, incompatible APIs.

  Steps:
  1. Delete the Component interface.
  2. Give Leaf and Composite classes different method names for the same conceptual
     operation (e.g. Leaf uses `getSize()`, Composite uses `computeSize()`).
  3. Change any collections of components from `List<Component>` to `List<Object>` or
     parallel typed lists.
  4. Update every call site to handle the two types separately.
-->

---

### C-4 · Explicit Stack-Based Traversal at Call Site ★★☆
**Realism:** ★★☆ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** Long Method, Code Duplication

<!--variant
id: C-4
realism: 2
smell: "Long Method / Code Duplication"
task: |
  Remove the recursive `operation()` methods from the Composite in {class_name}
  (file {pattern_file}). Instead, perform traversal externally using an iterative
  DFS stack.

  Steps:
  1. Remove `size()` and `print()` (or equivalent) from the Composite class (retain
     on Leaf if needed for the base case).
  2. Add an external utility class or static method that traverses the tree using an
     explicit `Deque<Component>` stack.
  3. The traversal must use instanceof to distinguish Leaf from Composite nodes.
-->

---

### C-5 · God Composite — Merge Leaf and Directory ★★☆
**Realism:** ★★☆ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** God Class, Schizophrenic Class

<!--variant
id: C-5
realism: 2
smell: "God Class / Schizophrenic Class"
task: |
  Remove the separate Leaf and Composite classes from the {class_name} hierarchy
  (file {pattern_file}). Merge them into one class with a boolean flag.

  Steps:
  1. Delete the separate Leaf and Composite classes.
  2. Create a single merged class with a `boolean isLeaf` (or `isDirectory`) field.
  3. Operations that apply only to Composites (e.g. `add()`, `getChildren()`) throw
     `UnsupportedOperationException` when called on a Leaf instance.
  4. Operations use if/else on the flag to select the right behaviour.
  5. Update all call sites.
-->
