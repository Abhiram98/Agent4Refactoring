#!/bin/bash

cd cucumber-jvm

git checkout $BRANCH_NAME

set -e
echo "Building Cucumber JVM..."
mvn clean install -DskipTests
