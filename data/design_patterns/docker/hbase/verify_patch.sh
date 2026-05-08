cd /Users/abhiram/Documents/TBE/evaluation_projects/hbase
git add .
git commit -m "refactor"
git format-patch -1 HEAD --stdout > /Users/abhiram/Documents/TBE/RefactoringAgentProject/Agent4Refactoring/data/design_patterns/docker/hbase/refactor_real.patch
git status

docker run --rm -v ~/.m2:/root/.m2 -v /Users/abhiram/Documents/TBE/RefactoringAgentProject/Agent4Refactoring/data/design_patterns/docker/hbase/refactor_real.patch:/app/refactor.patch hbase-val /app/run_build.sh > /Users/abhiram/Documents/TBE/RefactoringAgentProject/Agent4Refactoring/data/design_patterns/docker/hbase/build.out 2>&1

tail -100 /Users/abhiram/Documents/TBE/RefactoringAgentProject/Agent4Refactoring/data/design_patterns/docker/hbase/build.out