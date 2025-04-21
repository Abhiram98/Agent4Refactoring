from pydantic.v1 import BaseModel, Field, PrivateAttr


class ErrorFixing(BaseModel):
    def compile_and_run(self):
        pass

