FROM ubuntu:24.04

# Avoid interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Update and install dependencies
# We need JDK 11, git, curl, unzip, and Node.js/npm for frontend build
RUN apt-get update && apt-get install -y \
    openjdk-11-jdk-headless \
    git \
    curl \
    unzip \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Ensure Java is in the PATH and set JAVA_HOME dynamically
RUN java -version && \
    export JAVA_HOME=$(readlink -f /usr/bin/java | sed "s:/bin/java::") && \
    echo "Using JAVA_HOME=$JAVA_HOME"

# Copy project files into the container
# TODO: change this to shallow clone. Copy the run_build and run_test.sh
COPY . .


# Ensure gradlew and scripts are executable
RUN chmod +x gradlew run_build.sh run_test.sh

# Bootstrap the environment
# We detect the correct JAVA_HOME and run the build command in the same shell
RUN export JAVA_HOME=$(readlink -f /usr/bin/java | sed "s:/bin/java::") && \
    ./gradlew npm_install --no-daemon -x test --stacktrace

# Default command
CMD ["/bin/bash", "./run_build.sh"]
