"""No-network operator boundary regressions; no shared/target DB writes."""
import unittest,sys
from unittest.mock import patch,MagicMock
from contextlib import contextmanager
import db_operator_common as common
import initialize_database as initialize
from copy_database import insert,topo

class OperatorGuards(unittest.TestCase):
 def test_shared_write_connection_rejected_before_connect(self):
  with patch.object(common.psycopg,'connect',side_effect=AssertionError('network forbidden')) as driver:
   with self.assertRaisesRegex(RuntimeError,'shared writes forbidden'):common.connect(common.SOURCE)
   driver.assert_not_called()
 def test_unapproved_database_rejected_before_connect(self):
  with patch.object(common.psycopg,'connect',side_effect=AssertionError('network forbidden')) as driver:
   with self.assertRaisesRegex(RuntimeError,'allowlist'):common.connect('another_database',readonly=True)
   driver.assert_not_called()
 def test_existing_target_never_recreated_or_initialized(self):
  seen=[]
  class Cursor:
   def __init__(self,row):self.row=row
   def fetchone(self):return self.row
  class Source:
   def execute(self,query,args=None):
    return Cursor({'yes':True} if 'EXISTS' in query else {'encoding':'UTF8','datcollate':'en_US.utf8','datctype':'en_US.utf8'})
  @contextmanager
  def source_only(name,**kw):
   seen.append(name)
   self.assertEqual(name,common.SOURCE);self.assertTrue(kw['readonly']);yield Source()
  with patch.object(sys,'argv',['initialize_database.py','--create-approved-isolated-database']),patch.object(initialize.subprocess,'check_output',return_value='backend/migrations/0037_inst_doc_extract_privileges.sql'),patch.object(initialize,'connect',source_only),patch.object(initialize,'save',side_effect=AssertionError('must not write markers')):
   with self.assertRaisesRegex(RuntimeError,'already exists'):initialize.main()
  self.assertEqual(seen,[common.SOURCE])
 def test_copy_cannot_write_unapproved_table_or_source_connection(self):
  conn=MagicMock()
  with self.assertRaisesRegex(RuntimeError,'table not approved'):insert(conn,'some_private_table',[{'id':1}])
  conn.execute.assert_not_called()
  conn.execute.return_value.fetchone.return_value={'db':common.SOURCE}
  with self.assertRaisesRegex(RuntimeError,'write target mismatch'):insert(conn,'users',[{'id':1}])
  conn.cursor.assert_not_called()
 def test_missing_ancestor_does_not_disable_fk_or_copy_outside_scope(self):
  with self.assertRaisesRegex(RuntimeError,'missing or cyclic'):topo([{'id':'child','parent_id':'not-whitelisted'}],'parent_id')

if __name__=='__main__':unittest.main(verbosity=2)
