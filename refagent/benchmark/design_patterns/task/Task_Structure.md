# Refactoring Agent Task Structure & Evaluation Design

This document outlines a 4-tiered prompt system for evaluating Autonomous Refactoring Agents on design pattern applications. It also details the evaluation execution modes to measure both local refactoring capabilities and repository-level reasoning.

## 1. The 4-Tiered Prompt System

To effectively measure an agent's capability, we vary the task difficulty across four distinct "personas" or representation styles. This avoids underspecification (requiring the agent to "mind read" exact class names) while testing different levels of software engineering autonomy.

### Tier 1: The "Mechanic" (Direct Instruction)
**Difficulty: Easy**
**Focus:** Tests the agent's ability to safely edit code, follow structural instructions, and manage syntax. It heavily hand-holds the agent through the exact structural changes needed.

* **Example Prompt:**
  > "Please refactor the construction of `HTable`. Create a new interface called `TableBuilder` and a concrete class `TableBuilderBase`. Move the fields `rpcTimeout` and `writeBufferSize` from `HTable` into this builder. Change the `HTable` constructor to accept a single `TableBuilderBase` parameter instead of multiple individual configuration parameters. Introduce a `getTableBuilder()` method in the `Connection` interface."

### Tier 2: The "Architect" (Pattern Directive)
**Difficulty: Medium**
**Focus:** Tests whether the agent understands standard design patterns and can apply them to the specified classes without granular step-by-step instructions.

* **Example Prompt:**
  > "The `HTable` class currently requires passing many configuration parameters during instantiation, leading to a telescopic constructor anti-pattern. Please refactor this by applying the **Builder Pattern** to `HTable`. Create a `TableBuilder` to encapsulate the configuration, and update `Connection` to vend this builder."

### Tier 3: The "Product Owner" (Goal-Oriented complaint)
**Difficulty: Hard**
**Focus:** Tests whether the agent can interpret a high-level system complaint, recognize the underlying design flaw, select the appropriate pattern, and implement it.

* **Example Prompt (e.g. Jira Ticket):**
  > **Title:** Make HTable configuration more manageable
  > **Description:** Whenever we add a new configuration key to the HBase `Connection` or `HTable`, we have to modify massive constructors. Furthermore, clients are forced to pass `null` or default values for timeouts they don't care about. Please refactor the table instantiation flow to be more extensible and fluent so clients only have to set the configurations they care about.

### Tier 4: The "TDD / Contract-Driven" (Test-Driven)
**Difficulty: Medium-Hard / High Rigor**
**Focus:** Eliminates the "mind-reading" problem of arbitrary class naming while strictly enforcing an API contract. The agent is provided *only* with a failing test case that outlines the newly desired architectural design.

* **Example Prompt:**
  > "A senior engineer wrote the following integration test to improve our client API, but it currently does not compile because the backend classes do not support this fluent design. 
  > ```java
  > @Test
  > public void testNewTableBuilderAPI() {
  >     Connection conn = ConnectionFactory.createConnection(conf);
  >     Table myTable = conn.getTableBuilder(TableName.valueOf(\"my_table\"), pool)
  >                           .setOperationTimeout(5000)
  >                           .setReadRpcTimeout(2000)
  >                           .build();
  >     assertNotNull(myTable);
  > }
  > ```
  > **Task:** Refactor the codebase so that this test compiles and passes. You must preserve all existing underlying functionality, but you are free to restructure the internal classes to support this new fluent API. Do not modify the test."

---

## 2. Evaluation Modes (Search vs. Localized)

Every prompt tier can be executed in two distinct modes to decouple an agent's code-generation capability from its repository navigation capability.

* **Mode A: Seed File Provided ("The Code Review")**
  * **Mechanism:** The agent is given the absolute path to the "Seed File" (the primary file where the core design pattern change must originate).
  * **What it measures:** Pure refactoring and code generation logic. If an agent fails here, it cannot write the correct code even when looking at the problem.

* **Mode B: Seed File Omitted ("The Zero-Context Ticket")**
  * **Mechanism:** The agent is only given the prompt. It must use internal tools (e.g., `grep`, AST search, `ls`) to traverse the repository, locate the relevant classes, and begin its work.
  * **What it measures:** Repository-scale reasoning, tool usage, and problem localization.

---

## 3. Results Measurement: The "Blast Radius"

Rather than measuring difficulty purely by prompt vagueness, difficulty and agent success are graded incrementally based on how far the agent's changes safely propagate ("Blast Radius").

When computing the final scorecard, results are reported across three boundaries:

1. **The Seed Core:** Did the agent successfully apply the pattern to the primary class? *(e.g., Was the `TableBuilder` class created correctly?)*
2. **The Secondary Abstractions:** Did the agent update the interfaces and base classes directly related to the pattern? *(e.g., Was the `Connection` interface updated with abstract methods to support the builder?)*
3. **The Call Sites (Global Blast Radius):** Did the agent successfully hunt down and migrate all legacy usages of the old API across the entire codebase to use the newly refactored API, ensuring the project still compiles?

*Evaluation Note:* An agent might score 100% on the **Seed Core** but 0% on **Call Sites**, indicating a failure to handle cascading repository changes despite successfully generating local code.
