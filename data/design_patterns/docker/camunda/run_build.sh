#!/bin/bash

cd camunda

git fetch --all
git pull --all
git checkout $BRANCH_NAME

set -e
echo "Building Camunda..."
mvn clean install -DskipTests
