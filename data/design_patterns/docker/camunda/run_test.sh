#!/bin/bash

git fetch --all
git pull --all
git checkout $BRANCH_NAME

set -e
echo "Running Camunda tests..."
mvn test
