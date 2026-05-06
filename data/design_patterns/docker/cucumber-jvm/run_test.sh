#!/bin/bash

git checkout $BRANCH_NAME

set -e
echo "Running Cucumber JVM tests..."
mvn test
