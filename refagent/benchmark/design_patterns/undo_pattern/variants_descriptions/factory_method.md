# Undo: Factory Method

## Pattern Structure Being Removed

A `Creator` class (abstract or concrete) declares a `factoryMethod()` that returns a
`Product` interface. Each `ConcreteCreator` overrides the factory method to instantiate
a specific `ConcreteProduct`. The client works through the `Creator` and `Product`
interfaces — never touching concrete classes directly.

### Canonical "With Pattern" Code

```java
interface Notification {
    void send(String message);
}

class EmailNotification implements Notification {
    public void send(String message) { System.out.println("Email: " + message); }
}

class SMSNotification implements Notification {
    public void send(String message) { System.out.println("SMS: " + message); }
}

abstract class NotificationFactory {
    public abstract Notification createNotification();   // factory method

    public void notify(String message) {
        Notification n = createNotification();
        n.send(message);
    }
}

class EmailFactory extends NotificationFactory {
    public Notification createNotification() { return new EmailNotification(); }
}

class SMSFactory extends NotificationFactory {
    public Notification createNotification() { return new SMSNotification(); }
}

// Client — works through the abstract factory, never new-ing a concrete class
NotificationFactory factory = new EmailFactory();
factory.notify("Hello");
```

---

## Undo Variants (sorted by realism ★ high → low)

---

### FM-1 · switch/if-else Dispatcher ★★★
**Realism:** ★★★ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** Switch Statement smell

<!--variant
id: FM-1
realism: 3
smell: "Switch Statement"
task: |
  Remove the Factory Method pattern from class {class_name} in file {pattern_file}.
  Replace the factory hierarchy with a single switch/if-else dispatcher.

  Steps:
  1. Delete (or collapse) the abstract creator class ({class_name}) and all concrete
     creator subclasses.
  2. Create a single static method (e.g. `NotificationFactory.create(String type)`)
     that uses a switch or if-else chain to instantiate the correct concrete product.
  3. The concrete product classes (EmailNotification, SMSNotification, …) may remain,
     but the Creator hierarchy and the `createNotification()` polymorphism are removed.
  4. Update all call sites that previously chose a ConcreteCreator to instead call the
     static dispatcher with a type string/enum.

  The resulting code should have a switch or if-else dispatch on type, exhibiting the
  Switch Statement / Open-Closed violation smell.
-->

All `ConcreteCreator` subclasses are deleted. A single static method dispatches by type:

```java
// ConcreteCreator classes deleted.
class NotificationFactory {
    public static Notification create(String type) {
        switch (type) {
            case "email": return new EmailNotification();
            case "sms":   return new SMSNotification();
            default: throw new IllegalArgumentException("Unknown type: " + type);
        }
    }
}
// Client
Notification n = NotificationFactory.create("email");
n.send("Hello");
```

**What's smelly:** Adding a new notification type requires modifying `NotificationFactory`.

---

### FM-2 · Direct Instantiation at Call Sites ★★★
**Realism:** ★★★ | **Compile Risk:** 🔴 High | **Scope:** ⚫ Wide
**Smell:** Tight Coupling

<!--variant
id: FM-2
realism: 3
smell: "Tight Coupling"
task: |
  Remove the Factory Method pattern from class {class_name} in file {pattern_file}.
  Delete the factory class and instantiate concrete products directly at every call site.

  Steps:
  1. Delete the {class_name} creator class and all concrete creator subclasses.
  2. At each call site that previously used the factory, replace the factory call with
     a direct `new ConcreteProduct()` instantiation.
  3. Ensure call sites now import / reference the concrete product class directly.

  The resulting code should use direct `new ConcreteProduct()` at each call site,
  exhibiting Tight Coupling (callers depend on concrete classes, not abstractions).
-->

---

### FM-3 · Static Utility Class ★★★
**Realism:** ★★★ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** Utility Class, Low Cohesion

<!--variant
id: FM-3
realism: 3
smell: "Utility Class / Low Cohesion"
task: |
  Remove the Factory Method pattern from class {class_name} in file {pattern_file}.
  Collapse the factory hierarchy into a single non-instantiable utility class with
  one static `create(type)` method.

  Steps:
  1. Delete all concrete creator subclasses.
  2. Convert {class_name} into a final class with a private constructor and a single
     static method `create(String type)` that returns the product.
  3. Inside `create`, use a switch or if-else to instantiate the right product.
  4. Update call sites to use `ClassName.create("type")`.
-->

---

### FM-4 · God-Class Creator ★★☆
**Realism:** ★★☆ | **Compile Risk:** 🔴 High | **Scope:** ⚫ Wide
**Smell:** God Class

<!--variant
id: FM-4
realism: 2
smell: "God Class"
task: |
  Remove the Factory Method pattern from class {class_name} in file {pattern_file}.
  Merge all ConcreteProduct logic directly into a single God Creator class.

  Steps:
  1. Delete all ConcreteProduct classes; move their logic into {class_name} itself.
  2. Use instance fields or constructor parameters to determine which "product behaviour"
     the class exhibits (e.g. `private String mode;`).
  3. Replace polymorphic method calls with if/else blocks keyed on `mode`.
  4. Delete all concrete creator subclasses.
-->

---

### FM-5 · Reflection-Based Factory ★★☆
**Realism:** ★★☆ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** Magic Strings, Brittle Reflection

<!--variant
id: FM-5
realism: 2
smell: "Magic Strings / Brittle Reflection"
task: |
  Remove the Factory Method hierarchy from {class_name} in file {pattern_file}.
  Replace it with a single reflection-based factory: store class names as strings in a
  registry map and instantiate via `Class.forName(...).getDeclaredConstructor().newInstance()`.

  Steps:
  1. Delete all concrete creator subclasses.
  2. In {class_name}, maintain a `Map<String, String>` mapping type keys to fully-qualified
     class names.
  3. Replace the factory method with reflection: `Class.forName(registry.get(type)).newInstance()`.
  4. Update call sites to pass type-key strings.

  The result should rely on string-based class names at runtime, exhibiting the
  Magic Strings / Brittle Reflection code smell.
-->
