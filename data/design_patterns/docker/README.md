# Design Pattern Evaluation Docker Environments

This directory contains Docker environments for evaluating design pattern refactorings across various open-source projects. Each project directory contains a `Dockerfile`, a `run_build.sh` script, and a `run_test.sh` script.

## General Workflow

To build and test a project, follow these steps:

### 1. Build the Image
```bash
docker build -t <image_tag> data/design_patterns/docker/<project_dir>/
```

### 2. Run the Build Script
Compiles the project and installs dependencies, skipping tests.
```bash
docker run --rm -e BRANCH_NAME=<branch_name> <image_tag> /app/run_build.sh
```

### 3. Run the Test Script
Executes the full test suite.
```bash
docker run --rm -e BRANCH_NAME=<branch_name> <image_tag> /app/run_test.sh
```

---

## Project Matrix

| Project | Directory | Image Tag | Default Branch | Build System |
| :--- | :--- | :--- | :--- | :--- |
| **AxonFramework** | `AxonFramework` | `axon-val` | `main` | Maven (JDK 21) |
| **ant** | `ant` | `ant-val` | `master` | Ant |
| **camunda** | `camunda` | `camunda-val` | `main` | Maven |
| **cayenne** | `cayenne` | `cayenne-val` | `master` | Maven |
| **cucumber-jvm** | `cucumber-jvm` | `cucumber-jvm-val` | `main` | Maven |
| **flink** | `flink` | `flink-val` | `master` | Maven |
| **gson** | `gson` | `gson-val` | `main` | Maven |
| **hbase** | `hbase` | `hbase-val` | `master` | Maven |
| **jackrabbit** | `jackrabbit` | `jackrabbit-val` | `trunk` | Maven |
| **kafka** | `kafka` | `kafka-val` | `trunk` | Gradle |

---

## Advanced Usage

### Mounting Local Code
To test local changes without rebuilding the image, mount your project directory specifically to the `/app/<project>` subdirectory to avoid overwriting the pre-baked scripts in `/app`:
```bash
docker run --rm \
  -v /path/to/local/project:/app/<project> \
  -e BRANCH_NAME=main \
  <image_tag> /app/run_test.sh
```

### Memory Limits
For resource-intensive projects (**flink**, **hbase**, **kafka**), it is recommended to provide at least 8GB of RAM:
```bash
docker run --rm --memory="8g" -e BRANCH_NAME=master flink-val /app/run_test.sh
```

## Internal Structure
The environments are structured to keep the build scripts separate from the project code:
- `/app/run_build.sh` & `/app/run_test.sh`: Execution scripts.
- `/app/<project>/`: The cloned project source code.

This structure prevents build scripts from appearing in the project's git tree and simplifies volume mounting.

## Troubleshooting

- **JDK Version**: Modern versions of AxonFramework require JDK 21. Ensure the Dockerfile is using `openjdk-21-jdk`.
- **Git Failures**: If `git fetch --all` fails, ensure the remote fork exists and is public. If no fork is available, the setup defaults to the upstream repository.
