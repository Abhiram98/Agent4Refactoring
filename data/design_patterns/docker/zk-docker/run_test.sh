#!/bin/bash
set -e

# Detect JAVA_HOME if not already set
if [ -z "$JAVA_HOME" ]; then
    if [ -x /usr/bin/java ]; then
        export JAVA_HOME=$(readlink -f /usr/bin/java | sed "s:/bin/java::")
        echo "Using detected JAVA_HOME: $JAVA_HOME"
    fi
fi

echo "Running ZK Tests..."
# Run tests
./gradlew test --no-daemon
echo "Tests Completed!"
