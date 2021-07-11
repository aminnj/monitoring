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

from config import userprio_index, es_host

def run():
    df = pd.read_csv(
        StringIO(
            subprocess.getoutput(
                "condor_userprio -af:lh, Name Priority PriorityFactor WeightedAccumulatedUsage WeightedResourcesUsed ResourcesUsed LastUpdate"
            )
        ),index_col="Name",skipinitialspace=True,
    )

    df = df.reset_index()
    df["Name"] = df["Name"].str.strip().str.split("@",1).str[0]
    df["AvgCpus"] = df["WeightedResourcesUsed"]/df["ResourcesUsed"]
    df = df[df["Name"] != "<none>"]
    df = df.reset_index(drop=True)

    # sometimes WeightedResourcesUsed and ResourcesUsed are both 0
    df = df.fillna(0.)


    body = []
    for _, row in df.iterrows():
        row = dict(row)
        _id = str(row["Name"]) + "." + str(row["LastUpdate"])
        row["LastUpdate"] = datetime.datetime.fromtimestamp(row["LastUpdate"], tz=pytz.UTC)
        body.append({"index":{"_id":_id}})
        body.append(row)
        
    # print(body)

    es = Elasticsearch(es_host)
    if body:
        response = es.bulk(index=userprio_index, body=body)
        print(f"[userprio] Ingested {len(response['items'])} rows into index {userprio_index!r} in {response['took']} ms")
        if response["errors"]:
            print("ERRORS:")
            print(response)


if __name__ == "__main__":
    run()
