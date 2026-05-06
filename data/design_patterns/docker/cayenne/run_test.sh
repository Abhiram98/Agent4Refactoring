#!/bin/bash

git checkout $BRANCH_NAME

set -e
echo "Running Apache Cayenne tests..."
mvn test
