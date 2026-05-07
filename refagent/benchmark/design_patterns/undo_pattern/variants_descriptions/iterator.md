# Undo: Iterator

## Pattern Structure Being Removed

An `Iterator` interface exposes `hasNext()` / `next()`. A `ConcreteIterator` traverses
a `ConcreteCollection` without exposing its internal representation.

### Canonical "With Pattern" Code

```java
interface BookmarkIterator { boolean hasNext(); Bookmark next(); }

interface BookmarkCollection { BookmarkIterator iterator(); }

class BookmarkFolder implements BookmarkCollection {
    private final Bookmark[] bookmarks;
    private int count = 0;
    BookmarkFolder(int capacity) { this.bookmarks = new Bookmark[capacity]; }
    public void add(Bookmark b) { bookmarks[count++] = b; }
    public BookmarkIterator iterator() { return new ArrayBookmarkIterator(bookmarks, count); }

    private static class ArrayBookmarkIterator implements BookmarkIterator {
        private final Bookmark[] items; private final int count; private int cursor = 0;
        ArrayBookmarkIterator(Bookmark[] items, int count) { this.items = items; this.count = count; }
        public boolean hasNext() { return cursor < count; }
        public Bookmark next()   { return items[cursor++]; }
    }
}
```

---

## Undo Variants (sorted by realism ★ high → low)

---

### I-1 · Expose Internal Collection via getAll() ★★★
**Realism:** ★★★ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** Missing Encapsulation, Aliasing Risk

<!--variant
id: I-1
realism: 3
smell: "Missing Encapsulation"
task: |
  Remove the Iterator pattern from class {class_name} in file {pattern_file}.
  Delete the iterator class and expose the internal collection directly via a getter.

  Steps:
  1. Delete the Iterator interface and the ConcreteIterator class(es).
  2. Add a public `getAll()` method to {class_name} that returns the backing collection
     directly (not a defensive copy).
  3. Update all call sites: replace `iterator()` / `hasNext()` / `next()` loops with
     a for-each over the returned collection.

  The result exposes the internal collection to external mutation, exhibiting the
  Missing Encapsulation smell.
-->

---

### I-2 · Index-Based Access (get(i) + size()) ★★★
**Realism:** ★★★ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** Inappropriate Intimacy, Leaked Indexing

<!--variant
id: I-2
realism: 3
smell: "Inappropriate Intimacy"
task: |
  Remove the Iterator pattern from class {class_name} in file {pattern_file}.
  Delete the iterator and expose index-based access methods instead.

  Steps:
  1. Delete the Iterator and ConcreteIterator classes.
  2. Add `int size()` and `<T> get(int index)` methods to {class_name} that expose the
     backing array/list by index.
  3. Update all call sites to use `for (int i = 0; i < collection.size(); i++)` loops.

  The result leaks the indexable structure of the collection to all clients, exhibiting
  the Inappropriate Intimacy smell.
-->

---

### I-3 · Internal forEach(Consumer) ★★★
**Realism:** ★★★ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** No External Control / Cannot Short-Circuit

<!--variant
id: I-3
realism: 3
smell: "No External Control"
task: |
  Remove the Iterator from class {class_name} (file {pattern_file}).
  Replace it with an internal `forEach(Consumer<T>)` method on the collection.

  Steps:
  1. Delete the Iterator and ConcreteIterator classes.
  2. Add a `forEach(Consumer<Bookmark> action)` method to {class_name} that iterates
     internally and calls `action.accept(element)` for each element.
  3. Update all call sites to use the lambda-based forEach.

  The result cannot short-circuit traversal (no `break` inside a lambda) and cannot
  support interleaved traversal, exhibiting the No External Control smell.
-->

---

### I-4 · Snapshot / Copy-then-Iterate ★★☆
**Realism:** ★★☆ | **Compile Risk:** 🟢 Low | **Scope:** 🟣 Medium
**Smell:** Unnecessary Copying, Memory Waste

<!--variant
id: I-4
realism: 2
smell: "Unnecessary Copying"
task: |
  Remove the Iterator from class {class_name} (file {pattern_file}).
  Add a `snapshot()` method that returns a full copy of the collection on every call.

  Steps:
  1. Delete Iterator and ConcreteIterator classes.
  2. Add a `List<Bookmark> snapshot()` method that creates a defensive copy each time.
  3. Update call sites to call `snapshot()` and iterate over the copy.
-->

---

### I-5 · Legacy Enumeration ★★☆
**Realism:** ★★☆ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** Inappropriate Use of Legacy API

<!--variant
id: I-5
realism: 2
smell: "Legacy API / Reduced Expressiveness"
task: |
  Replace the custom Iterator in class {class_name} (file {pattern_file}) with
  Java's legacy `java.util.Enumeration` interface.

  Steps:
  1. Delete the custom Iterator interface and ConcreteIterator.
  2. Add an `elements()` method to {class_name} returning `Enumeration<Bookmark>`
     (use `Collections.enumeration(list)`).
  3. Update call sites to use `hasMoreElements()` / `nextElement()` instead of
     the enhanced for-each loop.
-->
