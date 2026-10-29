"""Bounded DNS and verified TLS diagnostics; records error classes, never disables TLS."""
import json
import socket
import ssl
import time
from datetime import datetime,timezone
from .core import seal

HOSTS=('external-api.kalshi.com','api.balldontlie.io','api.sportsdata.io','api.stlouisfed.org',
       'single-runs-api.open-meteo.com','www.ncei.noaa.gov','github.com')


def main():
    results=[]
    for host in HOSTS:
        r={'host':host,'observed_at':datetime.now(timezone.utc).isoformat()};start=time.monotonic()
        try:
            addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
            r['dns']='ok';r['address_count']=len(addresses)
            with socket.create_connection((host,443),timeout=4) as sock:
                with ssl.create_default_context().wrap_socket(sock,server_hostname=host) as conn:
                    r['tls']='verified';r['protocol']=conn.version()
        except Exception as exc:
            r['error']=type(exc).__name__
            if isinstance(exc,ssl.SSLCertVerificationError):r['verify_code']=exc.verify_code;r['verify_message']=exc.verify_message
        r['elapsed_seconds']=round(time.monotonic()-start,3);results.append(r)
    digest=seal('research_outputs/diagnostics',{'results':results,'certificate_verification':True})
    print(json.dumps({'evidence':digest,'results':results},indent=2))

if __name__=='__main__':main()
