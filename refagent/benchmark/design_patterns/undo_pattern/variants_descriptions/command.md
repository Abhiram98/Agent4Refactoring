# Undo: Command

## Pattern Structure Being Removed

A `Command` interface with `execute()` (and optionally `undo()`) encapsulates a request
as an object. `ConcreteCommand` ties a `Receiver` to its parameters. An `Invoker` stores
and calls commands, enabling undo/redo and queuing.

### Canonical "With Pattern" Code

```java
interface Command { void execute(); void undo(); }

class TextEditor {
    private StringBuilder text = new StringBuilder();
    public void insertText(int pos, String s) { text.insert(pos, s); }
    public void deleteText(int pos, int len)  { text.delete(pos, pos + len); }
    public String getText() { return text.toString(); }
}

class InsertTextCommand implements Command {
    private final TextEditor editor; private final int position; private final String text;
    InsertTextCommand(TextEditor editor, int position, String text) {
        this.editor = editor; this.position = position; this.text = text;
    }
    public void execute() { editor.insertText(position, text); }
    public void undo()    { editor.deleteText(position, text.length()); }
}

class CommandHistory {
    private final Deque<Command> history = new ArrayDeque<>();
    public void execute(Command cmd) { cmd.execute(); history.push(cmd); }
    public void undo()               { if (!history.isEmpty()) history.pop().undo(); }
}
```

---

## Undo Variants (sorted by realism ★ high → low)

---

### Cmd-1 · Direct Method Call on Receiver ★★★
**Realism:** ★★★ | **Compile Risk:** 🔴 High | **Scope:** ⚫ Wide
**Smell:** Tight Coupling, Loss of Undo

<!--variant
id: Cmd-1
realism: 3
smell: "Tight Coupling / Loss of Undo"
task: |
  Remove the Command pattern from class {class_name} in file {pattern_file}.
  Delete all ConcreteCommand classes and the Invoker. Call receiver methods directly.

  Steps:
  1. Delete the Command interface ({class_name} or the interface it relates to).
  2. Delete all ConcreteCommand classes.
  3. Delete the Invoker (CommandHistory or equivalent).
  4. At every call site that previously created and executed a Command, replace with a
     direct method call on the Receiver (e.g. `editor.insertText(pos, text)` instead of
     `history.execute(new InsertTextCommand(editor, pos, text))`).
  5. Undo is lost — document this with a `// TODO: undo not supported` comment.

  The result couples callers directly to the Receiver, exhibiting Tight Coupling.
-->

---

### Cmd-2 · Switch-Based Request Dispatcher ★★★
**Realism:** ★★★ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** Switch Statement smell

<!--variant
id: Cmd-2
realism: 3
smell: "Switch Statement"
task: |
  Remove the Command pattern from class {class_name} in file {pattern_file}.
  Replace Command objects with an enum-keyed switch dispatcher in the Invoker.

  Steps:
  1. Delete all ConcreteCommand classes and the Command interface.
  2. Create an enum listing all request types (e.g. `enum EditorAction { INSERT, DELETE }`).
  3. Modify the Invoker to have a single `execute(EditorAction action, Object... args)` method
     with a switch that dispatches to the Receiver directly.
  4. Update call sites to pass the enum + arguments instead of Command objects.
  5. Undo tracking is lost.

  The result requires modifying the switch for every new action, exhibiting the
  Switch Statement smell.
-->

---

### Cmd-3 · Lambda / Runnable (Lose Undo) ★★★
**Realism:** ★★★ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** Loss of Undo Capability

<!--variant
id: Cmd-3
realism: 3
smell: "Loss of Undo Capability"
task: |
  Remove the Command pattern from class {class_name} (file {pattern_file}).
  Replace ConcreteCommand classes with Runnable lambdas. Keep the Invoker history but
  lose undo capability.

  Steps:
  1. Delete all ConcreteCommand classes and the Command interface.
  2. Change the Invoker's history from `Deque<Command>` to `Deque<Runnable>`.
  3. Rename `execute(Command)` to `execute(Runnable)` — just call `action.run()` and
     `history.push(action)`.
  4. Make `undo()` throw `UnsupportedOperationException` (a Runnable has no inverse).
  5. Update all call sites to pass lambdas instead of Command objects.
-->

---

### Cmd-4 · Remove Invoker — Inline at Every Call Site ★★★
**Realism:** ★★★ | **Compile Risk:** 🔴 High | **Scope:** ⚫ Wide
**Smell:** Shotgun Surgery, Code Duplication

<!--variant
id: Cmd-4
realism: 3
smell: "Shotgun Surgery / Code Duplication"
task: |
  Remove the Invoker (CommandHistory) from the Command pattern in {pattern_file}.
  Each class that uses commands must manage its own history inline.

  Steps:
  1. Delete the Invoker class ({class_name} or the history class).
  2. Keep the Command interface and ConcreteCommand classes.
  3. At each call site that previously used the Invoker, add a local `Deque<Command>`
     and replicate the `execute()` / `undo()` logic inline.
  4. This duplication must appear independently in each calling class.

  The result duplicates undo stack management at every call site, exhibiting
  Shotgun Surgery and Code Duplication.
-->

---

### Cmd-5 · Merge Receiver into Command (Fat Command) ★★★
**Realism:** ★★★ | **Compile Risk:** 🔴 High | **Scope:** ⚫ Wide
**Smell:** God Object / Missing Separation of Concerns

<!--variant
id: Cmd-5
realism: 3
smell: "God Object / Missing Separation of Concerns"
task: |
  Remove the separate Receiver class from the Command pattern in {pattern_file}.
  Absorb all Receiver logic directly into the ConcreteCommand classes.

  Steps:
  1. Identify the Receiver class (the object that knows how to do the work, e.g. TextEditor).
  2. Move the Receiver's operation logic directly into each ConcreteCommand class.
  3. Delete the Receiver class (or reduce it to a simple data container).
  4. ConcreteCommands now both hold state AND implement the operation logic.
-->

---

### Cmd-6 · Remove undo() Only ★★★
**Realism:** ★★★ | **Compile Risk:** 🟢 Low | **Scope:** 🔵 Local
**Smell:** Missing Feature / Incomplete Abstraction

<!--variant
id: Cmd-6
realism: 3
smell: "Missing Undo Feature"
task: |
  Remove only the `undo()` capability from the Command pattern in class {class_name}
  (file {pattern_file}). Keep the Command interface and Invoker but strip undo support.

  Steps:
  1. Remove `undo()` from the Command interface.
  2. Remove all `undo()` implementations from ConcreteCommand classes.
  3. Remove the undo history from the Invoker (no more `Deque<Command>`); just execute
     and forget.
  4. If the Invoker had an `undo()` method, replace its body with
     `throw new UnsupportedOperationException("Undo not supported")`.

  This is the narrowest change — only undo capability is lost. The pattern structure
  otherwise remains intact.
-->

---

### Cmd-7 · Callback / Listener ★★☆
**Realism:** ★★☆ | **Compile Risk:** 🟡 Medium | **Scope:** 🟣 Medium
**Smell:** Loss of Command Identity / Queueability

<!--variant
id: Cmd-7
realism: 2
smell: "Loss of Command Identity"
task: |
  Remove the Command pattern from class {class_name} (file {pattern_file}).
  Replace Command objects with a listener/callback interface registered on the Invoker,
  turning it into a degenerate Observer.

  Steps:
  1. Delete the Command interface and ConcreteCommand classes.
  2. Define a listener interface: `interface ActionListener { void onAction(String type, Object... args); }`
  3. Convert the Invoker to accept registered `ActionListener` instances and notify them.
  4. Commands are no longer first-class objects; they become transient notifications.
  5. Undo and queuing are lost.
-->
