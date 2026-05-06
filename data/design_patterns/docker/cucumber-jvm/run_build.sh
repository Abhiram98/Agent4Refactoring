#!/bin/bash

git checkout $BRANCH_NAME

set -e
echo "Building Cucumber JVM..."
mvn clean install -DskipTests
