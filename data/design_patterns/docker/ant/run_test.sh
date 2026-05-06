#!/bin/bash

cd ant

git checkout $BRANCH_NAME

set -e
echo "Running Apache Ant tests..."
ant test
