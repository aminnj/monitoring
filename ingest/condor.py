import datetime
import subprocess
import ast
import pytz
from elasticsearch import Elasticsearch
import json

from config import condor_index, es_host

extra = ""

# extra = "-limit 2"
# since = 0

es = Elasticsearch(es_host)
result = es.search(index=condor_index, body={"aggs":{"latest":{"max":{"field":"CompletionDate"}}}}, size=0)
try:
    since = int(result["aggregations"]["latest"]["value"]/1e3)
    print(f"Grabbing records since {since}")
except:
    print("Grabbing as many records as possible")
    since = 0

columns = ['BytesRecvd', 'BytesSent', 'CPUsUsage', 'ClusterId', 'CompletionDate',
        'CumulativeRemoteUserCpu', 'CumulativeSlotTime', 'DiskUsage_RAW',
        'ExitCode', 'ExitStatus', 'GlobalJobId', 'JobStartDate',
        'LastJobStatus', 'LastRemoteHost', 'MATCH_EXP_JOBGLIDEIN_ResourceName',
        'MATCH_EXP_JOB_GLIDEIN_SiteWMS_Slot', 'MATCH_GLIDEIN_Site', 'Owner',
        'ProcId', 'RemoteUserCpu', 'RemoteWallClockTime', 'RequestCpus',
        'RequestDisk', 'RequestMemory', 'ResidentSetSize_RAW',
        'TransferInputSizeMB']
csvcolumns = ",".join(columns)

rows = []
hostnames = [f"uaf-{num}.t2.ucsd.edu" for num in [1, 7, 8, 10]]
for hostname in hostnames:
    out = subprocess.getoutput(
            f"""condor_history -name {hostname} -completedsince {since}  -const 'JobStatus!=3' -attributes  '{csvcolumns}' {extra} -json"""
            )
    rows.extend(ast.literal_eval(out))

print(f"Fetched {len(rows)} rows from condor_history")

# with open("latest.jsonl", "a") as fh:
#     for row in rows:
#         fh.write(json.dumps(row) + "\n")

body = []
for row in rows:

    if "Dask" in str(row["RequestCpus"]):
        continue

    _id = str(row["ClusterId"]) + "." + str(row["ProcId"])
    row.pop("ClusterId")
    row.pop("ProcId")
    row["Site"] = row["MATCH_EXP_JOBGLIDEIN_ResourceName"]
    row.pop("MATCH_EXP_JOBGLIDEIN_ResourceName")
    row["cpueff"] = row["CumulativeRemoteUserCpu"]/row["RemoteWallClockTime"]/row["RequestCpus"]
    row["memGB"] = row["ResidentSetSize_RAW"]/1024./1024.
    row["memfrac"] = row["ResidentSetSize_RAW"]/1024./row["RequestMemory"]
    row["CompletionDate"] = datetime.datetime.fromtimestamp(row["CompletionDate"], tz=pytz.UTC)
    row["JobStartDate"] = datetime.datetime.fromtimestamp(row["JobStartDate"], tz=pytz.UTC)
    row["submithost"] = row["GlobalJobId"].split("#",1)[0]
    row.pop("GlobalJobId")
    row["hostname"] = row["LastRemoteHost"].split("@",2)[-1]
    row["LastRemoteHost"] = ".".join(row["LastRemoteHost"].rsplit(".")[-3:])

    if ".unl.edu" in row["LastRemoteHost"]:
        row["LastRemoteHost"] = "unl.edu"

    body.append({"index":{"_id":_id}})
    body.append(row)

if body:
    response = es.bulk(index=condor_index, body=body)
    print(f"Ingested {len(response['items'])} rows into elasticsearch in {response['took']} ms")
    if response["errors"]:
        print("ERRORS:")
        print(response)

