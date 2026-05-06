#!/bin/bash

cd cayenne

git checkout $BRANCH_NAME

set -e
echo "Running Apache Cayenne tests..."
mvn test
