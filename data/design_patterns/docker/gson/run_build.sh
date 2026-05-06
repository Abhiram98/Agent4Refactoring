#!/bin/bash

git checkout $BRANCH_NAME

set -e
echo "Building Gson..."
mvn clean install -DskipTests
