import json,datetime,resource
from pathlib import Path
import pyarrow.parquet as pq
import numpy as np
from app.config import DEFAULT_CONFIG_PATH,load_runtime_settings
from app.database.data.providers.field_parquet_provider import FieldParquetProvider
symbols="000001.SZ,000063.SZ,000100.SZ,000333.SZ,000338.SZ,000568.SZ,000625.SZ,000651.SZ,000725.SZ,000768.SZ,000776.SZ,000858.SZ,000895.SZ,000938.SZ,002027.SZ,002049.SZ,002142.SZ,002230.SZ,002415.SZ,002475.SZ,600000.SH,600009.SH,600030.SH,600031.SH,600036.SH,600048.SH,600050.SH,600104.SH,600276.SH,600309.SH,600406.SH,600438.SH,600519.SH,600585.SH,600690.SH,600703.SH,600809.SH,601166.SH,601318.SH,601888.SH".split(',')
settings=load_runtime_settings(DEFAULT_CONFIG_PATH);base=Path(settings.data_dir);path=base/'market_data/market_data_hfq.parquet';schema=pq.ParquetFile(path).schema_arrow
fields=('open','high','low','close','volume','amount','turnover');columns=['date']+[str((symbol,field)) for symbol in symbols for field in fields]
missing=[x for x in columns if x not in schema.names]
if missing:raise ValueError('approved coverage missing columns: '+repr(missing))
windows=[]
for start,end in [('2025-07-01','2025-09-30'),('2025-10-01','2025-12-31'),('2026-06-22','2026-09-21')]:
 table=pq.read_table(path,columns=columns,filters=[('date','>=',start),('date','<=',end)],use_threads=False).replace_schema_metadata({});frame=table.to_pandas();dates=frame['date'];per=[]
 for symbol in symbols:
  masks=[np.isfinite(frame[str((symbol,field))].to_numpy(dtype=float)) for field in fields]
  per.append({'symbol':symbol,'finite_close_days':int(masks[3].sum()),'finite_all_ohlcva_turnover_days':int(np.logical_and.reduce(masks).sum()),'missing_by_field':{field:int((~mask).sum()) for field,mask in zip(fields,masks)}})
 windows.append({'start':start,'end':end,'published_market_date_count':len(frame),'first':str(dates.min()),'last':str(dates.max()),'per_security':per,'candidate_warmup_sessions':0,'maximum_one_day_forward_label_dates_before_missing_or_filters':max(0,len(frame)-1),'rolling20_full_window_upper_bound_before_missing_or_filters_and_one_day_label':max(0,len(frame)-20),'is_gate_pass':False,'note':'Coverage only; no factor, portfolio, IC, performance, novelty or approval executed. Published market dates are not independently verified exchange calendar.'})
calendar_path=base/'calendar/calendar_all_a.parquet';calendar=pq.read_table(calendar_path,use_threads=False).replace_schema_metadata({}).to_pandas()
calendar_summary={'columns':list(calendar.columns),'rows':len(calendar),'source':'published calendar_all_a.parquet, exchange ALL_A'}
for w in windows:
 selected=calendar.loc[(calendar['date'].astype(str)>=w['start'])&(calendar['date'].astype(str)<=w['end'])&(calendar['is_trade_day']==True)]
 w['published_calendar_trade_day_count']=int(selected['date'].nunique())
 w['calendar_sources']=sorted(selected['source'].dropna().astype(str).unique().tolist())
 w['calendar_exchanges']=sorted(selected['exchange'].dropna().astype(str).unique().tolist())
 w['calendar_first']=str(selected['date'].min());w['calendar_last']=str(selected['date'].max())
provider=FieldParquetProvider(base)
result={'kind':'readonly-approved-40-source-coverage','data_dir':str(base),'data_release_id':provider.release_id,'selected_symbols':symbols,'selected_columns':len(columns),'file_size_bytes':path.stat().st_size,'file_mtime_ns':path.stat().st_mtime_ns,'windows':windows,'published_calendar':calendar_summary,'reader_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'limitations':['Static selected sample; selection bias; not historical index membership.','No observations gate evaluated. Missing status/filter data may further reduce usable observations.']}
print(json.dumps(result,ensure_ascii=False,indent=2))
