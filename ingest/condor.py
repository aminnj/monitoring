import datetime
import subprocess
import ast
import pytz
from elasticsearch import Elasticsearch
import json

from config import condor_index, es_host

def run():
    extra = ""

    # extra = "-limit 2"
    # since = 0

    es = Elasticsearch(es_host)
    result = es.search(index=condor_index, body={"aggs":{"latest":{"max":{"field":"CompletionDate"}}}}, size=0)
    try:
        since = int(result["aggregations"]["latest"]["value"]/1e3)
        print(f"[condor] Grabbing records since {since}")
    except:
        print("[condor] Grabbing as many records as possible")
        since = 0



    columns = ['BytesRecvd', 'BytesSent', 'CPUsUsage', 'ClusterId', 'CompletionDate',
            'CumulativeRemoteUserCpu', 'CumulativeSlotTime', 'DiskUsage_RAW',
            'ExitCode', 'ExitStatus', 'GlobalJobId', 'JobStartDate',
            'LastJobStatus', 'LastRemoteHost', 'MATCH_EXP_JOBGLIDEIN_ResourceName',
            'MATCH_EXP_JOB_GLIDEIN_SiteWMS_Slot', 'MATCH_GLIDEIN_Site', 'Owner',
            'ProcId', 'RemoteUserCpu', 'RemoteWallClockTime', 'RequestCpus',
            'RequestDisk', 'RequestMemory', 'ResidentSetSize_RAW',
            'TransferInputSizeMB', 'QDate']
    csvcolumns = ",".join(columns)

    rows = []
    hostnames = [f"uaf-{num}.t2.ucsd.edu" for num in [1, 7, 8, 10]]
    for hostname in hostnames:
        cmd = f"""condor_history -name {hostname} -completedsince {since}  -const 'JobStatus!=3' -attributes  '{csvcolumns}' {extra} -json"""
        out = subprocess.getoutput(cmd)
        try:
            r = ast.literal_eval(out)
        except:
            print(f"[condor]     ERROR running condor_history for {hostname}:")
            print(f"[condor]     {cmd}")
            continue
        print(f"[condor]     Fetched {len(r)} rows from condor_history on {hostname}")
        rows.extend(r)

    print(f"[condor] Fetched {len(rows)} rows from condor_history in total")

    # with open("latest.jsonl", "a") as fh:
    #     for row in rows:
    #         fh.write(json.dumps(row) + "\n")

    body = []
    qdates = []
    for row in rows:

        if "Dask" in str(row["RequestCpus"]):
            continue

        if "LastRemoteHost" not in row: 
            row["LastRemoteHost"] = "uaf"
        if "MATCH_EXP_JOBGLIDEIN_ResourceName" not in row:
            row["MATCH_EXP_JOBGLIDEIN_ResourceName"] = "UAF"
        if "JobStartDate" not in row:
            row["JobStartDate"] = row["CompletionDate"]

        _id = str(row["ClusterId"]) + "." + str(row["ProcId"])
        row.pop("ClusterId")
        row.pop("ProcId")
        row["Site"] = row["MATCH_EXP_JOBGLIDEIN_ResourceName"]
        row.pop("MATCH_EXP_JOBGLIDEIN_ResourceName")
        if row["RemoteWallClockTime"] < 1e-6:
            row["cpueff"] = 1
        else:
            row["cpueff"] = row["CumulativeRemoteUserCpu"]/row["RemoteWallClockTime"]/row["RequestCpus"]
        row["memGB"] = row.get("ResidentSetSize_RAW",0)/1024./1024.
        row["memfrac"] = row.get("ResidentSetSize_RAW",0)/1024./float(row["RequestMemory"])
        row["CompletionDate"] = datetime.datetime.fromtimestamp(row["CompletionDate"], tz=pytz.UTC)
        row["JobStartDate"] = datetime.datetime.fromtimestamp(row["JobStartDate"], tz=pytz.UTC)
        row["submithost"] = row["GlobalJobId"].split("#",1)[0]
        row.pop("GlobalJobId")
        row["hostname"] = row["LastRemoteHost"].split("@",2)[-1]
        row["LastRemoteHost"] = ".".join(row["LastRemoteHost"].rsplit(".")[-3:])

        if ".unl.edu" in row["LastRemoteHost"]:
            row["LastRemoteHost"] = "unl.edu"

        if ".colorado.edu" in row["LastRemoteHost"]:
            row["LastRemoteHost"] = "colorado.edu"

        body.append({"index":{"_id":_id}})
        body.append(row)
        qdates.append(row["QDate"])

    # add in: `mins_since_latest_q` = smallest time between `now` and latest QDate
    es = Elasticsearch(es_host)
    result = es.search(index=condor_index, body={"aggs":{"latest":{"max":{"field":"QDate"}}}}, size=0)
    latest_qdate = int(result["aggregations"]["latest"]["value"])
    if len(qdates):
        latest_qdate = max(max(qdates), latest_qdate)
    latest_qdate = datetime.datetime.fromtimestamp(latest_qdate, tz=pytz.UTC)
    now = datetime.datetime.now(tz=pytz.UTC)
    time_since_last_sub = now-latest_qdate
    mins_since_latest_q = (now-latest_qdate).total_seconds()/60
    print(f"[condor] Time since latest queue date: {mins_since_latest_q:.1f} minutes")
    for i in range(len(body)):
        if "QDate" in body[i]:
            body[i]["mins_since_latest_q"] = mins_since_latest_q


    if body:
        response = es.bulk(index=condor_index, body=body)
        print(f"[condor] Ingested {len(response['items'])} rows into index {condor_index!r} in {response['took']} ms")
        if response["errors"]:
            print("ERRORS:")
            print(response)


if __name__ == "__main__":
    run()
