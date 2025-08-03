from typing import Tuple, List, Optional, Union,Any
from pydantic import BaseModel, model_validator
import json


class DataColumnModel(BaseModel):
    name: str
    description: str
    data_type: str
    examples: Optional[List[Any]] = None

class DataTableModel(BaseModel):
    name: str
    columns: List[DataColumnModel]

class DataDictionaryModel(BaseModel):
    database: str
    tables: List[DataTableModel]
    notes: Optional[List[str]]

class DataFilterModel(BaseModel):
    table: str
    column: str
    allowed: Optional[Union[List[int], List[str]]] = None
    forbidden: Optional[Union[List[int], List[str]]] = None
    
    @model_validator(mode='after')
    def check_exclusive_conditions(self) -> "DataFilterModel":
        if self.allowed is not None and self.forbidden is not None:
            raise ValueError('Only allowed or forbidden, but not both')

        if self.allowed is None and self.forbidden is None:
            raise ValueError('Either allowed or forbidden should be specified')
        return self

def format_schema_for_prompt(data_dictionary_json: str) -> Tuple[str, str]:
    data_dictionary = DataDictionaryModel.model_validate(json.loads(data_dictionary_json))
    schema_prompt = ""
    for table in data_dictionary.tables:
        schema_prompt += f"\nTable: {table.name}\n"
        for column in table.columns:
            example_str = f" (e.g., {', '.join(map(str, column.examples))})" if column.examples else ""
            schema_prompt += f"  - {column.name} ({column.data_type}): {column.description}{example_str}\n"
    if data_dictionary.notes:
        schema_prompt += "\nNotes:\n"
        for note in data_dictionary.notes:
            schema_prompt += f"- {note}\n"
    return data_dictionary.database, schema_prompt

def serialize_filters(filters: Optional[List["DataFilterModel"]]) -> str:
    """
    Serialize a list of DataFilterModels to a string block for prompting.
    """
    if not filters:
        return "No filters."
    lines = []
    for f in filters:
        table = f.table
        column = f.column
        if f.allowed is not None:
            lines.append(f'{table}.{column} allowed {f.allowed}')
        elif f.forbidden is not None:
            lines.append(f'{table}.{column} forbidden {f.forbidden}')
    return "\n".join(lines) if lines else "No filters."
