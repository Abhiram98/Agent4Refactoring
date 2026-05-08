#!/bin/bash

./apply_patch.sh

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
echo "Building Apache HBase..."
mvn clean install -DskipTests
