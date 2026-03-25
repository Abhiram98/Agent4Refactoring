#!/bin/bash
set -e
echo "Building Apache CXF..."
mvn clean install -DskipTests
