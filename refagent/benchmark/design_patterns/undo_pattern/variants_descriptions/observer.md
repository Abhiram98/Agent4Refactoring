# Undo: Observer

## Pattern Structure Being Removed

A `Subject` (or `Observable`) maintains a list of `Observer` objects and notifies all of
them by calling `update()` when its state changes. Observers register/deregister at
runtime. The subject knows nothing about concrete observer types.

### Canonical "With Pattern" Code

```java
interface Observer { void update(String event); }

class EventBus {
    private final List<Observer> listeners = new ArrayList<>();
    public void subscribe(Observer o)   { listeners.add(o);    }
    public void unsubscribe(Observer o) { listeners.remove(o); }
    private void notifyAll(String event) {
        listeners.forEach(o -> o.update(event));
    }
    public void publish(String event) { notifyAll(event); }
}

class LogListener implements Observer {
    public void update(String event) { System.out.println("Log: " + event); }
}
```

---

## Undo Variants (sorted by realism ★ high → low)

---

### O-1 · Polling (Remove Push Notification) ★★★
**Realism:** ★★★ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** Polling / Busy-wait

<!--variant
id: O-1
realism: 3
smell: "Polling / Busy-wait"
task: |
  Remove the Observer pattern from class {class_name} in file {pattern_file}.
  Replace the push notification mechanism with polling: expose a state getter and
  remove all subscribe/notify infrastructure.

  Steps:
  1. Delete the Observer interface and all ConcreteObserver classes.
  2. Remove the observer list, `subscribe()`, `unsubscribe()`, and `notifyAll()`
     methods from {class_name}.
  3. Add a public getter for the subject's state (e.g. `getLatestEvent()`) so callers
     can poll for changes.
  4. Update all former observers: they must now periodically call the getter themselves,
     typically in a loop with a sleep. If there is no obvious loop, add a comment where
     polling would occur.

  The resulting code should have no observer list and no push notification, exhibiting
  the Polling smell (consumers must actively query for state).
-->

---

### O-2 · Direct Method Call on Concrete Dependents ★★★
**Realism:** ★★★ | **Compile Risk:** 🔴 High | **Scope:** ⚫ Wide
**Smell:** Tight Coupling

<!--variant
id: O-2
realism: 3
smell: "Tight Coupling"
task: |
  Remove the Observer pattern from class {class_name} in file {pattern_file}.
  Replace dynamic observer dispatch with direct method calls on each concrete dependent.

  Steps:
  1. Delete the Observer interface.
  2. Replace the `List<Observer>` field in {class_name} with explicit typed references
     to each concrete dependent class (e.g. `private LogListener logListener;`,
     `private MetricsListener metricsListener;`).
  3. Replace the `notifyAll()` / `publish()` loop with direct method calls on each
     concrete reference.
  4. Remove or replace `subscribe()`/`unsubscribe()` with explicit setter/constructor
     injection for each concrete dependent.

  The resulting code directly couples the subject to every concrete observer class.
-->

---

### O-3 · Lambda / Consumer Callbacks ★★★
**Realism:** ★★★ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** Loss of Identity / Unsubscribable Callbacks

<!--variant
id: O-3
realism: 3
smell: "Loss of Identity / Unsubscribable Callbacks"
task: |
  Remove the Observer interface and ConcreteObserver classes from file {pattern_file}.
  Replace them with `Consumer<T>` lambda callbacks registered directly on {class_name}.

  Steps:
  1. Delete the Observer interface and all ConcreteObserver classes.
  2. Change the listener list from `List<Observer>` to `List<Consumer<String>>` (or the
     appropriate event type).
  3. Rename `subscribe(Observer o)` to `addListener(Consumer<String> c)`.
  4. Update all call sites to pass lambdas instead of Observer objects:
     `bus.addListener(event -> System.out.println("Log: " + event));`
  5. Remove `unsubscribe()` (lambdas have no identity for removal).
-->

---

### O-4 · Pull Observer (Expose State, Observer Pulls) ★★★
**Realism:** ★★★ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** Inappropriate Intimacy

<!--variant
id: O-4
realism: 3
smell: "Inappropriate Intimacy"
task: |
  Modify the Observer pattern in {class_name} (file {pattern_file}) to use pull instead
  of push: pass the entire subject reference in `update()` so observers must query it.

  Steps:
  1. Change the Observer interface's `update` signature from `update(Event event)` to
     `update({class_name} subject)` — passing the whole subject.
  2. Remove the event payload from the notification call inside {class_name}.
  3. Update all ConcreteObserver `update()` implementations to call getters on the
     subject to retrieve whatever data they need.

  The result couples each observer to the subject's full API instead of just the
  event payload, exhibiting the Inappropriate Intimacy smell.
-->

---

### O-5 · Synchronous Event Bus / Mediator ★★★
**Realism:** ★★★ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** God Object (Centralised Mediator)

<!--variant
id: O-5
realism: 3
smell: "God Object / Mediator"
task: |
  Remove the direct Observer registration from {class_name} (file {pattern_file}).
  Introduce a global singleton EventBus that all subjects and observers go through.

  Steps:
  1. Create a singleton `EventBus` class with `subscribe(String topic, Consumer<Event>)`
     and `publish(String topic, Event event)` methods.
  2. Remove the observer list and subscribe/notify methods from {class_name}.
  3. Have {class_name} call `EventBus.getInstance().publish(...)` instead.
  4. Have former observers subscribe to the EventBus instead of the subject directly.
-->

---

### O-6 · Future / CompletableFuture Based ★★★
**Realism:** ★★★ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** Loss of Repeated Notifications

<!--variant
id: O-6
realism: 3
smell: "Loss of Repeated Notifications"
task: |
  Remove the Observer pattern from {class_name} (file {pattern_file}).
  Replace it with a one-shot `CompletableFuture<Event>` that completes on the first event.

  Steps:
  1. Delete the Observer interface and listener list.
  2. Replace `publish()` with a method that `complete()`s a `CompletableFuture<Event>`.
  3. Expose the future via a getter so callers can attach `.thenAccept()` handlers.
  4. Note: only the first call to `complete()` delivers the event; subsequent calls are
     silently ignored — making this broken for repeated notifications.
-->

---

### O-7 · Remove Observer, Store Events in a Log ★★☆
**Realism:** ★★☆ | **Compile Risk:** 🟢 Low | **Scope:** 🔵 Local
**Smell:** Polling / Queue Coupling

<!--variant
id: O-7
realism: 2
smell: "Polling / Queue Coupling"
task: |
  Remove push notification from {class_name} (file {pattern_file}).
  Instead of notifying observers, append events to an internal `List<Event>` or queue.
  Observers must poll this list themselves.

  Steps:
  1. Delete the Observer interface and listener list.
  2. Replace the notification call with `eventLog.add(event)`.
  3. Expose `List<Event> getEventLog()` for callers to poll.
  4. Remove `subscribe()` / `unsubscribe()`.
-->
