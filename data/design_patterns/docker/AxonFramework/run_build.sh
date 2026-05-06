#!/bin/bash

cd AxonFramework

git checkout $BRANCH_NAME

set -e
echo "Building AxonFramework..."
mvn clean install -DskipTests
