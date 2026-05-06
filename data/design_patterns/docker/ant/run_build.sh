#!/bin/bash

git checkout $BRANCH_NAME

set -e
echo "Building Apache Ant..."
ant dist
