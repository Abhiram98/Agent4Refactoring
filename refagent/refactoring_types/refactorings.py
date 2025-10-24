from pydantic import BaseModel, Field
from typing import List, Self, Dict, Type, ClassVar, Optional


class CodeLocation(BaseModel):
    filePath: str = Field(
        ..., description="Path to the file where the code element is located"
    )
    startLine: int = Field(..., description="Starting line of the code element")
    endLine: int = Field(..., description="Ending line of the code element")
    startColumn: int = Field(..., description="Starting column of the code element")
    endColumn: int = Field(..., description="Ending column of the code element")
    codeElementType: str = Field(
        ..., description="Type of the code element (e.g., CLASS, METHOD, VARIABLE)"
    )
    description: str = Field(..., description="Description of the code element")
    codeElement: Optional[str] = Field(..., description="Actual code element")


class RefminerOut(BaseModel):
    type: str = Field(..., description="Refactoring type")
    description: str = Field(..., description="Description of the refactoring")
    leftSideLocations: List[CodeLocation] = Field(
        ..., description="Code element that _was_ refactored"
    )
    rightSideLocations: List[CodeLocation] = Field(
        ..., description="Modified/refactored code element"
    )

    subclass_registry: ClassVar[Dict[str, Type["RefminerOut"]]] = {}

    def __init_subclass__(cls, *args, **kwargs):
        """Automatically register subclasses based on their type field."""
        super().__init_subclass__(*args, **kwargs)
        if hasattr(cls, "TYPE"):
            cls.subclass_registry[cls.TYPE] = cls

    @classmethod
    def load(cls, raw_json) -> List["RefminerOut"]:
        """Loads refactorings and creates instances of the appropriate subclass."""
        if len(raw_json["commits"]) == 0:
            return []
        instances = []
        for refactoring in raw_json["commits"][0]["refactorings"]:
            ref_type = refactoring.get("type")
            subclass = cls.subclass_registry.get(
                ref_type, cls
            )  # Default to RefminerOut if unknown
            instances.append(subclass(**refactoring))
        return instances

    @classmethod
    def load_from_json(cls, json_element: List) -> List["RefminerOut"]:
        instances = []
        for refactoring in json_element:
            ref_obj = cls.load_from_dictionary(refactoring)
            instances.append(ref_obj)
        return instances

    @classmethod
    def load_from_dictionary(cls, dictionary: Dict) -> "RefminerOut":
        subclass = cls.subclass_registry.get(
            dictionary.get("type"), cls
        )  # Default to RefminerOut if unknown
        return subclass(**dictionary)

    def base_eq(self, other):
        if not isinstance(other, RefminerOut):
            return False
        if self.type != other.type or self.comparable_types(self.type, other.type):
            return False
        if self.leftSideLocations[0].filePath != other.leftSideLocations[0].filePath:
            return False
        return True

    def comparable_types(self, type1: str, type2: str) -> bool:
        # comparable_types = {
        #     'Move And Rename Class': 'Rename Class',
        #     'Move And Rename Method': 'Rename Method'
        # }
        # return comparable_types[type1] == comparable_types[type2]
        return False

    @property
    def is_synthetic(self) -> bool:
        return self.description.startswith("Synthetic")

    def __eq__(self, other):
        if not self.base_eq(other):
            return False
        assert isinstance(other, RefminerOut)
        return self.description == other.description


class ModifyMethodAnnotation(RefminerOut):
    TYPE: ClassVar[str] = "Modify Method Annotation"

    def __eq__(self, other: RefminerOut):
        if not self.base_eq(other):  # Call the parent class equality check
            return False

        self_method_decl = [
            l
            for l in self.leftSideLocations
            if l.codeElementType == "METHOD_DECLARATION"
        ]
        assert len(self_method_decl) == 1
        other_method_decl = [
            l
            for l in other.leftSideLocations
            if l.codeElementType == "METHOD_DECLARATION"
        ]
        assert len(other_method_decl) == 1
        return self_method_decl[0].codeElement == other_method_decl[0].codeElement


class AddMethodAnnotation(ModifyMethodAnnotation):
    TYPE: ClassVar[str] = "Add Method Annotation"


class PushDownMethod(RefminerOut):
    TYPE: ClassVar[str] = "Push Down Method"

    def __eq__(self, other: RefminerOut):
        if not self.base_eq(other):  # Call the parent class equality check
            return False

        self_method_decl = [
            l
            for l in self.leftSideLocations
            if l.codeElementType == "METHOD_DECLARATION"
        ]
        assert len(self_method_decl) == 1
        other_method_decl = [
            l
            for l in other.leftSideLocations
            if l.codeElementType == "METHOD_DECLARATION"
        ]
        assert len(other_method_decl) == 1
        return self_method_decl[0].codeElement == other_method_decl[0].codeElement


class PushDownAttribute(RefminerOut):
    TYPE: ClassVar[str] = "Push Down Attribute"

    def __eq__(self, other: RefminerOut):
        if not self.base_eq(other):  # Call the parent class equality check
            return False
        return (
            self.leftSideLocations[0].codeElement
            == other.leftSideLocations[0].codeElement
        )


class Rename(RefminerOut):
    @property
    def old_name(self):
        return self.leftSideLocations[0].codeElement

    @property
    def new_name(self):
        return self.rightSideLocations[0].codeElement

    @property
    def parent_method_signature(self):
        return self.description.split("in method ")[-1].split(" from class")[0]

    @property
    def start_line(self):
        return self.leftSideLocations[0].startLine

    @property
    def has_type_change(self) -> bool:
        return False

    def __eq__(self, other: RefminerOut):
        if not self.base_eq(other):  # Call the parent class equality check
            return False
        # true if the same code element was renamed.
        return (
            self.leftSideLocations[0].codeElement
            == other.leftSideLocations[0].codeElement
        )


class RenameMethod(Rename):
    TYPE: ClassVar[str] = "Rename Method"

    def get_name(self, method_str):
        return method_str.split("(")[0].split(" ")[-1]

    @property
    def old_name(self):
        return self.get_name(self.leftSideLocations[0].codeElement)

    @property
    def new_name(self):
        return self.get_name(self.rightSideLocations[0].codeElement)

    @property
    def old_return_type(self):
        return self.leftSideLocations[0].codeElement.split(" : ")[-1]

    @property
    def new_return_type(self):
        return self.rightSideLocations[0].codeElement.split(" : ")[-1]

    @property
    def has_type_change(self) -> bool:
        return self.old_return_type != self.new_return_type

    @property
    def parameters(self):
        before_rename = self.description.split("renamed to")[0]

        start = before_rename.find("(")
        end = before_rename.find(")", start)

        if start != -1 and end != -1:
            params = before_rename[start + 1 : end]

        return params

    @property
    def return_type(self):
        before_rename = self.description.split("renamed to")[0]
        parts = before_rename.split(":")
        if len(parts) > 1:
            return_type = parts[1].strip()
            return return_type
        return ""

    def get_name(self, method_str):
        return method_str.split("(")[0].split(" ")[-1]

    @property
    def old_name(self):
        return self.get_name(self.leftSideLocations[0].codeElement)

    @property
    def new_name(self):
        return self.get_name(self.rightSideLocations[0].codeElement)

    @property
    def old_return_type(self):
        return self.leftSideLocations[0].codeElement.split(" : ")[-1]

    @property
    def new_return_type(self):
        return self.rightSideLocations[0].codeElement.split(" : ")[-1]

    @property
    def has_type_change(self) -> bool:
        return self.old_return_type != self.new_return_type

    def __eq__(self, other):
        if self.is_synthetic or other.is_synthetic:
            return (
                self.base_eq(other)
                and self.start_line == other.start_line
                and self.old_name == other.old_name
            )

        res = (
            super().__eq__(other)
            and self.start_line == other.start_line
            and self.parameters == other.parameters
            and self.return_type == other.return_type
        )
        return res


class RenameVariable(Rename):
    TYPE: ClassVar[str] = "Rename Variable"

    @property
    def old_name(self):
        return self.leftSideLocations[0].codeElement.split(" :")[0]

    @property
    def new_name(self):
        return self.rightSideLocations[0].codeElement.split(" :")[0]

    @property
    def old_type(self):
        return self.leftSideLocations[0].codeElement.split(" :")[1]

    @property
    def new_type(self):
        return self.rightSideLocations[0].codeElement.split(" :")[1]

    @property
    def has_type_change(self) -> bool:
        return self.old_type != self.new_type

    @property
    def old_name(self):
        return self.leftSideLocations[0].codeElement.split(" :")[0]

    @property
    def new_name(self):
        return self.rightSideLocations[0].codeElement.split(" :")[0]

    @property
    def old_type(self):
        return self.leftSideLocations[0].codeElement.split(" :")[1]

    @property
    def new_type(self):
        return self.rightSideLocations[0].codeElement.split(" :")[1]

    @property
    def has_type_change(self) -> bool:
        return self.old_type != self.new_type

    def __eq__(self, other):
        if self.is_synthetic or other.is_synthetic:
            return (
                self.base_eq(other)
                and self.start_line == other.start_line
                and self.old_name == other.old_name
            )
        return super().__eq__(other) and self.start_line == other.start_line


class RenameParameter(Rename):
    TYPE: ClassVar[str] = "Rename Parameter"

    @property
    def start_line(self):
        return self.leftSideLocations[0].startLine

    @property
    def old_param_name(self):
        return self.leftSideLocations[0].codeElement

    @property
    def old_name(self):
        return self.leftSideLocations[0].codeElement.split(" :")[0]

    @property
    def new_name(self):
        return self.rightSideLocations[0].codeElement.split(" :")[0]

    @property
    def old_type(self):
        return self.leftSideLocations[0].codeElement.split(" :")[1]

    @property
    def new_type(self):
        return self.rightSideLocations[0].codeElement.split(" :")[1]

    @property
    def has_type_change(self) -> bool:
        return self.old_type != self.new_type

    def __eq__(self, other):
        if self.is_synthetic or other.is_synthetic:
            return (
                self.base_eq(other)
                and self.old_name == other.old_name
                and self.start_line == other.start_line
            )
        res = super().__eq__(other) and (
            self.start_line == other.start_line
            and self.old_param_name == other.old_param_name
        )
        return res


class RenameClass(Rename):

    @property
    def old_name(self):
        return self.leftSideLocations[0].codeElement.split(".")[-1]

    @property
    def new_name(self):
        return self.rightSideLocations[0].codeElement.split(".")[-1]

    @property
    def old_name(self):
        return self.leftSideLocations[0].codeElement.split(".")[-1]

    @property
    def new_name(self):
        return self.rightSideLocations[0].codeElement.split(".")[-1]

    def compare_synthetic(self, other: "RenameClass"):
        return self.old_name == other.old_name

    def __eq__(self, other: RefminerOut):
        if not self.base_eq(other):  # Call the parent class equality check
            return False
        if self.is_synthetic or other.is_synthetic:
            return self.compare_synthetic(other)
        # true if the same code element was renamed.
        return (
            self.leftSideLocations[0].codeElement
            == other.leftSideLocations[0].codeElement
        )

    TYPE: ClassVar[str] = "Rename Class"


class RenameAttribute(Rename):

    @property
    def old_name(self):
        return self.leftSideLocations[0].codeElement.split(" :")[0]

    @property
    def new_name(self):
        return self.rightSideLocations[0].codeElement.split(" :")[0]

    @property
    def has_type_change(self):
        return (
            self.leftSideLocations[0].codeElement.split(" : ")[1]
            != self.rightSideLocations[0].codeElement.split(" : ")[1]
        )

    @property
    def old_name(self):
        return self.leftSideLocations[0].codeElement.split(" :")[0]

    @property
    def new_name(self):
        return self.rightSideLocations[0].codeElement.split(" :")[0]

    @property
    def has_type_change(self):
        return (
            self.leftSideLocations[0].codeElement.split(" : ")[1]
            != self.rightSideLocations[0].codeElement.split(" : ")[1]
        )

    TYPE: ClassVar[str] = "Rename Attribute"

    def __eq__(self, other):
        if self.is_synthetic or other.is_synthetic:
            return (
                self.base_eq(other)
                and self.old_name == other.old_name
                and self.start_line == other.start_line
            )
        res = super().__eq__(other) and (
            self.start_line == other.start_line and self.old_name == other.old_name
        )
        return res


class ExtractMethod(RefminerOut):
    TYPE: ClassVar[str] = "Extract Method"

    def __eq__(self, other: RefminerOut):
        if not self.base_eq(other):
            return False

        self_method = [
            i
            for i in self.leftSideLocations
            if i.codeElementType == "METHOD_DECLARATION"
            and i.description == "source method declaration before extraction"
        ]
        other_method = [
            i
            for i in other.leftSideLocations
            if i.codeElementType == "METHOD_DECLARATION"
            and i.description == "source method declaration before extraction"
        ]
        assert len(self_method) == 1
        assert len(other_method) == 1
        return self_method[0].codeElement == other_method[0].codeElement


class ExtractClass(RefminerOut):
    TYPE: ClassVar[str] = "Extract Class"

    def __eq__(self, other: RefminerOut):
        if not self.base_eq(other):  # Call the parent class equality check
            return False
        # match the extracted class name
        extracted_name_self = (
            self.description.split("Extract Class ")[-1]
            .split(" from class")[0]
            .split(".")[-1]
        )
        extracted_name_other = (
            other.description.split("Extract Class ")[-1]
            .split(" from class")[0]
            .split(".")[-1]
        )
        # TODO: match at least one of the extracted fields/methods.
        #  This information is available in the leftSideLocations.
        return extracted_name_self == extracted_name_other


class MoveAndRenameClass(RefminerOut):
    TYPE: ClassVar[str] = "Move And Rename Class"

    @property
    def old_name(self):
        return self.leftSideLocations[0].codeElement.split(".")[-1]

    @property
    def new_name(self):
        return self.rightSideLocations[0].codeElement.split(".")[-1]

    @property
    def file_path(self):
        return self.leftSideLocations[0].filePath

    @property
    def start_line(self):
        return self.leftSideLocations[0].startLine

    def __eq__(self, other):
        if isinstance(other, RenameClass):
            return (
                self.old_name == other.old_name
                and self.file_path == other.leftSideLocations[0].filePath
            )
        elif isinstance(other, MoveAndRenameClass):
            return self.old_name == other.old_name and self.file_path == other.file_path
        return False


class MoveAndRenameMethod(RefminerOut):
    TYPE: ClassVar[str] = "Move And Rename Method"

    def get_name(self, method_str):
        return method_str.split("(")[0].split(" ")[-1]

    @property
    def old_name(self):
        return self.get_name(self.leftSideLocations[0].codeElement)

    @property
    def new_name(self):
        return self.get_name(self.rightSideLocations[0].codeElement)

    @property
    def file_path(self):
        return self.leftSideLocations[0].filePath

    @property
    def start_line(self):
        return self.leftSideLocations[0].startLine

    def __eq__(self, other):
        if isinstance(other, RenameMethod):
            # raise NotImplementedError("Should implement __eq__ between RenameMethod and MoveAndRenameMethod")
            return (
                self.old_name == other.old_name
                and self.file_path == other.leftSideLocations[0].filePath
                and self.start_line == other.start_line
            )
        elif isinstance(other, MoveAndRenameMethod):
            # raise NotImplementedError("Should implement __eq__ between MoveAndRenameMethod and MoveAndRenameMethod")
            return (
                self.old_name == other.old_name
                and self.start_line == other.start_line
                and self.file_path == other.file_path
            )
        return False
