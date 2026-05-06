#!/bin/bash

cd gson

git checkout $BRANCH_NAME

set -e
echo "Running Gson tests..."
mvn test
