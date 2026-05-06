#!/bin/bash

git checkout $BRANCH_NAME

set -e
echo "Building Apache Jackrabbit..."
mvn clean install -DskipTests
