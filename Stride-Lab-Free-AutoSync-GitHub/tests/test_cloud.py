"""Run with python -m unittest discover -s tests from project root.
All API interactions are synthetic. No Garmin credentials used in testing.
"""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parent.parent


class AutoSyncTests(unittest.TestCase):
    def test_no_private_keys_exported(self):
        # The read-only exporter must ignore the raw secret-bearing connection payload.
        from public_export import sanitized
        raw = {
            'sample': False, 'summary':{'runs':3,'all_km':31.5},
            'connection':{'key':'DO_NOT_EXPOSE','token':'DO_NOT_EXPOSE'},
            'recent':[{'gps':123,'name':'Home Address'}],
            'pbs':[{'name':'5 km','time':'25:00','seconds':1500,'pace':'5:00/km','date':'2026-08-01','activity_id':'123SECRET'}],
            'zones':{'available':True,'zones':[{'name':'Z2','low':140,'high':160}]},
        }
        view=sanitized(raw)
        txt=json.dumps(view)
        self.assertNotIn('DO_NOT_EXPOSE',txt)
        self.assertNotIn('Home Address',txt)
        self.assertNotIn('123SECRET',txt)
        self.assertNotIn('"zones": {"available": true', txt)
        self.assertEqual(view['overview']['runs'],3)

    def test_end_to_end_encrypted_state_and_readonly_page(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d)/'site_project'
            shutil.copytree(ROOT,target,ignore=shutil.ignore_patterns('.private_work','site','__pycache__','*.pyc','*.enc'))
            key=Fernet.generate_key().decode()
            env={**os.environ,'GARMIN_PERSONAL_API_KEY':'mock-key-only-for-tests','STRIDE_ARCHIVE_KEY':key}
            script=r'''
import cloud_sync as a
from datetime import datetime,timezone
class Fake:
    def profile(self): return {'maxHeartRate':202,'restingHeartRate':51}
    def hr_zones(self): return [{'sport':'RUNNING','lactateThresholdHeartRateUsed':181,'maxHeartRateUsed':202,'restingHeartRateUsed':51}]
    def activities(self,start,limit):
        return [{'activityId':1001,'activityName':'PRIVATE HOME RUN','startTimeLocal':'2026-07-04 08:00:00','duration':1800,'distance':5200,'averageHR':160,'activityType':{'typeKey':'running'}}] if start == 0 else []
    def activity_zip(self,activity_id): return b'SYNTHETIC'
a.parse_activity_archive=lambda data:[{'t':i,'d':i*3.2,'hr':160,'alt':20} for i in range(1800)]
x=a.sync(Fake()); a.make_site(x); a.persist(a.CIPHER)
assert x['runs']==1
payload=(a.SITE/'data.json').read_text()
assert 'PRIVATE HOME RUN' not in payload
assert 'mock-key-only-for-tests' not in payload
assert (a.ENC).exists()
assert (a.SITE/'app.js').exists()
print('E2E_OK')
'''
            run=subprocess.run([sys.executable,'-c',script],cwd=target,env=env,capture_output=True,text=True,timeout=60)
            self.assertEqual(run.returncode,0,msg=run.stdout+run.stderr)
            self.assertIn('E2E_OK',run.stdout)
            encrypted=(target/'state/history.enc').read_bytes()
            decrypted=Fernet(key.encode()).decrypt(encrypted)
            self.assertTrue(decrypted.startswith(b'SQLite format 3'))
            shutil.rmtree(target/'.private_work')
            second=r'''
import cloud_sync as a
from server.storage import db
with db() as c:
 assert c.execute('SELECT COUNT(*) FROM activities').fetchone()[0] == 1
print('RESTORE_OK')
'''
            run=subprocess.run([sys.executable,'-c',second],cwd=target,env=env,capture_output=True,text=True,timeout=60)
            self.assertEqual(run.returncode,0,msg=run.stdout+run.stderr)
            self.assertIn('RESTORE_OK',run.stdout)

if __name__=='__main__':unittest.main()
