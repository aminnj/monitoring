import json
import requests
import pytz
import datetime
from elasticsearch import Elasticsearch

from config import hadoop_index, es_host, namenode_host

data = requests.get(f"http://{namenode_host}/jmx").json()
data = dict((d["name"], d) for d in data["beans"])

total = data["Hadoop:service=NameNode,name=NameNodeInfo"]["Total"]
used = data["Hadoop:service=NameNode,name=NameNodeInfo"]["Used"]
free = data["Hadoop:service=NameNode,name=NameNodeInfo"]["Free"]
totalfiles = data["Hadoop:service=NameNode,name=NameNodeInfo"]["TotalFiles"]

usedfrac = 1.0*used/total

threadcount = data["java.lang:type=Threading"]["ThreadCount"]
totalload = data["Hadoop:service=NameNode,name=FSNamesystemState"]["TotalLoad"]

numlivenodes = data["Hadoop:service=NameNode,name=FSNamesystemState"]["NumLiveDataNodes"]
numdeadnodes = data["Hadoop:service=NameNode,name=FSNamesystemState"]["NumDeadDataNodes"]
numdecomnodes = data["Hadoop:service=NameNode,name=FSNamesystemState"]["NumDecommissioningDataNodes"]

numopenconnections = data["Hadoop:service=NameNode,name=RpcActivityForPort9000"]["NumOpenConnections"]

heap = data["java.lang:type=Memory"]["HeapMemoryUsage"]
nonheap = data["java.lang:type=Memory"]["NonHeapMemoryUsage"]

usedheapmemfrac = (1.0*heap["used"]/heap["committed"])
usednonheapmemfrac = (1.0*nonheap["used"]/nonheap["committed"])

timestamp = datetime.datetime.now(tz=pytz.UTC)

body = {
        "totalbytes": total,
        "usedbytes": used,
        "freebytes": free,
        "usedfrac": usedfrac,
        "totalfiles": totalfiles,
        "threadcount": threadcount,
        "totalload": totalload,
        "numlivenodes": numlivenodes,
        "numdeadnodes": numdeadnodes,
        "numdecomnodes": numdecomnodes,
        "numopenconnections": numopenconnections,
        "usedheapmemfrac": usedheapmemfrac,
        "usednonheapmemfrac": usednonheapmemfrac,
        "date": timestamp,
        }

es = Elasticsearch(es_host)
response = es.index(index=hadoop_index, body=body)
