import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from metacube_rgb.core import Presets
from metacube_rgb.web import Api, DemoDevice, make_handler

TOKEN='q'*48

class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.api=Api(DemoDevice(),Presets(Path(cls.temp.name)/'presets.json'),demo=True)
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(cls.api,TOKEN))
        cls.url=f'http://127.0.0.1:{cls.server.server_port}'
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
        cls.temp.cleanup()

    def req(self,path,method='GET',token=True,body=None,origin=None):
        headers={}
        if token:headers['Authorization']='Bearer '+TOKEN
        if body is not None:
            headers['Content-Type']='application/json'
            body=json.dumps(body).encode()
        if origin:headers['Origin']=origin
        request=urllib.request.Request(self.url+path,method=method,headers=headers,data=body)
        try:
            with urllib.request.urlopen(request,timeout=5) as resp:
                return resp.status,resp.read().decode()
        except urllib.error.HTTPError as exc:
            return exc.code,exc.read().decode()

    def test_static_assets(self):
        for path in ('/','/styles.css','/app.js'):
            with self.subTest(path=path):
                status,body=self.req(path,token=False)
                self.assertEqual(status,200)
                self.assertGreater(len(body),1000)

    def test_auth_and_status(self):
        self.assertEqual(self.req('/api/status',token=False)[0],401)
        self.assertEqual(self.req('/api/health',token=False)[0],200)
        self.assertEqual(self.req('/api/status')[0],200)

    def test_reject_cross_site(self):
        self.assertEqual(self.req('/api/lighting','POST',body={'brightness':10},origin='https://evil.example')[0],403)

    def test_write_and_presets(self):
        result=self.req('/api/lighting','POST',body={'colors':['FF0000','00FF00'],'mode':'spin','speed':45})
        self.assertEqual(result[0],200)
        self.assertEqual(json.loads(result[1])['lighting']['colors'],['FF0000','00FF00'])
        self.assertEqual(self.req('/api/presets/save','POST',body={'slot':1,'name':'Demo'})[0],200)
        self.assertEqual(self.req('/api/presets')[0],200)
        self.assertEqual(self.req('/api/platform','POST',body={'control':'system_mode','value':0})[0],400)

    def test_new_rgb_routes(self):
        resp,txt=self.req('/api/status')
        raw=json.loads(txt)['lighting']['raw']
        status,plan=self.req('/api/lighting/plan','POST',body={'mode':'spin','colors':['123456','654321'],'expected_raw':raw})
        self.assertEqual(status,200)
        self.assertEqual(json.loads(plan)['set_packet'][:8],'00fb000f')
        status,_=self.req('/api/presets/import','POST',body={'version':1,'slots':[None]*5})
        self.assertEqual(status,200)
        status,txt=self.req('/api/presets/export')
        self.assertEqual(status,200)
        self.assertEqual(json.loads(txt)['slots'],[None]*5)
        # Change state, then submit the stale raw; endpoint must answer conflict.
        status,_=self.req('/api/lighting','POST',body={'brightness':201})
        self.assertEqual(status,200)
        status,_=self.req('/api/lighting','POST',body={'brightness':200,'expected_raw':raw})
        self.assertEqual(status,409)

if __name__=='__main__':unittest.main()
