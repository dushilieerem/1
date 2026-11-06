import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

def uid(prefix):return prefix+'-'+uuid.uuid4().hex[:12]
def now():return time.time()

DEFAULT_METHOD={'version':1,'prompt':'优先检查数据与表达式，使用真实工具验证假设。失败时说明原因，优秀候选提交人审；不得伪造数值或自行登记入库。'}

class Store:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.path=self.root/'workspace.sqlite3';self.lock=threading.RLock()
        with self.connection() as c:
            c.execute('PRAGMA journal_mode=WAL')
            c.execute('CREATE TABLE IF NOT EXISTS objects(kind TEXT NOT NULL,id TEXT NOT NULL,body TEXT NOT NULL,PRIMARY KEY(kind,id))')
        if not self.get('settings','current'):self.put('settings','current',{'model':'deepseek-chat','token_limit':20000,'tokens':0,'reserved':0,'uncertain':0,'calls':0})
        for job in self.list('run')+self.list('agent'):
            if job['status'] in ('queued','running'):
                job.update(status='interrupted',error='服务重启中断；保留原输入，可创建新实验重试')
                self.put('agent' if job['id'].startswith('AI-') else 'run',job['id'],job)
        settings=self.get('settings','current')
        if settings['reserved']:
            settings['uncertain']+=settings['reserved'];settings['reserved']=0;self.put('settings','current',settings)
    @contextmanager
    def connection(self):
        connection=sqlite3.connect(self.path,timeout=20)
        try:
            with connection:yield connection
        finally:connection.close()
    def get(self,kind,identity):
        with self.connection() as c:row=c.execute('SELECT body FROM objects WHERE kind=? AND id=?',(kind,identity)).fetchone()
        return json.loads(row[0]) if row else None
    def put(self,kind,identity,body):
        encoded=json.dumps(body,ensure_ascii=False,allow_nan=False)
        with self.lock,self.connection() as c:c.execute('INSERT INTO objects(kind,id,body) VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body',(kind,identity,encoded))
    def put_many(self,items):
        rows=[(kind,identity,json.dumps(body,ensure_ascii=False,allow_nan=False)) for kind,identity,body in items]
        with self.lock,self.connection() as c:
            c.executemany('INSERT INTO objects(kind,id,body) VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body',rows)
    def list(self,kind):
        with self.connection() as c:rows=c.execute('SELECT body FROM objects WHERE kind=? ORDER BY rowid DESC',(kind,)).fetchall()
        return [json.loads(r[0]) for r in rows]
    def event(self,action,detail,source='human',run_id=None):
        e={'id':uid('EV'),'at':now(),'action':action,'detail':detail,'source':source,'run_id':run_id};self.put('event',e['id'],e);return e
