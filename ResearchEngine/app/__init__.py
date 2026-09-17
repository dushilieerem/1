"""SVQuant Python 门面；按需加载，导入数据模型不会启动服务依赖。"""

from importlib import import_module

_EXPORTS = {'ConfigManager': ('app.config', 'ConfigManager'),
 'FactorLoader': ('app.services.factor.loader', 'FactorLoader'),
 'SQLiteFactorLoader': ('app.services.factor.sqlite_loader', 'SQLiteFactorLoader'),
 'ResultManager': ('app.services.results.manager', 'ResultManager'),
 'CSVStorage': ('app.database.results.storage.csv_storage', 'CSVStorage'),
 'ClickHouseStorage': ('app.database.results.storage.clickhouse_storage', 'ClickHouseStorage'),
 'ParquetStorage': ('app.database.results.storage.parquet_storage', 'ParquetStorage'),
 'ResultStorage': ('app.database.results.storage.base', 'ResultStorage'),
 'SQLiteStorage': ('app.database.results.storage.sqlite_storage', 'SQLiteStorage'),
 'Experiment': ('app.services.experiment.base', 'Experiment'),
 'FactorBacktestExperiment': ('app.services.factor.experiment', 'FactorBacktestExperiment'),
 'StrategyExperiment': ('app.services.experiment.strategy', 'StrategyExperiment'),
 'ExperimentHandle': ('app.services.experiment.manager', 'ExperimentHandle'),
 'ExperimentManager': ('app.services.experiment.manager', 'ExperimentManager'),
 'ExperimentManagerClosedError': ('app.services.experiment.manager',
                                  'ExperimentManagerClosedError'),
 'ExperimentManagerError': ('app.services.experiment.manager', 'ExperimentManagerError'),
 'ExperimentQueueFullError': ('app.services.experiment.manager', 'ExperimentQueueFullError'),
 'ExperimentStatus': ('app.models.experiment', 'ExperimentStatus'),
 'plot_equity_drawdown': ('app.services.factor.plotting', 'plot_equity_drawdown'),
 'plot_group_ic': ('app.services.factor.plotting', 'plot_group_ic'),
 'plot_ic_analysis': ('app.services.factor.plotting', 'plot_ic_analysis'),
 'build_close_panel': ('app.services.factor.portfolio', 'build_close_panel'),
 'build_factor_portfolio': ('app.services.factor.portfolio', 'build_factor_portfolio')}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attribute = _EXPORTS[name]
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value
