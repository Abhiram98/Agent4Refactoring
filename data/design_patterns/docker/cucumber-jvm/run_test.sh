#!/bin/bash

cd cucumber-jvm

git checkout $BRANCH_NAME

set -e
echo "Running Cucumber JVM tests..."
mvn test
