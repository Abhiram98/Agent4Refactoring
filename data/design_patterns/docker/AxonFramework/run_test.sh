#!/bin/bash

cd AxonFramework

git checkout $BRANCH_NAME

set -e
echo "Running AxonFramework tests..."
mvn test
