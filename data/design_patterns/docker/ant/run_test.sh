#!/bin/bash

git checkout $BRANCH_NAME

set -e
echo "Running Apache Ant tests..."
ant test
