#!/bin/bash

cd cayenne

git checkout $BRANCH_NAME

set -e
echo "Building Apache Cayenne..."
mvn clean install -DskipTests
