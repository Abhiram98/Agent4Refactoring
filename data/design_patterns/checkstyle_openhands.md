Implemented an AuditListener observer contract for Checkstyle audit events.
What was added
•  
New API type: src/main/java/com/puppycrawl/tools/checkstyle/api/AuditListener.java

▪  Defines the audit “observer” callbacks (with default no-op implementations):

‣  auditStarted() / auditFinished()
‣  fileStarted(String) / fileFinished(String)
‣  addError(AuditEvent)
‣  addException(AuditEvent, Throwable)
▪  Javadoc explicitly documents the observer pattern relationship.
What was updated to use it

•  Marked existing audit/logging components as observers by adding implements AuditListener:
▪ DefaultLogger, XMLLogger, SarifLogger, MetadataGeneratorLogger
▪ DebugAuditAdapter
▪  XpathFileGeneratorAuditListener
▪  ChecksAndFilesSuppressionFileGeneratorAuditListener
▪  SeverityLevelCounter (also added addError(AuditEvent) delegating to existing severity-counting logic)
Audit infrastructure notes

•  Checker is the subject/dispatcher: it already emits lifecycle + violation notifications (e.g., via fireAuditStarted, fireErrors, etc.), and the above components now formally implement the listener contract.
•  ModuleReflectionUtil.isAuditListener(...) now correctly identifies audit listener modules via AuditListener.class.isAssignableFrom(clazz).
Verification

•  
./mvnw -DskipTests compile succeeds when run under Java 21.
•  Targeted tests related to listeners pass (after clean).
(Added AGENTS.md with the Java 21 + mvn clean/JaCoCo note for future runs.)