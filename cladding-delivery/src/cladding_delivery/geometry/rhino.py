from __future__ import annotations
import json, os, urllib.request
from pathlib import Path
from typing import Any
from .base import GeometryProvider, GeometryUnsupported

class RhinoAdapterProvider(GeometryProvider):
    name='rhino'
    def __init__(self):
        self.url=os.environ.get('CADFAB_RHINO_ADAPTER_URL','').rstrip('/')
        self.key=os.environ.get('CADFAB_RHINO_ADAPTER_KEY','')
        if not self.url: raise RuntimeError('CADFAB_RHINO_ADAPTER_URL is not configured')

    def _call(self,path,payload=None):
        body=None if payload is None else json.dumps(payload).encode('utf-8')
        req=urllib.request.Request(self.url+path,data=body,method='GET' if body is None else 'POST',headers={'Content-Type':'application/json', **({'X-Adapter-Key':self.key} if self.key else {})})
        with urllib.request.urlopen(req,timeout=120) as r:
            return json.loads(r.read().decode('utf-8'))

    def health(self)->dict[str,Any]: return self._call('/health')
    def build_component(self,component:dict,out_dir:Path)->dict:
        result=self._call('/v1/build-component',{'component':component})
        result['provider']='rhino'; return result
    def unfold_component(self,component:dict,out_dir:Path)->dict:
        result=self._call('/v1/unroll-component',{'component':component})
        result['provider']='rhino'; return result
