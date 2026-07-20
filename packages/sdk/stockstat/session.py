from __future__ import annotations

import tempfile
from io import BytesIO
from pathlib import Path

import pandas as pd
import pyarrow.ipc as ipc
from stockstat_contracts import ArtifactInput, DatasetInput, DatasetSelector, new_id

from .api import (
    BacktestAPI,
    DataAPI,
    ExperimentAPI,
    IndicatorAPI,
    SimulationAPI,
    StrategyAPI,
    ValidationAPI,
    dataframe_to_arrow,
)
from .dsl import DSLCompiler
from .jobs import JobHandle


class StockStat:
    def __init__(self, control, artifacts, local=None):
        self._control = control
        self._artifacts = artifacts
        self._local = local
        self.data = DataAPI(self)
        self.indicators = IndicatorAPI(self)
        self.timeseries = self.indicators
        self.backtests = BacktestAPI(self)
        self.experiments = ExperimentAPI(self)
        self.simulations = SimulationAPI(self)
        self.validation = ValidationAPI(self)
        self.strategies = StrategyAPI()
        self.dsl = DSLCompiler()

    @classmethod
    def local(cls, path=".stockstat-v31"):
        from stockstat_local import LocalRuntime

        return LocalRuntime(Path(path)).start().session

    @classmethod
    def connect(cls, dispatcher_url, *, storage_url=None, token=None):
        from .http import HttpArtifactClient, HttpControlChannel

        return cls(
            HttpControlChannel(dispatcher_url, token=token),
            HttpArtifactClient(storage_url or dispatcher_url, token=token),
        )

    def close(self):
        if self._local:
            self._local.close()
        else:
            self._control.close()
            self._artifacts.close()

    def _submit(self, spec):
        job_id = self._control.submit(spec, new_id())
        return JobHandle(self, job_id)

    def _binding(self, value, name):
        if isinstance(value, DatasetSelector):
            return DatasetInput(name=name, dataset=value)
        if isinstance(value, pd.Series):
            value = value.to_frame(name=value.name or "value")
        if isinstance(value, pd.DataFrame):
            with tempfile.NamedTemporaryFile(suffix=".arrow", delete=False) as stream:
                temporary = Path(stream.name)
            try:
                dataframe_to_arrow(value, temporary)
                reference = self._artifacts.commit_file(
                    temporary,
                    kind="uploaded_dataframe",
                    media_type="application/vnd.apache.arrow.stream",
                    codec="arrow-ipc-stream",
                    schema_ref="stockstat.table/1",
                )
            finally:
                temporary.unlink(missing_ok=True)
            return ArtifactInput(name=name, artifact=reference)
        raise TypeError("input must be DatasetSelector, Series, or DataFrame")

    def _read_table(self, reference_data):
        from stockstat_contracts import ArtifactRef

        reference = ArtifactRef.model_validate(reference_data)
        return ipc.open_stream(BytesIO(self._artifacts.read(reference))).read_all().to_pandas()
