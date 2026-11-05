"""Tests that the published site preserves the local interface's data contract.

Only simulated Garmin data is used in these tests.
"""
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


class OnlineParityTests(unittest.TestCase):
    def _run_case(self, share):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'project'
            shutil.copytree(ROOT,target,ignore=shutil.ignore_patterns('__pycache__','*.pyc','site','.private_work','preview-online.png','state','.git'))
            # Tests must NEVER inherit the real encrypted Garmin archive.
            # Each simulated run starts with a fresh, isolated test database.
            self.assertFalse((target / 'state' / 'history.enc').exists())
            env={**os.environ,'STRIDE_ARCHIVE_KEY':Fernet.generate_key().decode(),
                 'GARMIN_PERSONAL_API_KEY':'TEST_ONLY_CREDENTIAL',
                 'PUBLISH_PHYSIOLOGY':'true' if share else 'false',
                 'PUBLISH_ACTIVITY_SUMMARIES':'true' if share else 'false'}
            script='''
import cloud_sync as c,json
class Fake:
 def profile(self):return {'maxHeartRate':204,'restingHeartRate':62}
 def hr_zones(self):return [{'sport':'RUNNING','lactateThresholdHeartRateUsed':180,'maxHeartRateUsed':204,'restingHeartRateUsed':62}]
 def activities(self,start,limit):return [{'activityId':7113322,'activityName':'PRIVATE_ROUTE_LOCATION','startTimeLocal':'2026-10-21 06:42:00','duration':1900,'distance':5400,'averageHR':152,'activityType':{'typeKey':'running'}}] if start==0 else []
 def activity_zip(self,activity_id):return b'fake'
c.parse_activity_archive=lambda _: [{'t':t,'d':3.5*t,'hr':145+t%10,'alt':15} for t in range(1900)]
info=c.sync(Fake());c.make_site(info)
s=(c.SITE/'data.json').read_text();out=json.loads(s)
assert out['public_state']['summary']['runs']==1
assert 'summary' in out['public_state']
assert 'heatmap' in out['public_state']
assert 'pbs' in out['public_state']
assert 'connection' in out['public_state']
assert 'PRIVATE_ROUTE_LOCATION' not in s
assert 'TEST_ONLY_CREDENTIAL' not in s
assert '7113322' not in s
assert '06:42:00' not in s
assert 'alt' not in out['activity_hr_streams'].get('run-1',[{}])[0]
assert (c.SITE/'index.html').exists()
assert (c.SITE/'style.css').exists()
assert (c.SITE/'app.js').exists()
if bool(out['physiology_shared']):
 assert out['public_state']['threshold']['lthr']==180
 assert out['activity_feed'][0]['hr']==152
 assert out['activity_hr_streams']['run-1'][0].keys()=={'minute','hr'}
else:
 assert not out['activity_feed']
 assert out['public_state']['time_in_zone']==[]
print('PARITY_OK')
'''
            result=subprocess.run([sys.executable,'-c',script],env=env,cwd=target,capture_output=True,text=True,timeout=90)
            self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
            self.assertIn('PARITY_OK',result.stdout)

    def test_readonly_public_site_with_opt_in(self):
        self._run_case(True)

    def test_privacy_defaults_are_respected(self):
        self._run_case(False)


if __name__=='__main__':unittest.main()
