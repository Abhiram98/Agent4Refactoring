#!/bin/bash

cd hbase

git checkout $BRANCH_NAME

# Detect JAVA_HOME if not already set
if [ -z "$JAVA_HOME" ]; then
    if [ -x /usr/bin/java ]; then
        export JAVA_HOME=$(readlink -f /usr/bin/java | sed "s:/bin/java::")
        echo "Using detected JAVA_HOME: $JAVA_HOME"
    fi
fi

set -e
echo "Running Apache HBase tests..."
mvn test
