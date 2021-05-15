## Job/storage monitoring with grafana

Make a working area
```bash
mkdir -p ~/monitoring
cd ~/monitoring
```

Grafana and elasticsearch can be run in a GNU screen. Ingestion scripts
can be run in a screen as well, or in a crontab.

### Set up elasticsearch

```bash
cd ~/monitoring
mkdir elasticsearch
cd elasticsearch
# from https://www.elastic.co/guide/en/elasticsearch/reference/current/targz.html
wget https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-7.12.1-linux-x86_64.tar.gz
tar -xzf elasticsearch-7.12.1-linux-x86_64.tar.gz
cd elasticsearch-7.12.1/ 

# out of the box/default port is 9200
ES_JAVA_OPTS="-Xms3g -Xmx3g" ./bin/elasticsearch -Ehttp.port=9201
```


### Set up metrics ingestion

Set up the Python virtual environment
```bash
cd ~/monitoring
mkdir ingest
cd ingest

python3 -m venv myenv
source myenv/bin/activate
# make sure to match the installed ES version
pip install "elasticsearch>=7.0.0,<8.0.0" "elasticsearch-dsl>=7.0.0,<8.0.0" pytz tqdm requests
```

And to test...
```python
from elasticsearch import Elasticsearch
import datetime
es = Elasticsearch("localhost:9201")
response = es.index(
    index="mytest",
    doc_type="docs",
    body={"cpu": 20, "date": datetime.datetime.now()}
)
print(response)
```
The `mytest` index can be dropped later with `curl -X DELETE "localhost:9201/mytest?pretty"`.

Actual ingestion into the `condor` index is done with the [condor.py](ingest/condor.py) script
and into the `hadoop` index with the [hadoop.py](ingest/hadoop.py) script. Edit `ingest/config.py` to populate the hadoop namenode
host.

The HTCondor logging script saves a set of classads from completed jobs fetched via `condor_history` since a particular timestamp.
Each time the script is run, this `since` timestamp is calculated as the maximum of the `CompletionDate`
field in the ES database.

```bash
source myenv/bin/activate
for i in `seq 1 10000`; do 
    python condor.py
    python hadoop.py
    sleep 20m
done
```



### Set up grafana

```bash
cd ~/monitoring
mkdir grafana
cd grafana

# run docker container via singularity
GF_SERVER_HTTP_PORT=1234 # out of box default is 3000
singularity run \
    --env GF_AUTH_ANONYMOUS_ENABLED=true \
    --env GF_SERVER_HTTP_PORT=$GF_SERVER_HTTP_PORT \
    --env GF_PATHS_DATA=`pwd` \
    docker://grafana/grafana
# default login is `admin`
```

#### Tweak the UI

* Left panel `Server Admin` > `Users` > change admin password
* Left panel `Configuration` > `Data Sources` > `Elasticsearch`. Change the URL if using a non-standard port. Make this the default data source.
`Index name` = `condor`, `Time field name` = `CompletionDate`. ES `Version` = `7.0+`. `Save & Test`.
* Similarly, add a data source for the `hadoop` index with `Time field name` = `date`.
* Play around and make dashboards.
* To make a dropdown box to filter by username, `Dashboard settings` > `Variables`, 
then `Type` = `Query`, `Name`/`Label` = `username`, ES `Data source`,
`Query` = `{"find": "terms", "field": "Owner.keyword", "size": 50}`,
`Custom all value` = `*`.
and finally make sure that the preview shows some usernames. 
Finally, make sure the `Query` string is `$username` for dashboards where you want to filter by username.

A backup of the latest dashboards are in [grafana/settings](grafana/settings).
