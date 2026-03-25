set -e

# Detect JAVA_HOME if not already set
if [ -z "$JAVA_HOME" ]; then
    if [ -x /usr/bin/java ]; then
        export JAVA_HOME=$(readlink -f /usr/bin/java | sed "s:/bin/java::")
        echo "Using detected JAVA_HOME: $JAVA_HOME"
    fi
fi

echo "Starting ZK Build..."
# Build the project, skipping tests
./gradlew build -x test --no-daemon
echo "Build Successful!"
