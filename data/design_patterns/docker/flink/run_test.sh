#!/bin/bash

cd flink

git fetch --all
git pull --all
git checkout $BRANCH_NAME

set -e
echo "Running Apache Flink tests..."
mvn test
