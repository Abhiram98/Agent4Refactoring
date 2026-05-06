#!/bin/bash

git checkout $BRANCH_NAME

set -e
echo "Running Apache Jackrabbit tests..."
mvn test
