#!/bin/bash

git checkout $BRANCH_NAME

set -e
echo "Running Gson tests..."
mvn test
