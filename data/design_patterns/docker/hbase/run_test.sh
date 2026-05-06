#!/bin/bash

git checkout $BRANCH_NAME

set -e
echo "Running Apache HBase tests..."
mvn test
