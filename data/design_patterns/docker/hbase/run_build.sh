#!/bin/bash

cd hbase

git checkout $BRANCH_NAME

set -e
echo "Building Apache HBase..."
mvn clean install -DskipTests
