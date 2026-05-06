#!/bin/bash

cd kafka

git fetch --all
git pull --all
git checkout $BRANCH_NAME

set -e
echo "Building Apache Kafka..."
./gradlew jar -x test
