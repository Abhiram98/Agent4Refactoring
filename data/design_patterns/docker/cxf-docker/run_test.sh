#!/bin/bash

git fetch --all
git pull --all
git checkout $BRANCH_NAME

set -e
echo "Running Apache CXF tests..."
mvn test
