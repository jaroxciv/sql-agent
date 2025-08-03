import os
import json
from sqlalchemy import inspect, text
from data_models import DataDictionaryModel, DataTableModel, DataColumnModel


REQUIRED_PROMPT_KEYS = {"sql", "summary", "memory", "relevance"}


def get_clean_examples(col_type, ex_values):
    """
    Try to coerce to int, float, or str, depending on SQL type.
    """
    base_type = str(col_type).lower()
    clean_values = []
    if "int" in base_type:
        for v in ex_values:
            try:
                if v is not None:
                    clean_values.append(int(v))
            except Exception:
                continue
    elif "float" in base_type or "double" in base_type or "real" in base_type:
        for v in ex_values:
            try:
                if v is not None:
                    clean_values.append(float(v))
            except Exception:
                continue
    elif "char" in base_type or "text" in base_type or "str" in base_type:
        for v in ex_values:
            if v is not None:
                clean_values.append(str(v))
    else:
        for v in ex_values:
            if v is not None:
                clean_values.append(str(v))
    return clean_values if clean_values else None


def extract_data_dictionary(engine, db_label="Database", sample_rows=3):
    inspector = inspect(engine)
    tables = []
    with engine.connect() as conn:
        for table_name in inspector.get_table_names():
            columns = []
            try:
                example_rows = conn.execute(
                    text(f'SELECT * FROM "{table_name}" LIMIT {sample_rows}')
                ).fetchall()
            except Exception as e:
                example_rows = []
            for col in inspector.get_columns(table_name):
                col_name = col['name']
                ex_values = [row._mapping.get(col_name) for row in example_rows if col_name in row._mapping]
                clean_examples = get_clean_examples(col['type'], ex_values)
                columns.append(DataColumnModel(
                    name=col_name,
                    description=col.get('comment', "") or "",
                    data_type=str(col['type']),
                    examples=clean_examples
                ))
            tables.append(DataTableModel(name=table_name, columns=columns))
    return DataDictionaryModel(database=db_label, tables=tables, notes=None)


def load_prompts(prompt_file_path: str) -> dict:
    if not os.path.exists(prompt_file_path):
        raise FileNotFoundError(f"Prompt file not found: {prompt_file_path}")
    with open(prompt_file_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    remapped = {}
    for k, v in raw.items():
        short_k = k.replace("llm.prompt.", "") if k.startswith("llm.prompt.") else k
        remapped[short_k] = v
    missing = REQUIRED_PROMPT_KEYS - set(remapped)
    if missing:
        raise ValueError(f"Missing required prompts: {missing}")
    return remapped
    