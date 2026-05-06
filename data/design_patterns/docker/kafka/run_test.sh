#!/bin/bash

cd kafka

git fetch --all
git pull --all
git checkout $BRANCH_NAME

set -e
echo "Running Apache Kafka tests..."
./gradlew test
