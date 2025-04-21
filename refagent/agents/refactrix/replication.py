from pydantic.v1 import BaseModel, Field, PrivateAttr


class Replication(BaseModel):

    def compile_and_run(self):
        """Two phases of replication.
                1. Within file.
                2. Across files
                    - find other relevant files (using call graph/other techniques)
                    - Ask if the change can be replicated here.
                    - Invoke planning to replicate changes.
        """
        pass

