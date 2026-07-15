from __future__ import annotations

import json
import csv
import io

import pandas as pd


def to_json(df: pd.DataFrame) -> str:
    return df.to_json(orient="records", date_format="iso")


def to_csv(df: pd.DataFrame) -> str:
    return df.to_csv()


def to_dict(df: pd.DataFrame) -> list[dict]:
    return df.reset_index().to_dict(orient="records")
