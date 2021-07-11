import os
import sys
import datetime
import subprocess
import ast
import pytz
from elasticsearch import Elasticsearch
import json
import pandas as pd
import subprocess
from io import StringIO

from config import status_index, es_host

def run():


    df = pd.read_csv(
        StringIO(
            subprocess.getoutput(
                "condor_status -run -af:lh, Name FileTransferDownloadBytes FileTransferDownloadBytesPerSecond_1h FileTransferDownloadBytesPerSecond_5m FileTransferUploadBytes FileTransferUploadBytesPerSecond_1h FileTransferUploadBytesPerSecond_5m LastHeardFrom ShadowsRunning TotalHeldJobs TotalIdleJobs TotalRemovedJobs TotalRunningJobs DaemonCoreDutyCycle"
            ).replace("undefined", "0.0")
        ),skipinitialspace=True,
    )

    df = df.reset_index(drop=True)
    df.columns = df.columns.str.strip()
    df["Name"] = df["Name"].str.strip().str.split(".",1).str[0]
    df = df.reset_index(drop=True)

    # not realistic if a uaf is unresponsive, but prevents entries from going into different time buckets on grafana
    latest = df["LastHeardFrom"].max()

    s = df.sum(axis=0)
    s["Name"] = "all"
    df = df.append(s, ignore_index=True)
    df["LastHeardFrom"] = latest

    body = []
    for _, row in df.iterrows():
        row = dict(row)
        _id = str(row["Name"]) + "." + str(row["LastHeardFrom"])
        row["LastHeardFrom"] = datetime.datetime.fromtimestamp(row["LastHeardFrom"], tz=pytz.UTC)
        body.append({"index":{"_id":_id}})
        body.append(row)

    # print(body)
    # sys.exit()

    es = Elasticsearch(es_host)
    if body:
        response = es.bulk(index=status_index, body=body)
        print(f"[status] Ingested {len(response['items'])} rows into index {status_index!r} in {response['took']} ms")
        if response["errors"]:
            print("ERRORS:")
            print(response)


if __name__ == "__main__":
    run()
