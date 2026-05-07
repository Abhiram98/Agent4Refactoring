# Undo: Adapter

## Pattern Structure Being Removed

An `Adapter` class implements a `Target` interface while internally delegating to an
`Adaptee` whose API is incompatible. The client sees only the `Target` interface.

### Canonical "With Pattern" Code

```java
interface PagerAdapter {
    int getCount();
    Object getItem(int position);
}

class BookContents {                      // Adaptee — incompatible API
    public List<Chapter> chapters() { return List.of(); }
    public Chapter chapterAt(int idx) { return null; }
}

class ContentsAdapter implements PagerAdapter {  // Adapter
    private final BookContents contents;
    ContentsAdapter(BookContents c) { this.contents = c; }
    public int getCount()          { return contents.chapters().size(); }
    public Object getItem(int pos) { return contents.chapterAt(pos); }
}
```

---

## Undo Variants (sorted by realism ★ high → low)

---

### A-1 · instanceof Dispatch in Client ★★★
**Realism:** ★★★ | **Compile Risk:** 🟢 Low | **Scope:** 🔵 Local
**Smell:** Switch Statement smell

<!--variant
id: A-1
realism: 3
smell: "Switch Statement / instanceof chain"
task: |
  Remove the Adapter class ({class_name}) from file {pattern_file}.
  Replace it with instanceof type-dispatch in the client.

  Steps:
  1. Delete the {class_name} adapter class.
  2. Find the client code that previously called the adapter. Change it to accept
     `Object` (or a common supertype) and add an instanceof check to dispatch to the
     correct API branch (Adaptee API vs Target API).
  3. Directly call the Adaptee methods where the adapter previously translated.

  The result should have an instanceof / type-check dispatch replacing the adapter,
  exhibiting the Switch Statement smell and tightly coupling the client to the Adaptee.
-->

---

### A-2 · Modify Client to Call Adaptee Directly ★★★
**Realism:** ★★★ | **Compile Risk:** 🔴 High | **Scope:** ⚫ Wide
**Smell:** Tight Coupling, Shotgun Surgery

<!--variant
id: A-2
realism: 3
smell: "Tight Coupling"
task: |
  Remove the Adapter pattern. Delete the {class_name} adapter class (file {pattern_file})
  and update all client code to call the Adaptee directly.

  Steps:
  1. Delete the {class_name} adapter class and the Target interface (if it has no other
     implementors).
  2. Find every call site that used the Target interface via the adapter.
  3. Replace each with a direct call to the corresponding Adaptee method.
  4. The client field/parameter type changes from the Target interface to the Adaptee class.

  The result couples the client directly to the Adaptee, exhibiting Tight Coupling.
-->

---

### A-3 · Data Conversion Pre-Pass at Every Call Site ★★★
**Realism:** ★★★ | **Compile Risk:** 🟡 Medium | **Scope:** ⚫ Wide
**Smell:** Code Duplication, Shotgun Surgery

<!--variant
id: A-3
realism: 3
smell: "Code Duplication"
task: |
  Remove the {class_name} adapter class (file {pattern_file}).
  Instead, duplicate the conversion logic at every call site.

  Steps:
  1. Delete {class_name}.
  2. At each call site that previously used the adapter, inline the conversion:
     retrieve the Adaptee object and manually transform it to the form the client needs
     (e.g. convert a list of chapters to a list of fragments inline).
  3. This conversion must be repeated independently at every call site.

  The result scatters the translation logic across multiple files, exhibiting
  Code Duplication and Shotgun Surgery.
-->

---

### A-4 · Direct Interface Implementation (Event Adapter) ★★★
**Realism:** ★★★ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** Boilerplate proliferation

<!--variant
id: A-4
realism: 3
smell: "Boilerplate proliferation"
task: |
  If {class_name} (file {pattern_file}) is a listener/event adapter (an abstract class
  providing no-op implementations of a multi-method interface), remove it.

  Steps:
  1. Delete the abstract {class_name} adapter class.
  2. Find every class that extended {class_name}. Change each to directly implement the
     full listener interface instead.
  3. Each implementing class must now provide explicit empty/stub implementations for all
     interface methods it does not care about.

  The result forces every listener to implement ALL interface methods with empty stubs,
  exhibiting Boilerplate Proliferation.
-->

---

### A-5 · Default Interface Methods ★★★
**Realism:** ★★★ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** Interface carrying implementation

<!--variant
id: A-5
realism: 3
smell: "Interface carrying implementation"
task: |
  If {class_name} (file {pattern_file}) is an event/listener adapter, replace it with
  `default` method implementations on the Target interface itself.

  Steps:
  1. Delete the abstract {class_name} adapter class.
  2. Move its no-op method bodies into the Target interface as `default` methods.
  3. Update classes that extended {class_name} to now implement the interface directly.

  The result embeds implementation logic in an interface, violating interface/implementation
  separation.
-->

---

### A-6 · Subclass the Adaptee (Class Adapter) ★★★
**Realism:** ★★★ | **Compile Risk:** 🔴 High | **Scope:** ⚫ Wide
**Smell:** Fragile Base Class, Inappropriate Inheritance

<!--variant
id: A-6
realism: 3
smell: "Inappropriate Inheritance"
task: |
  Replace the object-adapter composition in {class_name} (file {pattern_file}) with
  inheritance: make the adapter extend the Adaptee class directly.

  Steps:
  1. Change {class_name} from holding an Adaptee field (composition) to extending the
     Adaptee class (inheritance).
  2. Remove the Adaptee field and constructor parameter; call Adaptee methods via
     `super` or direct inheritance.
  3. Update call sites that previously passed an Adaptee instance to the adapter's
     constructor — they no longer need to.

  The result leaks the full Adaptee API to clients through inheritance, exhibiting
  Inappropriate Inheritance and Fragile Base Class.
-->
